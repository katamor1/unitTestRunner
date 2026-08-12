from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from unit_test_runner.encoding import decode_bytes_auto

from .c90_writer import include_guard_for, relative_posix, sanitize_identifier, sha256_file, write_c_file
from .harness_models import (
    BuildHint,
    GeneratedFile,
    HarnessGenerationPolicy,
    HarnessGenerationWarning,
    HarnessSkeletonReport,
    StubParameter,
    StubSkeleton,
    TestSkeleton,
    UnresolvedPlaceholder,
)
from .harness_report_writer import write_harness_report
from .type_bridge import enrich_signature_bridge_types


_QUOTE_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)
_SCALAR_PUBLIC_TYPES = {
    "char",
    "signed char",
    "unsigned char",
    "short",
    "short int",
    "signed short",
    "signed short int",
    "unsigned short",
    "unsigned short int",
    "int",
    "signed",
    "signed int",
    "unsigned",
    "unsigned int",
    "long",
    "long int",
    "signed long",
    "signed long int",
    "unsigned long",
    "unsigned long int",
    "float",
    "double",
}
_SCALAR_BASE_TYPES = {
    *_SCALAR_PUBLIC_TYPES,
    "long long",
    "long long int",
    "signed long long",
    "signed long long int",
    "unsigned long long",
    "long double",
}
_SCALAR_TYPEDEFS = {
    "BOOL",
    "BYTE",
    "WORD",
    "DWORD",
    "UINT",
    "ULONG",
    "USHORT",
    "UCHAR",
    "INT",
    "LONG",
    "SHORT",
    "CHAR",
}


def generate_harness_skeleton(
    function_signature: Any,
    global_access: Any,
    call_report: Any,
    test_case_design: Any,
    output_root: Path | str,
    overwrite: bool = False,
) -> HarnessSkeletonReport:
    output_root = Path(output_root).resolve()
    policy = HarnessGenerationPolicy(overwrite_existing=overwrite)
    signature = enrich_signature_bridge_types(_payload(function_signature))
    globals_payload = _payload(global_access)
    calls = _payload(call_report)
    test_case_design_payload = _payload(test_case_design)
    function_payload = signature.get("function", {})
    function_name = function_payload.get("name") or test_case_design_payload.get("function", {}).get("name") or "unknown_function"
    source_path = Path(signature.get("source", {}).get("path") or test_case_design_payload.get("source", {}).get("path") or "")
    generated_files: list[GeneratedFile] = []
    warnings: list[HarnessGenerationWarning] = []
    unresolved: list[UnresolvedPlaceholder] = []
    build_hints: list[BuildHint] = []
    generation_blockers = _generation_blockers(
        function_name,
        source_path,
        function_payload,
        globals_payload,
        calls,
        test_case_design_payload,
    )

    _ensure_layout(output_root)
    _write_assert_files(output_root, generated_files, overwrite)
    stubs = _write_stub_files(output_root, calls, test_case_design_payload, generated_files, warnings, overwrite)
    tests = _write_test_files(
        output_root,
        signature,
        globals_payload,
        test_case_design_payload,
        stubs,
        generated_files,
        unresolved,
        warnings,
        generation_blockers,
        overwrite,
    )
    _write_target_invocation(output_root, signature, generated_files, warnings, overwrite)
    _write_runner_files(output_root, function_name, tests, generated_files, overwrite)
    build_hints.extend(_build_hints(source_path, stubs, tests))

    status = "partial" if unresolved or warnings else "generated"
    report = HarnessSkeletonReport(
        source_path=source_path,
        function_name=function_name,
        status=status,
        output_root=output_root,
        generation_policy=policy,
        generated_files=generated_files,
        stub_skeletons=stubs,
        test_skeletons=tests,
        unresolved_placeholders=unresolved,
        build_hints=build_hints,
        warnings=warnings,
    )
    write_harness_report(output_root, report)
    return report


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    raise TypeError(f"Unsupported harness input type: {type(value)!r}")


def _ensure_layout(output_root: Path) -> None:
    for relative in [
        "generated/include",
        "generated/harness",
        "generated/stubs",
        "generated/tests",
        "reports",
    ]:
        (output_root / relative).mkdir(parents=True, exist_ok=True)


def _record_file(output_root: Path, generated_files: list[GeneratedFile], path: Path, kind: str, generated_from: list[str], review: bool, overwrite: bool) -> None:
    relative = path.relative_to(output_root)
    existing = next((item for item in generated_files if item.path == relative), None)
    if existing is not None:
        existing.sha256 = sha256_file(path)
        return
    generated_files.append(
        GeneratedFile(
            path=relative,
            file_kind=kind,
            generated_from=generated_from,
            sha256=sha256_file(path),
            overwrite=overwrite,
            review_required=review,
        )
    )


def _write_c(output_root: Path, generated_files: list[GeneratedFile], relative: str, kind: str, text: str, generated_from: list[str], review: bool, overwrite: bool) -> Path:
    path = output_root / relative
    written, digest = write_c_file(path, text, overwrite=overwrite)
    generated_files.append(
        GeneratedFile(
            path=Path(relative),
            file_kind=kind,
            generated_from=generated_from,
            sha256=digest,
            overwrite=written,
            review_required=review,
        )
    )
    return path


