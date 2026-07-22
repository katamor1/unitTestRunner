from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from unit_test_runner.encoding import decode_bytes_auto
from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.function_locator import locate_functions
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.legacy import list_functions
from unit_test_runner.c_analyzer.object_definition_finder import find_file_scope_object_definitions
from unit_test_runner.c_analyzer.masker import mask_source_text
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest

from .models import (
    DependencyEvidence,
    DependencyPolicyEntry,
    DependencyPolicyReport,
    DependencyRewriteSite,
    ExternalObjectPolicyEntry,
)
from .signature_resolver import (
    build_dependency_signature_catalog,
    reachable_header_paths,
    resolve_dependency_signature_from_catalog,
)

_SUPPORTED_DIRECT_KINDS = {"external_function", "same_file_function", "standard_library"}
_UNSUPPORTED_KINDS = {"macro_like", "function_pointer", "member_call", "function_address_use", "unknown", "same_file_static_function", "mixed_call_forms"}
_VALID_DEPENDENCY_MODES = {"auto", "real", "stub"}
_VALID_OBJECT_MODES = {"auto", "real", "fixture"}


@dataclass
class _ImplementationSourceCache:
    root: Path
    digests: dict[Path, Any] = field(default_factory=dict)
    source_texts: dict[Path, str] = field(default_factory=dict)
    digest_failures: set[Path] = field(default_factory=set)
    function_locations: dict[Path, dict[str, Any]] = field(default_factory=dict)
    fallback_function_bodies: dict[Path, dict[str, str]] = field(default_factory=dict)
    defined_functions_by_source: dict[Path, dict[str, dict[str, object]]] = field(default_factory=dict)
    defined_function_failures: set[Path] = field(default_factory=set)

    def source_path(self, implementation_source: Path) -> Path:
        path = implementation_source if implementation_source.is_absolute() else self.root / implementation_source
        try:
            return path.resolve()
        except OSError:
            return path

    def digest(self, implementation_source: Path) -> Any | None:
        path = self.source_path(implementation_source)
        if path in self.digests:
            return self.digests[path]
        if path in self.digest_failures:
            return None
        try:
            digest = build_source_digest(path)
        except (OSError, UnicodeError, ValueError, KeyError, AttributeError):
            self.digest_failures.add(path)
            return None
        self.digests[path] = digest
        self.source_texts[path] = digest.source.text
        return digest

    def source_text(self, implementation_source: Path) -> str:
        path = self.source_path(implementation_source)
        if path in self.source_texts:
            return self.source_texts[path]
        try:
            text = decode_bytes_auto(path.read_bytes())
        except OSError:
            text = ""
        self.source_texts[path] = text
        return text

    def index_functions(self, implementation_source: Path, callees: Iterable[str]) -> None:
        path = self.source_path(implementation_source)
        requested = list(dict.fromkeys(callees))
        digest = self.digest(implementation_source)
        if digest is None:
            self.function_locations[path] = {}
            self.fallback_function_bodies[path] = _index_function_bodies(
                self.source_text(implementation_source),
                requested,
            )
            return
        self.function_locations[path] = locate_functions(digest, requested)

    def function_location(self, implementation_source: Path, callee: str) -> Any | None:
        path = self.source_path(implementation_source)
        return self.function_locations.get(path, {}).get(callee)

    def function_body(self, implementation_source: Path, callee: str) -> str | None:
        path = self.source_path(implementation_source)
        if path in self.fallback_function_bodies:
            return self.fallback_function_bodies[path].get(callee)
        location = self.function_location(implementation_source, callee)
        if location is None:
            return None
        selected = location.selected_candidate
        if selected is None:
            selected = next(
                (
                    candidate
                    for candidate in location.candidates
                    if candidate.kind == "definition" and candidate.body_range is not None
                ),
                None,
            )
        if selected is None:
            return None
        body_range = selected.body_range
        if body_range is None:
            return None
        text = self.source_text(implementation_source)
        return text[body_range.start.offset + 1 : body_range.end.offset]

    def defined_functions(self, implementation_source: Path) -> dict[str, dict[str, object]] | None:
        path = self.source_path(implementation_source)
        if path in self.defined_functions_by_source:
            return self.defined_functions_by_source[path]
        if path in self.defined_function_failures:
            return None
        try:
            defined = {item["name"]: item for item in list_functions(path)}
        except (OSError, UnicodeError, ValueError, KeyError, AttributeError):
            self.defined_function_failures.add(path)
            return None
        self.defined_functions_by_source[path] = defined
        return defined


