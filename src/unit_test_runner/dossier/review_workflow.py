from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.contracts.registry import get_contract
from unit_test_runner.reports.japanese import ja_label, ja_text
from unit_test_runner.review_ids import (
    StableReviewIdRegistry,
    build_function_id,
    semantic_case_id_token,
)
from unit_test_runner.test_spec.models import (
    materialize_test_spec_containers,
    require_exact_unresolved_case_id_lists,
)

from .dossier_models import DossierReviewItem, DossierUnresolvedItem


_CORE_KINDS = (
    "source_digest",
    "function_location",
    "function_signature",
)
_CORE_CONTRACT_KINDS = {
    "source_digest": ArtifactKind.SOURCE_DIGEST,
    "function_location": ArtifactKind.FUNCTION_LOCATION,
    "function_signature": ArtifactKind.FUNCTION_SIGNATURE,
}
_ARTIFACT_STATUSES = {
    "valid",
    "missing",
    "parse_error",
    "schema_error",
    "unsupported_version",
    "stale",
}


def build_review_items(
    payloads: dict[str, dict[str, Any]],
    *,
    artifacts: Iterable[Any] | None = None,
) -> tuple[list[DossierReviewItem], list[DossierUnresolvedItem]]:
    raw_test_spec = payloads.get("test_spec", {})
    require_exact_unresolved_case_id_lists(raw_test_spec)
    test_spec = materialize_test_spec_containers(raw_test_spec)
    payloads = dict(payloads)
    payloads["test_spec"] = test_spec
    artifact_by_kind = (
        None if artifacts is None else _artifact_records_by_kind(artifacts)
    )
    review_items: list[DossierReviewItem] = []
    unresolved: list[DossierUnresolvedItem] = []
    seen_review_ids: set[str] = set()
    registry = StableReviewIdRegistry()
    function_id = _semantic_function_id(payloads, artifact_by_kind)

    test_spec_is_authoritative = artifact_by_kind is None or (
        _strict_current_artifact(
            artifact_by_kind.get("test_spec"),
            ArtifactKind.TEST_SPEC,
        )
        and _test_spec_function_id(test_spec, payloads) is not None
    )
    if test_spec_is_authoritative:
        _from_test_case_design(
            test_spec,
            function_id,
            registry,
            seen_review_ids,
            review_items,
            unresolved,
        )
    _from_harness(
        payloads.get("harness_skeleton_report", {}),
        function_id,
        registry,
        seen_review_ids,
        review_items,
        unresolved,
    )
    _from_completion(
        payloads.get("build_completion_plan", {}),
        function_id,
        registry,
        seen_review_ids,
        review_items,
        unresolved,
    )
    _from_execution(
        payloads.get("test_execution_report", {}),
        function_id,
        registry,
        seen_review_ids,
        review_items,
        unresolved,
    )
    if not review_items:
        generic = _generic_review_identity(payloads, artifact_by_kind)
        if generic is not None:
            generic_function_id, related_artifacts = generic
            review_id = registry.register(
                category="evidence_review",
                function_id=generic_function_id,
                case_id=None,
                semantic_subject_key="final_dossier_review",
            )
            _append_review_item(
                review_items,
                seen_review_ids,
                DossierReviewItem(
                    review_id,
                    "evidence_review",
                    "生成dossierの最終確認",
                    "承認前に、生成された解析結果、テスト設計、ビルド状態、エビデンスを確認してください。",
                    related_artifacts,
                    severity="info",
                    suggested_reviewer_role="unit_test_lead",
                ),
            )
    if not unresolved:
        unresolved.append(
            DossierUnresolvedItem(
                "UNRESOLVED_REVIEW_001",
                "dossier_review_workflow",
                "manual_final_review",
                "最終的な人手レビューが必要です。",
                "dossier生成は承認判断そのものではありません。",
                suggested_action="function_dossier.md を確認し、チェック項目の完了判断をツール外で記録してください。",
            )
        )
    return review_items, unresolved


