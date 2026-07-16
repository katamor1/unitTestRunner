from __future__ import annotations

from typing import Any, Iterable

from unit_test_runner.reports.japanese import ja_label, ja_text
from unit_test_runner.review_ids import StableReviewIdRegistry, build_review_id

from .dossier_models import DossierArtifact, DossierReviewItem, DossierUnresolvedItem
from .review_decision_models import (
    ReviewItemCollection,
    ReviewItemSnapshot,
    ReviewSubjectReference,
)


def build_review_items(
    payloads: dict[str, dict[str, Any]],
    artifacts: list[DossierArtifact] | None = None,
) -> tuple[list[DossierReviewItem], list[DossierUnresolvedItem]]:
    review_items: list[DossierReviewItem] = []
    unresolved: list[DossierUnresolvedItem] = []
    artifact_map = {item.artifact_kind: item for item in artifacts or []}
    function_id = _function_id(payloads)
    registry = StableReviewIdRegistry()
    seen: set[str] = set()

    _from_test_spec_unresolved(
        payloads.get("test_spec", {}),
        review_items,
        unresolved,
        artifact_map,
        function_id,
        registry,
        seen,
    )
    _from_test_case_design(
        payloads.get("test_spec", {}),
        review_items,
        unresolved,
        artifact_map,
        function_id,
        registry,
        seen,
    )
    _from_harness(
        payloads.get("harness_skeleton_report", {}),
        review_items,
        unresolved,
        artifact_map,
        function_id,
        registry,
        seen,
    )
    _from_completion(
        payloads.get("build_completion_plan", {}),
        review_items,
        unresolved,
        artifact_map,
        function_id,
        registry,
        seen,
    )
    _from_execution(
        payloads.get("test_execution_report", {}),
        review_items,
        unresolved,
        artifact_map,
        function_id,
        registry,
        seen,
    )
    if not review_items:
        semantic_key = "dossier/final-review"
        review_id = registry.register(
            category="evidence_review",
            function_id=function_id,
            case_id=None,
            semantic_subject_key=semantic_key,
        )
        subject_kind = _first_available_kind(
            artifact_map,
            ("test_spec", "function_signature", "source_digest"),
        )
        review_items.append(
            _review_item(
                review_id=review_id,
                category="evidence_review",
                title="生成dossierの最終確認",
                description="承認前に、生成された解析結果、テスト設計、ビルド状態、エビデンスを確認してください。",
                related_artifacts=[subject_kind] if subject_kind else [],
                related_test_cases=[],
                severity="info",
                reviewer_role="unit_test_lead",
                case_id=None,
                semantic_key=semantic_key,
                subject_kind=subject_kind,
                artifact_map=artifact_map,
                function_id=function_id,
            )
        )
    if not unresolved:
        unresolved.append(
            DossierUnresolvedItem(
                "UNRESOLVED_REVIEW_001",
                "dossier_review_workflow",
                "manual_final_review",
                "最終的な人手レビューが必要です。",
                "dossier生成は承認判断そのものではありません。",
                suggested_action="function_dossier.md を確認し、review_decisions.json に判断を記録してください。",
            )
        )
    return review_items, unresolved


def build_review_item_collection(
    review_items: Iterable[DossierReviewItem],
) -> ReviewItemCollection:
    snapshots: list[ReviewItemSnapshot] = []
    for item in review_items:
        if item.semantic_subject_key is None or not item.subject_artifacts:
            continue
        subjects = tuple(
            subject
            if isinstance(subject, ReviewSubjectReference)
            else ReviewSubjectReference.from_dict(subject)
            for subject in item.subject_artifacts
        )
        function_ids = {subject.function_id for subject in subjects}
        if len(function_ids) != 1 or None in function_ids:
            continue
        snapshots.append(
            ReviewItemSnapshot(
                review_id=item.review_id,
                category=item.category,
                function_id=next(iter(function_ids)) or "",
                case_id=item.case_id,
                semantic_subject_key=item.semantic_subject_key,
                subject_artifacts=subjects,
            )
        )
    return ReviewItemCollection(tuple(snapshots))