def analyze_dependency_policy(
    *,
    workspace_root: Path | str,
    target_source: Path | str,
    source_digest: Any,
    function_signature: Any,
    global_access: Any,
    call_report: Any,
    project_sources: Iterable[Path | str],
    project_headers: Iterable[Path | str] = (),
    existing_policy: dict[str, Any] | None = None,
) -> DependencyPolicyReport:
    root = Path(workspace_root).resolve()
    target = Path(target_source).resolve()
    digest_payload = _as_dict(source_digest)
    signature_payload = _as_dict(function_signature)
    global_payload = _as_dict(global_access)
    call_payload = _as_dict(call_report)
    target_name = signature_payload.get("function", {}).get("name") or call_payload.get("function", {}).get("name") or target.stem
    sources = _unique_paths(project_sources)
    target_source_text, target_masked_text = _read_source_texts(target)
    target_body_span = _target_function_body_span(target_masked_text, target_name)
    reachable_headers = _expand_reachable_headers(root, reachable_header_paths(digest_payload))
    project_header_candidates = _expand_reachable_headers(root, _unique_paths(project_headers))
    headers = [*reachable_headers, *[path for path in project_header_candidates if path not in reachable_headers]]
    existing_dependency_modes, existing_object_modes = _existing_modes(existing_policy)
    target_globals = _target_global_names(global_payload)
    stub_tags = {item.get("name"): set(item.get("tags", [])) for item in call_payload.get("stub_candidates", [])}

    grouped_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in call_payload.get("calls", []):
        name = str(call.get("name") or "").strip()
        if name:
            grouped_calls[name].append(call)

    signature_catalog = build_dependency_signature_catalog(
        grouped_calls,
        workspace_root=root,
        target_source=target,
        reachable_headers=reachable_headers,
        project_headers=project_header_candidates,
        project_sources=sources,
    )
    resolved_signatures = {
        callee: resolve_dependency_signature_from_catalog(callee, catalog=signature_catalog, calls=calls)
        for callee, calls in grouped_calls.items()
    }
    implementation_cache = _ImplementationSourceCache(root)
    implementation_groups: dict[Path, tuple[Path, list[str]]] = {}
    for callee, signature in resolved_signatures.items():
        if signature.definition_source is None:
            continue
        path = implementation_cache.source_path(signature.definition_source)
        if path not in implementation_groups:
            implementation_groups[path] = (signature.definition_source, [])
        implementation_groups[path][1].append(callee)
    for implementation_source, callees in implementation_groups.values():
        implementation_cache.index_functions(implementation_source, callees)

    dependencies: list[DependencyPolicyEntry] = []
    for callee, calls in grouped_calls.items():
        call_kinds = {_refined_call_kind(call, target_masked_text) for call in calls}
        target_kind = next(iter(call_kinds)) if len(call_kinds) == 1 else "mixed_call_forms"
        if target_kind in _SUPPORTED_DIRECT_KINDS and _has_function_address_use(
            target_masked_text,
            target_body_span,
            callee,
            calls,
        ):
            target_kind = "function_address_use"
        configured_mode = existing_dependency_modes.get(callee, "auto")
        signature = resolved_signatures[callee]
        implementation_source = signature.definition_source
        external_link_calls = (
            _implementation_external_link_calls(implementation_cache, implementation_source, callee)
            if configured_mode != "stub" and signature.resolution in {"exact", "compatible_inferred"}
            else []
        )
        callee_globals = _callee_global_names(implementation_cache, implementation_source, callee, target_globals)
        shared_globals = sorted(target_globals.intersection(callee_globals))
        evidence = _dependency_evidence(
            callee,
            target_kind,
            calls,
            implementation_source,
            shared_globals,
            stub_tags.get(callee, set()),
            external_link_calls,
        )
        resolved_mode, review_status, warnings = _resolve_dependency_mode(
            configured_mode,
            target_kind,
            signature.resolution,
            implementation_source,
            evidence,
            external_link_calls,
        )
        rewrite_sites = []
        if target_kind in _SUPPORTED_DIRECT_KINDS and resolved_mode in {"real", "stub"} and signature.resolution in {"exact", "compatible_inferred"}:
            rewrite_sites = [_rewrite_site(call, callee) for call in calls if _rewrite_site(call, callee) is not None]
        dependencies.append(
            DependencyPolicyEntry(
                callee=callee,
                target_kind=target_kind,
                configured_mode=configured_mode,
                resolved_mode=resolved_mode,
                review_status=review_status,
                signature=signature,
                implementation_source=implementation_source,
                related_call_ids=[str(call.get("call_id") or "") for call in calls if call.get("call_id")],
                rewrite_sites=[item for item in rewrite_sites if item is not None],
                evidence=evidence,
                shared_globals=shared_globals,
                warnings=warnings,
            )
        )

    external_objects = _analyze_external_objects(
        root,
        headers,
        sources,
        global_payload,
        existing_object_modes,
    )
    warnings: list[str] = []
    for dependency in dependencies:
        warnings.extend(f"{dependency.callee}: {warning}" for warning in dependency.warnings)
    for item in external_objects:
        warnings.extend(f"{item.symbol}: {warning}" for warning in item.warnings)
    review_required = any(item.review_status == "review_required" for item in dependencies) or any(item.review_status == "review_required" for item in external_objects)
    return DependencyPolicyReport(
        source_path=_relative(target, root),
        target_function=target_name,
        status="review_required" if review_required else "resolved",
        dependencies=dependencies,
        external_objects=external_objects,
        warnings=warnings,
    )



