from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from importlib import resources
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from .kinds import ArtifactKind, ContractMode
from .migrations import migrate_payload
from .models import ContractViolation, LoadedArtifact
from .registry import ContractDefinition, get_contract


def validate_payload(
    kind: ArtifactKind,
    payload: Mapping[str, Any],
) -> tuple[ContractViolation, ...]:
    contract = get_contract(kind)
    version = str(payload.get("schema_version") or "")
    violations: list[ContractViolation] = []
    if version != contract.current_version:
        violations.append(
            ContractViolation(
                "unsupported_version",
                "$.schema_version",
                f"{kind.value} requires schema version {contract.current_version}; received {version or '<missing>'}.",
            )
        )
        if version:
            return tuple(violations)

    validator = _validator_for(contract)
    for error in sorted(validator.iter_errors(dict(payload)), key=_error_sort_key):
        violations.append(_schema_violation(error))

    if not any(item.code == "unsupported_version" for item in violations):
        violations.extend(_common_semantic_violations(payload))
        if contract.semantic_validator == "test_spec":
            violations.extend(_test_spec_semantic_violations(payload))
    return _deduplicate_violations(violations)


def load_artifact(
    path: Path,
    *,
    expected_kind: ArtifactKind,
    mode: ContractMode = ContractMode.COMPATIBLE,
) -> LoadedArtifact:
    contract = get_contract(expected_kind)
    try:
        raw = path.read_text(encoding="utf-8")
        decoded = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return LoadedArtifact(
            kind=expected_kind,
            source_version="",
            current_version=contract.current_version,
            payload={},
            migrated=False,
            violations=(
                ContractViolation("parse_error", "$", str(error)),
            ),
        )
    if not isinstance(decoded, dict):
        return LoadedArtifact(
            kind=expected_kind,
            source_version="",
            current_version=contract.current_version,
            payload={},
            migrated=False,
            violations=(
                ContractViolation(
                    "schema_error",
                    "$",
                    "Artifact root must be a JSON object.",
                ),
            ),
        )

    source_version = str(decoded.get("schema_version") or "")
    migrated = False
    payload = decoded
    if source_version != contract.current_version:
        if (
            mode is ContractMode.COMPATIBLE
            and source_version in contract.compatible_source_versions
        ):
            try:
                payload = migrate_payload(
                    expected_kind,
                    decoded,
                    target_version=contract.current_version,
                )
                migrated = True
            except (TypeError, ValueError) as error:
                return LoadedArtifact(
                    kind=expected_kind,
                    source_version=source_version,
                    current_version=contract.current_version,
                    payload=decoded,
                    migrated=False,
                    violations=(
                        ContractViolation(
                            "migration_error",
                            "$",
                            str(error),
                        ),
                    ),
                )
        else:
            return LoadedArtifact(
                kind=expected_kind,
                source_version=source_version,
                current_version=contract.current_version,
                payload=decoded,
                migrated=False,
                violations=(
                    ContractViolation(
                        "unsupported_version",
                        "$.schema_version",
                        f"{expected_kind.value} requires schema version {contract.current_version}; received {source_version or '<missing>'}.",
                    ),
                ),
            )

    violations = list(validate_payload(expected_kind, payload))
    actual_kind = payload.get("artifact_kind")
    if actual_kind != expected_kind.value:
        violations.append(
            ContractViolation(
                "artifact_kind_mismatch",
                "$.artifact_kind",
                f"Expected {expected_kind.value}; received {actual_kind!r}.",
            )
        )
    return LoadedArtifact(
        kind=expected_kind,
        source_version=source_version,
        current_version=contract.current_version,
        payload=dict(payload),
        migrated=migrated,
        violations=_deduplicate_violations(violations),
    )


@lru_cache(maxsize=1)
def _schema_registry() -> tuple[Registry, dict[str, dict[str, Any]]]:
    root = resources.files("unit_test_runner.schemas")
    documents: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for item in root.iterdir():
        if not item.name.endswith(".json"):
            continue
        document = json.loads(item.read_text(encoding="utf-8"))
        documents[item.name] = document
        registry = registry.with_resource(
            document["$id"], Resource.from_contents(document)
        )
    return registry, documents


@lru_cache(maxsize=None)
def _validator_for(contract: ContractDefinition) -> Draft202012Validator:
    registry, documents = _schema_registry()
    return Draft202012Validator(
        documents[contract.schema_resource],
        registry=registry,
    )


def _error_sort_key(error: ValidationError) -> tuple[str, str]:
    return (_json_path(error.absolute_path), error.message)


def _schema_violation(error: ValidationError) -> ContractViolation:
    code_by_validator = {
        "required": "required_property",
        "additionalProperties": "unknown_property",
        "enum": "invalid_enum",
        "const": "invalid_enum",
        "format": "invalid_format",
    }
    return ContractViolation(
        code_by_validator.get(str(error.validator), "schema_error"),
        _json_path(error.absolute_path),
        error.message,
    )