def _from_test_spec_unresolved(
    payload: dict[str, Any],
    review_items: list[DossierReviewItem],
    unresolved: list[DossierUnresolvedItem],
    artifact_map: dict[str, DossierArtifact],
    function_id: str,
    registry: StableReviewIdRegistry,
    seen: set[str],
) -> None:
    for raw in payload.get("unresolved_items", []):
        if not isinstance(raw, dict):
            continue
        semantic_key = str(raw.get("item_id") or "").strip()
        if not semantic_key:
            continue
        category = str(raw.get("item_kind") or "test_spec_review")
        case_ids = [
            str(value)
            for value in raw.get("related_test_case_ids", [])
            if str(value).strip()
        ] or [None]
        declared = [
            str(value)
            for value in raw.get("review_item_ids", [])
            if str(value).strip()
        ]
        description = str(raw.get("description") or semantic_key)
        unresolved.append(
            DossierUnresolvedItem(
                semantic_key,
                "test_case_design_generation",
                category,
                description,
                "生成テストはレビュー判断が記録されるまで承認済みとして扱えません。",
                ["test_spec"],
                [value for value in case_ids if value is not None],
                str(raw.get("suggested_action") or "TestSpecの対象項目を確認してください。"),
            )
        )
        for index, case_id in enumerate(case_ids):
            expected = registry.register(
                category=category,
                function_id=function_id,
                case_id=case_id,
                semantic_subject_key=semantic_key,
            )
            selected = declared[index] if index < len(declared) else expected
            authoritative = selected == expected
            _append_unique(
                review_items,
                seen,
                _review_item(
                    review_id=selected,
                    category=category,
                    title=f"レビュー項目を確認: {semantic_key}",
                    description=description,
                    related_artifacts=["test_spec"],
                    related_test_cases=[case_id] if case_id else [],
                    case_id=case_id if authoritative else None,
                    semantic_key=semantic_key if authoritative else None,
                    subject_kind="test_spec" if authoritative else None,
                    artifact_map=artifact_map,
                    function_id=function_id,
                ),
            )


def _from_test_case_design(
    payload: dict[str, Any],
    review_items: list[DossierReviewItem],
    unresolved: list[DossierUnresolvedItem],
    artifact_map: dict[str, DossierArtifact],
    function_id: str,
    registry: StableReviewIdRegistry,
    seen: set[str],
) -> None:
    for case in payload.get("test_cases", []) + payload.get("additional_case_candidates", []):
        if not isinstance(case, dict):
            continue
        test_case_id = str(case.get("test_case_id") or case.get("id") or "") or None
        case_review_ids = [
            str(value)
            for value in case.get("review_item_ids", [])
            if str(value).strip()
        ]
        has_tbd = any(
            str(obs.get("expected_expression", "")).startswith("TBD")
            or obs.get("expected_expression") is None
            for obs in case.get("expected_observations", [])
            if isinstance(obs, dict)
        )
        if not case_review_ids and not has_tbd:
            continue
        semantic_key = "expected/observations"
        expected = registry.register(
            category="expected_result_review",
            function_id=function_id,
            case_id=test_case_id,
            semantic_subject_key=semantic_key,
        )
        generated_semantic_key = "legacy/review-required"
        generated_expected = registry.register(
            category="generated_case_review",
            function_id=function_id,
            case_id=test_case_id,
            semantic_subject_key=generated_semantic_key,
        )
        if not case_review_ids:
            case_review_ids = [expected]
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_EXPECTED_{len(unresolved) + 1:03d}",
                "test_case_design_generation",
                "expected_result_unknown",
                f"テストケース {test_case_id} の期待結果を確認してください。",
                "生成テストは、期待値レビューが完了するまで承認済みとして扱えません。",
                ["test_spec"],
                [test_case_id] if test_case_id else [],
                "関数仕様を確認し、TBD の期待値を置き換えてください。",
            )
        )
        for selected in case_review_ids:
            if selected in seen:
                continue
            if selected == generated_expected:
                category = "generated_case_review"
                selected_semantic_key: str | None = generated_semantic_key
            elif selected == expected:
                category = "expected_result_review"
                selected_semantic_key = semantic_key
            else:
                category = "expected_result_review"
                selected_semantic_key = None
            authoritative = selected_semantic_key is not None
            _append_unique(
                review_items,
                seen,
                _review_item(
                    review_id=selected,
                    category=category,
                    title=f"期待結果を確認: {test_case_id}" if test_case_id else "期待結果を確認",
                    description=f"テストケース {test_case_id} の期待値・期待観測を確認してください。",
                    related_artifacts=["test_spec"],
                    related_test_cases=[test_case_id] if test_case_id else [],
                    case_id=test_case_id if authoritative else None,
                    semantic_key=selected_semantic_key,
                    subject_kind="test_spec" if authoritative else None,
                    artifact_map=artifact_map,
                    function_id=function_id,
                ),
            )