def _from_test_case_design(
    payload: dict[str, Any],
    function_id: str | None,
    registry: StableReviewIdRegistry,
    seen_review_ids: set[str],
    review_items: list[DossierReviewItem],
    unresolved: list[DossierUnresolvedItem],
) -> None:
    collections: dict[str, list[Any]] = {}
    for field_name in (
        "test_cases",
        "additional_case_candidates",
        "unresolved_items",
    ):
        value = payload[field_name] if field_name in payload else []
        if not isinstance(value, list):
            return
        collections[field_name] = value
    all_cases = (
        list(collections["test_cases"])
        + list(collections["additional_case_candidates"])
    )
    actual_case_by_token = _case_association_index(all_cases)
    represented_cases: set[str] = set()
    for raw_item in collections["unresolved_items"]:
        if not isinstance(raw_item, Mapping):
            continue
        item_kind = _required_identity_string(
            raw_item.get("item_kind"),
            "test_spec unresolved item_kind",
        )
        related_case_ids = [
            _canonical_case_reference(
                case_id,
                actual_case_by_token,
            )
            for case_id in _related_case_ids(raw_item)
        ]
        represented_cases.update(related_case_ids)
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_EXPECTED_{len(unresolved) + 1:03d}",
                "test_case_design_generation",
                item_kind or "expected_result_unknown",
                ja_text(
                    raw_item.get(
                        "description",
                        "生成テストの期待結果を確認してください。",
                    )
                ),
                ja_text(
                    raw_item.get(
                        "reason",
                        "生成テストは、期待値レビューが完了するまで承認済みとして扱えません。",
                    )
                ),
                ["test_spec"],
                related_case_ids,
                ja_text(
                    raw_item.get(
                        "suggested_action",
                        "関数仕様を確認し、TBD の期待値を置き換えてください。",
                    )
                ),
            )
        )
        if function_id is None or item_kind is None:
            continue
        cases: list[str | None] = related_case_ids or [None]
        for case_id in cases:
            review_id = registry.register(
                category="expected_result_review",
                function_id=function_id,
                case_id=case_id,
                semantic_subject_key=item_kind,
            )
            title = (
                f"期待結果を確認: {case_id}"
                if case_id is not None
                else "期待結果を確認"
            )
            _append_review_item(
                review_items,
                seen_review_ids,
                DossierReviewItem(
                    review_id,
                    "expected_result_review",
                    title,
                    ja_text(
                        raw_item.get(
                            "description",
                            "生成テストの期待値・期待観測を確認してください。",
                        )
                    ),
                    ["test_spec"],
                    [case_id] if case_id is not None else [],
                ),
            )

    for case in all_cases:
        if not isinstance(case, Mapping):
            continue
        raw_case_id = case.get("test_case_id")
        if raw_case_id is None:
            raw_case_id = case.get("id")
        test_case_id = _optional_identity_string(
            raw_case_id,
            "test_spec case ID",
        )
        needs_review = bool(case.get("review_item_ids"))
        observations = case.get("expected_observations")
        if observations is None:
            observations = []
        has_tbd = not isinstance(observations, list) or any(
            isinstance(observation, Mapping)
            and _unresolved_dossier_expected_expression(
                observation.get("expected_expression")
            )
            for observation in observations
        )
        if not (needs_review or has_tbd) or test_case_id in represented_cases:
            continue
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_EXPECTED_{len(unresolved) + 1:03d}",
                "test_case_design_generation",
                "expected_result_unknown",
                (
                    f"テストケース {test_case_id} の期待結果を確認してください。"
                    if test_case_id
                    else "テストケースの期待結果を確認してください。"
                ),
                "生成テストは、期待値レビューが完了するまで承認済みとして扱えません。",
                ["test_spec"],
                [test_case_id] if test_case_id else [],
                "関数仕様を確認し、TBD の期待値を置き換えてください。",
            )
        )
        if function_id is None:
            continue
        review_id = registry.register(
            category="expected_result_review",
            function_id=function_id,
            case_id=test_case_id,
            semantic_subject_key="test_case_review_required",
        )
        _append_review_item(
            review_items,
            seen_review_ids,
            DossierReviewItem(
                review_id,
                "expected_result_review",
                (
                    f"期待結果を確認: {test_case_id}"
                    if test_case_id
                    else "期待結果を確認"
                ),
                (
                    f"テストケース {test_case_id} の期待値・期待観測を確認してください。"
                    if test_case_id
                    else "テストケースの期待値・期待観測を確認してください。"
                ),
                ["test_spec"],
                [test_case_id] if test_case_id else [],
            ),
        )


_DOSSIER_PLACEHOLDER_PREFIXES = ("TBD", "UNKNOWN", "UNRESOLVED", "TODO")


def _unresolved_dossier_expected_expression(value: Any) -> bool:
    if type(value) is not str:
        return True
    normalized = value.strip().upper()
    return not normalized or normalized.startswith(_DOSSIER_PLACEHOLDER_PREFIXES)