def _read_source_texts(path: Path) -> tuple[str, str]:
    try:
        text = decode_bytes_auto(path.read_bytes())
    except OSError:
        return "", ""
    return text, mask_source_text(text, path).masked_text


def _refined_call_kind(call: dict[str, Any], masked_text: str) -> str:
    original = str(call.get("target_kind") or "unknown")
    if original in _UNSUPPORTED_KINDS:
        return original
    name = str(call.get("name") or "")
    position = call.get("name_position") or call.get("call_range", {}).get("start") or {}
    offset = _offset_from_position(masked_text, position)
    if offset is None or masked_text[offset : offset + len(name)] != name:
        return original
    before = masked_text[:offset].rstrip()
    if before.endswith("->") or before.endswith("."):
        return "member_call"
    if before.endswith("(*"):
        return "function_pointer"
    return original


def _has_function_address_use(
    masked_text: str,
    body_span: tuple[int, int] | None,
    callee: str,
    calls: list[dict[str, Any]],
) -> bool:
    if not masked_text or body_span is None:
        return False
    body_start, body_end = body_span
    direct_offsets = {
        offset
        for call in calls
        for offset in [_offset_from_position(masked_text, call.get("name_position") or call.get("call_range", {}).get("start") or {})]
        if offset is not None
    }
    for match in re.finditer(rf"\b{re.escape(callee)}\b", masked_text[body_start:body_end]):
        absolute = body_start + match.start()
        if absolute in direct_offsets:
            continue
        next_index = body_start + match.end()
        while next_index < body_end and masked_text[next_index].isspace():
            next_index += 1
        if next_index < body_end and masked_text[next_index] == "(":
            continue
        return True
    return False


def _target_function_body_span(masked_text: str, function_name: str) -> tuple[int, int] | None:
    if not masked_text or not function_name:
        return None
    for match in re.finditer(rf"\b{re.escape(function_name)}\s*\(", masked_text):
        open_paren = masked_text.find("(", match.start())
        close_paren = _matching(masked_text, open_paren, "(", ")")
        if close_paren == -1:
            continue
        brace = close_paren + 1
        while brace < len(masked_text) and masked_text[brace].isspace():
            brace += 1
        if brace >= len(masked_text) or masked_text[brace] != "{":
            continue
        close_brace = _matching(masked_text, brace, "{", "}")
        if close_brace != -1:
            return brace + 1, close_brace
    return None


def _offset_from_position(text: str, position: dict[str, Any]) -> int | None:
    line = position.get("line")
    column = position.get("column")
    if not isinstance(line, int) or not isinstance(column, int) or line < 1 or column < 1:
        return None
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    if line > len(starts):
        return None
    return starts[line - 1] + column - 1