def _write_assert_files(output_root: Path, generated_files: list[GeneratedFile], overwrite: bool) -> None:
    header = """/* generated assert skeleton: review required */
#ifndef UTR_ASSERT_H_
#define UTR_ASSERT_H_

#ifndef NULL
#define NULL ((void *)0)
#endif

void Utr_AssertTrue(int value, const char *file, int line, const char *expr);
void Utr_AssertFalse(int value, const char *file, int line, const char *expr);
void Utr_AssertEqInt(int expected, int actual, const char *file, int line, const char *expr);
void Utr_AssertPtrNull(const void *actual, const char *file, int line, const char *expr);
int Utr_GetFailureCount(void);
void Utr_ResetFailureCount(void);

#define UTR_ASSERT_TRUE(expr) Utr_AssertTrue((expr), __FILE__, __LINE__, #expr)
#define UTR_ASSERT_FALSE(expr) Utr_AssertFalse((expr), __FILE__, __LINE__, #expr)
#define UTR_ASSERT_EQ_INT(expected, actual) Utr_AssertEqInt((expected), (actual), __FILE__, __LINE__, #actual)
#define UTR_ASSERT_PTR_NULL(actual) Utr_AssertPtrNull((actual), __FILE__, __LINE__, #actual)

#endif
"""
    source = """/* generated assert skeleton: review required */
#include <stdio.h>
#include "utr_assert.h"

static int utr_failure_count;

static void Utr_ReportFailure(const char *kind, const char *file, int line, const char *expr)
{
    utr_failure_count++;
    printf("UTR ASSERT %s: %s:%d %s\\n", kind, file, line, expr);
}

void Utr_AssertTrue(int value, const char *file, int line, const char *expr)
{
    if (!value) {
        Utr_ReportFailure("TRUE", file, line, expr);
    }
}

void Utr_AssertFalse(int value, const char *file, int line, const char *expr)
{
    if (value) {
        Utr_ReportFailure("FALSE", file, line, expr);
    }
}

void Utr_AssertEqInt(int expected, int actual, const char *file, int line, const char *expr)
{
    if (expected != actual) {
        Utr_ReportFailure("EQ_INT", file, line, expr);
    }
}

void Utr_AssertPtrNull(const void *actual, const char *file, int line, const char *expr)
{
    if (actual != NULL) {
        Utr_ReportFailure("PTR_NULL", file, line, expr);
    }
}

int Utr_GetFailureCount(void)
{
    return utr_failure_count;
}

void Utr_ResetFailureCount(void)
{
    utr_failure_count = 0;
}
"""
    _write_c(output_root, generated_files, "generated/include/utr_assert.h", "assert_header", header, ["harness_skeleton_generation"], False, overwrite)
    _write_c(output_root, generated_files, "generated/harness/utr_assert.c", "assert_source", source, ["harness_skeleton_generation"], False, overwrite)


def _write_runner_files(output_root: Path, function_name: str, tests: list[TestSkeleton], generated_files: list[GeneratedFile], overwrite: bool) -> None:
    case_header = f"test_{sanitize_identifier(function_name)}_cases.h"
    table_entries = []
    for test in tests:
        table_entries.append(f'    {{"{test.test_case_id}", {test.generated_function_name}}}')
    entries = ",\n".join(table_entries) if table_entries else '    {"no_tests", 0}'
    source = f"""/* generated runner skeleton: review required */
#include <stdio.h>
#include "utr_assert.h"
#include "utr_runner.h"
#include "{case_header}"

typedef struct Utr_TestEntryTag {{
    const char *name;
    void (*func)(void);
}} Utr_TestEntry;

static Utr_TestEntry utr_tests[] = {{
{entries}
}};

void Utr_RunAllTests(void)
{{
    int index;
    int count;

    Utr_ResetFailureCount();
    count = (int)(sizeof(utr_tests) / sizeof(utr_tests[0]));
    for (index = 0; index < count; index++) {{
        if (utr_tests[index].func != 0) {{
            printf("UTR RUN %s\\n", utr_tests[index].name);
            utr_tests[index].func();
        }}
    }}
}}

int main(void)
{{
    Utr_RunAllTests();
    return Utr_GetFailureCount() == 0 ? 0 : 1;
}}
"""
    header = """/* generated runner skeleton: review required */
#ifndef UTR_RUNNER_H_
#define UTR_RUNNER_H_

void Utr_RunAllTests(void);

#endif
"""
    _write_c(output_root, generated_files, "generated/include/utr_runner.h", "runner_header", header, ["harness_skeleton_generation"], False, overwrite)
    _write_c(output_root, generated_files, "generated/harness/utr_runner.c", "runner_source", source, ["harness_skeleton_generation"], True, overwrite)


def _write_stub_files(
    output_root: Path,
    call_report: dict[str, Any],
    test_case_design: dict[str, Any],
    generated_files: list[GeneratedFile],
    warnings: list[HarnessGenerationWarning],
    overwrite: bool,
) -> list[StubSkeleton]:
    calls_by_id = {item.get("call_id"): item for item in call_report.get("calls", [])}
    calls_by_name = {item.get("name"): item for item in call_report.get("calls", [])}
    test_case_ids_by_stub = _test_case_ids_by_stub(test_case_design)
    skeletons: list[StubSkeleton] = []
    for candidate in call_report.get("stub_candidates", []):
        original_name = candidate.get("name", "UnknownStub")
        safe_name = sanitize_identifier(original_name)
        stub_name = f"Stub_{safe_name}"
        related_calls = list(candidate.get("related_calls", []))
        call = _first_call_for_stub(candidate, calls_by_id, calls_by_name)
        parameters = _stub_parameters(call, warnings, stub_name)
        return_type = "int" if candidate.get("return_value_control_needed") else "void"
        capabilities = ["call_count", "reset"]
        if candidate.get("return_value_control_needed"):
            capabilities.append("return_value_control")
        if candidate.get("argument_capture_needed") and parameters:
            capabilities.append("argument_capture")
        if candidate.get("side_effect_control_needed"):
            capabilities.append("side_effect_placeholder")
        header_rel = f"generated/stubs/stub_{safe_name}.h"
        source_rel = f"generated/stubs/stub_{safe_name}.c"
        header = _render_stub_header(safe_name, original_name, return_type, parameters)
        source = _render_stub_source(safe_name, original_name, return_type, parameters)
        _write_c(output_root, generated_files, header_rel, "stub_header", header, related_calls or [original_name], True, overwrite)
        _write_c(output_root, generated_files, source_rel, "stub_source", source, related_calls or [original_name], True, overwrite)
        skeletons.append(
            StubSkeleton(
                stub_name=stub_name,
                original_function_name=original_name,
                return_type_raw=return_type,
                parameters=parameters,
                source_file=Path(source_rel),
                header_file=Path(header_rel),
                capabilities=capabilities,
                related_call_ids=related_calls,
                related_test_case_ids=test_case_ids_by_stub.get(original_name, []),
                warnings=[warning for warning in warnings if warning.related_stub_name == stub_name],
            )
        )
    return skeletons


