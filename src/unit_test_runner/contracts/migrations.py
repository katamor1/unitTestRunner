from __future__ import annotations

import copy
import hashlib
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from unit_test_runner import __version__

from .kinds import ArtifactKind
from .path_policy import (
    ContractPathPolicy,
    iter_contract_path_values,
    path_policy_for,
)
from .registry import get_contract


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ArtifactKindMismatchError(ValueError):
    code = "artifact_kind_mismatch"

    def __init__(self, expected_kind: ArtifactKind, actual_kind: Any) -> None:
        self.expected_kind = expected_kind.value
        self.actual_kind = actual_kind
        super().__init__(
            f"{self.code}: expected {self.expected_kind}; received {actual_kind!r}."
        )


def migrate_payload(
    kind: ArtifactKind,
    payload: Mapping[str, Any],
    *,
    target_version: str,
) -> dict[str, Any]:
    declared_kind = payload.get("artifact_kind")
    if declared_kind is not None and declared_kind != kind.value:
        raise ArtifactKindMismatchError(kind, declared_kind)

    contract = get_contract(kind)
    if target_version != contract.current_version:
        raise ValueError(
            f"Unsupported migration target for {kind.value}: {target_version}"
        )

    source = copy.deepcopy(dict(payload))
    source_version = str(source.get("schema_version") or "")
    if source_version == target_version:
        return source
    if source_version not in contract.compatible_source_versions:
        raise ValueError(
            f"Unsupported source version for {kind.value}: {source_version or '<missing>'}"
        )

    if kind is ArtifactKind.TEST_SPEC:
        if source_version == "1.0.0":
            return _migrate_test_spec_v1_0(source, target_version)
        return _migrate_test_spec_v0_1(source, target_version)

    subject = _legacy_subject(source)
    if kind is ArtifactKind.TEST_SPEC:
        data = _migrate_test_spec_data(source, subject)
    elif kind is ArtifactKind.CLI_RESULT:
        data = _migrate_cli_result_data(source)
    elif kind is ArtifactKind.FUNCTION_DOSSIER:
        data = _migrate_function_dossier_data(source, subject)
    elif kind is ArtifactKind.BUILD_CONTEXT:
        data = _migrate_build_context_data(source)
    elif kind is ArtifactKind.SUITE_MANIFEST:
        data = _migrate_suite_manifest_data(source)
    elif kind is ArtifactKind.SUITE_RUN_REPORT:
        data = _migrate_suite_run_report_data(source)
    else:
        data = _migrate_generic_data(source)

    migration_metadata = {
        "source_version": source_version,
        "source_artifact_kind": source.get("artifact_kind"),
    }
    path_migrations = _migrate_contract_paths(kind, source, data, subject)
    if path_migrations:
        migration_metadata["path_migrations"] = path_migrations
    return {
        "artifact_kind": kind.value,
        "schema_version": target_version,
        "producer": {
            "name": "unit-test-runner",
            "version": __version__,
        },
        "subject": subject,
        "data": data,
        "extensions": {"migration": migration_metadata},
    }


def _legacy_subject(payload: Mapping[str, Any]) -> dict[str, str]:
    source = payload.get("source")
    source_info = source if isinstance(source, Mapping) else {}
    target = payload.get("target")
    target_info = target if isinstance(target, Mapping) else {}
    raw_source_path = _legacy_source_path_value(payload)
    source_path = _known_relative_path(raw_source_path)
    source_sha256 = _known_sha256(
        source_info.get("sha256") or payload.get("source_sha256")
    )

    function = payload.get("function")
    function_info = function if isinstance(function, Mapping) else {}
    raw_function_name = (
        function_info.get("name")
        or payload.get("function_name")
        or payload.get("target_function")
        or target_info.get("function")
    )
    function_name = str(raw_function_name) if raw_function_name else None
    subject: dict[str, str] = {}
    if source_path is not None:
        subject["source_path"] = source_path
    if source_sha256 is not None:
        subject["source_sha256"] = source_sha256
    if source_path is not None and function_name is not None:
        identity_seed = f"{source_path}\0{function_name}".encode("utf-8")
        suffix = hashlib.sha256(identity_seed).hexdigest()[:12]
        slug = re.sub(r"[^a-z0-9]+", "_", function_name.lower()).strip("_")
        subject["function_id"] = f"fn_{slug or 'function'}_{suffix}"
    return subject


