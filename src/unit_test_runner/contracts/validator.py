from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from functools import lru_cache
from importlib import resources
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from .kinds import ArtifactKind, ContractMode, RunOutcome
from .migrations import migrate_payload
from .models import ContractViolation, LoadedArtifact
from .path_policy import iter_contract_path_values, path_policy_for
from .registry import ContractDefinition, get_contract
from unit_test_runner.review_ids import subject_fingerprint


def validate_payload(
    kind: ArtifactKind,
    payload: Mapping[str, Any],
) -> tuple[ContractViolation, ...]:
    violations = list(validate_payload_schema(kind, payload))
    contract = get_contract(kind)
    if not any(item.code == "unsupported_version" for item in violations):
        violations.extend(_common_semantic_violations(kind, payload))
        violations.extend(
            _artifact_semantic_violations(
                contract.semantic_validator,
                payload,
            )
        )
    return _deduplicate_violations(violations)


def validate_payload_schema(
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
    decoded_kind = decoded.get("artifact_kind")
    if decoded_kind is not None and decoded_kind != expected_kind.value:
        return LoadedArtifact(
            kind=expected_kind,
            source_version=source_version,
            current_version=contract.current_version,
            payload=dict(decoded),
            migrated=False,
            violations=(
                ContractViolation(
                    "artifact_kind_mismatch",
                    "$.artifact_kind",
                    f"Expected {expected_kind.value}; received {decoded_kind!r}.",
                ),
            ),
        )
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
    kind: ArtifactKind,
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    builtin_payload = {
        key: value
        for key, value in payload.items()
        if key != "extensions"
    }
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
    semantic_payload = builtin_payload
    if kind is ArtifactKind.CLI_RESULT:
        cli_data = builtin_payload.get("data")
        if isinstance(cli_data, Mapping):
            cli_data = {key: value for key, value in cli_data.items() if key != "details"}
            semantic_payload = {**builtin_payload, "data": cli_data}
    violations.extend(_duplicate_id_violations(semantic_payload))
    violations.extend(_provenance_violations(kind, payload))
    violations.extend(_nested_path_violations(kind, semantic_payload))
    violations.extend(_nested_hash_violations(semantic_payload))
    violations.extend(_subject_consistency_violations(semantic_payload))
    return violations


def _provenance_violations(
    kind: ArtifactKind,
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    required_paths: list[tuple[str, Any]] = []
    producer = payload.get("producer")
    if isinstance(producer, Mapping) and not producer.get("commit"):
        violations.append(
            ContractViolation(
                "missing_provenance",
                "$.producer.commit",
                "A verified producer commit is required.",
                "blocking",
            )
        )
    subject = payload.get("subject")
    if kind is not ArtifactKind.CLI_RESULT and isinstance(subject, Mapping):
        if not subject.get("source_path"):
            violations.append(
                ContractViolation(
                    "missing_provenance",
                    "$.subject.source_path",
                    "A verified source path is required.",
                    "blocking",
                )
            )
        if not subject.get("function_id"):
            violations.append(
                ContractViolation(
                    "missing_identity",
                    "$.subject.function_id",
                    "A verified function identity is required.",
                    "blocking",
                )
            )
        required_paths.append(("$.subject.source_sha256", subject.get("source_sha256")))
    if kind is ArtifactKind.TEST_SPEC:
        data = payload.get("data")
        if isinstance(data, Mapping):
            source = data.get("source")
            function = data.get("function")
            if isinstance(source, Mapping):
                required_paths.append(("$.data.source.sha256", source.get("sha256")))
            if isinstance(function, Mapping):
                required_paths.append(
                    (
                        "$.data.function.signature_sha256",
                        function.get("signature_sha256"),
                    )
                )
    for json_path, value in required_paths:
        if value is None or value == "0" * 64:
            violations.append(
                ContractViolation(
                    "missing_provenance",
                    json_path,
                    "A verified SHA-256 provenance value is required.",
                    "blocking",
                )
            )
    extensions = payload.get("extensions")
    migration = extensions.get("migration") if isinstance(extensions, Mapping) else None
    path_migrations = (
        migration.get("path_migrations") if isinstance(migration, Mapping) else None
    )
    if isinstance(path_migrations, list):
        for item in path_migrations:
            if not isinstance(item, Mapping) or item.get("verified") is not False:
                continue
            json_path = item.get("json_path")
            if not isinstance(json_path, str):
                continue
            violations.append(
                ContractViolation(
                    "missing_provenance",
                    json_path,
                    "The legacy path has no verified workspace-relative mapping.",
                    "blocking",
                )
            )
    return violations


def _nested_path_violations(
    kind: ArtifactKind,
    value: Any,
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    path_policy = path_policy_for(kind)
    for path_value in iter_contract_path_values(value, path_policy):
        if path_value.value and not _is_relative_contract_path(path_value.value):
            violations.append(
                ContractViolation(
                    "invalid_relative_path",
                    path_value.json_path,
                    f"{path_value.field_name} must contain normalized relative contract paths.",
                )
            )
    return violations


def _nested_hash_violations(value: Any, path: str = "$") -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            is_hash = key == "sha256" or key.endswith("_sha256") or key.endswith("_hash")
            if is_hash and isinstance(child, str):
                if child == "0" * 64:
                    violations.append(
                        ContractViolation(
                            "missing_provenance",
                            child_path,
                            "An all-zero SHA-256 is not known provenance.",
                            "blocking",
                        )
                    )
                elif not re.fullmatch(r"[0-9a-f]{64}", child):
                    violations.append(
                        ContractViolation(
                            "invalid_hash",
                            child_path,
                            "SHA-256 values must be 64 lowercase hexadecimal characters.",
                        )
                    )
            if (
                key == "sha256"
                and child is None
                and bool(value.get("required"))
                and not (
                    value.get("exists") is False
                    and value.get("integrity_status") == "missing"
                )
            ):
                violations.append(
                    ContractViolation(
                        "missing_provenance",
                        child_path,
                        "A required evidence file must have a verified SHA-256.",
                        "blocking",
                    )
                )
            violations.extend(_nested_hash_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_nested_hash_violations(child, f"{path}[{index}]"))
    return violations


def _subject_consistency_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    subject = payload.get("subject")
    data = payload.get("data")
    if not isinstance(subject, Mapping) or not isinstance(data, Mapping):
        return []
    violations: list[ContractViolation] = []
    source = data.get("source")
    if isinstance(source, Mapping):
        source_path = source.get("path")
        if source_path and source_path != subject.get("source_path"):
            violations.append(
                ContractViolation(
                    "invalid_reference",
                    "$.data.source.path",
                    "Data source path must match the artifact subject.",
                )
            )
        source_sha256 = source.get("sha256")
        if source_sha256 and source_sha256 != subject.get("source_sha256"):
            violations.append(
                ContractViolation(
                    "invalid_reference",
                    "$.data.source.sha256",
                    "Data source SHA-256 must match the artifact subject.",
                )
            )
    target = data.get("target")
    if isinstance(target, Mapping):
        target_source = target.get("source")
        if target_source and target_source != subject.get("source_path"):
            violations.append(
                ContractViolation(
                    "invalid_reference",
                    "$.data.target.source",
                    "Dossier target source must match the artifact subject.",
                )
            )
    function = data.get("function")
    if isinstance(function, Mapping):
        function_id = function.get("function_id")
        if function_id and function_id != subject.get("function_id"):
            violations.append(
                ContractViolation(
                    "invalid_reference",
                    "$.data.function.function_id",
                    "Data function_id must match the artifact subject.",
                )
            )
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
        "artifact_id",
        "entry_id",
        "snapshot_id",
        "action_id",
        "candidate_id",
        "class_id",
        "group_id",
        "condition_id",
        "branch_id",
        "review_id",
        "review_item_id",
        "case_id",
        "switch_id",
        "loop_id",
        "ternary_id",
        "return_id",
        "placeholder_id",
        "hint_id",
        "command_id",
        "call_id",
        "edge_id",
        "link_id",
        "test_case_id",
        "coverage_id",
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
            if isinstance(identifier, (Mapping, list, set)):
                continue
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


def _artifact_semantic_violations(
    semantic_hook: str,
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    validator = _ARTIFACT_SEMANTIC_VALIDATORS.get(semantic_hook)
    if validator is None:
        return [
            ContractViolation(
                "missing_semantic_validator",
                "$.artifact_kind",
                f"No semantic validator is registered for {semantic_hook}.",
                "blocking",
            )
        ]
    return validator(payload)


def semantic_validator_names() -> frozenset[str]:
    return frozenset(_ARTIFACT_SEMANTIC_VALIDATORS)


def _no_artifact_semantic_violations(
    _payload: Mapping[str, Any],
) -> list[ContractViolation]:
    return []


def _cli_result_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    subject = payload.get("subject")
    if not isinstance(data, Mapping):
        return []
    violations: list[ContractViolation] = []
    invocation_id = data.get("invocation_id")
    subject_invocation = (
        subject.get("invocation_id") if isinstance(subject, Mapping) else None
    )
    if invocation_id != subject_invocation:
        violations.append(
            ContractViolation(
                "inconsistent_identity",
                "$.data.invocation_id",
                "CLI invocation_id must match the envelope subject invocation_id.",
            )
        )

    if data.get("outcome_kind") in {"test_run", "suite_run"}:
        outcome = data.get("outcome")
        expected_exit = {
            RunOutcome.PLANNED.value: 0,
            RunOutcome.PASSED.value: 0,
            RunOutcome.FAILED.value: 32,
            RunOutcome.INCONCLUSIVE.value: 33,
            RunOutcome.TIMED_OUT.value: 34,
            RunOutcome.BLOCKED.value: 35,
            RunOutcome.CANCELLED.value: 36,
            RunOutcome.ERROR.value: 10,
        }.get(outcome)
        if expected_exit is not None and data.get("exit_code") != expected_exit:
            violations.append(
                ContractViolation(
                    "inconsistent_exit_code",
                    "$.data.exit_code",
                    f"Test outcome {outcome!r} requires exit code {expected_exit}.",
                )
            )
        expected_green = None if outcome == RunOutcome.PLANNED.value else outcome == RunOutcome.PASSED.value
        if data.get("green") is not expected_green:
            violations.append(
                ContractViolation(
                    "inconsistent_green_status",
                    "$.data.green",
                    f"Test outcome {outcome!r} requires green={expected_green!r}.",
                )
            )
    return violations


def _call_report_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    calls = data.get("calls")
    call_ids = {
        str(item["call_id"])
        for item in calls or []
        if isinstance(item, Mapping) and item.get("call_id")
    }
    violations: list[ContractViolation] = []
    stub_candidates = data.get("stub_candidates")
    if isinstance(stub_candidates, list):
        for item_index, item in enumerate(stub_candidates):
            if not isinstance(item, Mapping):
                continue
            for reference_index, reference in enumerate(item.get("related_calls") or []):
                if str(reference) not in call_ids:
                    violations.append(
                        ContractViolation(
                            "invalid_reference",
                            f"$.data.stub_candidates[{item_index}].related_calls[{reference_index}]",
                            f"Unknown call_id reference: {reference}",
                        )
                    )
    side_effects = data.get("side_effect_candidates")
    if isinstance(side_effects, list):
        for index, item in enumerate(side_effects):
            if not isinstance(item, Mapping):
                continue
            reference = item.get("call_id")
            if reference and str(reference) not in call_ids:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.side_effect_candidates[{index}].call_id",
                        f"Unknown call_id reference: {reference}",
                    )
                )
    unresolved = data.get("unresolved_calls")
    if isinstance(unresolved, list):
        for index, item in enumerate(unresolved):
            if not isinstance(item, Mapping):
                continue
            reference = item.get("call_id")
            if reference and str(reference) not in call_ids:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.unresolved_calls[{index}].call_id",
                        f"Unknown call_id reference: {reference}",
                    )
                )
    return violations


