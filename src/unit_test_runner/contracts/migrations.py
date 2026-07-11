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
_ZERO_SHA256 = "0" * 64


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
    else:
        data = {
            key: value
            for key, value in source.items()
            if key not in {"artifact_kind", "schema_version"}
        }

    return {
        "artifact_kind": kind.value,
        "schema_version": CURRENT_CONTRACT_VERSION,
        "producer": {
            "name": "unit-test-runner",
            "version": __version__,
            "commit": "unknown",
        },
        "subject": subject,
        "data": data,
        "extensions": {
            "migration": {
                "source_version": source_version,
                "source_artifact_kind": source.get("artifact_kind"),
            }
        },
    }


def _legacy_subject(payload: Mapping[str, Any]) -> dict[str, str]:
    source = payload.get("source")
    source_info = source if isinstance(source, Mapping) else {}
    source_path = str(
        source_info.get("path")
        or payload.get("source_path")
        or payload.get("workspace")
        or "legacy/unknown.c"
    )
    source_path = _compatible_relative_path(source_path)
    source_sha256 = str(
        source_info.get("sha256")
        or payload.get("source_sha256")
        or _ZERO_SHA256
    ).lower()
    if not _SHA256_RE.fullmatch(source_sha256):
        source_sha256 = _ZERO_SHA256

    function = payload.get("function")
    function_info = function if isinstance(function, Mapping) else {}
    function_name = str(
        function_info.get("name")
        or payload.get("function_name")
        or payload.get("target_function")
        or "workspace"
    )
    identity_seed = f"{source_path}\0{function_name}".encode("utf-8")
    suffix = hashlib.sha256(identity_seed).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "_", function_name.lower()).strip("_")
    return {
        "function_id": f"fn_{slug or 'workspace'}_{suffix}",
        "source_path": source_path,
        "source_sha256": source_sha256,
    }


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
    function_name = str(
        function_info.get("name")
        or payload.get("function_name")
        or "unknown_function"
    )
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
    return {
        "spec_id": str(
            payload.get("spec_id")
            or f"spec-{subject['function_id'].removeprefix('fn_')}"
        ),
        "revision": int(payload.get("revision") or 1),
        "source": {
            "path": subject["source_path"],
            "sha256": subject["source_sha256"],
        },
        "function": {
            "function_id": subject["function_id"],
            "name": function_name,
            "signature_sha256": str(
                function_info.get("signature_sha256") or _ZERO_SHA256
            ),
        },
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


def _migrate_cli_result_data(payload: Mapping[str, Any]) -> dict[str, Any]:
    legacy_status = str(payload.get("status") or "error")
    outcome_by_status = {
        "tests_passed": "passed",
        "tests_failed": "failed",
        "tests_blocked": "blocked",
        "tests_timed_out": "timed_out",
        "tests_cancelled": "cancelled",
        "evidence_prepared": "planned",
    }
    return {
        "command": str(payload.get("command") or "unknown"),
        "lifecycle": "finished",
        "outcome": outcome_by_status.get(legacy_status, "error"),
        "exit_code": int(payload.get("exit_code") or 0),
        "message": str(payload.get("message") or ""),
        "artifacts": [],
        "errors": copy.deepcopy(payload.get("errors") or []),
    }
