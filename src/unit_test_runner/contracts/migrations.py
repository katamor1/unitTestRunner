from __future__ import annotations

import copy
import hashlib
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from unit_test_runner import __version__

from .kinds import ArtifactKind
from .registry import CURRENT_CONTRACT_VERSION, get_contract


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def migrate_payload(
    kind: ArtifactKind,
    payload: Mapping[str, Any],
    *,
    target_version: str,
) -> dict[str, Any]:
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
    else:
        data = _migrate_generic_data(source)

    migration_metadata = {
        "source_version": source_version,
        "source_artifact_kind": source.get("artifact_kind"),
    }
    original_source_path = _normalize_data_source_path(data, subject)
    if original_source_path is not None:
        migration_metadata["original_source_path"] = original_source_path
    if kind is ArtifactKind.SOURCE_DIGEST:
        original_masked_source_path = _normalize_masked_source_path(data)
        if original_masked_source_path is not None:
            migration_metadata["original_masked_source_path"] = (
                original_masked_source_path
            )
    return {
        "artifact_kind": kind.value,
        "schema_version": CURRENT_CONTRACT_VERSION,
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
    raw_source_path = (
        source_info.get("path")
        or payload.get("source_path")
        or target_info.get("source")
        or payload.get("workspace")
    )
    source_path = (
        _compatible_relative_path(str(raw_source_path))
        if raw_source_path
        else None
    )
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


def _known_sha256(value: Any) -> str | None:
    candidate = str(value or "").lower()
    if not _SHA256_RE.fullmatch(candidate) or candidate == "0" * 64:
        return None
    return candidate


def _compatible_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    windows = PureWindowsPath(value)
    posix = PurePosixPath(normalized)
    if windows.is_absolute() or posix.is_absolute() or ".." in posix.parts:
        name = windows.name or posix.name or "unknown"
        return f"legacy/{name}"
    return normalized or "legacy/unknown"


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


def _migrate_cli_result_data(payload: Mapping[str, Any]) -> dict[str, Any]:
    legacy_status = str(payload.get("status") or "")
    outcome_by_status = {
        "tests_passed": "passed",
        "tests_failed": "failed",
        "tests_blocked": "blocked",
        "tests_timed_out": "timed_out",
        "tests_cancelled": "cancelled",
        "evidence_prepared": "planned",
    }
    data: dict[str, Any] = {
        "lifecycle": "finished",
        "artifacts": [],
        "errors": copy.deepcopy(payload.get("errors") or []),
    }
    if payload.get("command"):
        data["command"] = str(payload["command"])
    if legacy_status in outcome_by_status:
        data["outcome"] = outcome_by_status[legacy_status]
    if payload.get("exit_code") is not None:
        data["exit_code"] = int(payload["exit_code"])
    if payload.get("message") is not None:
        data["message"] = str(payload["message"])
    return data


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
    function = data.get("function")
    if isinstance(function, Mapping) and source_path:
        normalized_function = dict(function)
        normalized_function["source_path"] = source_path
        data["function"] = normalized_function
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


def _normalize_data_source_path(
    data: dict[str, Any],
    subject: Mapping[str, str],
) -> str | None:
    source = data.get("source")
    source_path = subject.get("source_path")
    if not isinstance(source, Mapping) or not source_path:
        return None
    original = source.get("path")
    if not isinstance(original, str) or original == source_path:
        return None
    normalized_source = dict(source)
    normalized_source["path"] = source_path
    data["source"] = normalized_source
    return original


def _normalize_masked_source_path(data: dict[str, Any]) -> str | None:
    masking = data.get("masking")
    if not isinstance(masking, Mapping):
        return None
    original = masking.get("masked_source_path")
    if not isinstance(original, str) or not original:
        return None
    normalized = _compatible_relative_path(original)
    if normalized == original:
        return None
    normalized_masking = dict(masking)
    normalized_masking["masked_source_path"] = normalized
    data["masking"] = normalized_masking
    return original
