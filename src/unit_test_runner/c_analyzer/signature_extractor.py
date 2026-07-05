from __future__ import annotations

import re

from .analysis_common import (
    BASIC_TYPE_WORDS,
    CALLING_CONVENTIONS,
    STORAGE_CLASSES,
    TYPE_QUALIFIERS,
    find_matching_char,
    normalize_space,
    selected_candidate,
    slice_range,
    split_top_level,
)
from .signature_models import FunctionSignature, ParameterInfo, SignatureWarning, TypeInfo
from .source_models import SourceDigest


def extract_signature(digest: SourceDigest, function_location: object) -> FunctionSignature:
    candidate = selected_candidate(function_location)
    header_raw = slice_range(digest.source.text, candidate.header_range).strip()
    normalized = normalize_space(header_raw)
    warnings: list[SignatureWarning] = []
    function_name = candidate.name
    name_match = re.search(rf"\b{re.escape(function_name)}\b\s*\(", header_raw)
    if not name_match:
        return _malformed_signature(digest, candidate, header_raw, normalized, function_name, "signature_not_found", "Function name was not found in header range.")

    open_paren = header_raw.find("(", name_match.start())
    close_paren = find_matching_char(header_raw, open_paren)
    if close_paren == -1:
        return _malformed_signature(digest, candidate, header_raw, normalized, function_name, "malformed_parameter_list", "Parameter list parenthesis is not balanced.")

    return_side = header_raw[: name_match.start()].strip()
    params_raw = header_raw[open_paren + 1 : close_paren].strip()
    knr_block = header_raw[close_paren + 1 :].strip()
    style = "knr" if knr_block else "ansi"
    storage, calling, return_type = _parse_return_type(return_side, warnings, candidate.header_range.start.line)
    parameters = _parse_parameters(params_raw, style, knr_block, warnings)
    status = "parsed" if not any(warning.code in {"malformed_parameter_list", "signature_not_found"} for warning in warnings) else "partial"
    confidence = "medium" if style == "knr" or warnings else "high"
    return FunctionSignature(
        function_name=function_name,
        source_path=digest.source.path,
        source_sha256=digest.source.sha256,
        status=status,
        style=style,
        confidence=confidence,
        signature_range=candidate.header_range,
        header_text_raw=header_raw,
        header_text_normalized=normalized,
        storage_class=storage,
        calling_convention=calling,
        return_type=return_type,
        parameters=parameters,
        warnings=warnings,
    )


def _malformed_signature(digest: SourceDigest, candidate: object, raw: str, normalized: str, function_name: str, code: str, message: str) -> FunctionSignature:
    warning = SignatureWarning(code, message)
    return FunctionSignature(
        function_name=function_name,
        source_path=digest.source.path,
        source_sha256=digest.source.sha256,
        status="malformed",
        style="unknown",
        confidence="low",
        signature_range=candidate.header_range,
        header_text_raw=raw,
        header_text_normalized=normalized,
        storage_class=None,
        calling_convention=None,
        return_type=classify_type("", []),
        parameters=[],
        warnings=[warning],
    )


def _parse_return_type(return_side: str, warnings: list[SignatureWarning], line_number: int) -> tuple[str | None, str | None, TypeInfo]:
    tokens = re.findall(r"\*+|[A-Za-z_]\w*", return_side)
    storage = next((token for token in tokens if token in STORAGE_CLASSES), None)
    calling = next((token for token in tokens if token in CALLING_CONVENTIONS), None)
    if calling:
        warnings.append(SignatureWarning("calling_convention_detected", f"Calling convention detected: {calling}", line_number=line_number, text=calling))
    type_parts = [token for token in tokens if token not in STORAGE_CLASSES and token not in CALLING_CONVENTIONS]
    return storage, calling, classify_type(" ".join(type_parts), warnings)


def _parse_parameters(params_raw: str, style: str, knr_block: str, warnings: list[SignatureWarning]) -> list[ParameterInfo]:
    if not params_raw or params_raw.strip() == "void":
        return []
    if style == "knr":
        return _parse_knr_parameters(params_raw, knr_block, warnings)
    parameters: list[ParameterInfo] = []
    for index, part in enumerate(split_top_level(params_raw), start=0):
        parameters.append(_parse_parameter(index, part, warnings))
    return parameters


def _parse_knr_parameters(params_raw: str, knr_block: str, warnings: list[SignatureWarning]) -> list[ParameterInfo]:
    declarations: dict[str, str] = {}
    for declaration in [item.strip() for item in knr_block.split(";") if item.strip()]:
        for match in re.finditer(r"(?P<type>.+?)(?P<name>[A-Za-z_]\w*)\s*(?:,|$)", declaration):
            declarations[match.group("name")] = declaration
    parameters = []
    for index, name in enumerate([item.strip() for item in split_top_level(params_raw) if item.strip()], start=0):
        raw = declarations.get(name)
        if raw is None:
            warning = SignatureWarning("old_style_parameter_unresolved", f"Old-style parameter declaration was not found: {name}", text=name)
            warnings.append(warning)
            parameters.append(ParameterInfo(index, name, classify_type("", warnings), name, "unknown", confidence="low", warnings=[warning]))
            continue
        parameters.append(_parse_parameter(index, raw, warnings, forced_name=name, confidence="medium"))
    return parameters


