from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .c90_writer import include_guard_for, sanitize_identifier, sha256_file, write_c_file
from .harness_models import (
    DependencyDispatch,
    GeneratedFile,
    HarnessGenerationWarning,
    StubParameter,
)


def augment_call_report_for_dependency_policy(call_report: Any, dependency_policy: Any | None) -> dict[str, Any]:
    payload = copy.deepcopy(_payload(call_report))
    policy = _optional_payload(dependency_policy)
    if not policy:
        return payload
    candidates = payload.setdefault("stub_candidates", [])
    governed_names = {str(item.get("callee")) for item in policy.get("dependencies", []) if item.get("callee")}
    candidates[:] = [item for item in candidates if str(item.get("name") or "") not in governed_names]
    existing = {str(item.get("name")) for item in candidates if item.get("name")}
    for dependency in _dispatchable_dependencies(policy):
        callee = str(dependency.get("callee"))
        if callee in existing:
            continue
        signature = dependency.get("signature", {})
        parameters = signature.get("parameters", [])
        return_type = str(signature.get("return_type_raw") or "int")
        return_category = str(signature.get("return_type_category") or _return_kind(return_type))
        candidates.append(
            {
                "name": callee,
                "reason": "dependency policy dispatcher requires a collision-safe stub implementation",
                "target_kind": dependency.get("target_kind", "external_function"),
                "call_count": len(dependency.get("related_call_ids", [])),
                "return_value_control_needed": return_category != "void",
                "argument_capture_needed": bool(parameters),
                "side_effect_control_needed": any(
                    int(item.get("pointer_level") or 0) > 0 or item.get("type_category") == "pointer"
                    for item in parameters
                ),
                "related_calls": list(dependency.get("related_call_ids", [])),
                "confidence": "high",
                "tags": ["dependency_policy", "collision_safe_stub"],
            }
        )
        existing.add(callee)
    return payload