def _coverage_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    id_fields = {
        "branches": "branch_id",
        "switches": "switch_id",
        "loops": "loop_id",
        "ternaries": "ternary_id",
        "return_paths": "return_id",
        "condition_expressions": "condition_id",
    }
    target_ids: set[str] = set()
    for collection_name, id_field in id_fields.items():
        collection = data.get(collection_name)
        if isinstance(collection, list):
            target_ids.update(
                str(item[id_field])
                for item in collection
                if isinstance(item, Mapping) and item.get(id_field)
            )
            if collection_name == "switches":
                for switch in collection:
                    if not isinstance(switch, Mapping):
                        continue
                    target_ids.update(
                        str(case["case_id"])
                        for case in switch.get("cases") or []
                        if isinstance(case, Mapping) and case.get("case_id")
                    )
    violations: list[ContractViolation] = []
    coverage_items = data.get("coverage_items")
    if isinstance(coverage_items, list):
        for index, item in enumerate(coverage_items):
            if not isinstance(item, Mapping):
                continue
            target_id = item.get("target_id")
            if target_id and str(target_id) not in target_ids:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.coverage_items[{index}].target_id",
                        f"Unknown coverage target_id: {target_id}",
                    )
                )
    return violations


def _boundary_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    candidate_ids: set[str] = set()
    for collection_name in (
        "input_candidates",
        "state_candidates",
        "stub_return_candidates",
    ):
        collection = data.get(collection_name)
        if isinstance(collection, list):
            candidate_ids.update(
                str(item["candidate_id"])
                for item in collection
                if isinstance(item, Mapping) and item.get("candidate_id")
            )
    violations: list[ContractViolation] = []
    for collection_name in ("boundary_groups", "coverage_links"):
        collection = data.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item_index, item in enumerate(collection):
            if not isinstance(item, Mapping):
                continue
            for reference_index, reference in enumerate(item.get("candidate_ids") or item.get("candidates") or []):
                if str(reference) not in candidate_ids:
                    violations.append(
                        ContractViolation(
                            "invalid_reference",
                            f"$.data.{collection_name}[{item_index}].candidate_ids[{reference_index}]"
                            if "candidate_ids" in item
                            else f"$.data.{collection_name}[{item_index}].candidates[{reference_index}]",
                            f"Unknown candidate_id reference: {reference}",
                        )
                    )
    return violations


