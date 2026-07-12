from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from unit_test_runner.contracts import ContractViolation

from .models import TestSpecContractError
from .path_safety import assert_no_reparse_components, lexical_absolute
from .source_binding import (
    normalized_relative_source,
    source_declarations_match,
)


_TOP_LEVEL_FIELDS = {
    "schema_version",
    "source",
    "function",
    "generation_policy",
    "test_cases",
    "additional_case_candidates",
    "coverage_summary",
    "unresolved_items",
    "warnings",
}
_CASE_FIELDS = {
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
    "review_status",
}
_AUTHORITY_FIELDS = {
    "approved",
    "approval",
    "approval_status",
    "is_approved",
    "review_decision",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_legacy_test_case_design_view(
    path: Path | str,
    *,
    function_signature_path: Path | str,
) -> dict[str, Any]:
    """Validate a genuine v0.1 alias and return its unpromoted consumer view."""
    legacy_path, signature_path = assert_safe_legacy_alias_paths(
        path, function_signature_path
    )
    legacy = _read_object(legacy_path, "legacy_alias_invalid")
    signature = _read_object(signature_path, "legacy_companion_invalid")
    violations = _legacy_shape_violations(legacy)
    violations.extend(
        _identity_violations(legacy, signature, legacy_file_path=legacy_path)
    )
    if violations:
        raise TestSpecContractError(tuple(violations))
    return copy.deepcopy(legacy)


def assert_safe_legacy_alias_paths(
    path: Path | str,
    function_signature_path: Path | str,
) -> tuple[Path, Path]:
    legacy_path = lexical_absolute(path)
    signature_path = lexical_absolute(function_signature_path)
    if legacy_path.parent != signature_path.parent:
        raise TestSpecContractError(
            (
                ContractViolation(
                    "legacy_companion_invalid",
                    "$",
                    "Legacy alias and signature companion must share one report directory.",
                    "blocking",
                ),
            )
        )
    try:
        trusted_root = legacy_path.parent.parent
        assert_no_reparse_components(legacy_path, trusted_root)
        assert_no_reparse_components(signature_path, trusted_root)
    except ValueError as error:
        raise TestSpecContractError(
            (
                ContractViolation(
                    "unsafe_legacy_path", "$", str(error), "blocking"
                ),
            )
        ) from error
    return legacy_path, signature_path


def _read_object(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TestSpecContractError(
            (ContractViolation(code, "$", str(error), "blocking"),)
        ) from error
    if not isinstance(value, dict):
        raise TestSpecContractError(
            (
                ContractViolation(
                    code,
                    "$",
                    "Legacy alias and companion roots must be objects.",
                    "blocking",
                ),
            )
        )
    return value


def _legacy_shape_violations(payload: Mapping[str, Any]) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if str(payload.get("schema_version") or "") != "0.1":
        violations.append(
            ContractViolation(
                "unsupported_version",
                "$.schema_version",
                "The explicit legacy alias accepts only schema_version 0.1.",
                "blocking",
            )
        )
    unknown = set(payload) - _TOP_LEVEL_FIELDS
    if unknown:
        violations.append(
            ContractViolation(
                "legacy_unknown_field",
                "$",
                "Unknown legacy fields: " + ", ".join(sorted(unknown)),
                "blocking",
            )
        )
    violations.extend(_authority_violations(payload))
    for collection in ("test_cases", "additional_case_candidates"):
        cases = payload.get(collection)
        if not isinstance(cases, list):
            violations.append(
                ContractViolation(
                    "legacy_alias_invalid",
                    f"$.{collection}",
                    f"{collection} must be an array.",
                    "blocking",
                )
            )
            continue
        for index, case in enumerate(cases):
            if not isinstance(case, Mapping):
                violations.append(
                    ContractViolation(
                        "legacy_alias_invalid",
                        f"$.{collection}[{index}]",
                        "Legacy cases must be objects.",
                        "blocking",
                    )
                )
                continue
            unknown_case = set(case) - _CASE_FIELDS
            if unknown_case:
                violations.append(
                    ContractViolation(
                        "legacy_unknown_field",
                        f"$.{collection}[{index}]",
                        "Unknown legacy case fields: "
                        + ", ".join(sorted(str(item) for item in unknown_case)),
                        "blocking",
                    )
                )
    return violations


def _authority_violations(
    value: Any,
    path: str = "$",
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in _AUTHORITY_FIELDS:
                violations.append(
                    ContractViolation(
                        "embedded_review_authority",
                        child_path,
                        "The legacy alias cannot carry approval authority.",
                        "blocking",
                    )
                )
            violations.extend(_authority_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_authority_violations(child, f"{path}[{index}]"))
    return violations


def _identity_violations(
    legacy: Mapping[str, Any],
    signature_payload: Mapping[str, Any],
    *,
    legacy_file_path: Path,
) -> list[ContractViolation]:
    signature_data = signature_payload.get("data")
    signature = signature_data if isinstance(signature_data, Mapping) else signature_payload
    if signature_payload.get("artifact_kind") not in {None, "function_signature"}:
        return [
            ContractViolation(
                "legacy_companion_invalid",
                "$.artifact_kind",
                "The companion artifact must be a function_signature.",
                "blocking",
            )
        ]
    legacy_source = legacy.get("source")
    legacy_function = legacy.get("function")
    signature_source = signature.get("source")
    signature_function = signature.get("function")
    if not all(
        isinstance(item, Mapping)
        for item in (
            legacy_source,
            legacy_function,
            signature_source,
            signature_function,
        )
    ):
        return [
            ContractViolation(
                "legacy_identity_missing",
                "$",
                "Legacy alias and signature companion require source and function identity.",
                "blocking",
            )
        ]
    legacy_path = str(legacy_source.get("path") or "").replace("\\", "/")
    signature_path = str(signature_source.get("path") or "").replace("\\", "/")
    legacy_hash = str(legacy_source.get("sha256") or "")
    signature_hash = str(signature_source.get("sha256") or "")
    legacy_name = str(legacy_function.get("name") or "")
    signature_name = str(signature_function.get("name") or "")
    request_root, request_relative = _request_source_binding(
        legacy_path=legacy_file_path,
        source_sha256=legacy_hash,
    )
    path_matches = source_declarations_match(
        legacy_path,
        signature_path,
        request_root=request_root,
        request_relative=request_relative,
    )
    if (
        not legacy_path
        or not signature_path
        or not path_matches
        or not _SHA256_RE.fullmatch(legacy_hash)
        or legacy_hash == "0" * 64
        or legacy_hash != signature_hash
        or not legacy_name
        or legacy_name != signature_name
    ):
        return [
            ContractViolation(
                "legacy_identity_mismatch",
                "$.source",
                "Legacy source/function identity must exactly match the supplied function signature companion.",
                "blocking",
            )
        ]
    for collection in ("test_cases", "additional_case_candidates"):
        for index, case in enumerate(legacy.get(collection) or []):
            if not isinstance(case, Mapping):
                continue
            target = case.get("target_function")
            if target is not None and str(target) != legacy_name:
                return [
                    ContractViolation(
                        "legacy_identity_mismatch",
                        f"$.{collection}[{index}].target_function",
                        "Legacy case target_function must match the companion function.",
                        "blocking",
                    )
                ]
    return []


def _request_source_binding(
    *,
    legacy_path: Path,
    source_sha256: str,
) -> tuple[Path | None, str | None]:
    reports = legacy_path.parent
    if reports.name != "reports":
        return None, None
    workspace = reports.parent
    request_path = workspace / "input" / "request.json"
    try:
        assert_no_reparse_components(request_path, workspace)
        request = _read_object(request_path, "legacy_request_invalid")
        request_root_raw = request.get("workspace")
        request_source_raw = request.get("source")
        if not isinstance(request_root_raw, str) or not isinstance(
            request_source_raw, str
        ):
            return None, None
        request_source = normalized_relative_source(request_source_raw)
        request_root = lexical_absolute(Path(request_root_raw).expanduser())
        source_file = assert_no_reparse_components(
            request_root / Path(request_source),
            request_root,
        )
        if not source_file.is_file():
            return None, None
        if hashlib.sha256(source_file.read_bytes()).hexdigest() != source_sha256:
            return None, None
        return request_root, request_source
    except (OSError, ValueError, TestSpecContractError):
        return None, None