def apply_dependency_dispatcher(
    output_root: Path | str,
    dependency_policy: Any | None,
    test_case_design: Any,
    report: Any,
) -> list[Path]:
    policy = _optional_payload(dependency_policy)
    if not policy:
        return []
    output_root = Path(output_root).resolve()
    design = _payload(test_case_design)
    changed: list[Path] = []
    _remove_review_required_stubs(output_root, policy, report, changed)
    dependencies = _dispatchable_dependencies(policy)
    if not dependencies:
        return changed

    dispatches: list[DependencyDispatch] = []
    header_tokens: list[str] = []
    stub_headers: list[str] = []
    dispatcher_prototypes: list[str] = []
    real_prototypes: list[str] = []
    dispatcher_sources: list[str] = []
    mode_declarations: list[str] = []
    mode_reset_lines: list[str] = []
    control_lines = _control_header_prefix()

    stubs_by_original = {item.original_function_name: item for item in report.stub_skeletons}
    for dependency in dependencies:
        callee = str(dependency.get("callee"))
        safe = sanitize_identifier(callee)
        signature = dependency.get("signature", {})
        return_type = str(signature.get("return_type_raw") or "int").strip()
        return_category = str(signature.get("return_type_category") or _return_kind(return_type))
        parameters = _normalized_parameters(signature.get("parameters", []))
        calling_convention = str(signature.get("calling_convention") or "").strip() or None
        real_available = _real_available(dependency) and _real_mode_requested(dependency, design)
        default_mode = "real" if dependency.get("resolved_mode") == "real" and real_available else "stub"
        declaration_header = signature.get("declaration_source")
        header_token = str(declaration_header).replace("\\", "/") if declaration_header else ""
        if header_token and header_token not in header_tokens:
            header_tokens.append(header_token)
        if not _signature_supported(return_type, return_category, parameters):
            report.warnings.append(
                HarnessGenerationWarning(
                    code="dependency_signature_not_dispatchable",
                    message=f"Dependency {callee} has a signature that cannot be emitted safely as a C90 dispatcher.",
                    related_stub_name=f"Utr_Stub_{safe}",
                )
            )
            continue

        stub_header_rel = Path(f"generated/stubs/stub_{safe}.h")
        stub_source_rel = Path(f"generated/stubs/stub_{safe}.c")
        stub_header_path = output_root / stub_header_rel
        stub_source_path = output_root / stub_source_rel
        _write_stub_files(
            stub_header_path,
            stub_source_path,
            safe,
            return_type,
            return_category,
            calling_convention,
            parameters,
            header_token,
        )
        changed.extend([stub_header_path, stub_source_path])
        stub_headers.append(stub_header_rel.name)
        _record_generated_file(report.generated_files, output_root, stub_header_path, "stub_header", [callee], True)
        _record_generated_file(report.generated_files, output_root, stub_source_path, "stub_source", [callee], True)

        skeleton = stubs_by_original.get(callee)
        exact_stub_parameters = [
            StubParameter(
                index=int(item["index"]),
                name=str(item["name"]),
                type_raw=str(item["type_raw"]),
                capture_strategy="copy_pointer_value_only"
                if int(item.get("pointer_level") or 0) > 0 or item.get("type_category") == "pointer"
                else "copy_value",
                review_required=False,
            )
            for item in parameters
        ]
        if skeleton is not None:
            skeleton.stub_name = f"Utr_Stub_{safe}"
            skeleton.return_type_raw = return_type
            skeleton.parameters = exact_stub_parameters
            skeleton.source_file = stub_source_rel
            skeleton.header_file = stub_header_rel
            if "dependency_dispatch" not in skeleton.capabilities:
                skeleton.capabilities.append("dependency_dispatch")

        dispatcher_name = f"Utr_Dep_{safe}"
        stub_invoke_name = f"Utr_Stub_{safe}_Invoke"
        prototype = _prototype(return_type, calling_convention, dispatcher_name, parameters)
        dispatcher_prototypes.append(prototype + ";")
        if real_available and not header_token:
            real_prototype = _prototype(return_type, calling_convention, callee, parameters) + ";"
            if real_prototype not in real_prototypes:
                real_prototypes.append(real_prototype)
        mode_declarations.extend(
            [
                f"static int utr_dep_mode_{safe} = {_mode_constant(default_mode)};",
                f"void Utr_Dep_{safe}_SetMode(int mode)",
                "{",
                f"    utr_dep_mode_{safe} = mode;" if real_available else f"    utr_dep_mode_{safe} = UTR_DEP_MODE_STUB;",
                "}",
                "",
            ]
        )
        mode_reset_lines.append(f"    utr_dep_mode_{safe} = {_mode_constant(default_mode)};")
        dispatcher_sources.extend(
            _dispatcher_function_lines(
                callee,
                safe,
                return_type,
                return_category,
                calling_convention,
                parameters,
                real_available,
            )
        )
        control_lines.extend(_control_api_lines(safe, return_type, return_category, real_available))
        dispatches.append(
            DependencyDispatch(
                callee=callee,
                dispatcher_name=dispatcher_name,
                stub_invoke_name=stub_invoke_name,
                default_mode=default_mode,
                real_available=real_available,
                signature_resolution=str(signature.get("resolution") or "review_required"),
                related_call_ids=list(dependency.get("related_call_ids", [])),
                rewrite_sites=list(dependency.get("rewrite_sites", [])),
                implementation_source=Path(str(dependency["implementation_source"])) if dependency.get("implementation_source") else None,
                header_file=Path("generated/dependencies/utr_dependency_dispatch.h"),
                source_file=Path("generated/dependencies/utr_dependency_dispatch.c"),
            )
        )

    if not dispatches:
        return changed

    control_lines.extend(["", "#endif", ""])
    control_path = output_root / "generated" / "include" / "utr_dependency_control.h"
    _write_text_c(control_path, "\n".join(control_lines))
    changed.append(control_path)
    _record_generated_file(report.generated_files, output_root, control_path, "dependency_control_header", ["dependency_policy"], False)

    dispatch_header_path = output_root / "generated" / "dependencies" / "utr_dependency_dispatch.h"
    dispatch_source_path = output_root / "generated" / "dependencies" / "utr_dependency_dispatch.c"
    header_text = _dispatcher_header(dispatcher_prototypes)
    source_text = _dispatcher_source(header_tokens, stub_headers, real_prototypes, mode_declarations, mode_reset_lines, dispatcher_sources)
    _write_text_c(dispatch_header_path, header_text)
    _write_text_c(dispatch_source_path, source_text)
    changed.extend([dispatch_header_path, dispatch_source_path])
    _record_generated_file(report.generated_files, output_root, dispatch_header_path, "dependency_dispatch_header", ["dependency_policy"], True)
    _record_generated_file(report.generated_files, output_root, dispatch_source_path, "dependency_dispatch_source", ["dependency_policy"], True)

    changed.extend(_patch_test_sources(output_root, design, report, dispatches))
    report.dependency_dispatches = dispatches
    return changed