def _dependency_evidence(
    callee: str,
    target_kind: str,
    calls: list[dict[str, Any]],
    implementation_source: Path | None,
    shared_globals: list[str],
    tags: set[str],
    external_link_calls: list[str],
) -> list[DependencyEvidence]:
    result: list[DependencyEvidence] = []
    if target_kind == "same_file_function":
        result.append(DependencyEvidence("same_source", f"{callee} is defined in the target source.", "call_report", 3))
    elif implementation_source is not None:
        result.append(DependencyEvidence("implementation_available", f"Implementation found at {implementation_source.as_posix()}.", "signature_resolver", 1))
    else:
        result.append(DependencyEvidence("implementation_missing", "No project implementation source was found.", "signature_resolver", -2))
    for name in shared_globals:
        result.append(DependencyEvidence("shared_global", f"Target and {callee} both reference {name}.", "global_access", 4))
    if external_link_calls:
        result.append(
            DependencyEvidence(
                "implementation_transitive_dependency",
                f"{callee} calls additional link dependencies: {', '.join(external_link_calls)}.",
                "implementation_call_report",
                0,
            )
        )
    pointer_coupled = False
    for call in calls:
        for argument in call.get("arguments", []):
            if argument.get("passing_mode_hint") in {"by_address", "pointer_or_array"} or argument.get("argument_kind") in {"address_of_global", "address_of_local"}:
                pointer_coupled = True
                result.append(
                    DependencyEvidence(
                        "pointer_state_coupling",
                        f"Call {call.get('call_id', '')} passes {argument.get('raw', '')} by address or pointer.",
                        "call_report",
                        3,
                    )
                )
                break
    return_used = any(call.get("return_usage", {}).get("usage_kind") not in {"ignored", "unknown", None} for call in calls)
    if return_used and not pointer_coupled and not shared_globals:
        result.append(DependencyEvidence("return_only_boundary", "Only the return value is observed; no shared state coupling was found.", "call_report", -2))
    if tags.intersection({"hardware_like", "io_like"}):
        result.append(DependencyEvidence("external_boundary_tag", f"Dependency tags indicate an I/O or hardware boundary: {', '.join(sorted(tags))}.", "call_report", -3))
    if target_kind in _UNSUPPORTED_KINDS:
        result.append(DependencyEvidence("unsupported_call_form", f"{target_kind} calls are not automatically rewritten.", "call_report", 0))
    return result


def _resolve_dependency_mode(
    configured_mode: str,
    target_kind: str,
    signature_resolution: str,
    implementation_source: Path | None,
    evidence: list[DependencyEvidence],
    external_link_calls: list[str],
) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    if configured_mode not in _VALID_DEPENDENCY_MODES:
        warnings.append(f"Unsupported configured_mode {configured_mode}; auto was used.")
        configured_mode = "auto"
    if target_kind in _UNSUPPORTED_KINDS:
        return "review_required", "review_required", [*warnings, f"{target_kind} is outside the safe direct-call rewrite scope."]
    if signature_resolution == "review_required":
        return "review_required", "review_required", [*warnings, "Dependency signature requires review before dispatcher generation."]
    if configured_mode == "stub":
        return "stub", "resolved", warnings
    if configured_mode == "real":
        if implementation_source is None and target_kind not in {"same_file_function", "standard_library"}:
            return "review_required", "review_required", [*warnings, "real mode requires a unique implementation source."]
        if external_link_calls:
            return (
                "real",
                "review_required",
                [
                    *warnings,
                    "real implementation requires additional link dependencies: "
                    + ", ".join(external_link_calls)
                    + ".",
                ],
            )
        return "real", "resolved", warnings
    if target_kind == "standard_library":
        return "real", "resolved", warnings
    score = sum(item.weight for item in evidence)
    strong_state_coupling = any(item.kind in {"shared_global", "pointer_state_coupling"} for item in evidence)
    if implementation_source is not None and strong_state_coupling and score >= 3:
        auto_mode, auto_review = "real", "resolved"
    elif implementation_source is None and score <= 1:
        auto_mode, auto_review = "stub", "resolved"
    elif score <= 0:
        auto_mode, auto_review = "stub", "resolved"
    elif implementation_source is not None and score >= 4:
        auto_mode, auto_review = "real", "resolved"
    else:
        return "review_required", "review_required", [*warnings, f"auto evidence score {score} is ambiguous."]
    if auto_mode == "real" and external_link_calls:
        return (
            "stub",
            "review_required",
            [
                *warnings,
                "auto selected a safe stub because the real implementation requires additional link dependencies: "
                + ", ".join(external_link_calls)
                + ".",
            ],
        )
    return auto_mode, auto_review, warnings