def _from_harness(
    payload: dict[str, Any],
    function_id: str | None,
    registry: StableReviewIdRegistry,
    seen_review_ids: set[str],
    review_items: list[DossierReviewItem],
    unresolved: list[DossierUnresolvedItem],
) -> None:
    for placeholder in payload.get("unresolved_placeholders") or []:
        if not isinstance(placeholder, Mapping):
            continue
        test_case_id = _optional_identity_string(
            placeholder.get("related_test_case_id"),
            "harness related test case ID",
        )
        placeholder_name = _optional_identity_string(
            placeholder.get("name"),
            "harness placeholder name",
        )
        display_name = placeholder_name or "未命名プレースホルダ"
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_PLACEHOLDER_{len(unresolved) + 1:03d}",
                "harness_skeleton_generation",
                "harness_placeholder",
                f"プレースホルダが残っています: {display_name}",
                "生成ハーネスには手動補完が必要です。",
                ["harness_skeleton_report"],
                [test_case_id] if test_case_id else [],
                ja_text(
                    placeholder.get(
                        "suggested_action",
                        "生成ハーネスのプレースホルダを確認してください。",
                    )
                ),
            )
        )
        placeholder_kind = _optional_identity_string(
            placeholder.get("placeholder_kind"),
            "harness placeholder kind",
        )
        if function_id is None or placeholder_kind is None or placeholder_name is None:
            continue
        related_stub = _optional_identity_string(
            placeholder.get("related_stub_name"),
            "harness related stub name",
        )
        semantic_subject = _semantic_subject(
            ("kind", placeholder_kind),
            ("name", placeholder_name),
            ("stub", related_stub),
        )
        review_id = registry.register(
            category="stub_behavior_review",
            function_id=function_id,
            case_id=test_case_id,
            semantic_subject_key=semantic_subject,
        )
        description = f"{display_name} を確認してください。"
        if test_case_id:
            description = f"テストケース {test_case_id} の {description}"
        _append_review_item(
            review_items,
            seen_review_ids,
            DossierReviewItem(
                review_id,
                "stub_behavior_review",
                f"ハーネスのプレースホルダを確認: {display_name}",
                description,
                ["harness_skeleton_report"],
                [test_case_id] if test_case_id else [],
            ),
        )


def _from_completion(
    payload: dict[str, Any],
    function_id: str | None,
    registry: StableReviewIdRegistry,
    seen_review_ids: set[str],
    review_items: list[DossierReviewItem],
    unresolved: list[DossierUnresolvedItem],
) -> None:
    for manual in payload.get("manual_action_items") or []:
        if not isinstance(manual, Mapping):
            continue
        raw_item_kind = manual.get("item_kind")
        item_kind = (
            "manual_action"
            if raw_item_kind is None
            else _required_identity_string(
                raw_item_kind,
                "build manual item_kind",
            )
        )
        manual_kind = ja_label(item_kind)
        description = ja_text(
            manual.get("description", "手動でのビルド補完作業が残っています。")
        )
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_BUILD_{len(unresolved) + 1:03d}",
                "build_completion",
                item_kind,
                description,
                ja_text(
                    manual.get("reason", "ビルド補完は完全には自動化できません。")
                ),
                ["build_completion_plan"],
                [],
                ja_text(
                    manual.get(
                        "suggested_action",
                        "ビルド補完計画を確認してください。",
                    )
                ),
                blocks_readiness=False,
            )
        )
        if function_id is None:
            continue
        review_id = registry.register(
            category="build_review",
            function_id=function_id,
            case_id=None,
            semantic_subject_key=item_kind,
        )
        _append_review_item(
            review_items,
            seen_review_ids,
            DossierReviewItem(
                review_id,
                "build_review",
                f"ビルド補完項目を確認: {manual_kind}",
                description,
                ["build_completion_plan"],
            ),
        )


def _from_execution(
    payload: dict[str, Any],
    function_id: str | None,
    registry: StableReviewIdRegistry,
    seen_review_ids: set[str],
    review_items: list[DossierReviewItem],
    unresolved: list[DossierUnresolvedItem],
) -> None:
    function = payload.get("function")
    status = function.get("status") if isinstance(function, Mapping) else None
    if status is None:
        status = payload.get("status")
    status = _optional_identity_string(status, "execution status")
    if status not in {"inconclusive", "failed", "blocked", "timeout", "not_run"}:
        return
    status_label = ja_label(status)
    unresolved.append(
        DossierUnresolvedItem(
            f"UNRESOLVED_EXEC_{len(unresolved) + 1:03d}",
            "execution_evidence",
            "execution_inconclusive",
            f"テスト実行状態は「{status_label}」です。",
            "このエビデンスだけでは最終PASS判定にはなりません。",
            ["test_execution_report"],
            [],
            "プレースホルダを解消するか、レビュー後にテストを再実行してください。",
        )
    )
    if function_id is None:
        return
    review_id = registry.register(
        category="execution_review",
        function_id=function_id,
        case_id=None,
        semantic_subject_key=f"execution_status_{status}",
    )
    _append_review_item(
        review_items,
        seen_review_ids,
        DossierReviewItem(
            review_id,
            "execution_review",
            f"実行エビデンスを確認: {status_label}",
            f"テスト実行状態は「{status_label}」です。",
            ["test_execution_report"],
        ),
    )


