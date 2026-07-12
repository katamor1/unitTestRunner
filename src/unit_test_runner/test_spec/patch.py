from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Mapping

from unit_test_runner.cli.artifacts import ProducedArtifact
from unit_test_runner.contracts import ContractMode

from .models import CurrentArtifactContext, TestSpec
from .repository import TestSpecSnapshot, load_test_spec, save_test_spec_snapshot


class InvalidTestSpecPatchError(ValueError):
    pass


_EDITABLE_CASE_FIELDS = {
    "title",
    "purpose",
    "priority",
    "case_kind",
    "preconditions",
    "input_assignments",
    "state_setups",
    "stub_setups",
    "dependency_overrides",
    "execution_steps",
    "expected_observations",
    "coverage_links",
    "candidate_links",
    "confidence",
    "warnings",
    "review_item_ids",
}
_FORBIDDEN_SEGMENTS = {
    "approved",
    "approval",
    "approval_status",
    "is_approved",
    "review_status",
    "review_decision",
    "revision",
    "schema_version",
    "spec_id",
    "test_case_id",
    "generated_from",
    "source",
    "function",
}
_FIELD_SEGMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARRAY_INDEX_SEGMENT = re.compile(r"^[0-9]+$")


def apply_test_spec_patch(
    spec: TestSpec,
    patch: Mapping[str, Any],
) -> TestSpec:
    if set(patch) != {"operations"} or not isinstance(patch.get("operations"), list):
        raise InvalidTestSpecPatchError("Patch must contain only an operations array.")
    operations = patch["operations"]
    if not operations:
        raise InvalidTestSpecPatchError("Patch operations must not be empty.")
    payload = spec.to_payload()
    normalized: list[tuple[str, tuple[str, ...], Any]] = []
    keys: list[tuple[str, tuple[str, ...]]] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping) or set(operation) != {"op", "case_id", "path", "value"}:
            raise InvalidTestSpecPatchError(
                f"Operation {index} must contain exactly op, case_id, path, and value."
            )
        if operation["op"] != "replace":
            raise InvalidTestSpecPatchError("Only replace operations are supported.")
        case_id = str(operation["case_id"] or "")
        segments = _parse_pointer(str(operation["path"] or ""))
        if segments[0] not in _EDITABLE_CASE_FIELDS:
            raise InvalidTestSpecPatchError(
                f"Case field is immutable or unknown: {segments[0]}"
            )
        if any(segment.lower() in _FORBIDDEN_SEGMENTS for segment in segments):
            raise InvalidTestSpecPatchError(
                "Patch paths cannot edit identity, provenance, revision, version, or review authority."
            )
        case = _find_case(payload["data"], case_id)
        segments = _canonicalize_pointer(case, segments)
        key = (case_id, segments)
        if any(
            existing_case == case_id
            and (_is_prefix(existing_path, segments) or _is_prefix(segments, existing_path))
            for existing_case, existing_path in keys
        ):
            raise InvalidTestSpecPatchError("Duplicate or conflicting patch operations are not allowed.")
        keys.append(key)
        normalized.append((case_id, segments, copy.deepcopy(operation["value"])))

    for case_id, segments, value in normalized:
        case = _find_case(payload["data"], case_id)
        _replace_existing(case, segments, value)
    return TestSpec.from_payload(payload)


def update_test_spec(
    path: Path,
    patch: Mapping[str, Any],
    *,
    expected_revision: int,
    current_context: CurrentArtifactContext,
) -> tuple[TestSpec, ProducedArtifact]:
    saved, artifact = update_test_spec_snapshot(
        path,
        patch,
        expected_revision=expected_revision,
        current_context=current_context,
    )
    return saved.spec, artifact


def update_test_spec_snapshot(
    path: Path,
    patch: Mapping[str, Any],
    *,
    expected_revision: int,
    current_context: CurrentArtifactContext,
) -> tuple[TestSpecSnapshot, ProducedArtifact]:
    current = load_test_spec(path, mode=ContractMode.STRICT)
    candidate = apply_test_spec_patch(current, patch)
    saved, artifact = save_test_spec_snapshot(
        path,
        candidate,
        expected_revision=expected_revision,
        current_context=current_context,
    )
    return saved, artifact