def _first_call_for_stub(candidate: dict[str, Any], calls_by_id: dict[str | None, dict[str, Any]], calls_by_name: dict[str | None, dict[str, Any]]) -> dict[str, Any] | None:
    for call_id in candidate.get("related_calls", []):
        if call_id in calls_by_id:
            return calls_by_id[call_id]
    return calls_by_name.get(candidate.get("name"))


def _stub_parameters(call: dict[str, Any] | None, warnings: list[HarnessGenerationWarning], stub_name: str) -> list[StubParameter]:
    if not call:
        return []
    parameters: list[StubParameter] = []
    for arg in call.get("arguments", []):
        index = int(arg.get("index", len(parameters)))
        name = f"arg{index}"
        kind = arg.get("argument_kind", "")
        raw = arg.get("raw", "")
        if "address" in kind or raw.strip().startswith("&"):
            type_raw = "void *"
            capture = "copy_pointer_value_only"
            review = True
            warnings.append(
                HarnessGenerationWarning(
                    code="pointer_fixture_required",
                    message=f"Pointer argument capture for {stub_name} records pointer value only.",
                    related_stub_name=stub_name,
                )
            )
        else:
            type_raw = "int"
            capture = "copy_value"
            review = False
        parameters.append(StubParameter(index=index, name=name, type_raw=type_raw, capture_strategy=capture, review_required=review))
    return parameters


def _render_stub_header(safe_name: str, original_name: str, return_type: str, parameters: list[StubParameter]) -> str:
    guard = include_guard_for(f"stub_{safe_name}.h")
    lines = [
        "/* generated stub skeleton: review required */",
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        f"void Stub_{safe_name}_Reset(void);",
    ]
    if return_type != "void":
        lines.append(f"void Stub_{safe_name}_SetReturn({return_type} value);")
    lines.append(f"int Stub_{safe_name}_GetCallCount(void);")
    for parameter in parameters:
        capture_type = "void *" if parameter.capture_strategy == "copy_pointer_value_only" else parameter.type_raw
        lines.append(f"{capture_type} Stub_{safe_name}_GetArg{parameter.index}Last(void);")
    lines.extend(["", f"{return_type} {original_name}({_parameter_list(parameters)});", "", "#endif"])
    return "\n".join(lines) + "\n"


def _render_stub_source(safe_name: str, original_name: str, return_type: str, parameters: list[StubParameter]) -> str:
    declarations = ["static int stub_call_count;"]
    if return_type != "void":
        declarations.append(f"static {return_type} stub_return_value;")
    for parameter in parameters:
        capture_type = "void *" if parameter.capture_strategy == "copy_pointer_value_only" else parameter.type_raw
        declarations.append(f"static {capture_type} stub_arg{parameter.index}_last;")
    reset_lines = ["    stub_call_count = 0;"]
    if return_type != "void":
        reset_lines.append("    stub_return_value = 0;")
    for parameter in parameters:
        reset_lines.append(f"    stub_arg{parameter.index}_last = 0;")
    accessors: list[str] = []
    if return_type != "void":
        accessors.extend(
            [
                f"void Stub_{safe_name}_SetReturn({return_type} value)",
                "{",
                "    stub_return_value = value;",
                "}",
                "",
            ]
        )
    accessors.extend([f"int Stub_{safe_name}_GetCallCount(void)", "{", "    return stub_call_count;", "}", ""])
    for parameter in parameters:
        capture_type = "void *" if parameter.capture_strategy == "copy_pointer_value_only" else parameter.type_raw
        accessors.extend([f"{capture_type} Stub_{safe_name}_GetArg{parameter.index}Last(void)", "{", f"    return stub_arg{parameter.index}_last;", "}", ""])
    capture_lines = ["    stub_call_count++;"]
    for parameter in parameters:
        capture_lines.append(f"    stub_arg{parameter.index}_last = {parameter.name};")
    if return_type != "void":
        capture_lines.append("    return stub_return_value;")
    body = "\n".join(capture_lines)
    lines = [
        "/* generated stub skeleton: review required */",
        f'#include "stub_{safe_name}.h"',
        "",
        *declarations,
        "",
        f"void Stub_{safe_name}_Reset(void)",
        "{",
        *reset_lines,
        "}",
        "",
        *accessors,
        f"{return_type} {original_name}({_parameter_list(parameters)})",
        "{",
        body,
        "}",
        "",
    ]
    return "\n".join(lines)


def _parameter_list(parameters: list[StubParameter]) -> str:
    if not parameters:
        return "void"
    return ", ".join(f"{parameter.type_raw} {parameter.name}" for parameter in parameters)