def _legacy_source_path_value(payload: Mapping[str, Any]) -> Any:
    source = payload.get("source")
    source_info = source if isinstance(source, Mapping) else {}
    target = payload.get("target")
    target_info = target if isinstance(target, Mapping) else {}
    return (
        source_info.get("path")
        or payload.get("source_path")
        or target_info.get("source")
        or payload.get("workspace")
    )


def _known_sha256(value: Any) -> str | None:
    candidate = str(value or "").lower()
    if not _SHA256_RE.fullmatch(candidate) or candidate == "0" * 64:
        return None
    return candidate


def _known_relative_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    normalized = text.replace("\\", "/")
    windows = PureWindowsPath(text)
    posix = PurePosixPath(normalized)
    if (
        not normalized
        or windows.is_absolute()
        or posix.is_absolute()
        or ".." in posix.parts
        or re.match(r"^[A-Za-z]:", text)
    ):
        return None
    return normalized


def _migrate_test_spec_data(
    payload: Mapping[str, Any],
    subject: Mapping[str, str],
) -> dict[str, Any]:
    function = payload.get("function")
    function_info = function if isinstance(function, Mapping) else {}
    raw_function_name = function_info.get("name") or payload.get("function_name")
    function_name = str(raw_function_name) if raw_function_name else None
    coverage_summary = payload.get("coverage_summary")
    if not isinstance(coverage_summary, Mapping):
        coverage_summary = {
            "total_coverage_items": 0,
            "covered_by_design_count": 0,
            "uncovered_coverage_ids": [],
            "coverage_to_test_cases": {},
        }
    unresolved = payload.get("unresolved_items")
    unresolved_items = list(unresolved) if isinstance(unresolved, list) else []
    source_data: dict[str, Any] = {}
    if subject.get("source_path"):
        source_data["path"] = subject["source_path"]
    if subject.get("source_sha256"):
        source_data["sha256"] = subject["source_sha256"]
    function_data: dict[str, Any] = {}
    if subject.get("function_id"):
        function_data["function_id"] = subject["function_id"]
    if function_name is not None:
        function_data["name"] = function_name
    signature_sha256 = _known_sha256(function_info.get("signature_sha256"))
    if signature_sha256 is not None:
        function_data["signature_sha256"] = signature_sha256
    data = {
        "revision": int(payload.get("revision") or 1),
        "source": source_data,
        "function": function_data,
        "generated_from": [],
        "generation_policy": copy.deepcopy(payload.get("generation_policy") or {}),
        "test_cases": copy.deepcopy(payload.get("test_cases") or []),
        "additional_case_candidates": copy.deepcopy(
            payload.get("additional_case_candidates") or []
        ),
        "coverage_summary": copy.deepcopy(dict(coverage_summary)),
        "unresolved_items": copy.deepcopy(unresolved_items),
        "warnings": copy.deepcopy(payload.get("warnings") or []),
        "review_item_ids": [
            str(item["item_id"])
            for item in unresolved_items
            if isinstance(item, Mapping) and item.get("item_id")
        ],
    }
    spec_id = payload.get("spec_id")
    if spec_id:
        data["spec_id"] = str(spec_id)
    elif subject.get("function_id"):
        data["spec_id"] = f"spec-{subject['function_id'].removeprefix('fn_')}"
    return data


