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
        violations.extend(_common_semantic_violations(kind, payload))
        violations.extend(
            _artifact_semantic_violations(
                contract.semantic_validator,
                payload,
            )
        )
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
    violations.extend(_duplicate_id_violations(builtin_payload))
    violations.extend(_provenance_violations(kind, payload))
    violations.extend(_nested_path_violations(builtin_payload))
    violations.extend(_nested_hash_violations(builtin_payload))
    violations.extend(_subject_consistency_violations(payload))
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
    if isinstance(subject, Mapping):
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
    return violations


_CONTRACT_PATH_KEYS = {
    "path",
    "source_path",
    "masked_source_path",
    "workspace_path",
    "log_file",
    "stdout_log",
    "stderr_log",
    "combined_log",
    "completion_plan",
    "input_probe_report",
    "probe_report",
    "related_file",
    "source_file",
    "header_file",
    "stub_source_path",
    "stub_header_path",
}


def _nested_path_violations(value: Any, path: str = "$") -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if (
                key in _CONTRACT_PATH_KEYS
                and isinstance(child, str)
                and child
                and not _is_relative_contract_path(child)
            ):
                violations.append(
                    ContractViolation(
                        "invalid_relative_path",
                        child_path,
                        f"{key} must be a normalized relative contract path.",
                    )
                )
            violations.extend(_nested_path_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_nested_path_violations(child, f"{path}[{index}]"))
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
        "case_id",
        "switch_id",
        "loop_id",
        "ternary_id",
        "return_id",
        "placeholder_id",
        "hint_id",
        "command_id",
        "review_id",
        "call_id",
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


_RESERVED_SEMANTIC_HOOKS = {
    ArtifactKind.STATE_SETUP_REFLECTION.value,
    ArtifactKind.REVIEW_DECISIONS.value,
    ArtifactKind.REANALYSIS_SNAPSHOT.value,
    ArtifactKind.LATEST_RUN_POINTER.value,
    ArtifactKind.LATEST_EVIDENCE_POINTER.value,
    ArtifactKind.LATEST_SUITE_RUN_POINTER.value,
    ArtifactKind.EVIDENCE_SOURCE_RUN.value,
}


def _artifact_semantic_violations(
    semantic_hook: str,
    payload: Mapping[str, Any],
) -> list[ContractViolation]:
    if semantic_hook in _RESERVED_SEMANTIC_HOOKS:
        return [
            ContractViolation(
                "unsupported_artifact_payload",
                "$.data",
                f"{semantic_hook} has no current public producer contract.",
                "blocking",
            )
        ]
    if semantic_hook == ArtifactKind.TEST_SPEC.value:
        return _test_spec_semantic_violations(payload)
    if semantic_hook in {
        ArtifactKind.FUNCTION_DOSSIER.value,
        ArtifactKind.DOSSIER_MANIFEST.value,
    }:
        return _dossier_semantic_violations(payload)
    if semantic_hook == ArtifactKind.SUITE_RUN_REPORT.value:
        return _suite_run_semantic_violations(payload)
    if semantic_hook == ArtifactKind.CALL_REPORT.value:
        return _call_report_semantic_violations(payload)
    if semantic_hook == ArtifactKind.COVERAGE_DESIGN.value:
        return _coverage_semantic_violations(payload)
    if semantic_hook == ArtifactKind.BOUNDARY_CANDIDATES.value:
        return _boundary_semantic_violations(payload)
    if semantic_hook == ArtifactKind.BUILD_COMPLETION_PLAN.value:
        return _build_completion_semantic_violations(payload)
    if semantic_hook in {
        ArtifactKind.TEST_CASE_RECONCILIATION.value,
        ArtifactKind.REGRESSION_SELECTION.value,
    }:
        return _partition_semantic_violations(payload)
    if semantic_hook in {
        ArtifactKind.TEST_EXECUTION_REPORT.value,
        ArtifactKind.TEST_RESULT.value,
        ArtifactKind.EVIDENCE_MANIFEST.value,
    }:
        return _execution_semantic_violations(payload)
    return []


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
    if selected_ids is not None and isinstance(results, list):
        for index, result in enumerate(results):
            if not isinstance(result, Mapping):
                continue
            entry_id = result.get("entry_id")
            if entry_id and str(entry_id) not in selected_ids:
                violations.append(
                    ContractViolation(
                        "invalid_reference",
                        f"$.data.results[{index}].entry_id",
                        f"Result entry_id was not selected: {entry_id}",
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


def _execution_semantic_violations(
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