def _remove_review_required_stubs(output_root: Path, policy: dict[str, Any], report: Any, changed: list[Path]) -> None:
    blocked_names = {
        str(item.get("callee"))
        for item in policy.get("dependencies", [])
        if item.get("callee") and item.get("resolved_mode") not in {"real", "stub"}
    }
    if not blocked_names:
        return
    safe_names = {sanitize_identifier(name): name for name in blocked_names}
    for safe, callee in safe_names.items():
        for relative in (Path(f"generated/stubs/stub_{safe}.h"), Path(f"generated/stubs/stub_{safe}.c")):
            path = output_root / relative
            if path.exists():
                path.unlink()
                changed.append(path)
        report.warnings.append(
            HarnessGenerationWarning(
                code="dependency_policy_review_required",
                message=f"Dependency {callee} requires review; no callable stub or dispatcher was generated.",
                related_stub_name=f"Utr_Stub_{safe}",
            )
        )
    report.stub_skeletons = [item for item in report.stub_skeletons if item.original_function_name not in blocked_names]
    blocked_paths = {
        Path(f"generated/stubs/stub_{safe}.h") for safe in safe_names
    } | {
        Path(f"generated/stubs/stub_{safe}.c") for safe in safe_names
    }
    report.generated_files = [item for item in report.generated_files if item.path not in blocked_paths]