_TEST_SPEC_V1_1_CASE_FIELDS = {
    "test_case_id",
    "title",
    "target_function",
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
_TEST_SPEC_AUTHORITY_FIELDS = {
    "approved",
    "approval",
    "approval_status",
    "is_approved",
    "review_status",
    "review_decision",
}

_TEST_SPEC_V0_1_TOP_LEVEL_FIELDS = {
    "artifact_kind",
    "schema_version",
    "producer",
    "extensions",
    "spec_id",
    "revision",
    "source",
    "function",
    "generated_from",
    "generation_policy",
    "test_cases",
    "additional_case_candidates",
    "coverage_summary",
    "unresolved_items",
    "warnings",
    "review_item_ids",
}


def _migrate_test_spec_v0_1(
    payload: Mapping[str, Any],
    target_version: str,
) -> dict[str, Any]:
    authority_path = _first_test_spec_authority_path(payload, "$")
    if authority_path is not None:
        raise ValueError(
            f"Lossless test_spec v0.1 migration cannot preserve embedded review authority at {authority_path}."
        )
    unknown = set(payload) - _TEST_SPEC_V0_1_TOP_LEVEL_FIELDS
    if unknown:
        names = ", ".join(sorted(str(item) for item in unknown))
        raise ValueError(
            f"Lossless test_spec v0.1 migration cannot represent unknown top-level fields: {names}."
        )
    _validate_test_spec_case_fields(payload, version="v0.1")
    producer = payload.get("producer")
    if not isinstance(producer, Mapping):
        raise ValueError(
            "migration_requires_fabrication at $.producer: lossless v0.1 migration requires supplied producer provenance."
        )
    source = payload.get("source")
    function = payload.get("function")
    if not isinstance(source, Mapping) or not isinstance(function, Mapping):
        raise ValueError(
            "migration_requires_fabrication at $.source/$.function: lossless v0.1 migration requires supplied identity."
        )
    required = {
        "$.spec_id": payload.get("spec_id"),
        "$.revision": payload.get("revision"),
        "$.source.path": source.get("path"),
        "$.source.sha256": source.get("sha256"),
        "$.function.function_id": function.get("function_id"),
        "$.function.name": function.get("name"),
        "$.function.signature_sha256": function.get("signature_sha256"),
    }
    missing = [path for path, value in required.items() if value is None or value == ""]
    if missing:
        raise ValueError(
            "migration_requires_fabrication: missing " + ", ".join(missing)
        )
    data_fields = (
        "spec_id",
        "revision",
        "generated_from",
        "generation_policy",
        "test_cases",
        "additional_case_candidates",
        "coverage_summary",
        "unresolved_items",
        "warnings",
        "review_item_ids",
    )
    missing_data = [field for field in data_fields if field not in payload]
    if missing_data:
        raise ValueError(
            "migration_requires_fabrication: missing "
            + ", ".join(f"$.{field}" for field in missing_data)
        )
    extensions = _migration_extensions(
        payload.get("extensions"),
        source_version="0.1",
        source_artifact_kind=payload.get("artifact_kind"),
    )
    data = {field: copy.deepcopy(payload[field]) for field in data_fields}
    data["source"] = copy.deepcopy(dict(source))
    data["function"] = copy.deepcopy(dict(function))
    return {
        "artifact_kind": ArtifactKind.TEST_SPEC.value,
        "schema_version": target_version,
        "producer": copy.deepcopy(dict(producer)),
        "subject": {
            "function_id": str(function["function_id"]),
            "source_path": str(source["path"]),
            "source_sha256": str(source["sha256"]),
        },
        "data": data,
        "extensions": extensions,
    }


def _migrate_test_spec_v1_0(
    payload: Mapping[str, Any],
    target_version: str,
) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("test_spec v1.0 data must be an object.")
    _validate_test_spec_case_fields(data, version="v1.0", data_prefix="$.data")
    authority_path = _first_test_spec_authority_path(data)
    if authority_path is not None:
        raise ValueError(
            f"Lossless test_spec v1.0 migration cannot preserve embedded review authority at {authority_path}; review_decisions.json is authoritative."
        )
    migrated = copy.deepcopy(dict(payload))
    migrated["schema_version"] = target_version
    migrated["extensions"] = _migration_extensions(
        migrated.get("extensions"),
        source_version="1.0.0",
        source_artifact_kind=ArtifactKind.TEST_SPEC.value,
    )
    return migrated


def _validate_test_spec_case_fields(
    value: Mapping[str, Any],
    *,
    version: str,
    data_prefix: str = "$",
) -> None:
    for collection in ("test_cases", "additional_case_candidates"):
        cases = value.get(collection)
        if not isinstance(cases, list):
            continue
        for index, case in enumerate(cases):
            if not isinstance(case, Mapping):
                continue
            unknown = set(case) - _TEST_SPEC_V1_1_CASE_FIELDS
            if unknown:
                names = ", ".join(sorted(str(item) for item in unknown))
                raise ValueError(
                    f"Lossless test_spec {version} migration cannot represent unknown fields at {data_prefix}.{collection}[{index}]: {names}."
                )


def _migration_extensions(
    extensions: Any,
    *,
    source_version: str,
    source_artifact_kind: Any,
) -> dict[str, Any]:
    if extensions is None:
        normalized: dict[str, Any] = {}
    elif isinstance(extensions, Mapping):
        normalized = copy.deepcopy(dict(extensions))
    else:
        raise ValueError("Lossless test_spec migration requires extensions to be an object.")
    if "migration" in normalized:
        raise ValueError(
            "Lossless test_spec migration cannot overwrite existing extensions.migration metadata."
        )
    normalized["migration"] = {
        "source_version": source_version,
        "source_artifact_kind": source_artifact_kind,
        "in_memory_only": True,
    }
    return normalized


def _first_test_spec_authority_path(value: Any, path: str = "$.data") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in _TEST_SPEC_AUTHORITY_FIELDS:
                return child_path
            nested = _first_test_spec_authority_path(child, child_path)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for index, child in enumerate(value):
            nested = _first_test_spec_authority_path(child, f"{path}[{index}]")
            if nested is not None:
                return nested
    return None


def _migrate_cli_result_data(payload: Mapping[str, Any]) -> dict[str, Any]:
    legacy_status = str(payload.get("status") or "")
    top_level_outcomes = {
        "tests_passed": "passed",
        "tests_failed": "failed",
        "tests_timed_out": "timed_out",
        "tests_cancelled": "cancelled",
        "evidence_prepared": "planned",
        "tests_error": "error",
        "error": "error",
        "internal_error": "error",
    }
    data: dict[str, Any] = {
        "lifecycle": "finished",
        "artifacts": [],
        "errors": copy.deepcopy(payload.get("errors") or []),
    }
    if payload.get("command"):
        data["command"] = str(payload["command"])
    nested_outcome = _legacy_cli_nested_outcome(payload)
    if nested_outcome is not None:
        data["outcome"] = nested_outcome
    elif legacy_status in top_level_outcomes:
        data["outcome"] = top_level_outcomes[legacy_status]
    if payload.get("exit_code") is not None:
        data["exit_code"] = int(payload["exit_code"])
    if payload.get("message") is not None:
        data["message"] = str(payload["message"])
    return data


def _legacy_cli_nested_outcome(payload: Mapping[str, Any]) -> str | None:
    legacy_data = payload.get("data")
    if not isinstance(legacy_data, Mapping):
        return None
    for field in ("test_execution", "evidence"):
        nested = legacy_data.get(field)
        if not isinstance(nested, Mapping):
            continue
        outcome = _canonical_run_outcome(nested.get("status"))
        if outcome is not None:
            return outcome
    return None


def _canonical_run_outcome(value: Any) -> str | None:
    candidate = str(value or "")
    aliases = {
        "not_run": "planned",
        "timeout": "timed_out",
    }
    candidate = aliases.get(candidate, candidate)
    if candidate in {
        "planned",
        "passed",
        "failed",
        "blocked",
        "inconclusive",
        "cancelled",
        "timed_out",
        "error",
    }:
        return candidate
    return None


def _migrate_generic_data(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"artifact_kind", "schema_version"}
    }


