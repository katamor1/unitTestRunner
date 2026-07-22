from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from unit_test_runner.encoding import decode_bytes_auto
from unit_test_runner.c_analyzer.analysis_common import split_top_level
from unit_test_runner.c_analyzer.masker import mask_source_text

from .models import ResolvedParameter, ResolvedSignature

_CALLING_CONVENTIONS = ("__stdcall", "__cdecl", "__fastcall", "WINAPI", "CALLBACK", "PASCAL")
_STORAGE_CLASSES = {"extern", "EXTERN", "static", "inline", "__inline", "register", "auto"}
_TYPE_KEYWORDS = {
    "void", "char", "short", "int", "long", "float", "double", "signed", "unsigned",
    "const", "volatile", "struct", "union", "enum", "__stdcall", "__cdecl", "__fastcall",
    "WINAPI", "CALLBACK", "PASCAL",
}

_BASIC_TYPE_WORDS = {"void", "char", "short", "int", "long", "float", "double", "signed", "unsigned", "_Bool"}
_QUALIFIERS = {"const", "volatile"}
_FUNCTION_POINTER_TYPE = "<function-pointer>"


@dataclass
class _SignatureCandidate:
    source: Path
    is_definition: bool
    return_type: str
    return_type_canonical: str
    return_type_category: str
    calling_convention: str | None
    parameters: list[ResolvedParameter]
    prototype: str

    def compatibility_key(self) -> tuple[Any, ...]:
        convention = None if self.calling_convention in {None, "__cdecl"} else self.calling_convention
        return (
            self.return_type_canonical,
            convention,
            tuple(((item.canonical_type or _normalize_type(item.type_raw)), item.is_variadic) for item in self.parameters),
        )


@dataclass
class DependencySignatureCatalog:
    workspace_root: Path
    declaration_candidates: dict[str, list[_SignatureCandidate]]
    definition_candidates: dict[str, list[_SignatureCandidate]]


def build_dependency_signature_catalog(
    callees: Iterable[str],
    *,
    workspace_root: Path | str,
    target_source: Path | str,
    reachable_headers: Iterable[Path | str],
    project_headers: Iterable[Path | str],
    project_sources: Iterable[Path | str],
) -> DependencySignatureCatalog:
    root = Path(workspace_root).resolve()
    requested = list(dict.fromkeys(str(callee) for callee in callees if str(callee)))
    reachable = _unique_paths(reachable_headers)
    project_candidates = _unique_paths(project_headers)
    headers = [*reachable, *[path for path in project_candidates if path not in reachable]]
    sources = _unique_paths([target_source, *project_sources])
    candidate_paths = [*headers, *[path for path in sources if path not in headers]]
    typedefs = _collect_typedefs(candidate_paths)
    declarations = {callee: [] for callee in requested}
    definitions = {callee: [] for callee in requested}
    requested_set = set(requested)
    header_set = set(headers)
    source_set = set(sources)
    for path in candidate_paths:
        found = _find_requested_signature_candidates(
            path,
            requested_set,
            allow_declarations=path in header_set,
            allow_definitions=path in source_set,
            typedefs=typedefs,
        )
        for callee, candidate in found:
            target = definitions if candidate.is_definition else declarations
            target[callee].append(candidate)
    return DependencySignatureCatalog(root, declarations, definitions)


def resolve_dependency_signature_from_catalog(
    callee: str,
    *,
    catalog: DependencySignatureCatalog,
    calls: list[dict[str, Any]],
) -> ResolvedSignature:
    declaration_candidates = catalog.declaration_candidates.get(callee, [])
    definition_candidates = catalog.definition_candidates.get(callee, [])
    return _resolve_signature_candidates(
        callee,
        root=catalog.workspace_root,
        declaration_candidates=declaration_candidates,
        definition_candidates=definition_candidates,
        calls=calls,
    )


def resolve_dependency_signature(
    callee: str,
    *,
    workspace_root: Path | str,
    target_source: Path | str,
    reachable_headers: Iterable[Path | str],
    project_headers: Iterable[Path | str] = (),
    project_sources: Iterable[Path | str] = (),
    calls: list[dict[str, Any]],
) -> ResolvedSignature:
    catalog = build_dependency_signature_catalog(
        [callee],
        workspace_root=workspace_root,
        target_source=target_source,
        reachable_headers=reachable_headers,
        project_headers=project_headers,
        project_sources=project_sources,
    )
    return resolve_dependency_signature_from_catalog(callee, catalog=catalog, calls=calls)