def _test_case_ids_by_stub(test_case_design: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for test_case in test_case_design.get("test_cases", []):
        test_case_id = test_case.get("test_case_id", "")
        for setup in test_case.get("stub_setups", []):
            mapping.setdefault(setup.get("stub_name", ""), []).append(test_case_id)
    return mapping


def _write_target_invocation(
    output_root: Path,
    signature: dict[str, Any],
    generated_files: list[GeneratedFile],
    warnings: list[HarnessGenerationWarning],
    overwrite: bool,
) -> None:
    function_payload = signature.get("function", {})
    function_name = function_payload.get("name", "unknown_function")
    source_path = Path(signature.get("source", {}).get("path") or "")
    raw_return_type = _return_type(function_payload)
    return_info = function_payload.get("return_type") if isinstance(function_payload.get("return_type"), dict) else {}
    return_bridge_kind = str(return_info.get("bridge_kind") or "unresolved")
    parameters = _signature_parameters(function_payload)
    raw_parameter_list = _signature_parameter_list(parameters)
    public_return_type = _public_return_type(raw_return_type, return_bridge_kind)
    public_parameter_list = _public_parameter_list(parameters)
    public_prototype = f"{public_return_type} Target_Invoke_{sanitize_identifier(function_name)}({public_parameter_list})"
    target_prototype = f"{raw_return_type} {function_name}({raw_parameter_list})"
    source_includes = _source_quote_includes(source_path)
    include_block = _include_block(source_includes)
    public_include_block = include_block if _public_prototype_needs_headers(
        raw_return_type,
        return_bridge_kind,
        parameters,
    ) else ""
    if function_payload.get("storage_class") == "static":
        warnings.append(
            HarnessGenerationWarning(
                code="static_target_direct_call_warning",
                message="Static target function may require an expose wrapper during build workspace generation.",
                related_file=Path("generated/harness/target_invocation.c"),
            )
        )
    header = f"""/* generated target invocation skeleton: review required */
#ifndef TARGET_INVOCATION_H_
#define TARGET_INVOCATION_H_

{public_include_block}{public_prototype};

#endif
"""
    invocation_args = ", ".join(_target_argument_cast(parameter) for parameter in parameters) or ""
    call_expression = f"{function_name}({invocation_args})"
    if raw_return_type == "void":
        call_line = f"    {call_expression};"
    elif public_return_type == raw_return_type:
        call_line = f"    return {call_expression};"
    else:
        call_line = f"    return ({public_return_type})({call_expression});"
    source = f"""/* generated target invocation skeleton: review required */
#include "target_invocation.h"
{include_block}
{target_prototype};

{public_prototype}
{{
{call_line}
}}
"""
    _write_c(output_root, generated_files, "generated/harness/target_invocation.h", "target_invocation_header", header, [function_name], True, overwrite)
    _write_c(output_root, generated_files, "generated/harness/target_invocation.c", "target_invocation_source", source, [function_name], True, overwrite)


def _source_quote_includes(source_path: Path) -> list[str]:
    try:
        text = decode_bytes_auto(source_path.read_bytes())
    except OSError:
        return []
    includes: list[str] = []
    for match in _QUOTE_INCLUDE_RE.finditer(text):
        include = match.group(1).strip().replace("\\", "/")
        if include and include not in includes:
            includes.append(include)
    return includes


def _include_block(includes: list[str]) -> str:
    if not includes:
        return ""
    return "".join(f'#include "{include}"\n' for include in includes) + "\n"


def _write_test_files(
    output_root: Path,
    signature: dict[str, Any],
    globals_payload: dict[str, Any],
    test_case_design: dict[str, Any],
    stubs: list[StubSkeleton],
    generated_files: list[GeneratedFile],
    unresolved: list[UnresolvedPlaceholder],
    warnings: list[HarnessGenerationWarning],
    generation_blockers: list[str],
    overwrite: bool,
) -> list[TestSkeleton]:
    function_payload = signature.get("function", {})
    function_name = function_payload.get("name") or test_case_design.get("function", {}).get("name") or "unknown_function"
    safe_function = sanitize_identifier(function_name)
    parameters = _signature_parameters(function_payload)
    return_type = _return_type(function_payload)
    stub_names = [item.original_function_name for item in stubs]
    stub_safe_names = [sanitize_identifier(item.original_function_name) for item in stubs]
    global_declarations = _extern_global_declarations(globals_payload, test_case_design)
    test_skeletons: list[TestSkeleton] = []
    functions: list[str] = []
    prototypes: list[str] = []
    all_blockers: list[str] = list(generation_blockers)
    for index, case in enumerate(test_case_design.get("test_cases", []), start=1):
        case_id = case.get("test_case_id") or f"TC_{safe_function}_{index:03d}"
        test_func = f"Test_{sanitize_identifier(case_id)}"
        prototypes.append(f"void {test_func}(void);")
        coverage_ids = [link.get("coverage_id", "") for link in case.get("coverage_links", []) if link.get("coverage_id")]
        related_stubs = sorted({setup.get("stub_name", "") for setup in case.get("stub_setups", []) if setup.get("stub_name")})
        blockers = _case_review_blockers(case, parameters, return_type, stub_names)
        blockers = list(dict.fromkeys([*generation_blockers, *blockers]))
        all_blockers.extend(blockers)
        placeholder_count = len(blockers)
        if blockers:
            unresolved.append(
                UnresolvedPlaceholder(
                    placeholder_id=f"UP_{sanitize_identifier(case_id)}_REVIEW",
                    placeholder_kind="review_gate",
                    name="review_required",
                    related_test_case_id=case_id,
                    related_stub_name=None,
                    reason="; ".join(blockers),
                    suggested_action="Review the exact inputs, dependency behavior, and expected observations before a real run.",
                )
            )
            warnings.append(
                HarnessGenerationWarning(
                    code="review_only_scaffold_generated",
                    message=f"Review-only scaffold generated for {case_id}: {'; '.join(blockers)}.",
                    related_test_case_id=case_id,
                )
            )
            functions.append(_render_review_only_test_function(test_func, blockers))
        else:
            functions.append(_render_test_function(test_func, case, parameters, return_type, function_name, stub_safe_names))
        test_skeletons.append(
            TestSkeleton(
                test_case_id=case_id,
                function_name=function_name,
                source_file=Path(f"generated/tests/test_{safe_function}.c"),
                generated_function_name=test_func,
                related_coverage_ids=coverage_ids,
                related_stub_names=related_stubs,
                placeholder_count=placeholder_count,
                review_required=bool(blockers),
            )
        )
    if not functions:
        test_func = f"Test_TC_{safe_function}_001"
        prototypes.append(f"void {test_func}(void);")
        blocker = "no reviewed test case was supplied"
        all_blockers.append(blocker)
        unresolved.append(
            UnresolvedPlaceholder(
                placeholder_id=f"UP_TC_{safe_function}_001_REVIEW",
                placeholder_kind="review_gate",
                name="review_required",
                related_test_case_id=f"TC_{safe_function}_001",
                related_stub_name=None,
                reason=blocker,
                suggested_action="Supply and review at least one exact test case before a real run.",
            )
        )
        functions.append(_render_review_only_test_function(test_func, [blocker]))
        test_skeletons.append(
            TestSkeleton(
                test_case_id=f"TC_{safe_function}_001",
                function_name=function_name,
                source_file=Path(f"generated/tests/test_{safe_function}.c"),
                generated_function_name=test_func,
                related_coverage_ids=[],
                related_stub_names=stub_names,
                placeholder_count=1,
                review_required=True,
            )
        )
    source_path = Path(signature.get("source", {}).get("path") or "")
    include_lines = [
        *(f'#include "{include}"' for include in _source_quote_includes(source_path)),
        '#include "utr_assert.h"',
        '#include "utr_runner.h"',
        '#include "target_invocation.h"',
    ]
    if _needs_string_compare(test_case_design):
        include_lines.insert(0, "#include <string.h>")
    for stub_safe in stub_safe_names:
        include_lines.append(f'#include "stub_{stub_safe}.h"')
    gate_lines = []
    if all_blockers:
        gate_lines = ['#error "UTR_REVIEW_REQUIRED: exact reviewed inputs and oracles are required before execution"', ""]
    source = "\n".join(
        [
            "/* generated test skeleton: review required */",
            *gate_lines,
            *include_lines,
            "",
            *global_declarations,
            "",
            *functions,
        ]
    )
    guard = include_guard_for(f"test_{safe_function}_cases.h")
    header = "\n".join(["/* generated test case declarations: review required */", f"#ifndef {guard}", f"#define {guard}", "", *prototypes, "", "#endif", ""])
    _write_c(output_root, generated_files, f"generated/tests/test_{safe_function}.c", "test_source", source, [case.test_case_id for case in test_skeletons], True, overwrite)
    _write_c(output_root, generated_files, f"generated/tests/test_{safe_function}_cases.h", "test_header", header, [case.test_case_id for case in test_skeletons], True, overwrite)
    return test_skeletons


def _render_test_function(
    test_func: str,
    case: dict[str, Any],
    parameters: list[dict[str, Any]],
    return_type: str,
    function_name: str,
    stub_safe_names: list[str],
) -> str:
    assignments = {item.get("target_name"): item for item in case.get("input_assignments", [])}
    lines = [f"void {test_func}(void)", "{"]
    declarations: list[str] = []
    setup_lines: list[str] = []
    call_args: list[str] = []
    for parameter in parameters:
        name = parameter["name"]
        call_args.append(name)
        assignment = assignments.get(name, {})
        value = assignment.get("value_expression")
        if parameter.get("is_array") or int(parameter.get("pointer_level") or 0) > 0:
            declarations.append(f"    static double {name}_storage[512];")
            declarations.append(f"    void *{name};")
            if value == "NULL":
                setup_lines.append(f"    {name} = NULL;")
            else:
                setup_lines.append(f"    {name} = (void *){name}_storage;")
            continue
        declarations.extend(
            _value_parameter_declaration_and_setup(
                value,
                name,
                _public_value_type(parameter.get("type_raw"), parameter.get("bridge_kind")),
                str(parameter.get("bridge_kind") or "unresolved"),
                setup_lines,
            )
        )
    public_return_type = _public_return_type(return_type)
    if public_return_type != "void":
        declarations.append(f"    {public_return_type} actual_return;")
    lines.extend(declarations)
    lines.append("")
    for stub_safe in stub_safe_names:
        lines.append(f"    Stub_{stub_safe}_Reset();")
    for setup in case.get("stub_setups", []):
        if setup.get("setup_kind") != "return_value" or setup.get("value_expression") is None:
            continue
        stub_safe = sanitize_identifier(setup.get("stub_name"))
        lines.append(f"    Stub_{stub_safe}_SetReturn({_safe_c_value(setup.get('value_expression'))});")
    lines.extend(setup_lines)
    invocation = f"Target_Invoke_{sanitize_identifier(function_name)}({', '.join(call_args)})"
    if public_return_type == "void":
        lines.append(f"    {invocation};")
    else:
        lines.append(f"    actual_return = {invocation};")
    if public_return_type != "void":
        lines.append(f"    UTR_ASSERT_EQ_INT({_return_expectation(case)}, (int)actual_return);")
    for stub_safe, expected in _stub_call_count_expectations(case).items():
        lines.append(f"    UTR_ASSERT_EQ_INT({expected}, Stub_{stub_safe}_GetCallCount());")
    lines.extend(_expected_observation_assertions(case))
    lines.extend(["}", ""])
    return "\n".join(lines)


def _value_parameter_declaration_and_setup(
    value: Any,
    name: str,
    type_raw: str,
    bridge_kind: str,
    setup_lines: list[str],
) -> list[str]:
    if bridge_kind == "aggregate":
        return [f"    {type_raw} {name} = {{0}};"]
    if bridge_kind == "unresolved":
        setup_lines.append(f"    /* review required: unresolved value type for {name}; no lossy initializer emitted. */")
        return [f"    {type_raw} {name};"]
    setup_lines.append(f"    {name} = {_safe_initializer_value(value)};")
    return [f"    {type_raw} {name};"]


def _safe_initializer_value(value: Any) -> str:
    return _safe_c_value(value)


def _render_review_only_test_function(test_func: str, blockers: list[str]) -> str:
    reason = "; ".join(blockers).replace("*/", "* /")
    return "\n".join(
        [
            f"void {test_func}(void)",
            "{",
            f"    /* review required: {reason} */",
            "}",
            "",
        ]
    )


def _generation_blockers(
    function_name: str,
    source_path: Path,
    function_payload: dict[str, Any],
    globals_payload: dict[str, Any],
    call_report: dict[str, Any],
    test_case_design: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not _is_supported_execution_target(function_name, source_path):
        blockers.append("target is outside the reviewed Control_Update/practical fixture paths")
    if _has_executable_unresolved_items(test_case_design):
        blockers.append("test design contains unresolved items")
    return_type = function_payload.get("return_type") or {}
    if not str(return_type.get("raw") or return_type.get("normalized") or "").strip():
        blockers.append("target return type is missing")
    elif return_type.get("bridge_kind") == "unresolved":
        blockers.append("target return type is unresolved")
    for parameter in function_payload.get("parameters", []):
        type_info = parameter.get("type") or {}
        name = parameter.get("name") or f"arg{parameter.get('index', '?')}"
        if type_info.get("is_function_pointer"):
            blockers.append(f"parameter {name} is a function pointer")
        elif type_info.get("bridge_kind") == "unresolved":
            blockers.append(f"parameter {name} type is unresolved")
    declarations = {
        str(item.get("name") or ""): item
        for item in globals_payload.get("file_scope_declarations", [])
        if item.get("name")
    }
    if any(item.get("confidence") == "low" for item in declarations.values()):
        blockers.append("file-scope type classification is unresolved")
    expected_globals = {
        str(observation.get("target_name") or "")
        for case in test_case_design.get("test_cases", [])
        for observation in case.get("expected_observations", [])
        if observation.get("observation_kind") == "global_value"
    }
    for name in sorted(expected_globals):
        declaration = declarations.get(name)
        if declaration is None or not str(declaration.get("type_raw") or "").strip():
            blockers.append(f"global oracle {name} has no exact declaration type")
    unsupported = {
        "macro_like",
        "function_pointer",
        "member_call",
        "function_address_use",
        "mixed_call_forms",
        "unknown",
    }
    for call in call_report.get("calls", []):
        kind = str(call.get("target_kind") or "unknown")
        if kind in unsupported:
            blockers.append(f"call {call.get('name') or '<unknown>'} has unsupported form {kind}")
    blockers.extend(str(item) for item in call_report.get("_generation_blockers", []) if str(item).strip())
    return list(dict.fromkeys(blockers))


def _has_executable_unresolved_items(test_case_design: dict[str, Any]) -> bool:
    executable_case_ids = {
        str(case.get("test_case_id") or "")
        for case in test_case_design.get("test_cases", [])
        if str(case.get("test_case_id") or "").strip()
    }
    for item in test_case_design.get("unresolved_items", []):
        if not isinstance(item, dict):
            return True
        related_case_ids = {
            str(case_id)
            for case_id in item.get("related_test_case_ids") or []
            if str(case_id).strip()
        }
        if not related_case_ids or related_case_ids & executable_case_ids:
            return True
    return False


def _is_supported_execution_target(function_name: str, source_path: Path) -> bool:
    if function_name == "Control_Update":
        return True
    normalized = source_path.as_posix().casefold()
    return function_name == "DeviceControl_Update" and "/vc6_practical_project/" in f"/{normalized.strip('/')}"


def _case_review_blockers(
    case: dict[str, Any],
    parameters: list[dict[str, Any]],
    return_type: str,
    stub_names: list[str],
) -> list[str]:
    blockers: list[str] = []
    for field in ("input_assignments", "state_setups", "stub_setups", "dependency_overrides", "expected_observations"):
        if any(bool(item.get("review_required")) for item in case.get(field, [])):
            blockers.append(f"{field} contains review-required values")
    assignments = {str(item.get("target_name") or ""): item for item in case.get("input_assignments", [])}
    for parameter in parameters:
        name = str(parameter.get("name") or "")
        assignment = assignments.get(name)
        if assignment is None:
            blockers.append(f"parameter {name} has no exact assignment")
            continue
        value = str(assignment.get("value_expression") or "").strip()
        if parameter.get("is_array") or int(parameter.get("pointer_level") or 0) > 0:
            if value not in {"NULL", "VALID_STORAGE"}:
                blockers.append(f"parameter {name} has an unrepresentable pointer value")
        elif not _is_safe_c_scalar_expression(value):
            blockers.append(f"parameter {name} has an unrepresentable scalar value")
    if return_type != "void" and _return_expectation(case) is None:
        blockers.append("non-void target has no exact reviewed return oracle")
    for observation in case.get("expected_observations", []):
        kind = observation.get("observation_kind")
        value = str(observation.get("expected_expression") or "").strip()
        if kind in {"return_value", "global_value"} and not _is_safe_c_scalar_expression(value):
            blockers.append(f"{kind} has an unrepresentable expected value")
        elif kind == "char_array_string" and not _is_safe_c_string_expression(value):
            blockers.append("char_array_string has an unrepresentable expected value")
    call_counts = _stub_call_count_expectations(case)
    related = {sanitize_identifier(name) for name in stub_names}
    for setup in case.get("stub_setups", []):
        if setup.get("setup_kind") == "call_count_observation":
            safe = sanitize_identifier(setup.get("stub_name"))
            requested = str(setup.get("value_expression") or "").strip()
            if requested and safe in related and safe not in call_counts:
                blockers.append(f"stub {setup.get('stub_name')} has no exact call-count oracle")
    return list(dict.fromkeys(blockers))


def _return_expectation(case: dict[str, Any]) -> str | None:
    for observation in case.get("expected_observations", []):
        if observation.get("observation_kind") != "return_value" or observation.get("review_required"):
            continue
        value = str(observation.get("expected_expression") or "").strip()
        if _is_safe_c_scalar_expression(value):
            return value
    return None


def _stub_call_count_expectations(case: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for setup in case.get("stub_setups", []):
        if setup.get("setup_kind") != "call_count_observation" or setup.get("review_required"):
            continue
        value = str(setup.get("value_expression") or "").strip()
        if _is_safe_c_integer_expression(value):
            result[sanitize_identifier(setup.get("stub_name"))] = value
    return result


def _is_safe_c_integer_expression(value: str) -> bool:
    return re.fullmatch(r"[-+]?(?:0[xX][0-9A-Fa-f]+|[0-9]+)[uUlL]*", value) is not None


def _is_safe_c_scalar_expression(value: str) -> bool:
    return _is_safe_c_integer_expression(value) or re.fullmatch(r"[A-Za-z_]\w*", value) is not None


def _is_safe_c_string_expression(value: str) -> bool:
    return re.fullmatch(r'L?"(?:[^"\\]|\\.)*"', value) is not None


def _needs_string_compare(test_case_design: dict[str, Any]) -> bool:
    for case in test_case_design.get("test_cases", []):
        for observation in case.get("expected_observations", []):
            if observation.get("observation_kind") == "char_array_string":
                return True
    return False


def _extern_global_declarations(globals_payload: dict[str, Any], test_case_design: dict[str, Any]) -> list[str]:
    targets = _global_observation_targets(test_case_design)
    if not targets:
        return []
    declarations_by_name = {_optional_identifier(item.get("name")): item for item in globals_payload.get("file_scope_declarations", []) if _optional_identifier(item.get("name"))}
    access_declarations: dict[str, dict[str, Any]] = {}
    static_targets: set[str] = set()
    for access in globals_payload.get("global_accesses", []):
        name = _optional_identifier(access.get("name"))
        if not name:
            continue
        declaration = access.get("related_declaration") or declarations_by_name.get(name) or {}
        if _is_static_global(access, declaration):
            static_targets.add(name)
            continue
        if name in targets and name not in access_declarations:
            access_declarations[name] = declaration
    lines: list[str] = []
    for name in sorted(targets):
        if name in static_targets:
            continue
        declaration = access_declarations.get(name) or declarations_by_name.get(name) or {}
        type_raw = _global_type_raw(declaration)
        lines.append(f"extern {type_raw} {name};")
    return lines


def _global_observation_targets(test_case_design: dict[str, Any]) -> set[str]:
    targets: set[str] = set()
    for case in test_case_design.get("test_cases", []):
        for observation in case.get("expected_observations", []):
            if observation.get("observation_kind") != "global_value":
                continue
            target = _optional_identifier(observation.get("target_name"))
            if target:
                targets.add(target)
    return targets


def _is_static_global(access: dict[str, Any], declaration: dict[str, Any]) -> bool:
    scope = access.get("scope") or declaration.get("scope")
    storage_class = declaration.get("storage_class")
    return scope == "file_static" or storage_class == "static"


def _global_type_raw(declaration: dict[str, Any]) -> str:
    type_raw = str(declaration.get("type_raw") or "int").strip()
    type_raw = re.sub(r"\b(?:extern|static)\b", "", type_raw).strip()
    return re.sub(r"\s+", " ", type_raw) or "int"


def _expected_observation_assertions(case: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for observation in case.get("expected_observations", []):
        kind = observation.get("observation_kind")
        target = _optional_identifier(observation.get("target_name"))
        if kind == "global_value" and target:
            expected = _c_expression(observation.get("expected_expression"), f"TBD_EXPECTED_GLOBAL_{target.upper()}")
            lines.append(f"    UTR_ASSERT_EQ_INT({expected}, {target});")
        elif kind == "char_array_string" and target:
            expected = _c_string_expression(observation.get("expected_expression"), f"TBD_EXPECTED_STRING_{target.upper()}")
            lines.append(f"    UTR_ASSERT_TRUE(strcmp({target}, {expected}) == 0);")
    return lines


def _optional_identifier(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return ""
    return sanitize_identifier(str(value))


def _c_expression(value: Any, placeholder: str) -> str:
    if value is None:
        return placeholder
    text = str(value).strip()
    return text or placeholder


def _c_string_expression(value: Any, placeholder: str) -> str:
    if value is None:
        return placeholder
    text = str(value).strip()
    if not text:
        return placeholder
    if text.startswith('"') or text.startswith("L\"") or text.startswith("TBD_EXPECTED_STRING_"):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _safe_c_value(value: Any) -> str:
    if value is None:
        raise ValueError("A reviewed C value is required.")
    text = str(value).strip()
    if text == "NULL":
        return "NULL"
    if _is_safe_c_scalar_expression(text):
        return text
    raise ValueError(f"C value cannot be represented without review: {text}")


def _signature_parameters(function_payload: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = []
    for item in function_payload.get("parameters", []):
        if item.get("is_void") or item.get("is_variadic"):
            continue
        name = sanitize_identifier(item.get("name"), f"arg{item.get('index', len(parameters))}")
        type_info = item.get("type", {})
        type_raw = type_info.get("raw") or "int"
        if type_info.get("is_array"):
            array_size = (type_info.get("array_dimensions") or ["1"])[0] or "1"
            parameters.append(
                {
                    "name": name,
                    "type_raw": f"{type_raw} {name}[{array_size}]",
                    "base_type": type_info.get("base_type") or type_raw,
                    "array_base_type": type_raw,
                    "array_size": array_size,
                    "is_array": True,
                    "pointer_level": 0,
                    "bridge_kind": type_info.get("bridge_kind") or item.get("bridge_kind") or "unresolved",
                }
            )
            continue
        parameters.append(
            {
                "name": name,
                "type_raw": type_raw,
                "base_type": type_info.get("base_type") or "int",
                "is_array": False,
                "pointer_level": int(type_info.get("pointer_level") or 0),
                "bridge_kind": type_info.get("bridge_kind") or item.get("bridge_kind") or "unresolved",
            }
        )
    return parameters


def _signature_parameter_list(parameters: list[dict[str, Any]]) -> str:
    if not parameters:
        return "void"
    return ", ".join(_signature_parameter_declaration(parameter) for parameter in parameters)


def _signature_parameter_declaration(parameter: dict[str, Any]) -> str:
    type_raw = str(parameter["type_raw"])
    name = str(parameter["name"])
    if parameter.get("is_array") or re.search(rf"\b{re.escape(name)}\b", type_raw):
        return type_raw
    return f"{type_raw} {name}"


def _public_parameter_list(parameters: list[dict[str, Any]]) -> str:
    if not parameters:
        return "void"
    return ", ".join(f"{_public_type_for_parameter(parameter)} {parameter['name']}" for parameter in parameters)


def _public_type_for_parameter(parameter: dict[str, Any]) -> str:
    if int(parameter.get("pointer_level") or 0) > 0 or parameter.get("is_array"):
        return "void *"
    raw = _compact_type(parameter.get("type_raw"))
    return raw or "int"


def _public_value_type(type_raw: Any, bridge_kind: Any = None) -> str:
    compact = _compact_type(type_raw)
    if bridge_kind in {"scalar", "aggregate", "unresolved"} and compact:
        return compact
    return compact if compact in _SCALAR_BASE_TYPES or compact in _SCALAR_TYPEDEFS else (compact or "int")


def _public_return_type(raw_return_type: Any, bridge_kind: str = "unresolved") -> str:
    raw = _compact_type(raw_return_type)
    if raw == "void":
        return "void"
    if "*" in raw:
        return "void *"
    if bridge_kind in {"scalar", "aggregate", "unresolved"} and raw:
        return raw
    return raw if raw in _SCALAR_PUBLIC_TYPES else (raw or "int")


def _public_prototype_needs_headers(
    raw_return_type: str,
    return_bridge_kind: str,
    parameters: list[dict[str, Any]],
) -> bool:
    return_type = _compact_type(raw_return_type)
    if return_type not in {"", "void"} and "*" not in return_type:
        if return_bridge_kind != "unresolved" or return_type not in _SCALAR_PUBLIC_TYPES:
            if return_type not in _SCALAR_PUBLIC_TYPES:
                return True
    for parameter in parameters:
        if int(parameter.get("pointer_level") or 0) > 0 or parameter.get("is_array"):
            continue
        raw = _compact_type(parameter.get("type_raw"))
        if raw and raw not in _SCALAR_PUBLIC_TYPES:
            return True
    return False


def _target_argument_cast(parameter: dict[str, Any]) -> str:
    name = parameter["name"]
    raw_type = str(parameter.get("type_raw") or "int").strip()
    if int(parameter.get("pointer_level") or 0) > 0 or parameter.get("is_array"):
        return f"({raw_type}){name}"
    public_type = _public_type_for_parameter(parameter)
    if public_type != raw_type:
        return f"({raw_type}){name}"
    return name


def _is_scalar_type(type_raw: Any) -> bool:
    compact = _compact_type(type_raw)
    if not compact:
        return True
    if "*" in compact:
        return True
    if compact in _SCALAR_BASE_TYPES:
        return True
    if compact in _SCALAR_TYPEDEFS:
        return True
    if compact.endswith("_t"):
        return True
    if compact.startswith("enum "):
        return True
    if compact.startswith("struct ") or compact.startswith("union "):
        return False
    return False


def _compact_type(type_raw: Any) -> str:
    text = str(type_raw or "").strip()
    text = text.replace("const ", "").replace("volatile ", "")
    return " ".join(text.split())


def _return_type(function_payload: dict[str, Any]) -> str:
    return_type = function_payload.get("return_type", {})
    raw = return_type.get("raw") or return_type.get("normalized") or "int"
    return str(raw).strip() or "int"


def _build_hints(source_path: Path, stubs: list[StubSkeleton], tests: list[TestSkeleton]) -> list[BuildHint]:
    hints = [
        BuildHint(
            hint_id="BH_TARGET_SOURCE_001",
            hint_kind="target_source_required",
            message="Target source file must be included in the build workspace.",
            related_file=source_path if source_path.as_posix() else None,
            severity="info",
        ),
        BuildHint(
            hint_id="BH_VC6_C90_001",
            hint_kind="vc6_c90_constraint",
            message="Generated C files are written as CP932 C90-compatible skeletons.",
            severity="info",
        ),
    ]
    if stubs:
        hints.append(
            BuildHint(
                hint_id="BH_STUB_SOURCE_001",
                hint_kind="stub_source_required",
                message="Generated stub sources must be compiled with the harness.",
                severity="info",
            )
        )
    if tests:
        hints.append(
            BuildHint(
                hint_id="BH_TEST_SOURCE_001",
                hint_kind="test_source_required",
                message="Generated test source must be compiled with the runner.",
                severity="info",
            )
        )
    return hints