def _build_completion_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    actions = data.get("completion_actions")
    action_ids = {
        str(item["action_id"])
        for item in actions or []
        if isinstance(item, Mapping) and item.get("action_id")
    }
    violations: list[ContractViolation] = []
    reference_fields = (
        ("include_completion_candidates", "selected_action_id"),
        ("pch_completion_candidates", "action_id"),
        ("warnings", "related_action_id"),
    )
    for collection_name, reference_field in reference_fields:
        collection = data.get(collection_name)
        if not isinstance(collection, list):
            continue
        for index, item in enumerate(collection):
            if not isinstance(item, Mapping):
                continue
            reference = item.get(reference_field)
            if reference and str(reference) not in action_ids:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.{collection_name}[{index}].{reference_field}",
                        f"Unknown action_id reference: {reference}",
                    )
                )
    return violations


def _partition_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    partition_names = (
        "preserved_test_cases",
        "updated_test_cases",
        "obsolete_test_cases",
        "new_test_case_candidates",
        "selected_test_cases",
        "skipped_test_cases",
        "new_required_test_cases",
        "blocked_test_cases",
    )
    seen: set[str] = set()
    violations: list[ContractViolation] = []
    for partition_name in partition_names:
        partition = data.get(partition_name)
        if not isinstance(partition, list):
            continue
        for index, item in enumerate(partition):
            if not isinstance(item, Mapping) or not item.get("test_case_id"):
                continue
            test_case_id = str(item["test_case_id"])
            if test_case_id in seen:
                violations.append(
                    ContractViolation(
                        "duplicate_id",
                        f"$.data.{partition_name}[{index}].test_case_id",
                        f"test_case_id appears in multiple partitions: {test_case_id}",
                    )
                )
            seen.add(test_case_id)
    manual_items = data.get("manual_merge_items")
    if isinstance(manual_items, list):
        for index, item in enumerate(manual_items):
            if not isinstance(item, Mapping):
                continue
            reference = item.get("test_case_id")
            if reference and str(reference) not in seen:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.manual_merge_items[{index}].test_case_id",
                        f"Unknown test_case_id reference: {reference}",
                    )
                )
    return violations