def _resolve_signature_candidates(
    callee: str,
    *,
    root: Path,
    declaration_candidates: list[_SignatureCandidate],
    definition_candidates: list[_SignatureCandidate],
    calls: list[dict[str, Any]],
) -> ResolvedSignature:
    candidates = declaration_candidates + definition_candidates
    if candidates:
        keys: dict[tuple[Any, ...], list[_SignatureCandidate]] = {}
        for candidate in candidates:
            keys.setdefault(candidate.compatibility_key(), []).append(candidate)
        if len(keys) != 1:
            conflicts = [
                f"{_relative(path_candidate.source, root)}: {path_candidate.prototype}"
                for path_candidate in candidates
            ]
            return ResolvedSignature(
                resolution="review_required",
                conflicts=["Conflicting dependency declarations or definitions were found.", *conflicts],
                confidence="low",
            )
        selected = declaration_candidates[0] if declaration_candidates else definition_candidates[0]
        declaration = declaration_candidates[0] if declaration_candidates else None
        definition = definition_candidates[0] if definition_candidates else None
        conflicts: list[str] = []
        if any(parameter.is_variadic for parameter in selected.parameters):
            conflicts.append("Variadic dependency signatures require manual review.")
        if any(parameter.type_category == "function_pointer" for parameter in selected.parameters):
            conflicts.append("Function-pointer parameters require manual review.")
        if any(parameter.type_category == "unknown" for parameter in selected.parameters):
            conflicts.append("An unresolved parameter typedef requires manual review.")
        if selected.return_type_category == "aggregate":
            conflicts.append("Aggregate return values require manual review before dispatcher generation.")
        elif selected.return_type_category in {"function_pointer", "unknown"}:
            conflicts.append("The dependency return type could not be emitted safely.")
        resolution = "review_required" if conflicts else "exact"
        return ResolvedSignature(
            resolution=resolution,
            return_type_raw=selected.return_type,
            return_type_canonical=selected.return_type_canonical,
            return_type_category=selected.return_type_category,
            calling_convention=selected.calling_convention,
            parameters=selected.parameters,
            prototype=selected.prototype,
            declaration_source=_relative(declaration.source, root) if declaration else None,
            definition_source=_relative(definition.source, root) if definition else None,
            conflicts=conflicts,
            confidence="high" if resolution == "exact" else "low",
        )

    inferred = _infer_simple_signature(callee, calls)
    if inferred is not None:
        return inferred
    return ResolvedSignature(
        resolution="review_required",
        conflicts=["No compatible prototype or definition was found, and the call expression is not safe to infer."],
        confidence="low",
    )


def reachable_header_paths(source_digest: dict[str, Any]) -> list[Path]:
    result: list[Path] = []
    for include in source_digest.get("preprocessor", {}).get("includes", []):
        for raw in include.get("resolved_candidates", []):
            path = Path(raw)
            if path.is_file() and path not in result:
                result.append(path)
    return result


def _find_requested_signature_candidates(
    path: Path,
    callees: set[str],
    *,
    allow_declarations: bool,
    allow_definitions: bool,
    typedefs: dict[str, str],
) -> list[tuple[str, _SignatureCandidate]]:
    try:
        text = decode_bytes_auto(path.read_bytes())
    except OSError:
        return []
    result: list[tuple[str, _SignatureCandidate]] = []
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", text):
        callee = match.group(1)
        if callee not in callees:
            continue
        name_start = match.start(1)
        if name_start > 0 and text[name_start - 1] == "*":
            continue
        open_paren = text.find("(", match.start())
        close_paren = _matching_paren(text, open_paren)
        if close_paren == -1:
            continue
        next_index = _next_nonspace(text, close_paren + 1)
        if next_index >= len(text):
            continue
        terminator = text[next_index]
        is_definition = terminator == "{"
        if is_definition and not allow_definitions:
            continue
        if not is_definition and (terminator != ";" or not allow_declarations):
            continue
        start = _signature_start(text, name_start)
        prefix = _strip_preprocessor(text[start:name_start]).strip()
        if not _looks_like_type_prefix(prefix):
            continue
        return_type, convention = _return_type_and_convention(prefix)
        if not return_type:
            continue
        parameter_text = text[open_paren + 1 : close_paren]
        parameters = _parse_parameters(parameter_text, typedefs)
        return_canonical, return_category = _canonical_type(return_type, typedefs)
        prototype = _render_prototype(return_type, convention, callee, parameters)
        result.append(
            (
                callee,
                _SignatureCandidate(
                    path,
                    is_definition,
                    return_type,
                    return_canonical,
                    return_category,
                    convention,
                    parameters,
                    prototype,
                ),
            )
        )
    return result