def _parse_parameter(index: int, raw: str, warnings: list[SignatureWarning], forced_name: str | None = None, confidence: str = "high") -> ParameterInfo:
    raw = raw.strip()
    if raw == "...":
        warning = SignatureWarning("variadic_parameter_detected", "Variadic parameter detected.", text=raw)
        warnings.append(warning)
        type_info = classify_type("...", warnings, confidence="medium")
        return ParameterInfo(index, None, type_info, raw, "unknown", is_variadic=True, confidence="medium", warnings=[warning])

    parameter_warnings: list[SignatureWarning] = []
    function_pointer_match = re.search(r"\(\s*\*\s*(?P<name>[A-Za-z_]\w*)\s*\)", raw)
    array_dimensions = re.findall(r"\[([^\]]*)\]", raw)
    if function_pointer_match:
        name = function_pointer_match.group("name")
        warning = SignatureWarning("function_pointer_parameter", f"Function pointer parameter detected: {name}", text=raw)
        warnings.append(warning)
        parameter_warnings.append(warning)
        type_info = classify_type(raw, warnings, is_function_pointer=True, confidence="medium")
        return ParameterInfo(index, name, type_info, raw, "input", confidence="medium", warnings=parameter_warnings)

    name = forced_name or _last_identifier(raw)
    if name is None:
        warning = SignatureWarning("unnamed_parameter", "Parameter name could not be determined.", text=raw)
        warnings.append(warning)
        parameter_warnings.append(warning)
    type_raw = _remove_name(raw, name) if name else raw
    type_info = classify_type(type_raw, warnings, array_dimensions=array_dimensions, confidence=confidence)
    direction = _direction_hint(name, type_info)
    if type_info.is_array:
        warning = SignatureWarning("array_parameter_detected", f"Array parameter detected: {name or raw}", text=raw)
        warnings.append(warning)
        parameter_warnings.append(warning)
    return ParameterInfo(index, name, type_info, raw, direction, confidence=confidence, warnings=parameter_warnings)


def classify_type(
    raw: str,
    warnings: list[SignatureWarning],
    *,
    array_dimensions: list[str] | None = None,
    is_function_pointer: bool = False,
    confidence: str = "high",
) -> TypeInfo:
    raw = raw.strip()
    array_dimensions = array_dimensions or re.findall(r"\[([^\]]*)\]", raw)
    normalized = normalize_space(raw.replace("[", " [").replace("]", "] "))
    pointer_level = raw.count("*")
    words = re.findall(r"\b[A-Za-z_]\w*\b", raw)
    storage = next((word for word in words if word in STORAGE_CLASSES), None)
    qualifiers = [word for word in words if word in TYPE_QUALIFIERS]
    type_words = [word for word in words if word not in STORAGE_CLASSES and word not in TYPE_QUALIFIERS and word not in CALLING_CONVENTIONS]
    if type_words[:1] in (["struct"], ["union"], ["enum"]) and len(type_words) >= 2:
        base_type = " ".join(type_words[:2])
    elif type_words:
        base_type = " ".join(type_words)
    else:
        base_type = None
    is_struct = bool(type_words[:1] == ["struct"])
    is_union = bool(type_words[:1] == ["union"])
    is_enum = bool(type_words[:1] == ["enum"])
    is_typedef_like = bool(base_type and not is_struct and not is_union and not is_enum and not all(word in BASIC_TYPE_WORDS for word in type_words))
    if is_typedef_like:
        warnings.append(SignatureWarning("typedef_unresolved", f"Typedef-like type was not resolved: {base_type}", text=raw))
    return TypeInfo(
        raw=raw,
        normalized=normalized,
        base_type=base_type,
        qualifiers=qualifiers,
        storage_class=storage,
        pointer_level=pointer_level,
        is_const_pointer=("const" in qualifiers if pointer_level else None),
        is_struct=is_struct,
        is_union=is_union,
        is_enum=is_enum,
        is_typedef_like=is_typedef_like,
        is_function_pointer=is_function_pointer,
        is_array=bool(array_dimensions),
        array_dimensions=array_dimensions,
        confidence=confidence,
    )


def _last_identifier(raw: str) -> str | None:
    without_arrays = re.sub(r"\[[^\]]*\]", "", raw)
    identifiers = [item for item in re.findall(r"\b[A-Za-z_]\w*\b", without_arrays) if item not in STORAGE_CLASSES and item not in TYPE_QUALIFIERS and item not in CALLING_CONVENTIONS and item not in BASIC_TYPE_WORDS and item not in {"struct", "union", "enum"}]
    if identifiers:
        return identifiers[-1]
    all_identifiers = re.findall(r"\b[A-Za-z_]\w*\b", without_arrays)
    return all_identifiers[-1] if len(all_identifiers) > 1 else None


def _remove_name(raw: str, name: str | None) -> str:
    if not name:
        return raw
    value = re.sub(rf"\b{re.escape(name)}\b", "", raw, count=1)
    value = re.sub(r"\[[^\]]*\]", "", value)
    return value.strip()


def _direction_hint(name: str | None, type_info: TypeInfo) -> str:
    if type_info.is_function_pointer:
        return "input"
    if type_info.is_array:
        return "input_output_candidate"
    if type_info.pointer_level:
        lower = (name or "").lower()
        if "out" in lower or "result" in lower or "buffer" in lower or lower in {"buf"}:
            return "output_candidate"
        if "const" in type_info.qualifiers:
            return "input"
        return "input_output_candidate"
    if not type_info.raw or type_info.raw == "void":
        return "none"
    return "input"