def _dossier_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    artifact_index = data.get("artifact_index")
    artifact_ids = {
        str(reference)
        for item in artifact_index or []
        if isinstance(item, Mapping)
        for reference in (item.get("artifact_id"), item.get("artifact_kind"))
        if reference
    }
    violations: list[ContractViolation] = []
    for collection_name in ("review_items", "unresolved_items"):
        collection = data.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item_index, item in enumerate(collection):
            if not isinstance(item, Mapping):
                continue
            references = item.get("related_artifacts")
            if not isinstance(references, list):
                continue
            for reference_index, reference in enumerate(references):
                if str(reference) not in artifact_ids:
                    violations.append(
                        ContractViolation(
                            "invalid_reference",
                            f"$.data.{collection_name}[{item_index}].related_artifacts[{reference_index}]",
                            f"Unknown artifact_id reference: {reference}",
                        )
                    )
    unresolved = data.get("unresolved_items")
    unresolved_ids = {
        str(item["item_id"])
        for item in unresolved or []
        if isinstance(item, Mapping) and item.get("item_id")
    }
    actions = data.get("next_actions")
    if isinstance(actions, list):
        for action_index, action in enumerate(actions):
            if not isinstance(action, Mapping):
                continue
            for reference_index, reference in enumerate(
                action.get("related_unresolved_items") or []
            ):
                if str(reference) not in unresolved_ids:
                    violations.append(
                        ContractViolation(
                            "invalid_reference",
                            f"$.data.next_actions[{action_index}].related_unresolved_items[{reference_index}]",
                            f"Unknown unresolved item reference: {reference}",
                        )
                    )
    return violations


def _suite_run_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    selector = data.get("selector")
    selected_ids: set[str] | None = None
    if isinstance(selector, Mapping) and selector.get("kind") == "entry_id":
        selected_ids = {str(item) for item in selector.get("entry_ids") or []}
    violations: list[ContractViolation] = []
    results = data.get("results")
    result_by_id: dict[str, Mapping[str, Any]] = {}
    if selected_ids is not None and isinstance(results, list):
        for index, result in enumerate(results):
            if not isinstance(result, Mapping):
                continue
            entry_id = result.get("entry_id")
            if entry_id:
                result_by_id[str(entry_id)] = result
            if entry_id and str(entry_id) not in selected_ids:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.results[{index}].entry_id",
                        f"Result entry_id was not selected: {entry_id}",
                    )
                )
    elif isinstance(results, list):
        result_by_id = {
            str(result["entry_id"]): result
            for result in results
            if isinstance(result, Mapping) and result.get("entry_id")
        }
    if isinstance(results, list):
        for index, result in enumerate(results):
            if not isinstance(result, Mapping):
                continue
            if "not_run_tests" not in result:
                violations.append(
                    ContractViolation(
                        "missing_provenance",
                        f"$.data.results[{index}].not_run_tests",
                        "Legacy suite output did not preserve the not-run test count.",
                        "blocking",
                    )
                )
            is_green = _suite_result_is_green(result)
            if (result.get("green_status") == "green") != is_green:
                violations.append(
                    ContractViolation(
                        "inconsistent_green_status",
                        f"$.data.results[{index}].green_status",
                        "GREEN requires executed, nonempty, coherent passed counts and zero failure, inconclusive, not-run, unresolved, or error evidence.",
                    )
                )
    if data.get("outcome") == "passed":
        if selected_ids is None:
            selected_results = list(result_by_id.values())
            complete = bool(selected_results) or not results
        else:
            complete = selected_ids.issubset(result_by_id)
            selected_results = [
                result_by_id[entry_id]
                for entry_id in selected_ids
                if entry_id in result_by_id
            ]
        if not complete or any(
            result.get("green_status") != "green"
            or not _suite_result_is_green(result)
            for result in selected_results
        ):
            violations.append(
                ContractViolation(
                    "inconsistent_suite_outcome",
                    "$.data.outcome",
                    "A passed suite outcome requires every selected result to be GREEN and passed.",
                )
            )
    summary = data.get("summary")
    if isinstance(summary, Mapping):
        total = summary.get("total")
        green = summary.get("green")
        not_green = summary.get("not_green")
        if all(isinstance(item, int) for item in (total, green, not_green)):
            if green + not_green != total:
                violations.append(
                    ContractViolation(
                        "inconsistent_summary",
                        "$.data.summary",
                        "green + not_green must equal total.",
                    )
                )
    return violations


def _suite_result_is_green(result: Mapping[str, Any]) -> bool:
    count_fields = (
        "total_tests",
        "passed_tests",
        "failed_tests",
        "inconclusive_tests",
        "not_run_tests",
    )
    counts = {field: result.get(field) for field in count_fields}
    if not all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in counts.values()
    ):
        return False
    coherent = counts["total_tests"] == sum(
        counts[field]
        for field in (
            "passed_tests",
            "failed_tests",
            "inconclusive_tests",
            "not_run_tests",
        )
    )
    return (
        result.get("executed") is True
        and counts["total_tests"] > 0
        and coherent
        and result.get("outcome") == "passed"
        and not result.get("error")
        and counts["failed_tests"] == 0
        and counts["inconclusive_tests"] == 0
        and counts["not_run_tests"] == 0
        and result.get("unresolved_review_count") == 0
    )