def _matching_paren(text: str, open_index: int) -> int:
    depth = 0
    state = "normal"
    quote = ""
    index = open_index
    while index < len(text):
        current = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if state == "normal":
            if current == "/" and nxt == "*":
                state = "block_comment"
                index += 2
                continue
            if current == "/" and nxt == "/":
                state = "line_comment"
                index += 2
                continue
            if current in {'"', "'"}:
                state = "literal"
                quote = current
            elif current == "(":
                depth += 1
            elif current == ")":
                depth -= 1
                if depth == 0:
                    return index
        elif state == "block_comment" and current == "*" and nxt == "/":
            state = "normal"
            index += 2
            continue
        elif state == "line_comment" and current == "\n":
            state = "normal"
        elif state == "literal":
            if current == "\\":
                index += 2
                continue
            if current == quote:
                state = "normal"
        index += 1
    return -1


def _signature_start(text: str, name_start: int) -> int:
    boundary = max(text.rfind(";", 0, name_start), text.rfind("}", 0, name_start), text.rfind("{", 0, name_start))
    start = boundary + 1
    while start < name_start and text[start].isspace():
        start += 1
    return start


def _next_nonspace(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _strip_preprocessor(prefix: str) -> str:
    lines = [line for line in prefix.splitlines() if not line.lstrip().startswith("#")]
    return " ".join(lines)


def _looks_like_type_prefix(prefix: str) -> bool:
    if not prefix or any(token in prefix for token in ("=", "return ", "if ", "while ", "for ")):
        return False
    return re.fullmatch(r"[A-Za-z_][\w\s\*]*", " ".join(prefix.split())) is not None


def _return_type_and_convention(prefix: str) -> tuple[str, str | None]:
    tokens = prefix.replace("*", " * ").split()
    convention = next((token for token in tokens if token in _CALLING_CONVENTIONS), None)
    filtered = [token for token in tokens if token not in _STORAGE_CLASSES and token not in _CALLING_CONVENTIONS]
    return _normalize_type(" ".join(filtered)), convention


def _parse_parameters(text: str, typedefs: dict[str, str]) -> list[ResolvedParameter]:
    stripped = text.strip()
    if not stripped or stripped == "void":
        return []
    result: list[ResolvedParameter] = []
    for index, raw in enumerate(split_top_level(stripped)):
        item = " ".join(raw.strip().split())
        if item == "...":
            result.append(ResolvedParameter(index, None, "...", 0, [], True, "...", "variadic"))
            continue
        name, type_raw = _parameter_name_and_type(item)
        normalized_type = _normalize_parameter_type(type_raw)
        qualifiers = [token for token in ("const", "volatile") if re.search(rf"\b{token}\b", normalized_type)]
        canonical, category = _canonical_type(normalized_type, typedefs)
        result.append(ResolvedParameter(index, name, normalized_type, normalized_type.count("*"), qualifiers, False, canonical, category))
    return result


def _parameter_name_and_type(raw: str) -> tuple[str | None, str]:
    if "(*" in raw.replace(" ", ""):
        match = re.search(r"\(\s*\*\s*([A-Za-z_]\w*)\s*\)", raw)
        return (match.group(1) if match else None), raw
    array_match = re.search(r"([A-Za-z_]\w*)\s*((?:\[[^\]]*\]\s*)+)$", raw)
    if array_match:
        name = array_match.group(1)
        type_part = raw[: array_match.start(1)].strip()
        return name, f"{type_part} *"
    match = re.search(r"([A-Za-z_]\w*)\s*$", raw)
    if not match:
        return None, raw
    candidate = match.group(1)
    prefix = raw[: match.start(1)].strip()
    if candidate in _TYPE_KEYWORDS or not prefix or prefix.endswith(("struct", "union", "enum")):
        return None, raw
    return candidate, prefix


def _normalize_parameter_type(type_raw: str) -> str:
    return _normalize_type(type_raw)


def _normalize_type(type_raw: str) -> str:
    text = " ".join(str(type_raw).strip().split())
    text = re.sub(r"\s*\*\s*", " *", text)
    return text.strip()


def _render_prototype(return_type: str, convention: str | None, callee: str, parameters: list[ResolvedParameter]) -> str:
    prefix = " ".join(item for item in (return_type, convention) if item)
    values = []
    for parameter in parameters:
        if parameter.is_variadic:
            values.append("...")
        elif parameter.name:
            values.append(f"{parameter.type_raw} {parameter.name}")
        else:
            values.append(parameter.type_raw)
    return f"{prefix} {callee}({', '.join(values) if values else 'void'})"


def _infer_simple_signature(callee: str, calls: list[dict[str, Any]]) -> ResolvedSignature | None:
    if not calls:
        return None
    counts = {len(call.get("arguments", [])) for call in calls}
    if len(counts) != 1:
        return None
    count = counts.pop()
    for call in calls:
        for argument in call.get("arguments", []):
            if argument.get("passing_mode_hint") != "by_value":
                return None
            if argument.get("argument_kind") not in {"literal", "parameter", "global", "local", "constant_or_macro"}:
                return None
    parameters = [ResolvedParameter(index, f"arg{index}", "int", canonical_type="int", type_category="scalar") for index in range(count)]
    return ResolvedSignature(
        resolution="compatible_inferred",
        return_type_raw="int",
        return_type_canonical="int",
        return_type_category="scalar",
        parameters=parameters,
        prototype=_render_prototype("int", None, callee, parameters),
        confidence="medium",
    )



def _collect_typedefs(paths: Iterable[Path]) -> dict[str, str]:
    typedefs: dict[str, str] = {}
    for path in paths:
        try:
            original = decode_bytes_auto(path.read_bytes())
        except OSError:
            continue
        text = mask_source_text(original, path).masked_text
        occupied: list[tuple[int, int]] = []
        for match in re.finditer(r"\btypedef\s+([^;{}]+?)\(\s*\*\s*([A-Za-z_]\w*)\s*\)\s*\([^;]*\)\s*;", text, re.DOTALL):
            typedefs[match.group(2)] = _FUNCTION_POINTER_TYPE
            occupied.append(match.span())
        for match in re.finditer(r"\btypedef\s+(struct|union|enum)\s*([A-Za-z_]\w*)?\s*\{[^{}]*\}\s*([A-Za-z_]\w*)\s*;", text, re.DOTALL):
            kind, tag, alias = match.group(1), match.group(2), match.group(3)
            typedefs[alias] = f"{kind} {tag}" if tag else f"{kind} <anonymous:{alias}>"
            occupied.append(match.span())
        for match in re.finditer(r"\btypedef\s+([^;{}]+?)\s+([A-Za-z_]\w*)\s*;", text, re.DOTALL):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            underlying = " ".join(match.group(1).split())
            alias = match.group(2)
            if underlying and alias:
                typedefs[alias] = underlying
    return typedefs


def _canonical_type(type_raw: str, typedefs: dict[str, str]) -> tuple[str, str]:
    current = _normalize_type(type_raw)
    seen: set[str] = set()
    while True:
        tokens = re.findall(r"[A-Za-z_]\w*", current)
        alias = next((token for token in tokens if token in typedefs and token not in seen), None)
        if alias is None:
            break
        seen.add(alias)
        underlying = typedefs[alias]
        if underlying == _FUNCTION_POINTER_TYPE:
            return _FUNCTION_POINTER_TYPE, "function_pointer"
        current = re.sub(rf"\b{re.escape(alias)}\b", underlying, current, count=1)
        current = _normalize_type(current)
    compact = current.replace(" ", "")
    if current == "void":
        return current, "void"
    if _FUNCTION_POINTER_TYPE in current or "(*" in compact:
        return current, "function_pointer"
    if "*" in current:
        return current, "pointer"
    words = [word for word in re.findall(r"[A-Za-z_]\w*", current) if word not in _QUALIFIERS]
    if words and words[0] in {"struct", "union"}:
        return current, "aggregate"
    if words and words[0] == "enum":
        return current, "scalar"
    if words and all(word in _BASIC_TYPE_WORDS for word in words):
        return current, "scalar"
    return current, "unknown"

def _unique_paths(values: Iterable[Path | str]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        path = Path(value)
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = resolved.as_posix().lower()
        if key not in seen and resolved.exists():
            seen.add(key)
            result.append(resolved)
    return result


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return path