def _parse_pointer(value: str) -> tuple[str, ...]:
    if not value.startswith("/") or value == "/":
        raise InvalidTestSpecPatchError("Patch path must be a non-empty JSON Pointer.")
    raw_segments = value[1:].split("/")
    segments: list[str] = []
    for raw in raw_segments:
        if not raw or raw in {".", ".."} or "~" in raw:
            raise InvalidTestSpecPatchError("Patch path contains an escaping or malformed segment.")
        if not _ARRAY_INDEX_SEGMENT.fullmatch(raw) and not _FIELD_SEGMENT.fullmatch(raw):
            raise InvalidTestSpecPatchError(f"Invalid patch path segment: {raw}")
        segments.append(raw)
    return tuple(segments)


def _canonicalize_pointer(
    container: Any,
    segments: tuple[str, ...],
) -> tuple[str, ...]:
    current = container
    canonical: list[str] = []
    for segment in segments:
        if isinstance(current, dict):
            if segment not in current:
                raise InvalidTestSpecPatchError(
                    f"Unknown patch path: /{'/'.join(segments)}"
                )
            canonical.append(segment)
            current = current[segment]
            continue
        if isinstance(current, list):
            if not _ARRAY_INDEX_SEGMENT.fullmatch(segment):
                raise InvalidTestSpecPatchError(
                    f"Patch path requires an ASCII array index: {segment}"
                )
            index = _array_index(segment)
            if index >= len(current):
                raise InvalidTestSpecPatchError(
                    f"Array index outside patch target: {segment}"
                )
            canonical.append(str(index))
            current = current[index]
            continue
        raise InvalidTestSpecPatchError(
            f"Patch path is not traversable: /{'/'.join(segments)}"
        )
    return tuple(canonical)


def _is_prefix(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return len(left) <= len(right) and right[: len(left)] == left


def _array_index(segment: str) -> int:
    try:
        return int(segment)
    except ValueError as error:
        raise InvalidTestSpecPatchError(
            f"Array index is outside the supported numeric range: {segment[:32]}"
        ) from error


def _find_case(data: Mapping[str, Any], case_id: str) -> dict[str, Any]:
    matches = [
        case
        for collection in ("test_cases", "additional_case_candidates")
        for case in data.get(collection) or []
        if isinstance(case, dict) and str(case.get("test_case_id") or "") == case_id
    ]
    if len(matches) != 1:
        raise InvalidTestSpecPatchError(f"Unknown or ambiguous case_id: {case_id}")
    return matches[0]


def _replace_existing(container: Any, segments: tuple[str, ...], value: Any) -> None:
    current = container
    for segment in segments[:-1]:
        if isinstance(current, dict):
            if segment not in current:
                raise InvalidTestSpecPatchError(f"Unknown patch path: /{'/'.join(segments)}")
            current = current[segment]
        elif isinstance(current, list) and _ARRAY_INDEX_SEGMENT.fullmatch(segment):
            index = _array_index(segment)
            if index >= len(current):
                raise InvalidTestSpecPatchError(f"Array index outside patch target: {segment}")
            current = current[index]
        else:
            raise InvalidTestSpecPatchError(f"Patch path is not traversable: /{'/'.join(segments)}")
    leaf = segments[-1]
    if isinstance(current, dict):
        if leaf not in current:
            raise InvalidTestSpecPatchError(f"Unknown patch path: /{'/'.join(segments)}")
        current[leaf] = value
    elif isinstance(current, list) and _ARRAY_INDEX_SEGMENT.fullmatch(leaf):
        index = _array_index(leaf)
        if index >= len(current):
            raise InvalidTestSpecPatchError(f"Array index outside patch target: {leaf}")
        current[index] = value
    else:
        raise InvalidTestSpecPatchError(f"Patch path is not replaceable: /{'/'.join(segments)}")