def _json_path(parts: Iterable[Any]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(part)):
            result += f".{part}"
        else:
            result += f"[{json.dumps(str(part))}]"
    return result


def _common_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    subject = payload.get("subject")
    if isinstance(subject, Mapping):
        source_path = subject.get("source_path")
        if isinstance(source_path, str) and not _is_relative_contract_path(source_path):
            violations.append(
                ContractViolation(
                    "invalid_relative_path",
                    "$.subject.source_path",
                    "source_path must be a normalized relative path without '..'.",
                )
            )
    violations.extend(_duplicate_id_violations(payload))
    return violations


def _duplicate_id_violations(value: Any, path: str = "$") -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            violations.extend(_duplicate_id_violations(child, f"{path}.{key}"))
        return violations
    if not isinstance(value, list):
        return violations

    identifier_keys = (
        "edge_id",
        "link_id",
        "test_case_id",
        "coverage_id",
        "review_item_id",
        "item_id",
        "id",
    )
    records = [child for child in value if isinstance(child, Mapping)]
    primary_key = next(
        (
            key
            for key in identifier_keys
            if records and all(record.get(key) is not None for record in records)
        ),
        None,
    )
    if primary_key is not None:
        identifiers = [record[primary_key] for record in records]
        seen: set[Any] = set()
        for identifier in identifiers:
            if identifier in seen:
                violations.append(
                    ContractViolation(
                        "duplicate_id",
                        path,
                        f"Duplicate {primary_key}: {identifier}",
                    )
                )
            seen.add(identifier)
    for index, child in enumerate(value):
        violations.extend(_duplicate_id_violations(child, f"{path}[{index}]"))
    return violations


def _test_spec_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    violations: list[ContractViolation] = []

    source = data.get("source")
    if isinstance(source, Mapping):
        source_path = source.get("path")
        if isinstance(source_path, str) and not _is_relative_contract_path(source_path):
            violations.append(
                ContractViolation(
                    "invalid_relative_path",
                    "$.data.source.path",
                    "Test spec source path must be relative.",
                )
            )
    generated_from = data.get("generated_from")
    if isinstance(generated_from, list):
        for index, reference in enumerate(generated_from):
            if isinstance(reference, Mapping):
                reference_path = reference.get("path")
                if isinstance(reference_path, str) and not _is_relative_contract_path(reference_path):
                    violations.append(
                        ContractViolation(
                            "invalid_relative_path",
                            f"$.data.generated_from[{index}].path",
                            "Artifact reference path must be relative.",
                        )
                    )

    cases = [
        case
        for key in ("test_cases", "additional_case_candidates")
        for case in (data.get(key) or [])
        if isinstance(case, Mapping)
    ]
    case_ids = {
        str(case["test_case_id"])
        for case in cases
        if case.get("test_case_id")
    }
    coverage_summary = data.get("coverage_summary")
    coverage_ids: set[str] = set()
    if isinstance(coverage_summary, Mapping):
        mapping = coverage_summary.get("coverage_to_test_cases")
        if isinstance(mapping, Mapping):
            coverage_ids.update(str(item) for item in mapping)
            for coverage_id, references in mapping.items():
                if isinstance(references, Sequence) and not isinstance(references, str):
                    for reference in references:
                        if str(reference) not in case_ids:
                            violations.append(
                                ContractViolation(
                                    "invalid_reference",
                                    f"$.data.coverage_summary.coverage_to_test_cases.{coverage_id}",
                                    f"Unknown test_case_id reference: {reference}",
                                )
                            )
        uncovered = coverage_summary.get("uncovered_coverage_ids")
        if isinstance(uncovered, list):
            coverage_ids.update(str(item) for item in uncovered)

    for case_index, case in enumerate(cases):
        links = case.get("coverage_links")
        if not isinstance(links, list):
            continue
        for link_index, link in enumerate(links):
            if not isinstance(link, Mapping) or not link.get("coverage_id"):
                continue
            coverage_id = str(link["coverage_id"])
            if coverage_id not in coverage_ids:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.test_cases[{case_index}].coverage_links[{link_index}].coverage_id",
                        f"Unknown coverage_id reference: {coverage_id}",
                    )
                )
    return violations


def _is_relative_contract_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    windows = PureWindowsPath(value)
    posix = PurePosixPath(normalized)
    return bool(
        normalized
        and not windows.is_absolute()
        and not posix.is_absolute()
        and ".." not in posix.parts
        and not re.match(r"^[A-Za-z]:", value)
    )


def _deduplicate_violations(
    violations: Iterable[ContractViolation],
) -> tuple[ContractViolation, ...]:
    unique: dict[tuple[str, str, str, str], ContractViolation] = {}
    for item in violations:
        unique[(item.code, item.json_path, item.message, item.severity)] = item
    return tuple(unique.values())