def _execution_count_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    summary = data.get("summary") or data.get("parsed_result")
    case_results = data.get("case_results")
    if not isinstance(summary, Mapping) or not isinstance(case_results, list):
        return []
    total = summary.get("total")
    if isinstance(total, int) and total != len(case_results):
        return [
            ContractViolation(
                "inconsistent_summary",
                "$.data.summary.total" if "summary" in data else "$.data.parsed_result.total",
                "Summary total must equal the number of case results.",
            )
        ]
    return []


def _test_execution_report_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    violations = _execution_count_semantic_violations(payload)
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return violations
    function = data.get("function")
    status = function.get("status") if isinstance(function, Mapping) else None
    canonical = {outcome.value for outcome in RunOutcome}
    if isinstance(status, str) and status not in canonical:
        violations.append(
            ContractViolation(
                "invalid_run_outcome",
                "$.data.function.status",
                f"Execution status must be a canonical RunOutcome; received {status!r}.",
                "blocking",
            )
        )
    return violations


def _evidence_manifest_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    summary = data.get("summary")
    if not isinstance(summary, Mapping):
        return []
    violations: list[ContractViolation] = []
    status = summary.get("test_execution_status")
    canonical = {outcome.value for outcome in RunOutcome}
    if isinstance(status, str) and status not in canonical:
        violations.append(
            ContractViolation(
                "invalid_run_outcome",
                "$.data.summary.test_execution_status",
                f"Execution status must be a canonical RunOutcome; received {status!r}.",
                "blocking",
            )
        )
    total = summary.get("total_tests")
    passed = summary.get("passed_tests")
    failed = summary.get("failed_tests")
    inconclusive = summary.get("inconclusive_tests")
    counts = (total, passed, failed, inconclusive)
    if all(isinstance(value, int) for value in counts):
        accounted = passed + failed + inconclusive
        if accounted > total:
            violations.append(
                ContractViolation(
                    "inconsistent_summary",
                    "$.data.summary.total_tests",
                    "Outcome counts cannot exceed total_tests.",
                    "blocking",
                )
            )
    green_counts_are_consistent = (
        isinstance(total, int)
        and isinstance(passed, int)
        and isinstance(failed, int)
        and isinstance(inconclusive, int)
        and total > 0
        and passed == total
        and failed == 0
        and inconclusive == 0
    )
    if summary.get("test_green") is True and (
        status != RunOutcome.PASSED.value or not green_counts_are_consistent
    ):
        violations.append(
            ContractViolation(
                "inconsistent_summary",
                "$.data.summary.test_green",
                "test_green requires a non-empty passed outcome with every test passed and no failed or inconclusive tests.",
                "blocking",
            )
        )
    if summary.get("ready_for_review") is True:
        evidence_items = [
            item
            for field in (
                "source_files",
                "generated_files",
                "build_reports",
                "test_reports",
                "logs",
            )
            for item in (data.get(field) or [])
            if isinstance(item, Mapping) and item.get("required") is True
        ]
        if any(
            item.get("exists") is not True
            or item.get("integrity_status") != "valid"
            for item in evidence_items
        ):
            violations.append(
                ContractViolation(
                    "inconsistent_readiness",
                    "$.data.summary.ready_for_review",
                    "ready_for_review requires every required evidence file to exist with valid integrity.",
                    "blocking",
                )
            )
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

    violations.extend(_test_spec_authority_violations(data))
    cases = [
        (collection, index, case)
        for collection in ("test_cases", "additional_case_candidates")
        for index, case in enumerate(data.get(collection) or [])
        if isinstance(case, Mapping)
    ]
    case_ids = [
        str(case["test_case_id"])
        for _collection, _index, case in cases
        if case.get("test_case_id")
    ]
    seen_case_ids: set[str] = set()
    for collection, index, case in cases:
        case_id = str(case.get("test_case_id") or "")
        if case_id and case_id in seen_case_ids:
            violations.append(
                ContractViolation(
                    "duplicate_id",
                    f"$.data.{collection}[{index}].test_case_id",
                    f"Duplicate test_case_id: {case_id}",
                )
            )
        seen_case_ids.add(case_id)
    known_case_ids = set(case_ids)
    coverage_summary = data.get("coverage_summary")
    coverage_ids: set[str] = set()
    if isinstance(coverage_summary, Mapping):
        mapping = coverage_summary.get("coverage_to_test_cases")
        if isinstance(mapping, Mapping):
            coverage_ids.update(str(item) for item in mapping)
            for coverage_id, references in mapping.items():
                if isinstance(references, Sequence) and not isinstance(references, str):
                    for reference in references:
                        if str(reference) not in known_case_ids:
                            violations.append(
                                ContractViolation(
                                    "invalid_case_reference",
                                    f"$.data.coverage_summary.coverage_to_test_cases.{coverage_id}",
                                    f"Unknown test_case_id reference: {reference}",
                                )
                            )
        uncovered = coverage_summary.get("uncovered_coverage_ids")
        if isinstance(uncovered, list):
            coverage_ids.update(str(item) for item in uncovered)

    function = data.get("function")
    function_name = (
        str(function.get("name") or "") if isinstance(function, Mapping) else ""
    )
    known_reviews = {str(item) for item in data.get("review_item_ids") or []}
    known_dependencies = {
        str(item)
        for item in (data.get("generation_policy") or {}).get("dependency_ids", [])
    }
    for json_path, key, reference in _test_spec_reference_values(data):
        if key in {"review_item_id", "review_item_ids"} and reference not in known_reviews:
            violations.append(
                ContractViolation(
                    "invalid_review_reference",
                    json_path,
                    f"Unknown review_item_id reference: {reference}",
                )
            )
        if key in {"dependency_id", "dependency_ids", "related_dependency_id"} and reference not in known_dependencies:
            violations.append(
                ContractViolation(
                    "invalid_dependency_reference",
                    json_path,
                    f"Unknown dependency_id reference: {reference}",
                )
            )

    executable_ids = {
        str(case.get("test_case_id") or "")
        for collection, _index, case in cases
        if collection == "test_cases"
    }
    for unresolved_index, unresolved in enumerate(data.get("unresolved_items") or []):
        if not isinstance(unresolved, Mapping) or not _blocking_unresolved_item(unresolved):
            continue
        for reference_index, reference in enumerate(
            unresolved.get("related_test_case_ids") or []
        ):
            if str(reference) in executable_ids:
                violations.append(
                    ContractViolation(
                        "blocking_unresolved_executable",
                        f"$.data.unresolved_items[{unresolved_index}].related_test_case_ids[{reference_index}]",
                        f"Blocking unresolved item references executable test case: {reference}",
                        "blocking",
                    )
                )

    for collection, case_index, case in cases:
        target_function = case.get("target_function")
        if target_function is not None and str(target_function) != function_name:
            violations.append(
                ContractViolation(
                    "target_function_mismatch",
                    f"$.data.{collection}[{case_index}].target_function",
                    "Case target_function must match the top-level function name.",
                    "blocking",
                )
            )
        links = case.get("coverage_links")
        if isinstance(links, list):
            for link_index, link in enumerate(links):
                if not isinstance(link, Mapping) or not link.get("coverage_id"):
                    continue
                coverage_id = str(link["coverage_id"])
                if coverage_id not in coverage_ids:
                    violations.append(
                        ContractViolation(
                            "invalid_coverage_reference",
                            f"$.data.{collection}[{case_index}].coverage_links[{link_index}].coverage_id",
                            f"Unknown coverage_id reference: {coverage_id}",
                        )
                    )
        if collection == "test_cases":
            violations.extend(_test_spec_executable_violations(case, case_index))
    return violations