def _analyze_external_objects(
    root: Path,
    headers: list[Path],
    sources: list[Path],
    global_payload: dict[str, Any],
    existing_modes: dict[str, str],
) -> list[ExternalObjectPolicyEntry]:
    declarations = []
    for item in global_payload.get("file_scope_declarations", []):
        storage = str(item.get("storage_class") or "")
        raw = str(item.get("raw") or "")
        if storage == "extern" or re.match(r"\s*(?:extern|EXTERN)\b", raw):
            declarations.append(item)
    requested_symbols = [str(item.get("name") or "") for item in declarations]
    requested_symbols = [symbol for symbol in requested_symbols if symbol]
    declaration_headers = _declaration_header_map(requested_symbols, headers, root)
    definition_sources = _object_definition_map(requested_symbols, sources)
    result: list[ExternalObjectPolicyEntry] = []
    for declaration in declarations:
        symbol = str(declaration.get("name") or "")
        if not symbol:
            continue
        configured_mode = existing_modes.get(symbol, "auto")
        declaration_header = declaration_headers.get(symbol)
        definition_candidates = [_relative(path, root) for path in definition_sources.get(symbol, [])]
        resolved_mode, review_status, warnings = _resolve_object_mode(configured_mode, definition_candidates)
        definition_source = definition_candidates[0] if resolved_mode == "real" and len(definition_candidates) == 1 else None
        evidence = []
        if definition_source:
            evidence.append(DependencyEvidence("unique_definition", f"Unique definition found at {definition_source.as_posix()}.", "project_sources", 2))
        elif not definition_candidates:
            evidence.append(DependencyEvidence("declaration_only", "No project definition was found; a fixture object is required.", "project_sources", 0))
        else:
            evidence.append(DependencyEvidence("multiple_definitions", f"Multiple definitions found: {', '.join(path.as_posix() for path in definition_candidates)}.", "project_sources", 0))
        result.append(
            ExternalObjectPolicyEntry(
                symbol=symbol,
                type_raw=str(declaration.get("type_raw") or "int"),
                configured_mode=configured_mode,
                resolved_mode=resolved_mode,
                review_status=review_status,
                declaration_header=declaration_header,
                definition_source=definition_source,
                definition_candidates=definition_candidates,
                evidence=evidence,
                warnings=warnings,
            )
        )
    return result


def _resolve_object_mode(configured_mode: str, candidates: list[Path]) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    if configured_mode not in _VALID_OBJECT_MODES:
        configured_mode = "auto"
        warnings.append("Unsupported external-object configured mode; auto was used.")
    if configured_mode == "real":
        if len(candidates) != 1:
            return "review_required", "review_required", [*warnings, "real mode requires exactly one definition source."]
        return "real", "resolved", warnings
    if configured_mode == "fixture":
        if candidates:
            return "review_required", "review_required", [*warnings, "fixture mode would conflict with an existing product definition."]
        return "fixture", "resolved", warnings
    if len(candidates) == 1:
        return "real", "resolved", warnings
    if len(candidates) == 0:
        return "fixture", "resolved", warnings
    return "review_required", "review_required", [*warnings, "Multiple product definitions were found."]


def _implementation_external_link_calls(
    cache: _ImplementationSourceCache,
    implementation_source: Path | None,
    callee: str,
) -> list[str]:
    if implementation_source is None:
        return []
    try:
        digest = cache.digest(implementation_source)
        if digest is None:
            return []
        location = cache.function_location(implementation_source, callee)
        if location is None:
            return []
        if location.status != "found":
            return []
        signature = extract_signature(digest, location)
        global_access = analyze_global_access(digest, location, signature)
        defined_functions = cache.defined_functions(implementation_source)
        if defined_functions is None:
            return []
        call_report = analyze_calls(
            digest,
            location,
            signature,
            global_access,
            defined_functions_by_name=defined_functions,
        )
    except (OSError, UnicodeError, ValueError, KeyError, AttributeError):
        return []
    unsafe_kinds = {"external_function", "linked_library_function"}
    return sorted(
        {
            call.name
            for call in call_report.calls
            if call.target_kind in unsafe_kinds and call.name
        }
    )


def _callee_global_names(
    cache: _ImplementationSourceCache,
    implementation_source: Path | None,
    callee: str,
    target_globals: set[str],
) -> set[str]:
    if implementation_source is None:
        return set()
    body = cache.function_body(implementation_source, callee)
    if body is None:
        return set()
    return {name for name in target_globals if re.search(rf"\b{re.escape(name)}\b", body)}


