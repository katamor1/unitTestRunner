from __future__ import annotations

import re
from pathlib import Path
from typing import Any

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


def generate_harness_skeleton(
    function_signature: Any,
    global_access: Any,
    call_report: Any,
    test_case_draft: Any,
    output_root: Path | str,
    overwrite: bool = False,
) -> HarnessSkeletonReport:
    del global_access
    output_root = Path(output_root).resolve()
    policy = HarnessGenerationPolicy(overwrite_existing=overwrite)
    signature = _payload(function_signature)
    calls = _payload(call_report)
    draft = _payload(test_case_draft)
    function_payload = signature.get("function", {})
    function_name = function_payload.get("name") or draft.get("function", {}).get("name") or "unknown_function"
    source_path = Path(signature.get("source", {}).get("path") or draft.get("source", {}).get("path") or "")
    generated_files: list[GeneratedFile] = []
    warnings: list[HarnessGenerationWarning] = []
    unresolved: list[UnresolvedPlaceholder] = []
    build_hints: list[BuildHint] = []

    _ensure_layout(output_root)
    _write_assert_files(output_root, generated_files, overwrite)
    stubs = _write_stub_files(output_root, calls, draft, generated_files, warnings, overwrite)
    tests = _write_test_files(output_root, signature, draft, stubs, generated_files, unresolved, warnings, overwrite)
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
    _write_c(output_root, generated_files, "generated/include/utr_assert.h", "assert_header", header, ["Step13"], False, overwrite)
    _write_c(output_root, generated_files, "generated/harness/utr_assert.c", "assert_source", source, ["Step13"], False, overwrite)


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
    _write_c(output_root, generated_files, "generated/include/utr_runner.h", "runner_header", header, ["Step13"], False, overwrite)
    _write_c(output_root, generated_files, "generated/harness/utr_runner.c", "runner_source", source, ["Step13"], True, overwrite)


def _write_stub_files(
    output_root: Path,
    call_report: dict[str, Any],
    draft: dict[str, Any],
    generated_files: list[GeneratedFile],
    warnings: list[HarnessGenerationWarning],
    overwrite: bool,
) -> list[StubSkeleton]:
    calls_by_id = {item.get("call_id"): item for item in call_report.get("calls", [])}
    calls_by_name = {item.get("name"): item for item in call_report.get("calls", [])}
    test_case_ids_by_stub = _test_case_ids_by_stub(draft)
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