_TEST_SPEC_AUTHORITY_FIELDS = {
    "approved",
    "approval",
    "approval_status",
    "is_approved",
    "review_status",
    "review_decision",
}
_TEST_SPEC_PLACEHOLDER_PREFIXES = ("TBD", "UNKNOWN", "UNRESOLVED", "TODO")


def _test_spec_authority_violations(
    value: Any,
    path: str = "$.data",
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in _TEST_SPEC_AUTHORITY_FIELDS:
                violations.append(
                    ContractViolation(
                        "embedded_review_authority",
                        child_path,
                        "Approval and review status belong only to review_decisions.json; store review-item references instead.",
                    )
                )
            violations.extend(_test_spec_authority_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(
                _test_spec_authority_violations(child, f"{path}[{index}]")
            )
    return violations


def _test_spec_reference_values(value: Any, path: str = "$.data"):
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in {
                "review_item_id",
                "review_item_ids",
                "dependency_id",
                "dependency_ids",
                "related_dependency_id",
            }:
                values = child if isinstance(child, list) else [child]
                for index, item in enumerate(values):
                    if item is not None and str(item):
                        suffix = f"[{index}]" if isinstance(child, list) else ""
                        yield child_path + suffix, key, str(item)
            yield from _test_spec_reference_values(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _test_spec_reference_values(child, f"{path}[{index}]")


def _blocking_unresolved_item(item: Mapping[str, Any]) -> bool:
    if item.get("blocking") is False:
        return False
    severity = str(item.get("severity") or "blocking").lower()
    return severity not in {"info", "warning", "non_blocking"}


def _test_spec_executable_violations(
    case: Mapping[str, Any],
    case_index: int,
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    observations = case.get("expected_observations")
    resolved_oracles = 0
    if isinstance(observations, list):
        for observation in observations:
            if not isinstance(observation, Mapping):
                continue
            value = observation.get("expected_expression")
            if not _unresolved_test_spec_value(value):
                resolved_oracles += 1
    if resolved_oracles == 0:
        violations.append(
            ContractViolation(
                "missing_executable_oracle",
                f"$.data.test_cases[{case_index}].expected_observations",
                "Executable test cases require at least one resolved oracle.",
                "blocking",
            )
        )
    for collection, field_name in (
        ("input_assignments", "value_expression"),
        ("state_setups", "value_expression"),
        ("stub_setups", "value_expression"),
        ("expected_observations", "expected_expression"),
    ):
        for item_index, item in enumerate(case.get(collection) or []):
            if not isinstance(item, Mapping):
                continue
            if collection == "stub_setups" and item.get("setup_kind") in {
                "call_count_observation",
                "argument_capture",
            }:
                continue
            if _unresolved_test_spec_value(item.get(field_name)):
                violations.append(
                    ContractViolation(
                        "unresolved_executable_value",
                        f"$.data.test_cases[{case_index}].{collection}[{item_index}].{field_name}",
                        "Executable test cases require resolved values and oracles.",
                        "blocking",
                    )
                )
    return violations


def _unresolved_test_spec_value(value: Any) -> bool:
    normalized = str(value or "").strip().upper()
    return not normalized or normalized.startswith(_TEST_SPEC_PLACEHOLDER_PREFIXES)


def _timestamp_violation(value: Any, path: str) -> list[ContractViolation]:
    if not isinstance(value, str):
        return []
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None and parsed.tzinfo is not None:
        return []
    return [
        ContractViolation(
            "invalid_timestamp",
            path,
            "Timestamp must be an ISO-8601 value with an explicit UTC offset.",
        )
    ]


def _review_decisions_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    violations: list[ContractViolation] = []
    decisions = data.get("decisions")
    if isinstance(decisions, list):
        for index, decision in enumerate(decisions):
            if isinstance(decision, Mapping):
                violations.extend(
                    _timestamp_violation(
                        decision.get("decided_at"),
                        f"$.data.decisions[{index}].decided_at",
                    )
                )
                references = decision.get("subject_artifacts")
                declared = decision.get("subject_fingerprint")
                if isinstance(references, list) and isinstance(declared, str):
                    actual = subject_fingerprint(references)
                    if declared != actual:
                        violations.append(
                            ContractViolation(
                                "invalid_subject_fingerprint",
                                f"$.data.decisions[{index}].subject_fingerprint",
                                "subject_fingerprint must match the exact canonical subject references.",
                                "blocking",
                            )
                        )
    return violations


def _state_setup_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    setups = data.get("state_setups")
    if not isinstance(setups, list):
        return []
    violations: list[ContractViolation] = []
    for index, setup in enumerate(setups):
        if not isinstance(setup, Mapping):
            continue
        method = setup.get("setup_method_hint")
        invalid = False
        if method == "fixture_pointer":
            invalid = not setup.get("fixture_declarations") or not setup.get(
                "setup_statements"
            )
        elif method == "not_directly_accessible":
            invalid = not bool(setup.get("review_required"))
        if invalid:
            violations.append(
                ContractViolation(
                    "invalid_state_setup",
                    f"$.data.state_setups[{index}]",
                    f"State setup method {method!r} lacks its required review or fixture evidence.",
                )
            )
    return violations


def _reanalysis_snapshot_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    violations = _timestamp_violation(data.get("created_at"), "$.data.created_at")
    producer = payload.get("producer")
    if (
        isinstance(producer, Mapping)
        and data.get("producer_version")
        and data.get("producer_version") != producer.get("version")
    ):
        violations.append(
            ContractViolation(
                "invalid_reference",
                "$.data.producer_version",
                "Snapshot producer_version must match the envelope producer version.",
            )
        )
    versions = data.get("contract_versions")
    if isinstance(versions, Mapping):
        for name, version in versions.items():
            try:
                kind = ArtifactKind(str(name))
            except ValueError:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.contract_versions.{name}",
                        f"Unknown artifact contract: {name}",
                    )
                )
                continue
            if version != get_contract(kind).current_version:
                violations.append(
                    ContractViolation(
                        "unsupported_version",
                        f"$.data.contract_versions.{name}",
                        f"Unsupported {name} contract version: {version}",
                    )
                )
    return violations


def _expected_artifact_reference_violations(
    payload: Mapping[str, Any],
    field: str,
    expected_kind: ArtifactKind,
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    reference = data.get(field)
    if not isinstance(reference, Mapping):
        return []
    actual = reference.get("artifact_kind")
    if actual == expected_kind.value:
        return []
    return [
        ContractViolation(
            "invalid_reference",
            f"$.data.{field}.artifact_kind",
            f"{field} must reference {expected_kind.value}; received {actual!r}.",
        )
    ]


def _latest_run_pointer_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    violations = _expected_artifact_reference_violations(
        payload,
        "execution_report",
        ArtifactKind.TEST_EXECUTION_REPORT,
    )
    if isinstance(data, Mapping):
        violations.extend(_timestamp_violation(data.get("updated_at"), "$.data.updated_at"))
    return violations


def _latest_evidence_pointer_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    violations = _expected_artifact_reference_violations(
        payload,
        "evidence_manifest",
        ArtifactKind.EVIDENCE_MANIFEST,
    )
    if isinstance(data, Mapping):
        violations.extend(_timestamp_violation(data.get("updated_at"), "$.data.updated_at"))
    return violations


def _latest_suite_run_pointer_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    violations = _expected_artifact_reference_violations(
        payload,
        "suite_run_report",
        ArtifactKind.SUITE_RUN_REPORT,
    )
    if isinstance(data, Mapping):
        violations.extend(_timestamp_violation(data.get("updated_at"), "$.data.updated_at"))
    return violations


def _evidence_source_run_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    violations = _expected_artifact_reference_violations(
        payload,
        "execution_report",
        ArtifactKind.TEST_EXECUTION_REPORT,
    )
    if isinstance(data, Mapping):
        violations.extend(_timestamp_violation(data.get("created_at"), "$.data.created_at"))
    return violations


def _dsw_semantic_violations(
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    workspaces = data.get("workspaces")
    if not isinstance(workspaces, list):
        return []
    violations: list[ContractViolation] = []
    workspace_paths: set[str] = set()
    for workspace_index, workspace in enumerate(workspaces):
        if not isinstance(workspace, Mapping):
            continue
        dsw_path = workspace.get("dsw_path")
        if isinstance(dsw_path, str):
            if dsw_path in workspace_paths:
                violations.append(
                    ContractViolation(
                        "duplicate_id",
                        "$.data.workspaces",
                        f"Duplicate dsw_path: {dsw_path}",
                    )
                )
            workspace_paths.add(dsw_path)
        projects = workspace.get("projects")
        names: set[str] = set()
        if isinstance(projects, list):
            for project_index, project in enumerate(projects):
                if not isinstance(project, Mapping):
                    continue
                name = project.get("name")
                if isinstance(name, str):
                    if name in names:
                        violations.append(
                            ContractViolation(
                                "duplicate_id",
                                f"$.data.workspaces[{workspace_index}].projects",
                                f"Duplicate project name: {name}",
                            )
                        )
                    names.add(name)
                if (
                    project.get("dsp_path")
                    and project.get("dsp_path_normalized")
                    != project.get("dsp_path")
                ):
                    violations.append(
                        ContractViolation(
                            "invalid_reference",
                            f"$.data.workspaces[{workspace_index}].projects[{project_index}].dsp_path_normalized",
                            "dsp_path_normalized must match dsp_path.",
                        )
                    )
        dependencies = workspace.get("dependencies")
        if isinstance(dependencies, list):
            for dependency_index, dependency in enumerate(dependencies):
                if not isinstance(dependency, Mapping):
                    continue
                for field in ("from_project", "to_project"):
                    reference = dependency.get(field)
                    if reference and str(reference) not in names:
                        violations.append(
                            ContractViolation(
                                "invalid_reference",
                                f"$.data.workspaces[{workspace_index}].dependencies[{dependency_index}].{field}",
                                f"Unknown DSW project reference: {reference}",
                            )
                        )
    warnings = data.get("warnings")
    if isinstance(warnings, list):
        for index, warning in enumerate(warnings):
            if not isinstance(warning, Mapping):
                continue
            dsw_path = warning.get("dsw_path")
            if dsw_path and str(dsw_path) not in workspace_paths:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.warnings[{index}].dsw_path",
                        f"Unknown warning workspace: {dsw_path}",
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


_ARTIFACT_SEMANTIC_VALIDATORS: dict[
    str,
    Callable[[Mapping[str, Any]], list[ContractViolation]],
] = {
    ArtifactKind.CLI_RESULT.value: _cli_result_semantic_violations,
    ArtifactKind.INPUT_REQUEST.value: _no_artifact_semantic_violations,
    ArtifactKind.DSW_DISCOVERY.value: _dsw_semantic_violations,
    ArtifactKind.SOURCE_MEMBERSHIP.value: _no_artifact_semantic_violations,
    ArtifactKind.PROJECT_MEMBERSHIP.value: _no_artifact_semantic_violations,
    ArtifactKind.BUILD_CONTEXT.value: _no_artifact_semantic_violations,
    ArtifactKind.SOURCE_DIGEST.value: _no_artifact_semantic_violations,
    ArtifactKind.FUNCTION_LOCATION.value: _no_artifact_semantic_violations,
    ArtifactKind.FUNCTION_SIGNATURE.value: _no_artifact_semantic_violations,
    ArtifactKind.GLOBAL_ACCESS.value: _no_artifact_semantic_violations,
    ArtifactKind.CALL_REPORT.value: _call_report_semantic_violations,
    ArtifactKind.COVERAGE_DESIGN.value: _coverage_semantic_violations,
    ArtifactKind.BOUNDARY_CANDIDATES.value: _boundary_semantic_violations,
    ArtifactKind.DEPENDENCY_POLICY.value: _no_artifact_semantic_violations,
    ArtifactKind.TEST_SPEC.value: _test_spec_semantic_violations,
    ArtifactKind.HARNESS_SKELETON_REPORT.value: _no_artifact_semantic_violations,
    ArtifactKind.BUILD_WORKSPACE_REPORT.value: _no_artifact_semantic_violations,
    ArtifactKind.BUILD_PROBE_REPORT.value: _no_artifact_semantic_violations,
    ArtifactKind.BUILD_COMPLETION_PLAN.value: _build_completion_semantic_violations,
    ArtifactKind.BUILD_COMPLETION_ITERATION.value: _no_artifact_semantic_violations,
    ArtifactKind.BUILD_COMPLETION_HISTORY.value: _no_artifact_semantic_violations,
    ArtifactKind.TEST_EXECUTION_REPORT.value: _test_execution_report_semantic_violations,
    ArtifactKind.TEST_RESULT.value: _execution_count_semantic_violations,
    ArtifactKind.EVIDENCE_MANIFEST.value: _evidence_manifest_semantic_violations,
    ArtifactKind.FUNCTION_DOSSIER.value: _dossier_semantic_violations,
    ArtifactKind.DOSSIER_MANIFEST.value: _dossier_semantic_violations,
    ArtifactKind.STATE_SETUP_REFLECTION.value: _state_setup_semantic_violations,
    ArtifactKind.REVIEW_DECISIONS.value: _review_decisions_semantic_violations,
    ArtifactKind.CHANGE_IMPACT.value: _no_artifact_semantic_violations,
    ArtifactKind.TEST_CASE_RECONCILIATION.value: _partition_semantic_violations,
    ArtifactKind.REGRESSION_SELECTION.value: _partition_semantic_violations,
    ArtifactKind.REANALYSIS_SNAPSHOT.value: _reanalysis_snapshot_semantic_violations,
    ArtifactKind.SUITE_MANIFEST.value: _no_artifact_semantic_violations,
    ArtifactKind.SUITE_RUN_REPORT.value: _suite_run_semantic_violations,
    ArtifactKind.LATEST_RUN_POINTER.value: _latest_run_pointer_semantic_violations,
    ArtifactKind.LATEST_EVIDENCE_POINTER.value: _latest_evidence_pointer_semantic_violations,
    ArtifactKind.LATEST_SUITE_RUN_POINTER.value: _latest_suite_run_pointer_semantic_violations,
    ArtifactKind.EVIDENCE_SOURCE_RUN.value: _evidence_source_run_semantic_violations,
    ArtifactKind.PROMPT_PACK.value: _no_artifact_semantic_violations,
    ArtifactKind.QUICK_SUMMARY.value: _no_artifact_semantic_violations,
}