def _function_body(text: str, name: str) -> str | None:
    return _index_function_bodies(text, [name]).get(name)


def _index_function_bodies(text: str, names: Iterable[str]) -> dict[str, str]:
    requested = set(names)
    result: dict[str, str] = {}
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", text):
        name = match.group(1)
        if name not in requested or name in result:
            continue
        open_paren = text.find("(", match.start(1))
        close_paren = _matching(text, open_paren, "(", ")")
        if close_paren == -1:
            continue
        brace = close_paren + 1
        while brace < len(text) and text[brace].isspace():
            brace += 1
        if brace >= len(text) or text[brace] != "{":
            continue
        close_brace = _matching(text, brace, "{", "}")
        if close_brace != -1:
            result[name] = text[brace + 1 : close_brace]
            if len(result) == len(requested):
                break
    return result


def _matching(text: str, start: int, open_char: str, close_char: str) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == open_char:
            depth += 1
        elif text[index] == close_char:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _declaration_header_map(symbols: Iterable[str], headers: list[Path], root: Path) -> dict[str, Path]:
    requested = set(symbols)
    result: dict[str, Path] = {}
    declaration_pattern = re.compile(r"(?m)^\s*(?:extern|EXTERN)\b[^;\n]*;")
    for header in headers:
        try:
            text = decode_bytes_auto(header.read_bytes())
        except OSError:
            continue
        for match in declaration_pattern.finditer(text):
            for name in re.findall(r"\b[A-Za-z_]\w*\b", match.group(0)):
                if name in requested and name not in result:
                    result[name] = _relative(header, root)
    return result


def _object_definition_map(symbols: Iterable[str], sources: list[Path]) -> dict[str, list[Path]]:
    requested = set(symbols)
    result = {symbol: [] for symbol in requested}
    for source in sources:
        try:
            text = decode_bytes_auto(source.read_bytes())
        except OSError:
            continue
        definitions = find_file_scope_object_definitions(text)
        names = set()
        for item in definitions:
            if item.name in requested and item.storage_class != "static" and item.name not in names:
                result[item.name].append(source)
                names.add(item.name)
    return result


def _target_global_names(payload: dict[str, Any]) -> set[str]:
    names = {str(item.get("name")) for item in payload.get("global_accesses", []) if item.get("name")}
    names.update(str(item.get("name")) for item in payload.get("file_scope_declarations", []) if item.get("name"))
    return names


def _rewrite_site(call: dict[str, Any], callee: str) -> DependencyRewriteSite | None:
    position = call.get("name_position") or call.get("call_range", {}).get("start") or {}
    line = position.get("line")
    column = position.get("column")
    if not isinstance(line, int) or not isinstance(column, int):
        return None
    return DependencyRewriteSite(str(call.get("call_id") or ""), line, column, line, column + len(callee))


def _existing_modes(existing: dict[str, Any] | None) -> tuple[dict[str, str], dict[str, str]]:
    if not existing:
        return {}, {}
    dependencies = {
        str(item.get("callee")): str(item.get("configured_mode"))
        for item in existing.get("dependencies", [])
        if item.get("callee") and item.get("configured_mode") in _VALID_DEPENDENCY_MODES
    }
    objects = {
        str(item.get("symbol")): str(item.get("configured_mode"))
        for item in existing.get("external_objects", [])
        if item.get("symbol") and item.get("configured_mode") in _VALID_OBJECT_MODES
    }
    return dependencies, objects


def _expand_reachable_headers(root: Path, initial: list[Path]) -> list[Path]:
    result = _unique_paths(initial)
    queue = list(result)
    seen = {path.as_posix().lower() for path in result}
    include_pattern = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)
    search_roots = [root, *{path.parent for path in result}]
    while queue:
        current = queue.pop(0)
        try:
            text = decode_bytes_auto(current.read_bytes())
        except OSError:
            continue
        for match in include_pattern.finditer(text):
            token = match.group(1)
            candidates = [current.parent / token, *[base / token for base in search_roots]]
            found = next((path.resolve() for path in candidates if path.is_file()), None)
            if found is None:
                continue
            key = found.as_posix().lower()
            if key not in seen:
                seen.add(key)
                result.append(found)
                queue.append(found)
                search_roots.append(found.parent)
    return result


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"Unsupported dependency policy input: {type(value)!r}")


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
