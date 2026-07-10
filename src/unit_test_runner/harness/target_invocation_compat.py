from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from unit_test_runner.encoding import decode_bytes_auto

from . import harness_skeleton_generator as hsg
from .c90_writer import sanitize_identifier
from .harness_models import HarnessGenerationWarning

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


def _write_target_invocation(
    output_root: Path,
    signature: dict,
    generated_files: list,
    warnings: list[HarnessGenerationWarning],
    overwrite: bool,
) -> None:
    function_payload = signature.get("function", {})
    function_name = function_payload.get("name", "unknown_function")
    source_path = Path(signature.get("source", {}).get("path") or "")
    raw_return_type = hsg._return_type(function_payload)
    parameters = hsg._signature_parameters(function_payload)
    raw_parameter_list = hsg._signature_parameter_list(parameters)
    public_return_type = _public_return_type(raw_return_type)
    public_parameter_list = _public_parameter_list(parameters)
    public_prototype = f"{public_return_type} Target_Invoke_{sanitize_identifier(function_name)}({public_parameter_list})"
    target_prototype = f"{raw_return_type} {function_name}({raw_parameter_list})"
    include_block = _include_block(_source_quote_includes(source_path))
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

{public_prototype};

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
    hsg._write_c(output_root, generated_files, "generated/harness/target_invocation.h", "target_invocation_header", header, [function_name], True, overwrite)
    hsg._write_c(output_root, generated_files, "generated/harness/target_invocation.c", "target_invocation_source", source, [function_name], True, overwrite)


def _public_parameter_list(parameters: list[dict[str, Any]]) -> str:
    if not parameters:
        return "void"
    return ", ".join(f"{_public_type_for_parameter(parameter)} {parameter['name']}" for parameter in parameters)


def _public_type_for_parameter(parameter: dict[str, Any]) -> str:
    if int(parameter.get("pointer_level") or 0) > 0 or parameter.get("is_array"):
        return "void *"
    raw = _compact_type(parameter.get("type_raw"))
    return raw if raw in _SCALAR_PUBLIC_TYPES else "int"


def _public_return_type(raw_return_type: str) -> str:
    raw = _compact_type(raw_return_type)
    if raw == "void":
        return "void"
    if "*" in raw:
        return "void *"
    return raw if raw in _SCALAR_PUBLIC_TYPES else "int"


def _target_argument_cast(parameter: dict[str, Any]) -> str:
    name = parameter["name"]
    raw_type = str(parameter.get("type_raw") or "int").strip()
    if int(parameter.get("pointer_level") or 0) > 0 or parameter.get("is_array"):
        return f"({raw_type}){name}"
    public_type = _public_type_for_parameter(parameter)
    if public_type != raw_type:
        return f"({raw_type}){name}"
    return name


def _compact_type(type_raw: Any) -> str:
    text = str(type_raw or "").strip()
    text = text.replace("const ", "").replace("volatile ", "")
    return " ".join(text.split())


def apply_target_invocation_compat() -> None:
    hsg._source_quote_includes = _source_quote_includes
    hsg._include_block = _include_block
    hsg._write_target_invocation = _write_target_invocation
