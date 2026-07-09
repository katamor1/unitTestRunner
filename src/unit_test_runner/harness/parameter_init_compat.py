from __future__ import annotations

from typing import Any

from . import harness_skeleton_generator as hsg

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
    "unsigned long long int",
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
        type_raw = parameter["type_raw"]
        call_args.append(name)
        assignment = assignments.get(name, {})
        value = assignment.get("value_expression")
        if parameter.get("is_array"):
            base_type = parameter.get("array_base_type") or type_raw
            if _is_scalar_type(base_type):
                declarations.append(f"    {base_type} {name}[{parameter['array_size']}];")
                setup_lines.append(f"    {name}[0] = {_safe_initializer_value(value)};")
            else:
                declarations.append(f"    {base_type} {name}[{parameter['array_size']}] = {{0}};")
            continue
        if int(parameter.get("pointer_level") or 0) > 0:
            base_type = parameter.get("base_type") or "int"
            if value == "NULL":
                declarations.append(f"    {type_raw} {name};")
                setup_lines.append(f"    {name} = NULL;")
            else:
                if _is_scalar_type(base_type):
                    declarations.append(f"    {base_type} {name}_storage;")
                    setup_lines.append(f"    {name}_storage = {_safe_initializer_value(value)};")
                else:
                    declarations.append(f"    {base_type} {name}_storage = {{0}};")
                declarations.append(f"    {type_raw} {name};")
                setup_lines.append(f"    {name} = &{name}_storage;")
            continue
        declarations.extend(_value_parameter_declaration_and_setup(value, name, type_raw, setup_lines))
    if return_type != "void":
        declarations.append(f"    {return_type} actual_return;")
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
    if return_type == "void":
        lines.append(f"    {invocation};")
    else:
        lines.append(f"    actual_return = {invocation};")
    if return_type != "void":
        lines.append("    UTR_ASSERT_EQ_INT(TBD_EXPECTED_RETURN_INT, actual_return);")
    for stub_safe in stub_safe_names:
        lines.append(f"    UTR_ASSERT_TRUE(Stub_{stub_safe}_GetCallCount() >= 0);")
    lines.extend(hsg._expected_observation_assertions(case))
    lines.extend(["}", ""])
    return "\n".join(lines)


def _value_parameter_declaration_and_setup(value: Any, name: str, type_raw: str, setup_lines: list[str]) -> list[str]:
    if _is_scalar_type(type_raw):
        setup_lines.append(f"    {name} = {_safe_initializer_value(value)};")
        return [f"    {type_raw} {name};"]
    if value not in (None, ""):
        setup_lines.append(f"    /* review required: non-scalar input candidate for {name}: {value} */")
    return [f"    {type_raw} {name} = {{0}};"]


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
    hsg._render_test_function = _render_test_function
    hsg._is_scalar_type = _is_scalar_type