def _generic_review_identity(
    payloads: dict[str, dict[str, Any]],
    artifact_by_kind: dict[str, Any] | None,
) -> tuple[str, list[str]] | None:
    if artifact_by_kind is None:
        return None
    test_spec_artifact = artifact_by_kind.get("test_spec")
    if _strict_current_artifact(test_spec_artifact, ArtifactKind.TEST_SPEC):
        function_id = _test_spec_function_id(
            payloads.get("test_spec", {}),
            payloads,
        )
        if function_id is None:
            return None
        return function_id, ["test_spec"]
    if not _verified_absent(test_spec_artifact):
        return None
    core_identity = _strict_core_identity(payloads, artifact_by_kind)
    if core_identity is None:
        return None
    return core_identity[0], list(_CORE_KINDS)


def _semantic_function_id(
    payloads: dict[str, dict[str, Any]],
    artifact_by_kind: dict[str, Any] | None,
) -> str | None:
    if artifact_by_kind is not None:
        if _strict_current_artifact(
            artifact_by_kind.get("test_spec"),
            ArtifactKind.TEST_SPEC,
        ):
            return _test_spec_function_id(
                payloads.get("test_spec", {}),
                payloads,
            )
        core = _strict_core_identity(payloads, artifact_by_kind)
        return core[0] if core is not None else None
    test_spec_id = _test_spec_function_id(
        payloads.get("test_spec", {}),
        payloads,
    )
    if test_spec_id is not None:
        return test_spec_id
    core = _core_identity(payloads)
    return core[0] if core is not None else None


def _test_spec_function_id(
    payload: Mapping[str, Any],
    payloads: dict[str, dict[str, Any]],
) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    source = payload.get("source")
    function = payload.get("function")
    if not isinstance(source, Mapping) or not isinstance(function, Mapping):
        return None
    source_path = _optional_identity_string(
        source.get("path"),
        "test_spec source path",
    )
    source_sha = _optional_identity_string(
        source.get("sha256"),
        "test_spec source sha256",
    )
    function_name = _optional_identity_string(
        function.get("name"),
        "test_spec function name",
    )
    function_id = _optional_identity_string(
        function.get("function_id"),
        "test_spec function_id",
    )
    if source_path is None or function_name is None or function_id is None:
        return None
    try:
        if build_function_id(source_path, function_name) != function_id:
            return None
    except (TypeError, ValueError, UnicodeError):
        return None
    core = _core_identity(payloads)
    if all(kind in payloads for kind in _CORE_KINDS):
        if core is None:
            return None
        _, core_path, core_sha, core_name = core
        if (
            source_path != core_path
            or function_name != core_name
            or (source_sha is not None and source_sha != core_sha)
        ):
            return None
    return function_id


def _strict_core_identity(
    payloads: dict[str, dict[str, Any]],
    artifact_by_kind: dict[str, Any],
) -> tuple[str, str, str, str] | None:
    for kind in _CORE_KINDS:
        if not _strict_current_artifact(
            artifact_by_kind.get(kind),
            _CORE_CONTRACT_KINDS[kind],
        ):
            return None
    return _core_identity(payloads)


