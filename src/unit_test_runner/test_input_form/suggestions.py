from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .field_catalog import FIELD_RULES
from .field_locator import LocatedFormItem, canonical_bytes
from .models import FormSuggestion
from .validation import is_unresolved


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FLAG_NAME_RE = re.compile(r"(?:^|_)(?:flag|flags|enable|enabled|bool|is|has)(?:_|$)", re.IGNORECASE)
_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}
_SOURCE_RANK = {
    "boundary_candidate": 0,
    "enum_candidate": 1,
    "function_signature": 2,
    "canonical_sibling": 3,
    "name_heuristic": 4,
}
_TARGET_EXCLUDED_FIELDS = {"source_candidate_id", "related_call_id", "source"}


def _payload_data(value: Mapping[str, Any]) -> Mapping[str, Any]:
    data = value.get("data")
    return data if isinstance(data, Mapping) else value


def _read_json(path: Path) -> Mapping[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(parsed, Mapping):
        raise ValueError(f"Suggestion artifact root must be an object: {path}")
    return _payload_data(parsed)


def _spec_cases(spec: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(spec, Mapping):
        data = _payload_data(spec)
        collections = (data.get("test_cases", []), data.get("additional_case_candidates", []))
    else:
        collections = (
            getattr(spec, "test_cases", []),
            getattr(spec, "additional_case_candidates", []),
        )
    for collection in collections:
        if isinstance(collection, list):
            for case in collection:
                if isinstance(case, Mapping):
                    yield case


def _candidate_value(candidate: Mapping[str, Any]) -> str | None:
    for field in ("value_expression", "expected_expression", "value"):
        value = candidate.get(field)
        if isinstance(value, str) and not is_unresolved(value):
            return value.strip()
    return None


def _candidate_target(candidate: Mapping[str, Any]) -> tuple[str, str] | None:
    name = candidate.get("target_name") or candidate.get("variable_name") or candidate.get("stub_name")
    if not isinstance(name, str) or not name.strip():
        return None
    kind = candidate.get("target_kind") or candidate.get("scope") or candidate.get("setup_kind") or "unknown"
    return str(kind), name.strip()


def semantic_target_key(item: LocatedFormItem) -> bytes:
    identity = {
        name: item.parent.get(name)
        for name in item.rule.locator_fields
        if name not in _TARGET_EXCLUDED_FIELDS
    }
    return canonical_bytes(
        {
            "collection": item.collection,
            "kind": item.kind,
            "identity": identity,
        }
    )


def _parent_target_key(collection: str, parent: Mapping[str, Any]) -> bytes:
    rule = FIELD_RULES[collection]
    identity = {
        name: parent.get(name)
        for name in rule.locator_fields
        if name not in _TARGET_EXCLUDED_FIELDS
    }
    return canonical_bytes(
        {"collection": collection, "kind": rule.kind, "identity": identity}
    )


def _signature_parts(workspace: Path) -> tuple[dict[str, Mapping[str, Any]], Mapping[str, Any] | None]:
    payload = _read_json(workspace / "reports" / "function_signature.json")
    function = payload.get("function")
    if not isinstance(function, Mapping):
        return {}, None
    parameters = function.get("parameters")
    by_name: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    if isinstance(parameters, list):
        for parameter in parameters:
            if not isinstance(parameter, Mapping):
                continue
            name = parameter.get("name")
            type_hint = parameter.get("type")
            if isinstance(name, str) and isinstance(type_hint, Mapping):
                by_name[name].append(type_hint)
    unique = {
        name: values[0]
        for name, values in by_name.items()
        if len(values) == 1
    }
    return_type = function.get("return_type")
    return unique, return_type if isinstance(return_type, Mapping) else None


@dataclass(frozen=True)
class SuggestionIndex:
    candidates_by_id: Mapping[str, Mapping[str, Any]]
    candidates_by_target: Mapping[tuple[str, str], tuple[Mapping[str, Any], ...]]
    parameter_types: Mapping[str, Mapping[str, Any]]
    return_type: Mapping[str, Any] | None
    concrete_values: Mapping[bytes, tuple[str, ...]]


def build_suggestion_index(workspace: Path, spec: Any) -> SuggestionIndex:
    workspace = Path(workspace)
    boundary = _read_json(workspace / "reports" / "boundary_equivalence_candidates.json")
    candidates: list[Mapping[str, Any]] = []
    for collection in ("input_candidates", "state_candidates", "stub_return_candidates"):
        values = boundary.get(collection)
        if isinstance(values, list):
            candidates.extend(item for item in values if isinstance(item, Mapping))
    id_counts = Counter(
        str(item.get("candidate_id"))
        for item in candidates
        if item.get("candidate_id")
    )
    candidates_by_id = {
        str(item["candidate_id"]): item
        for item in candidates
        if item.get("candidate_id") and id_counts[str(item["candidate_id"])] == 1
    }
    by_target: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        target = _candidate_target(candidate)
        if target is not None:
            by_target[target].append(candidate)

    parameter_types, return_type = _signature_parts(workspace)
    concrete: dict[bytes, list[str]] = defaultdict(list)
    for case in _spec_cases(spec):
        for collection, rule in FIELD_RULES.items():
            parents = case.get(collection)
            if not isinstance(parents, list):
                continue
            c_controls = {
                control.name
                for control in rule.controls
                if control.control_kind == "c_expression"
            }
            if not c_controls:
                continue
            for parent in parents:
                if not isinstance(parent, Mapping):
                    continue
                key = _parent_target_key(collection, parent)
                for name in c_controls:
                    value = parent.get(name)
                    if isinstance(value, str) and not is_unresolved(value):
                        concrete[key].append(value.strip())
    return SuggestionIndex(
        candidates_by_id=candidates_by_id,
        candidates_by_target={key: tuple(values) for key, values in by_target.items()},
        parameter_types=parameter_types,
        return_type=return_type,
        concrete_values={
            key: tuple(dict.fromkeys(values))
            for key, values in concrete.items()
        },
    )


def type_hint_for_item(
    index: SuggestionIndex,
    item: LocatedFormItem,
) -> Mapping[str, Any] | None:
    if item.collection == "input_assignments":
        name = item.parent.get("target_name")
        return index.parameter_types.get(str(name)) if name is not None else None
    if item.collection == "expected_observations" and str(
        item.parent.get("observation_kind") or ""
    ) == "return_value":
        return index.return_type
    return None


def _is_pointer(type_hint: Mapping[str, Any] | None) -> bool:
    if not type_hint:
        return False
    pointer_level = type_hint.get("pointer_level")
    return (
        isinstance(pointer_level, int)
        and not isinstance(pointer_level, bool)
        and pointer_level > 0
    ) or bool(type_hint.get("is_pointer"))


def _is_enum(type_hint: Mapping[str, Any] | None) -> bool:
    if not type_hint:
        return False
    return bool(type_hint.get("is_enum")) or str(type_hint.get("base_type") or "").startswith("enum ")


def _target_for_item(item: LocatedFormItem) -> tuple[str, str] | None:
    return _candidate_target(item.parent)


def _suggestion(
    value: str,
    source: str,
    confidence: str,
    *,
    label: str | None = None,
) -> FormSuggestion:
    return FormSuggestion(
        value=value,
        label=label or value,
        source=source,
        confidence=confidence if confidence in _CONFIDENCE_RANK else "low",
    )


def suggestions_for_item(
    index: SuggestionIndex,
    item: LocatedFormItem,
    control_name: str,
) -> tuple[FormSuggestion, ...]:
    rule_control = next(
        (control for control in item.rule.controls if control.name == control_name),
        None,
    )
    if rule_control is None or rule_control.control_kind != "c_expression":
        return ()
    suggestions: list[FormSuggestion] = []
    candidate_id = item.parent.get("source_candidate_id")
    if isinstance(candidate_id, str):
        candidate = index.candidates_by_id.get(candidate_id)
        if candidate is not None:
            value = _candidate_value(candidate)
            if value is not None:
                suggestions.append(
                    _suggestion(
                        value,
                        "boundary_candidate",
                        str(candidate.get("confidence") or "low"),
                    )
                )
    type_hint = type_hint_for_item(index, item)
    target = _target_for_item(item)
    if _is_enum(type_hint) and target is not None:
        for candidate in index.candidates_by_target.get(target, ()):
            value = _candidate_value(candidate)
            if value is not None and _IDENTIFIER_RE.fullmatch(value):
                suggestions.append(
                    _suggestion(
                        value,
                        "enum_candidate",
                        str(candidate.get("confidence") or "low"),
                    )
                )
    if _is_pointer(type_hint):
        suggestions.append(_suggestion("NULL", "function_signature", "high"))
    target_name = str(item.parent.get("target_name") or item.parent.get("variable_name") or "")
    if target_name and _FLAG_NAME_RE.search(target_name) and not _is_pointer(type_hint):
        suggestions.extend(
            (
                _suggestion("0", "name_heuristic", "medium", label="0 (false/clear)"),
                _suggestion("1", "name_heuristic", "medium", label="1 (true/set)"),
            )
        )
    for value in index.concrete_values.get(semantic_target_key(item), ()):
        suggestions.append(_suggestion(value, "canonical_sibling", "medium"))

    best_by_value: dict[str, FormSuggestion] = {}
    for suggestion in suggestions:
        current = best_by_value.get(suggestion.value)
        rank = (
            _CONFIDENCE_RANK.get(suggestion.confidence, 9),
            _SOURCE_RANK.get(suggestion.source, 9),
            suggestion.value,
        )
        current_rank = (
            _CONFIDENCE_RANK.get(current.confidence, 9),
            _SOURCE_RANK.get(current.source, 9),
            current.value,
        ) if current is not None else None
        if current is None or rank < current_rank:
            best_by_value[suggestion.value] = suggestion
    return tuple(
        sorted(
            best_by_value.values(),
            key=lambda suggestion: (
                _CONFIDENCE_RANK.get(suggestion.confidence, 9),
                _SOURCE_RANK.get(suggestion.source, 9),
                suggestion.value,
            ),
        )
    )