def _test_case_ids_by_stub(draft: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for test_case in draft.get("test_cases", []):
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
    return_type = _return_type(function_payload)
    parameters = _signature_parameters(function_payload)
    prototype = f"{return_type} Target_Invoke_{sanitize_identifier(function_name)}({_signature_parameter_list(parameters)})"
    target_include = f"{source_path.stem}.h" if source_path.stem else "target_header_review_required.h"
    if function_payload.get("storage_class") == "static":
        warnings.append(
            HarnessGenerationWarning(
                code="static_target_direct_call_warning",
                message="Static target function may require an expose wrapper in Step 14 or later.",
                related_file=Path("generated/harness/target_invocation.c"),
            )
        )
    header = f"""/* generated target invocation skeleton: review required */
#ifndef TARGET_INVOCATION_H_
#define TARGET_INVOCATION_H_

{prototype};

#endif
"""
    invocation_args = ", ".join(parameter["name"] for parameter in parameters) or ""
    if return_type == "void":
        call_line = f"    {function_name}({invocation_args});"
    else:
        call_line = f"    return {function_name}({invocation_args});"
    source = f"""/* generated target invocation skeleton: review required */
#include "target_invocation.h"
#include "{target_include}"

{prototype}
{{
{call_line}
}}
"""
    _write_c(output_root, generated_files, "generated/harness/target_invocation.h", "target_invocation_header", header, [function_name], True, overwrite)
    _write_c(output_root, generated_files, "generated/harness/target_invocation.c", "target_invocation_source", source, [function_name], True, overwrite)


def _write_test_files(
    output_root: Path,
    signature: dict[str, Any],
    draft: dict[str, Any],
    stubs: list[StubSkeleton],
    generated_files: list[GeneratedFile],
    unresolved: list[UnresolvedPlaceholder],
    warnings: list[HarnessGenerationWarning],
    overwrite: bool,
) -> list[TestSkeleton]:
    function_payload = signature.get("function", {})
    function_name = function_payload.get("name") or draft.get("function", {}).get("name") or "unknown_function"
    safe_function = sanitize_identifier(function_name)
    parameters = _signature_parameters(function_payload)
    return_type = _return_type(function_payload)
    stub_names = [item.original_function_name for item in stubs]
    stub_safe_names = [sanitize_identifier(item.original_function_name) for item in stubs]
    test_skeletons: list[TestSkeleton] = []
    functions: list[str] = []
    prototypes: list[str] = []
    for index, case in enumerate(draft.get("test_cases", []), start=1):
        case_id = case.get("test_case_id") or f"TC_{safe_function}_{index:03d}"
        test_func = f"Test_{sanitize_identifier(case_id)}"
        prototypes.append(f"void {test_func}(void);")
        coverage_ids = [link.get("coverage_id", "") for link in case.get("coverage_links", []) if link.get("coverage_id")]
        related_stubs = sorted({setup.get("stub_name", "") for setup in case.get("stub_setups", []) if setup.get("stub_name")})
        placeholder_count = _count_placeholders(case)
        if placeholder_count:
            unresolved.append(
                UnresolvedPlaceholder(
                    placeholder_id=f"UP_{sanitize_identifier(case_id)}_EXPECTED",
                    placeholder_kind="expected_return",
                    name="TBD_EXPECTED_RETURN_INT",
                    related_test_case_id=case_id,
                    related_stub_name=None,
                    reason="Expected result is not determined in Step 12.",
                    suggested_action="Review generated test case and replace TBD expected values.",
                )
            )
            warnings.append(
                HarnessGenerationWarning(
                    code="expected_value_placeholder_generated",
                    message=f"Expected placeholder generated for {case_id}.",
                    related_test_case_id=case_id,
                )
            )
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
                review_required=True,
            )
        )
    if not functions:
        test_func = f"Test_TC_{safe_function}_001"
        prototypes.append(f"void {test_func}(void);")
        functions.append(_render_test_function(test_func, {}, parameters, return_type, function_name, stub_safe_names))
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
    include_lines = [
        '#include "utr_assert.h"',
        '#include "utr_runner.h"',
        '#include "target_invocation.h"',
    ]
    for stub_safe in stub_safe_names:
        include_lines.append(f'#include "stub_{stub_safe}.h"')
    source = "\n".join(
        [
            "/* generated test skeleton: review required */",
            "#define TBD_EXPECTED_RETURN_INT (0)",
            "#define TBD_VALID_INT_VALUE (0)",
            "",
            *include_lines,
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
        type_raw = parameter["type_raw"]
        call_args.append(name)
        if parameter.get("is_array"):
            declarations.append(f"    {parameter['array_base_type']} {name}[{parameter['array_size']}];")
            setup_lines.append(f"    {name}[0] = 0;")
            continue
        if parameter.get("pointer_level", 0) > 0:
            base_type = parameter.get("base_type") or "int"
            declarations.append(f"    {base_type} {name}_storage;")
            declarations.append(f"    {type_raw} {name};")
            value = assignments.get(name, {}).get("value_expression")
            if value == "NULL":
                setup_lines.append(f"    {name} = NULL;")
            else:
                setup_lines.append(f"    {name}_storage = 0;")
                setup_lines.append(f"    {name} = &{name}_storage;")
            continue
        declarations.append(f"    {type_raw} {name};")
        value = _safe_c_value(assignments.get(name, {}).get("value_expression"))
        setup_lines.append(f"    {name} = {value};")
    if return_type != "void":
        declarations.append(f"    {return_type} actual_return;")
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
    if return_type == "void":
        lines.append(f"    {invocation};")
    else:
        lines.append(f"    actual_return = {invocation};")
    if return_type != "void":
        lines.append("    UTR_ASSERT_EQ_INT(TBD_EXPECTED_RETURN_INT, actual_return);")
    for stub_safe in stub_safe_names:
        lines.append(f"    UTR_ASSERT_TRUE(Stub_{stub_safe}_GetCallCount() >= 0);")
    lines.extend(["}", ""])
    return "\n".join(lines)


def _safe_c_value(value: Any) -> str:
    if value is None:
        return "TBD_VALID_INT_VALUE"
    text = str(value).strip()
    if text == "NULL":
        return "NULL"
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        return text
    return f"0 /* candidate: {text} */"


def _count_placeholders(case: dict[str, Any]) -> int:
    count = 0
    for observation in case.get("expected_observations", []):
        expression = observation.get("expected_expression")
        if expression is None or str(expression).startswith("TBD"):
            count += 1
    return count or 1


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