def _from_harness(
    payload: dict[str, Any],
    review_items: list[DossierReviewItem],
    unresolved: list[DossierUnresolvedItem],
    artifact_map: dict[str, DossierArtifact],
    function_id: str,
    registry: StableReviewIdRegistry,
    seen: set[str],
) -> None:
    for placeholder in payload.get("unresolved_placeholders", []):
        if not isinstance(placeholder, dict):
            continue
        test_case_id = str(placeholder.get("related_test_case_id") or "") or None
        placeholder_name = str(
            placeholder.get("name")
            or placeholder.get("placeholder_id")
            or "未命名プレースホルダ"
        )
        semantic_key = f"harness/placeholder/{placeholder_name}"
        review_id = registry.register(
            category="stub_behavior_review",
            function_id=function_id,
            case_id=test_case_id,
            semantic_subject_key=semantic_key,
        )
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_PLACEHOLDER_{len(unresolved) + 1:03d}",
                "harness_skeleton_generation",
                "harness_placeholder",
                f"プレースホルダが残っています: {placeholder_name}",
                "生成ハーネスには手動補完が必要です。",
                ["harness_skeleton_report"],
                [test_case_id] if test_case_id else [],
                ja_text(placeholder.get("suggested_action", "生成ハーネスのプレースホルダを確認してください。")),
            )
        )
        _append_unique(
            review_items,
            seen,
            _review_item(
                review_id=review_id,
                category="stub_behavior_review",
                title=f"ハーネスのプレースホルダを確認: {placeholder_name}",
                description=(
                    f"テストケース {test_case_id} の {placeholder_name} を確認してください。"
                    if test_case_id
                    else f"{placeholder_name} を確認してください。"
                ),
                related_artifacts=["harness_skeleton_report"],
                related_test_cases=[test_case_id] if test_case_id else [],
                case_id=test_case_id,
                semantic_key=semantic_key,
                subject_kind="harness_skeleton_report",
                artifact_map=artifact_map,
                function_id=function_id,
            ),
        )


def _from_completion(
    payload: dict[str, Any],
    review_items: list[DossierReviewItem],
    unresolved: list[DossierUnresolvedItem],
    artifact_map: dict[str, DossierArtifact],
    function_id: str,
    registry: StableReviewIdRegistry,
    seen: set[str],
) -> None:
    for index, manual in enumerate(payload.get("manual_action_items", []), start=1):
        if not isinstance(manual, dict):
            continue
        raw_kind = str(manual.get("item_kind") or "manual_action")
        semantic_key = str(manual.get("item_id") or f"build/manual/{raw_kind}/{index}")
        review_id = registry.register(
            category="build_review",
            function_id=function_id,
            case_id=None,
            semantic_subject_key=semantic_key,
        )
        description = ja_text(manual.get("description", "手動でのビルド補完作業が残っています。"))
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_BUILD_{len(unresolved) + 1:03d}",
                "build_completion",
                raw_kind,
                description,
                ja_text(manual.get("reason", "ビルド補完は完全には自動化できません。")),
                ["build_completion_plan"],
                [],
                ja_text(manual.get("suggested_action", "ビルド補完計画を確認してください。")),
                blocks_readiness=False,
            )
        )
        _append_unique(
            review_items,
            seen,
            _review_item(
                review_id=review_id,
                category="build_review",
                title=f"ビルド補完項目を確認: {ja_label(raw_kind)}",
                description=description,
                related_artifacts=["build_completion_plan"],
                related_test_cases=[],
                case_id=None,
                semantic_key=semantic_key,
                subject_kind="build_completion_plan",
                artifact_map=artifact_map,
                function_id=function_id,
            ),
        )


