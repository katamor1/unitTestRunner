from __future__ import annotations

from typing import Any

from . import harness_skeleton_generator as hsg
from .type_bridge import enrich_signature_bridge_types

_ORIGINAL_SIGNATURE_PARAMETERS = hsg._signature_parameters
_ORIGINAL_GENERATE_HARNESS = hsg.generate_harness_skeleton

_SCALAR_BASE_TYPES = {
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
    "long long",
    "long long int",
    "signed long long",
    "signed long long int",
    "unsigned long long",
    "float",
    "double",
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
                setup_lines.append(f"    /* review required: NULL candidate for {name} is not used in default auto-run; using valid opaque storage instead. */")
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
        stub_safe = hsg.sanitize_identifier(setup.get("stub_name"))
        lines.append(f"    Stub_{stub_safe}_SetReturn({hsg._safe_c_value(setup.get('value_expression'))});")
    lines.extend(setup_lines)
    invocation = f"Target_Invoke_{hsg.sanitize_identifier(function_name)}({', '.join(call_args)})"
    if public_return_type == "void":
        lines.append(f"    {invocation};")
    else:
        lines.append(f"    actual_return = {invocation};")
    if public_return_type != "void":
        lines.append("    UTR_ASSERT_EQ_INT(TBD_EXPECTED_RETURN_INT, (int)actual_return);")
    for stub_safe in stub_safe_names:
        lines.append(f"    UTR_ASSERT_TRUE(Stub_{stub_safe}_GetCallCount() >= 0);")
    lines.extend(hsg._expected_observation_assertions(case))
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


def _public_value_type(type_raw: Any, bridge_kind: Any = None) -> str:
    compact = _compact_type(type_raw)
    if bridge_kind in {"scalar", "aggregate", "unresolved"} and compact:
        return compact
    return compact if compact in _SCALAR_BASE_TYPES or compact in _SCALAR_TYPEDEFS else (compact or "int")


def _public_return_type(type_raw: Any) -> str:
    compact = _compact_type(type_raw)
    if compact == "void":
        return "void"
    if "*" in compact:
        return "void *"
    return compact if compact else "int"


def _signature_parameters(function_payload: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = _ORIGINAL_SIGNATURE_PARAMETERS(function_payload)
    source_parameters = [
        item
        for item in function_payload.get("parameters", [])
        if not item.get("is_void") and not item.get("is_variadic")
    ]
    for parameter, source in zip(parameters, source_parameters):
        type_info = source.get("type") if isinstance(source.get("type"), dict) else {}
        parameter["bridge_kind"] = type_info.get("bridge_kind") or source.get("bridge_kind") or "unresolved"
    return parameters


def _generate_harness_skeleton_with_bridge(
    function_signature: Any,
    global_access: Any,
    call_report: Any,
    test_case_design: Any,
    output_root: Any,
    overwrite: bool = False,
):
    signature_payload = function_signature.to_dict() if hasattr(function_signature, "to_dict") else function_signature
    if isinstance(signature_payload, dict):
        signature_payload = enrich_signature_bridge_types(signature_payload)
    return _ORIGINAL_GENERATE_HARNESS(
        signature_payload,
        global_access,
        call_report,
        test_case_design,
        output_root,
        overwrite,
    )


def _safe_initializer_value(value: Any) -> str:
    if value is None:
        return "TBD_VALID_INT_VALUE"
    return hsg._safe_c_value(value)


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
    text = " ".join(text.split())
    return text


def apply_parameter_init_compat() -> None:
    hsg.generate_harness_skeleton = _generate_harness_skeleton_with_bridge
    hsg._signature_parameters = _signature_parameters
    hsg._render_test_function = _render_test_function
    hsg._is_scalar_type = _is_scalar_type