def _core_identity(
    payloads: dict[str, dict[str, Any]],
) -> tuple[str, str, str, str] | None:
    core_payloads: list[Mapping[str, Any]] = []
    for kind in _CORE_KINDS:
        payload = payloads.get(kind)
        if not isinstance(payload, Mapping):
            return None
        core_payloads.append(payload)
    source_identities: list[tuple[str, str]] = []
    for payload in core_payloads:
        source = payload.get("source")
        if not isinstance(source, Mapping):
            return None
        path = _optional_identity_string(
            source.get("path"),
            f"{_CORE_KINDS[len(source_identities)]} source path",
        )
        sha256 = _optional_identity_string(
            source.get("sha256"),
            f"{_CORE_KINDS[len(source_identities)]} source sha256",
        )
        if path is None or sha256 is None:
            return None
        source_identities.append((path, sha256))
    if len(set(source_identities)) != 1:
        return None
    function_names: list[str] = []
    for payload in core_payloads[1:]:
        function = payload.get("function")
        if not isinstance(function, Mapping):
            return None
        name = _optional_identity_string(
            function.get("name"),
            "core function name",
        )
        if name is None:
            return None
        function_names.append(name)
    if len(set(function_names)) != 1:
        return None
    source_path, source_sha = source_identities[0]
    function_name = function_names[0]
    try:
        function_id = build_function_id(source_path, function_name)
    except (TypeError, ValueError, UnicodeError):
        return None
    return function_id, source_path, source_sha, function_name


def _strict_current_artifact(artifact: Any, kind: ArtifactKind) -> bool:
    return bool(
        artifact is not None
        and artifact.exists is True
        and artifact.contract_status == "valid"
        and artifact.schema_version == get_contract(kind).current_version
    )


def _verified_absent(artifact: Any) -> bool:
    return bool(
        artifact is not None
        and artifact.exists is False
        and artifact.contract_status == "missing"
    )


def _append_review_item(
    review_items: list[DossierReviewItem],
    seen_review_ids: set[str],
    item: DossierReviewItem,
) -> None:
    if item.review_id in seen_review_ids:
        return
    seen_review_ids.add(item.review_id)
    review_items.append(item)


def _artifact_records_by_kind(artifacts: Iterable[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for index, artifact in enumerate(artifacts):
        try:
            raw_kind = artifact.artifact_kind
            exists = artifact.exists
            raw_status = artifact.contract_status
            raw_version = artifact.schema_version
        except AttributeError as error:
            raise TypeError(
                f"Artifact metadata record {index} is incomplete."
            ) from error
        kind = _required_identity_string(
            raw_kind,
            f"artifact metadata record {index} kind",
        )
        if type(exists) is not bool:
            raise TypeError(
                f"artifact metadata record {index} exists must be an exact bool."
            )
        status = _required_identity_string(
            raw_status,
            f"artifact metadata record {index} contract_status",
        )
        if status not in _ARTIFACT_STATUSES:
            raise ValueError(
                f"artifact metadata record {index} has unknown status: {status}"
            )
        if raw_version is not None:
            _required_identity_string(
                raw_version,
                f"artifact metadata record {index} schema_version",
            )
        if kind in result:
            raise ValueError(f"Duplicate artifact metadata kind: {kind}")
        result[kind] = artifact
    return result


def _semantic_subject(*parts: tuple[str, str | None]) -> str:
    canonical = json.dumps(
        [[name, value] for name, value in parts],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8", errors="strict")
    return "v1hex" + canonical.hex()


def _required_identity_string(value: object, field: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact string.")
    if not value:
        raise ValueError(f"{field} must not be empty.")
    if "\x00" in value:
        raise ValueError(f"{field} must not contain NUL.")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field} must be strict UTF-8.") from error
    return value


def _optional_identity_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_identity_string(value, field)


def _related_case_ids(item: Mapping[str, Any]) -> list[str]:
    if "related_test_case_ids" not in item:
        return []
    value = item["related_test_case_ids"]
    if type(value) is not list:
        raise TypeError("related_test_case_ids must be an exact list.")
    return [
        _required_identity_string(case_id, "related test case ID")
        for case_id in value
    ]


def _case_association_index(
    cases: list[Any],
) -> dict[str, str]:
    actual_case_by_token: dict[str, str] = {}
    for case in cases:
        if not isinstance(case, Mapping):
            continue
        raw_case_id = case.get("test_case_id")
        if raw_case_id is None:
            raw_case_id = case.get("id")
        case_id = _optional_identity_string(
            raw_case_id,
            "test_spec case ID",
        )
        if case_id is None:
            continue
        token = semantic_case_id_token(case_id)
        existing = actual_case_by_token.get(token)
        if existing is not None and existing != case_id:
            raise ValueError(
                "Ambiguous test case IDs normalize to one semantic identity: "
                f"{existing!r} and {case_id!r}."
            )
        actual_case_by_token[token] = case_id
    return actual_case_by_token


def _canonical_case_reference(
    case_id: str,
    actual_case_by_token: Mapping[str, str],
) -> str:
    token = semantic_case_id_token(case_id)
    return actual_case_by_token.get(token, case_id)