def _from_execution(
    payload: dict[str, Any],
    review_items: list[DossierReviewItem],
    unresolved: list[DossierUnresolvedItem],
    artifact_map: dict[str, DossierArtifact],
    function_id: str,
    registry: StableReviewIdRegistry,
    seen: set[str],
) -> None:
    status = payload.get("function", {}).get("status") or payload.get("status")
    if status not in {
        "inconclusive",
        "failed",
        "blocked",
        "timeout",
        "timed_out",
        "not_run",
        "cancelled",
        "error",
    }:
        return
    status_text = str(status)
    semantic_key = f"execution/outcome/{status_text}"
    review_id = registry.register(
        category="execution_review",
        function_id=function_id,
        case_id=None,
        semantic_subject_key=semantic_key,
    )
    status_label = ja_label(status_text)
    unresolved.append(
        DossierUnresolvedItem(
            f"UNRESOLVED_EXEC_{len(unresolved) + 1:03d}",
            "execution_evidence",
            "execution_inconclusive",
            f"テスト実行状態は「{status_label}」です。",
            "このエビデンスだけでは最終PASS判定にはなりません。",
            ["test_execution_report"],
            [],
            "結果を確認し、必要に応じてテストを再実行してください。",
        )
    )
    _append_unique(
        review_items,
        seen,
        _review_item(
            review_id=review_id,
            category="execution_review",
            title=f"実行エビデンスを確認: {status_label}",
            description=f"テスト実行状態は「{status_label}」です。",
            related_artifacts=["test_execution_report"],
            related_test_cases=[],
            case_id=None,
            semantic_key=semantic_key,
            subject_kind="test_execution_report",
            artifact_map=artifact_map,
            function_id=function_id,
        ),
    )


def _review_item(
    *,
    review_id: str,
    category: str,
    title: str,
    description: str,
    related_artifacts: list[str],
    related_test_cases: list[str],
    case_id: str | None,
    semantic_key: str | None,
    subject_kind: str | None,
    artifact_map: dict[str, DossierArtifact],
    function_id: str,
    severity: str = "warning",
    reviewer_role: str = "unit_test_reviewer",
) -> DossierReviewItem:
    subjects: list[ReviewSubjectReference] = []
    if subject_kind is not None and semantic_key is not None:
        reference = _subject_reference(
            artifact_map.get(subject_kind),
            semantic_key=semantic_key,
            function_id=function_id,
        )
        if reference is not None:
            subjects.append(reference)
    return DossierReviewItem(
        review_id=review_id,
        category=category,
        title=title,
        description=description,
        related_artifacts=related_artifacts,
        related_test_cases=related_test_cases,
        severity=severity,
        suggested_reviewer_role=reviewer_role,
        done=False,
        case_id=case_id,
        semantic_subject_key=semantic_key,
        subject_artifacts=subjects,
    )


def _subject_reference(
    artifact: DossierArtifact | None,
    *,
    semantic_key: str,
    function_id: str,
) -> ReviewSubjectReference | None:
    if (
        artifact is None
        or artifact.contract_status != "valid"
        or artifact.compatible_migrated
        or artifact.sha256 is None
    ):
        return None
    subject = artifact.contract_subject
    source_path = subject.get("source_path")
    source_sha256 = subject.get("source_sha256")
    subject_function_id = subject.get("function_id")
    if (
        not isinstance(source_path, str)
        or not isinstance(source_sha256, str)
        or subject_function_id != function_id
    ):
        return None
    return ReviewSubjectReference(
        artifact_kind=artifact.artifact_kind,
        path=artifact.path.as_posix(),
        sha256=artifact.sha256,
        revision=artifact.contract_revision,
        source_path=source_path,
        source_sha256=source_sha256,
        function_id=function_id,
        semantic_subject_key=semantic_key,
    )


def _append_unique(
    review_items: list[DossierReviewItem],
    seen: set[str],
    item: DossierReviewItem,
) -> None:
    if item.review_id in seen:
        return
    seen.add(item.review_id)
    review_items.append(item)


def _function_id(payloads: dict[str, dict[str, Any]]) -> str:
    for key in ("test_spec", "function_signature", "function_location"):
        payload = payloads.get(key, {})
        function = payload.get("function")
        if isinstance(function, dict):
            value = function.get("function_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "unknown-function"


def _first_available_kind(
    artifact_map: dict[str, DossierArtifact],
    kinds: Iterable[str],
) -> str | None:
    for kind in kinds:
        if kind in artifact_map:
            return kind
    return None


__all__ = ["build_review_item_collection", "build_review_items"]