def _dispatchable_dependencies(policy: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for dependency in policy.get("dependencies", []):
        signature = dependency.get("signature", {})
        if dependency.get("resolved_mode") not in {"real", "stub"}:
            continue
        if signature.get("resolution") not in {"exact", "compatible_inferred"}:
            continue
        if dependency.get("target_kind") in {"macro_like", "function_pointer", "unknown", "same_file_static_function"}:
            continue
        if not dependency.get("rewrite_sites"):
            continue
        result.append(dependency)
    return result


def _normalized_parameters(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index, item in enumerate(values):
        name = sanitize_identifier(item.get("name"), f"arg{index}")
        result.append(
            {
                "index": int(item.get("index", index)),
                "name": name,
                "type_raw": str(item.get("type_raw") or "int").strip(),
                "pointer_level": int(item.get("pointer_level") or 0),
                "qualifiers": list(item.get("qualifiers", [])),
                "is_variadic": bool(item.get("is_variadic", False)),
                "canonical_type": str(item.get("canonical_type") or item.get("type_raw") or "int").strip(),
                "type_category": str(item.get("type_category") or _type_category_from_raw(str(item.get("type_raw") or "int"))),
            }
        )
    return result


def _signature_supported(return_type: str, return_category: str, parameters: list[dict[str, Any]]) -> bool:
    if return_category in {"aggregate", "function_pointer", "unknown", "variadic"}:
        return False
    compact_return = _compact_type(return_type)
    if (compact_return.startswith("struct ") or compact_return.startswith("union ")) and "*" not in compact_return:
        return False
    for item in parameters:
        if item.get("is_variadic"):
            return False
        if item.get("type_category") in {"function_pointer", "unknown", "variadic"}:
            return False
        if "(*" in str(item.get("type_raw", "")).replace(" ", ""):
            return False
    return True



def _real_mode_requested(dependency: dict[str, Any], design: dict[str, Any]) -> bool:
    if dependency.get("resolved_mode") == "real":
        return True
    callee = str(dependency.get("callee") or "")
    return any(
        str(override.get("callee") or "") == callee and str(override.get("mode") or "inherit") == "real"
        for case in design.get("test_cases", [])
        for override in case.get("dependency_overrides", [])
    )

def _real_available(dependency: dict[str, Any]) -> bool:
    return bool(dependency.get("implementation_source")) or dependency.get("target_kind") in {"same_file_function", "standard_library"}


def _write_stub_files(
    header_path: Path,
    source_path: Path,
    safe: str,
    return_type: str,
    return_category: str,
    calling_convention: str | None,
    parameters: list[dict[str, Any]],
    declaration_header: str,
) -> None:
    guard = include_guard_for(header_path.name)
    prototype = _prototype(return_type, calling_convention, f"Utr_Stub_{safe}_Invoke", parameters)
    header_lines = [
        "/* generated collision-safe stub: review required */",
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        f"void Utr_Stub_{safe}_Reset(void);",
    ]
    return_kind = _return_kind(return_type, return_category)
    if return_kind == "pointer":
        header_lines.append(f"void Utr_Stub_{safe}_SetReturnPointer(void *value);")
    elif return_kind == "value":
        header_lines.append(f"void Utr_Stub_{safe}_SetReturnInt(long value);")
    header_lines.extend([f"int Utr_Stub_{safe}_GetCallCount(void);", prototype + ";", "", "#endif", ""])
    _write_text_c(header_path, "\n".join(header_lines))

    source_lines = ["/* generated collision-safe stub: review required */"]
    if declaration_header:
        source_lines.append(f'#include "{declaration_header}"')
    source_lines.extend(["#include <string.h>", f'#include "stub_{safe}.h"', "", "static int utr_stub_call_count;"])
    if return_kind != "void":
        source_lines.append(f"static {_storage_type(return_type)} utr_stub_return_value;")
    for item in parameters:
        source_lines.append(f"static {_storage_type(item['type_raw'])} utr_stub_arg{item['index']}_last;")
    source_lines.extend(["", f"void Utr_Stub_{safe}_Reset(void)", "{", "    utr_stub_call_count = 0;"])
    if return_kind != "void":
        source_lines.append("    memset(&utr_stub_return_value, 0, sizeof(utr_stub_return_value));")
    for item in parameters:
        source_lines.append(f"    memset(&utr_stub_arg{item['index']}_last, 0, sizeof(utr_stub_arg{item['index']}_last));")
    source_lines.extend(["}", ""])
    if return_kind == "pointer":
        source_lines.extend(
            [
                f"void Utr_Stub_{safe}_SetReturnPointer(void *value)",
                "{",
                f"    utr_stub_return_value = ({return_type})value;",
                "}",
                "",
            ]
        )
    elif return_kind == "value":
        source_lines.extend(
            [
                f"void Utr_Stub_{safe}_SetReturnInt(long value)",
                "{",
                f"    utr_stub_return_value = ({return_type})value;",
                "}",
                "",
            ]
        )
    source_lines.extend([f"int Utr_Stub_{safe}_GetCallCount(void)", "{", "    return utr_stub_call_count;", "}", "", prototype, "{", "    utr_stub_call_count++;"])
    for item in parameters:
        source_lines.append(f"    utr_stub_arg{item['index']}_last = {item['name']};")
    if return_kind != "void":
        source_lines.append("    return utr_stub_return_value;")
    source_lines.extend(["}", ""])
    _write_text_c(source_path, "\n".join(source_lines))


def _control_header_prefix() -> list[str]:
    return [
        "/* generated dependency control API: product types intentionally excluded */",
        "#ifndef UTR_DEPENDENCY_CONTROL_H_",
        "#define UTR_DEPENDENCY_CONTROL_H_",
        "",
        "#define UTR_DEP_MODE_REAL (0)",
        "#define UTR_DEP_MODE_STUB (1)",
        "",
        "void Utr_Dep_ResetAllModes(void);",
    ]


def _control_api_lines(safe: str, return_type: str, return_category: str, real_available: bool) -> list[str]:
    lines = [
        f"void Utr_Dep_{safe}_SetMode(int mode);",
        f"void Utr_Stub_{safe}_Reset(void);",
        f"int Utr_Stub_{safe}_GetCallCount(void);",
        f"#define Stub_{safe}_Reset Utr_Stub_{safe}_Reset",
        f"#define Stub_{safe}_GetCallCount Utr_Stub_{safe}_GetCallCount",
    ]
    kind = _return_kind(return_type, return_category)
    if kind == "pointer":
        lines.extend(
            [
                f"void Utr_Stub_{safe}_SetReturnPointer(void *value);",
                f"#define Stub_{safe}_SetReturn(value) Utr_Stub_{safe}_SetReturnPointer((void *)(value))",
            ]
        )
    elif kind == "value":
        lines.extend(
            [
                f"void Utr_Stub_{safe}_SetReturnInt(long value);",
                f"#define Stub_{safe}_SetReturn(value) Utr_Stub_{safe}_SetReturnInt((long)(value))",
            ]
        )
    if not real_available:
        lines.append(f"/* Utr_Dep_{safe}: real mode is unavailable and will be clamped to stub mode. */")
    lines.append("")
    return lines


def _dispatcher_header(prototypes: list[str]) -> str:
    lines = [
        "/* generated dependency dispatcher declarations: include after product headers */",
        "#ifndef UTR_DEPENDENCY_DISPATCH_H_",
        "#define UTR_DEPENDENCY_DISPATCH_H_",
        "",
        *prototypes,
        "",
        "#endif",
        "",
    ]
    return "\n".join(lines)


def _dispatcher_source(
    header_tokens: list[str],
    stub_headers: list[str],
    real_prototypes: list[str],
    mode_declarations: list[str],
    reset_lines: list[str],
    dispatcher_sources: list[str],
) -> str:
    lines = ["/* generated dependency dispatchers: review required */"]
    lines.extend(f'#include "{token}"' for token in header_tokens)
    lines.extend(['#include "utr_dependency_control.h"', '#include "utr_dependency_dispatch.h"'])
    lines.extend(f'#include "{header}"' for header in stub_headers)
    lines.append("")
    lines.extend(real_prototypes)
    if real_prototypes:
        lines.append("")
    lines.extend(mode_declarations)
    lines.extend(["void Utr_Dep_ResetAllModes(void)", "{", *reset_lines, "}", ""])
    lines.extend(dispatcher_sources)
    return "\n".join(lines) + "\n"


def _dispatcher_function_lines(
    callee: str,
    safe: str,
    return_type: str,
    return_category: str,
    calling_convention: str | None,
    parameters: list[dict[str, Any]],
    real_available: bool,
) -> list[str]:
    prototype = _prototype(return_type, calling_convention, f"Utr_Dep_{safe}", parameters)
    args = ", ".join(item["name"] for item in parameters)
    kind = _return_kind(return_type, return_category)
    lines = [prototype, "{"]
    if real_available:
        lines.append(f"    if (utr_dep_mode_{safe} == UTR_DEP_MODE_STUB) {{")
        if kind == "void":
            lines.extend([f"        Utr_Stub_{safe}_Invoke({args});", "        return;"])
        else:
            lines.append(f"        return Utr_Stub_{safe}_Invoke({args});")
        lines.append("    }")
        if kind == "void":
            lines.extend([f"    {callee}({args});", "    return;"])
        else:
            lines.append(f"    return {callee}({args});")
    else:
        if kind == "void":
            lines.extend([f"    Utr_Stub_{safe}_Invoke({args});", "    return;"])
        else:
            lines.append(f"    return Utr_Stub_{safe}_Invoke({args});")
    lines.extend(["}", ""])
    return lines


def _patch_test_sources(output_root: Path, design: dict[str, Any], report: Any, dispatches: list[DependencyDispatch]) -> list[Path]:
    changed: list[Path] = []
    cases = {item.get("test_case_id"): item for item in design.get("test_cases", [])}
    by_callee = {item.callee: item for item in dispatches}
    paths = sorted({output_root / item.source_file for item in report.test_skeletons})
    for path in paths:
        if not path.exists():
            continue
        text = path.read_bytes().decode("cp932")
        safe_names = [sanitize_identifier(item.callee) for item in dispatches]
        for safe in safe_names:
            text = re.sub(rf'^\s*#include\s+"stub_{re.escape(safe)}\.h"\s*\r?\n', "", text, flags=re.MULTILINE)
        if '#include "utr_dependency_control.h"' not in text:
            include_matches = list(re.finditer(r'^#include[^\r\n]*(?:\r?\n)', text, flags=re.MULTILINE))
            insert_at = include_matches[-1].end() if include_matches else 0
            text = text[:insert_at] + '#include "utr_dependency_control.h"\r\n' + text[insert_at:]
        for skeleton in report.test_skeletons:
            if output_root / skeleton.source_file != path:
                continue
            case = cases.get(skeleton.test_case_id, {})
            setup_lines = ["    Utr_Dep_ResetAllModes();"]
            for override in case.get("dependency_overrides", []):
                callee = str(override.get("callee") or "")
                mode = str(override.get("mode") or "inherit")
                dispatch = by_callee.get(callee)
                if dispatch is None or mode == "inherit":
                    continue
                if mode == "real" and not dispatch.real_available:
                    report.warnings.append(
                        HarnessGenerationWarning(
                            code="dependency_real_override_unavailable",
                            message=f"Test case {skeleton.test_case_id} requested real mode for {callee}, but no real implementation is available.",
                            related_test_case_id=skeleton.test_case_id,
                            related_stub_name=f"Utr_Stub_{sanitize_identifier(callee)}",
                        )
                    )
                    continue
                setup_lines.append(f"    Utr_Dep_{sanitize_identifier(callee)}_SetMode({_mode_constant(mode)});")
            text = _insert_case_setup(text, skeleton.generated_function_name, setup_lines)
        path.write_text(text, encoding="cp932", newline="")
        changed.append(path)
    return changed


def _insert_case_setup(text: str, function_name: str, setup_lines: list[str]) -> str:
    marker = f"void {function_name}(void)"
    start = text.find(marker)
    if start == -1:
        return text
    next_function = text.find("\nvoid Test_", start + len(marker))
    end = next_function if next_function != -1 else len(text)
    block = text[start:end]
    block = re.sub(r"^\s*Utr_Dep_ResetAllModes\(\);\s*\r?\n", "", block, flags=re.MULTILINE)
    block = re.sub(r"^\s*Utr_Dep_[A-Za-z_]\w*_SetMode\([^;]+\);\s*\r?\n", "", block, flags=re.MULTILINE)
    insertion = re.search(r"^\s*Stub_[A-Za-z_]\w*_Reset\(\);", block, flags=re.MULTILINE)
    if insertion is None:
        insertion = re.search(r"^\s*(?:actual_return\s*=\s*)?Target_Invoke_", block, flags=re.MULTILINE)
    if insertion is None:
        brace = block.find("{")
        insert_at = brace + 1
        addition = "\r\n" + "\r\n".join(setup_lines)
    else:
        insert_at = insertion.start()
        addition = "\r\n".join(setup_lines) + "\r\n"
    block = block[:insert_at] + addition + block[insert_at:]
    return text[:start] + block + text[end:]


def _prototype(return_type: str, convention: str | None, name: str, parameters: list[dict[str, Any]]) -> str:
    prefix = " ".join(item for item in (return_type, convention) if item)
    values = ", ".join(f"{item['type_raw']} {item['name']}" for item in parameters) or "void"
    return f"{prefix} {name}({values})"


def _return_kind(return_type: str, type_category: str | None = None) -> str:
    if type_category == "void":
        return "void"
    if type_category == "pointer":
        return "pointer"
    compact = _compact_type(return_type)
    if compact == "void":
        return "void"
    if "*" in compact:
        return "pointer"
    return "value"


def _type_category_from_raw(type_raw: str) -> str:
    compact = _compact_type(type_raw)
    if compact == "void":
        return "void"
    if "(*" in compact.replace(" ", ""):
        return "function_pointer"
    if "*" in compact:
        return "pointer"
    if compact.startswith("struct ") or compact.startswith("union "):
        return "aggregate"
    return "scalar"


def _storage_type(type_raw: str) -> str:
    text = re.sub(r"\b(?:const|volatile)\b", "", type_raw)
    return " ".join(text.split()) or "int"


def _compact_type(value: str) -> str:
    return " ".join(str(value).strip().split())


def _mode_constant(mode: str) -> str:
    return "UTR_DEP_MODE_REAL" if mode == "real" else "UTR_DEP_MODE_STUB"


def _record_generated_file(
    generated_files: list[GeneratedFile],
    output_root: Path,
    path: Path,
    kind: str,
    generated_from: list[str],
    review_required: bool,
) -> None:
    relative = path.relative_to(output_root)
    existing = next((item for item in generated_files if item.path == relative), None)
    if existing is not None:
        existing.file_kind = kind
        existing.sha256 = sha256_file(path)
        existing.overwrite = True
        existing.review_required = review_required
        return
    generated_files.append(
        GeneratedFile(
            path=relative,
            file_kind=kind,
            generated_from=generated_from,
            sha256=sha256_file(path),
            overwrite=True,
            review_required=review_required,
        )
    )


def _write_text_c(path: Path, text: str) -> None:
    write_c_file(path, text, overwrite=True)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"Unsupported dependency dispatcher payload: {type(value)!r}")


def _optional_payload(value: Any | None) -> dict[str, Any]:
    return {} if value is None else _payload(value)