def _migrate_function_dossier_data(
    payload: Mapping[str, Any],
    subject: Mapping[str, str],
) -> dict[str, Any]:
    data = _migrate_generic_data(payload)
    source_path = subject.get("source_path")
    target = data.get("target")
    if isinstance(target, Mapping) and source_path:
        normalized_target = dict(target)
        normalized_target["source"] = source_path
        data["target"] = normalized_target
    return data


def _migrate_build_context_data(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    wrapped = payload.get("build_context")
    if not isinstance(wrapped, Mapping):
        return _migrate_generic_data(payload)
    data = copy.deepcopy(dict(wrapped))
    for key in ("project", "configuration"):
        if payload.get(key) is not None and key not in data:
            data[key] = copy.deepcopy(payload[key])
    return data


def _migrate_suite_manifest_data(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    data = _migrate_generic_data(payload)
    for key in ("source_root", "dsw_path"):
        if data.get(key) == "":
            data[key] = None
    return data


def _migrate_suite_run_report_data(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    data = _migrate_generic_data(payload)
    data.pop("status", None)
    data["lifecycle"] = "finished"
    migrated_results: list[Any] = []
    outcomes: list[str] = []
    results = data.get("results")
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, Mapping):
                migrated_results.append(result)
                continue
            migrated_result = copy.deepcopy(dict(result))
            outcome = _canonical_run_outcome(
                migrated_result.pop("execution_status", None)
            )
            if outcome is not None:
                migrated_result["outcome"] = outcome
                outcomes.append(outcome)
            migrated_results.append(migrated_result)
        data["results"] = migrated_results
    if outcomes and len(outcomes) == len(migrated_results) and len(set(outcomes)) == 1:
        data["outcome"] = outcomes[0]
    return data


def _migrate_contract_paths(
    kind: ArtifactKind,
    payload: Mapping[str, Any],
    data: dict[str, Any],
    subject: Mapping[str, str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    path_policy = path_policy_for(kind)
    raw_source_path = _legacy_source_path_value(payload)
    data_source = data.get("source")
    if (
        isinstance(raw_source_path, str)
        and _known_relative_path(raw_source_path) is None
        and (
            not isinstance(data_source, Mapping)
            or "path" not in data_source
        )
    ):
        _record_path_migration(
            records,
            "$.data.source.path"
            if isinstance(data_source, Mapping)
            else "$.subject.source_path",
            raw_source_path,
            None,
            verified=False,
            reason="no_workspace_relative_mapping",
        )
    if kind is ArtifactKind.FUNCTION_DOSSIER:
        target = data.get("target")
        if isinstance(target, Mapping):
            original_target = target.get("source")
            if (
                isinstance(original_target, str)
                and _known_relative_path(original_target) is None
            ):
                normalized_target = dict(target)
                migrated_target = subject.get("source_path")
                if migrated_target:
                    normalized_target["source"] = migrated_target
                else:
                    normalized_target.pop("source", None)
                data["target"] = normalized_target
                _record_path_migration(
                    records,
                    "$.data.target.source",
                    original_target,
                    migrated_target,
                    verified=migrated_target is not None,
                    reason=(
                        "matched_to_verified_subject_source"
                        if migrated_target
                        else "no_workspace_relative_mapping"
                    ),
                )
        legacy_function = payload.get("function")
        if isinstance(legacy_function, Mapping):
            original = legacy_function.get("source_path")
            if isinstance(original, str) and _known_relative_path(original) is None:
                subject_source = subject.get("source_path")
                verified = bool(
                    subject_source
                    and _absolute_path_matches_relative(original, subject_source)
                )
                migrated = subject_source if verified else None
                function = data.get("function")
                if isinstance(function, Mapping):
                    normalized_function = dict(function)
                    normalized_function["source_path"] = migrated
                    data["function"] = normalized_function
                _record_path_migration(
                    records,
                    "$.data.function.source_path",
                    original,
                    migrated,
                    verified=verified,
                    reason=(
                        "matched_absolute_suffix_to_relative_dossier_target"
                        if verified
                        else "dossier_function_source_does_not_match_target"
                    ),
                )

    workspace_root: str | None = None
    if kind is ArtifactKind.BUILD_WORKSPACE_REPORT:
        output_root = data.get("output_root")
        if isinstance(output_root, str) and _known_relative_path(output_root) is None:
            workspace_root = output_root
            data["output_root"] = "."
            _record_path_migration(
                records,
                "$.data.output_root",
                output_root,
                ".",
                verified=True,
                reason="build_report_output_root",
            )
            _rewrite_workspace_paths(
                data,
                "$.data",
                workspace_root,
                records,
                path_policy,
            )

    source = data.get("source")
    if isinstance(source, Mapping):
        original = source.get("path")
        if isinstance(original, str) and _known_relative_path(original) is None:
            normalized_source = dict(source)
            verified_source = subject.get("source_path")
            if verified_source:
                normalized_source["path"] = verified_source
                _record_path_migration(
                    records,
                    "$.data.source.path",
                    original,
                    verified_source,
                    verified=True,
                    reason="matched_to_verified_subject_source",
                )
            else:
                normalized_source.pop("path", None)
                _record_path_migration(
                    records,
                    "$.data.source.path",
                    original,
                    None,
                    verified=False,
                    reason="no_workspace_relative_mapping",
                )
            data["source"] = normalized_source

    _rewrite_unverified_paths(data, "$.data", records, path_policy)
    return records


def _rewrite_workspace_paths(
    value: Any,
    json_path: str,
    workspace_root: str,
    records: list[dict[str, Any]],
    path_policy: ContractPathPolicy,
) -> None:
    for path_value in list(
        iter_contract_path_values(value, path_policy, json_path)
    ):
        relative = _relative_to_workspace(path_value.value, workspace_root)
        if (
            relative is not None
            and relative != path_value.value.replace("\\", "/")
        ):
            path_value.container[path_value.key] = relative
            _record_path_migration(
                records,
                path_value.json_path,
                path_value.value,
                relative,
                verified=True,
                reason="relative_to_build_output_root",
            )


def _rewrite_unverified_paths(
    value: Any,
    json_path: str,
    records: list[dict[str, Any]],
    path_policy: ContractPathPolicy,
) -> None:
    path_values = list(iter_contract_path_values(value, path_policy, json_path))
    for path_value in reversed(path_values):
        if not path_value.value:
            continue
        normalized = _known_relative_path(path_value.value)
        if normalized is not None:
            if normalized != path_value.value:
                path_value.container[path_value.key] = normalized
                _record_path_migration(
                    records,
                    path_value.json_path,
                    path_value.value,
                    normalized,
                    verified=True,
                    reason="normalized_relative_path",
                )
            continue
        if path_value.is_list_item:
            path_value.container.pop(path_value.key)
        elif path_value.field_name in path_policy.nullable_scalar_fields:
            path_value.container[path_value.key] = None
        else:
            path_value.container.pop(path_value.key, None)
        _record_path_migration(
            records,
            path_value.json_path,
            path_value.value,
            None,
            verified=False,
            reason="no_workspace_relative_mapping",
        )


def _relative_to_workspace(value: str, workspace_root: str) -> str | None:
    normalized_value = value.replace("\\", "/")
    normalized_root = workspace_root.replace("\\", "/")
    candidates = (
        (PureWindowsPath(value), PureWindowsPath(workspace_root)),
        (PurePosixPath(normalized_value), PurePosixPath(normalized_root)),
    )
    for path, root in candidates:
        if not path.is_absolute() or not root.is_absolute():
            continue
        if ".." in path.parts or ".." in root.parts:
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if ".." in relative.parts:
            continue
        relative_text = relative.as_posix()
        return relative_text or "."
    return None


def _absolute_path_matches_relative(value: str, relative: str) -> bool:
    normalized_value = value.replace("\\", "/")
    normalized_relative = _known_relative_path(relative)
    if normalized_relative is None:
        return False
    windows = PureWindowsPath(value)
    posix = PurePosixPath(normalized_value)
    if not windows.is_absolute() and not posix.is_absolute():
        return False
    relative_parts = tuple(
        part.casefold() for part in PurePosixPath(normalized_relative).parts
    )
    if len(relative_parts) < 2:
        return False
    value_parts = tuple(part.casefold() for part in PurePosixPath(normalized_value).parts)
    return value_parts[-len(relative_parts) :] == relative_parts


def _record_path_migration(
    records: list[dict[str, Any]],
    json_path: str,
    original_value: str,
    migrated_value: str | None,
    *,
    verified: bool,
    reason: str,
) -> None:
    if any(item["json_path"] == json_path for item in records):
        return
    records.append(
        {
            "json_path": json_path,
            "original_value": original_value,
            "migrated_value": migrated_value,
            "verified": verified,
            "reason": reason,
        }
    )
