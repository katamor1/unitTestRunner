from __future__ import annotations

import re
from pathlib import Path

from unit_test_runner.encoding import decode_bytes_auto

from . import harness_skeleton_generator as hsg
from .c90_writer import sanitize_identifier
from .harness_models import HarnessGenerationWarning

_QUOTE_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)


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
    return_type = hsg._return_type(function_payload)
    parameters = hsg._signature_parameters(function_payload)
    parameter_list = hsg._signature_parameter_list(parameters)
    prototype = f"{return_type} Target_Invoke_{sanitize_identifier(function_name)}({parameter_list})"
    target_prototype = f"{return_type} {function_name}({parameter_list})"
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

{include_block}{prototype};

#endif
"""
    invocation_args = ", ".join(parameter["name"] for parameter in parameters) or ""
    if return_type == "void":
        call_line = f"    {function_name}({invocation_args});"
    else:
        call_line = f"    return {function_name}({invocation_args});"
    source = f"""/* generated target invocation skeleton: review required */
#include "target_invocation.h"

{target_prototype};

{prototype}
{{
{call_line}
}}
"""
    hsg._write_c(output_root, generated_files, "generated/harness/target_invocation.h", "target_invocation_header", header, [function_name], True, overwrite)
    hsg._write_c(output_root, generated_files, "generated/harness/target_invocation.c", "target_invocation_source", source, [function_name], True, overwrite)


def apply_target_invocation_compat() -> None:
    hsg._source_quote_includes = _source_quote_includes
    hsg._include_block = _include_block
    hsg._write_target_invocation = _write_target_invocation
