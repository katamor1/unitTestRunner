from __future__ import annotations

import copy
import hashlib
import threading
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from unit_test_runner.contracts import ArtifactKind, migrate_payload, validate_payload
from unit_test_runner.contracts.registry import get_contract
from unit_test_runner.dossier.review_decision_models import (
    ReviewDecision,
    ReviewDecisionSet,
    ReviewIdCollisionError,
    ReviewItemCollection,
    ReviewItemSnapshot,
    ReviewSnapshot,
    ReviewResolution,
    ReviewSubjectReference,
    StableReviewIdRegistry,
    build_review_id,
)

from unit_test_runner.dossier.review_decision_repository import (
    ReviewDecisionRepository,
    ReviewDecisionWriteStatus,
)


class StableReviewIdTests(unittest.TestCase):
    def test_stable_id_normalizes_unicode_whitespace_and_separators(self):
        first = build_review_id(
            category=" expected＿result ",
            function_id="Control_Update",
            case_id="TC-01",
            semantic_subject_key=" return／value ",
        )
        second = build_review_id(
            category="expected-result",
            function_id="Control_Update",
            case_id="TC-01",
            semantic_subject_key="return/value",
        )

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("review-expected-result-"))

    def test_c_identifier_case_is_not_folded(self):
        upper = build_review_id(
            "expected_result",
            "Control_Update",
            "TC-01",
            "return/value",
        )
        lower = build_review_id(
            "expected_result",
            "control_update",
            "TC-01",
            "return/value",
        )

        self.assertNotEqual(upper, lower)

    def test_registry_reports_typed_collision_for_different_semantic_tuples(self):
        registry = StableReviewIdRegistry()
        with mock.patch(
            "unit_test_runner.review_ids._semantic_digest",
            return_value="0" * 16,
        ):
            registry.register(
                category="expected_result",
                function_id="Control_Update",
                case_id="TC-01",
                semantic_subject_key="return/value",
            )
            with self.assertRaises(ReviewIdCollisionError):
                registry.register(
                    category="expected_result",
                    function_id="Control_Update",
                    case_id="TC-02",
                    semantic_subject_key="return/value",
                )


class ReviewDecisionModelTests(unittest.TestCase):
    def _subject(self, *, revision: int | None = 2) -> ReviewSubjectReference:
        return ReviewSubjectReference(
            artifact_kind="test_spec",
            path="reports/test_spec.json",
            sha256="a" * 64,
            revision=revision,
            source_path="src/control.c",
            source_sha256="b" * 64,
            function_id="fn-Control_Update",
            semantic_subject_key="expected/return",
        )

    def test_terminal_decisions_require_reviewer_rationale_and_timezone(self):
        for resolution in (
            ReviewResolution.APPROVED,
            ReviewResolution.CHANGES_REQUESTED,
            ReviewResolution.WAIVED,
        ):
            with self.subTest(resolution=resolution, field="reviewer"):
                with self.assertRaisesRegex(ValueError, "reviewer"):
                    ReviewDecision(
                        review_id="review-1",
                        resolution=resolution,
                        reviewer=" ",
                        rationale="Reviewed evidence.",
                        decided_at="2026-07-12T00:00:00+00:00",
                        subject_artifacts=(self._subject(),),
                    )
            with self.subTest(resolution=resolution, field="rationale"):
                with self.assertRaisesRegex(ValueError, "rationale"):
                    ReviewDecision(
                        review_id="review-1",
                        resolution=resolution,
                        reviewer="reviewer01",
                        rationale=" ",
                        decided_at="2026-07-12T00:00:00+00:00",
                        subject_artifacts=(self._subject(),),
                    )
            with self.subTest(resolution=resolution, field="decided_at"):
                with self.assertRaisesRegex(ValueError, "timezone"):
                    ReviewDecision(
                        review_id="review-1",
                        resolution=resolution,
                        reviewer="reviewer01",
                        rationale="Reviewed evidence.",
                        decided_at="2026-07-12T00:00:00",
                        subject_artifacts=(self._subject(),),
                    )

    def test_open_decision_may_clear_terminal_metadata(self):
        decision = ReviewDecision(
            review_id="review-1",
            resolution=ReviewResolution.OPEN,
            reviewer="",
            rationale="",
            decided_at=None,
            subject_artifacts=(self._subject(),),
        )
        self.assertEqual(ReviewResolution.OPEN, decision.resolution)

    def test_decision_set_round_trips_exact_subject_fields(self):
        decision = ReviewDecision(
            review_id="review-1",
            resolution=ReviewResolution.APPROVED,
            reviewer="reviewer01",
            rationale="Reviewed evidence.",
            decided_at="2026-07-12T00:00:00+00:00",
            subject_artifacts=(self._subject(),),
        )
        decision_set = ReviewDecisionSet(revision=3, decisions=(decision,))

        restored = ReviewDecisionSet.from_data(decision_set.to_data())

        self.assertEqual(decision_set, restored)
        self.assertEqual(
            decision.subject_fingerprint,
            restored.decisions[0].subject_fingerprint,
        )

    def test_review_item_rejects_mismatched_semantic_subject_reference(self):
        subject = self._subject()
        review_id = build_review_id(
            "expected_result",
            "fn-Control_Update",
            "TC-01",
            "expected/return",
        )

        with self.assertRaisesRegex(ValueError, "semantic_subject_key"):
            ReviewItemSnapshot(
                review_id=review_id,
                category="expected_result",
                function_id="fn-Control_Update",
                case_id="TC-01",
                semantic_subject_key="expected/return",
                subject_artifacts=(
                    ReviewSubjectReference(
                        artifact_kind=subject.artifact_kind,
                        path=subject.path,
                        sha256=subject.sha256,
                        revision=subject.revision,
                        source_path=subject.source_path,
                        source_sha256=subject.source_sha256,
                        function_id=subject.function_id,
                        semantic_subject_key="different/subject",
                    ),
                ),
            )

    def test_review_snapshot_rejects_cross_source_subjects(self):
        subject = self._subject()
        review_id = build_review_id(
            "expected_result",
            "fn-Control_Update",
            "TC-01",
            "expected/return",
        )
        item = ReviewItemSnapshot(
            review_id=review_id,
            category="expected_result",
            function_id="fn-Control_Update",
            case_id="TC-01",
            semantic_subject_key="expected/return",
            subject_artifacts=(subject,),
        )

        with self.assertRaisesRegex(ValueError, "source identity"):
            ReviewSnapshot(
                items=ReviewItemCollection((item,)),
                function_id="fn-Control_Update",
                source_path="src/other.c",
                source_sha256="c" * 64,
            )


class ReviewDecisionContractTests(unittest.TestCase):
    def test_task6_contract_versions_are_current_and_v1_remains_registered(self):
        self.assertEqual(
            "1.1.0", get_contract(ArtifactKind.REVIEW_DECISIONS).current_version
        )
        self.assertEqual(
            "1.1.0", get_contract(ArtifactKind.FUNCTION_DOSSIER).current_version
        )
        self.assertEqual(
            "1.1.0", get_contract(ArtifactKind.DOSSIER_MANIFEST).current_version
        )
        for kind in (
            ArtifactKind.REVIEW_DECISIONS,
            ArtifactKind.FUNCTION_DOSSIER,
            ArtifactKind.DOSSIER_MANIFEST,
        ):
            self.assertEqual("1.0.0", get_contract(kind, "1.0.0").current_version)

    def test_current_contract_rejects_mismatched_subject_fingerprint(self):
        reference = ReviewSubjectReference(
            artifact_kind="test_spec",
            path="reports/test_spec.json",
            sha256="a" * 64,
            revision=2,
            source_path="src/control.c",
            source_sha256="b" * 64,
            function_id="fn-Control_Update",
            semantic_subject_key="expected/return",
        )
        decision = ReviewDecision(
            review_id="review-1",
            resolution=ReviewResolution.APPROVED,
            reviewer="reviewer01",
            rationale="Reviewed evidence.",
            decided_at="2026-07-12T00:00:00+00:00",
            subject_artifacts=(reference,),
        )
        payload = {
            "artifact_kind": "review_decisions",
            "schema_version": "1.1.0",
            "producer": {
                "name": "unit-test-runner",
                "version": "0.1.0",
                "commit": "test-commit",
            },
            "subject": {
                "function_id": "fn-Control_Update",
                "source_path": "src/control.c",
                "source_sha256": "b" * 64,
            },
            "data": ReviewDecisionSet(revision=1, decisions=(decision,)).to_data(),
            "extensions": {},
        }
        payload["data"]["decisions"][0]["subject_fingerprint"] = "f" * 64

        violations = validate_payload(ArtifactKind.REVIEW_DECISIONS, payload)

        self.assertIn(
            ("invalid_subject_fingerprint", "$.data.decisions[0].subject_fingerprint"),
            {(item.code, item.json_path) for item in violations},
        )

    def test_v1_decision_migration_is_lossless_and_marks_revision_unproven(self):
        original = {
            "artifact_kind": "review_decisions",
            "schema_version": "1.0.0",
            "producer": {
                "name": "unit-test-runner",
                "version": "0.1.0",
                "commit": "test-commit",
            },
            "subject": {
                "function_id": "fn-Control_Update",
                "source_path": "src/control.c",
                "source_sha256": "b" * 64,
            },
            "data": {
                "revision": 1,
                "decisions": [
                    {
                        "review_id": "review-1",
                        "resolution": "approved",
                        "reviewer": "reviewer01",
                        "rationale": "Reviewed evidence.",
                        "decided_at": "2026-07-12T00:00:00+00:00",
                        "subject_artifacts": [
                            {
                                "artifact_kind": "test_spec",
                                "path": "reports/test_spec.json",
                                "sha256": "a" * 64,
                            }
                        ],
                    }
                ],
            },
            "extensions": {},
        }
        before = copy.deepcopy(original)
        encoded_before = json.dumps(original, sort_keys=True).encode("utf-8")

        migrated = migrate_payload(
            ArtifactKind.REVIEW_DECISIONS,
            original,
            target_version="1.1.0",
        )

        self.assertEqual(before, original)
        self.assertEqual(encoded_before, json.dumps(original, sort_keys=True).encode("utf-8"))
        reference = migrated["data"]["decisions"][0]["subject_artifacts"][0]
        self.assertIsNone(reference["revision"])
        self.assertIsNone(reference["semantic_subject_key"])
        self.assertTrue(migrated["extensions"]["migration"]["display_only"])
        self.assertEqual((), validate_payload(ArtifactKind.REVIEW_DECISIONS, migrated))


class DossierReviewIdParityTests(unittest.TestCase):
    def test_generated_case_review_id_retains_exact_test_spec_subject(self):
        from unit_test_runner.dossier.dossier_models import DossierArtifact
        from unit_test_runner.dossier.review_workflow import (
            build_review_item_collection,
            build_review_items,
        )

        function_id = "fn-Control_Update"
        case_id = "TC_ADD_1"
        review_id = build_review_id(
            "generated_case_review",
            function_id,
            case_id,
            "legacy/review-required",
        )
        artifact = DossierArtifact(
            artifact_id="ARTIFACT_TEST_SPEC",
            artifact_kind="test_spec",
            path=Path("reports/test_spec.json"),
            exists=True,
            sha256="a" * 64,
            schema_version="1.1.0",
            produced_by_item="test_spec_generation",
            required_level="required",
            contract_status="valid",
            contract_violations=[],
            contract_subject={
                "function_id": function_id,
                "source_path": "src/control.c",
                "source_sha256": "b" * 64,
            },
            contract_revision=3,
        )

        review_items, _unresolved = build_review_items(
            {
                "test_spec": {
                    "function": {
                        "function_id": function_id,
                        "name": "Control_Update",
                    },
                    "additional_case_candidates": [
                        {
                            "test_case_id": case_id,
                            "review_item_ids": [review_id],
                            "expected_observations": [
                                {"expected_expression": "TBD_EXPECTED_RETURN"}
                            ],
                        }
                    ],
                }
            },
            [artifact],
        )
        collection = build_review_item_collection(review_items)

        snapshot = next(item for item in collection.items if item.review_id == review_id)
        self.assertEqual("generated_case_review", snapshot.category)
        self.assertEqual(case_id, snapshot.case_id)
        self.assertEqual("legacy/review-required", snapshot.semantic_subject_key)
        self.assertEqual(1, len(snapshot.subject_artifacts))
        self.assertEqual("reports/test_spec.json", snapshot.subject_artifacts[0].path)
        self.assertEqual(3, snapshot.subject_artifacts[0].revision)

    def test_dossier_reuses_test_spec_review_ids_instead_of_ordinal_ids(self):
        from unit_test_runner.dossier.review_workflow import build_review_items

        review_id = build_review_id(
            "expected_result_review",
            "fn-Control_Update",
            "TC-01",
            "expected/return",
        )
        review_items, _unresolved = build_review_items(
            {
                "test_spec": {
                    "function": {
                        "function_id": "fn-Control_Update",
                        "name": "Control_Update",
                    },
                    "test_cases": [
                        {
                            "test_case_id": "TC-01",
                            "review_item_ids": [review_id],
                            "expected_observations": [
                                {"expected_expression": "TBD_EXPECTED_RETURN"}
                            ],
                        }
                    ],
                }
            }
        )

        self.assertIn(review_id, {item.review_id for item in review_items})
        self.assertFalse(
            any(item.review_id.startswith("REVIEW_EXPECTED_") for item in review_items)
        )


class TestSpecStableReviewIdTests(unittest.TestCase):
    def test_test_spec_generation_uses_the_shared_stable_id_builder(self):
        from unit_test_runner.c_analyzer.boundary_candidate_analyzer import (
            generate_boundary_equivalence_candidates,
        )
        from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
        from unit_test_runner.c_analyzer.coverage_design_analyzer import (
            analyze_coverage_design,
        )
        from unit_test_runner.c_analyzer.function_locator import locate_function
        from unit_test_runner.c_analyzer.global_access_analyzer import (
            analyze_global_access,
        )
        from unit_test_runner.c_analyzer.signature_extractor import extract_signature
        from unit_test_runner.c_analyzer.source_digest import build_source_digest
        from unit_test_runner.test_design.test_case_design_generator import (
            generate_test_case_design,
        )
        from unit_test_runner.test_spec import (
            ArtifactReference,
            create_test_spec_from_design,
        )

        source = (
            __import__("pathlib").Path(__file__).resolve().parent
            / "fixtures"
            / "c_sources"
            / "analysis_pipeline"
            / "pipeline.c"
        )
        digest = build_source_digest(source)
        location = locate_function(digest, "Control_Update")
        signature = extract_signature(digest, location)
        globals_report = analyze_global_access(digest, location, signature)
        calls = analyze_calls(digest, location, signature, globals_report)
        coverage = analyze_coverage_design(
            digest, location, signature, globals_report, calls
        )
        boundaries = generate_boundary_equivalence_candidates(
            signature, globals_report, calls, coverage
        )
        design = generate_test_case_design(
            signature, globals_report, calls, coverage, boundaries
        )
        spec = create_test_spec_from_design(
            design,
            signature.to_dict(),
            source_path="src/pipeline.c",
            generated_from=[
                ArtifactReference(
                    "function_signature",
                    "reports/function_signature.json",
                    "3" * 64,
                )
            ],
        )

        expected = set()
        for item in design.unresolved_items:
            case_ids = item.related_test_case_ids or [None]
            for case_id in case_ids:
                expected.add(
                    build_review_id(
                        item.item_kind,
                        spec.function.function_id,
                        case_id,
                        item.item_id,
                    )
                )
        self.assertTrue(expected)
        self.assertTrue(expected.issubset(set(spec.review_item_ids)))
        self.assertTrue(
            all(
                set(case.get("review_item_ids", ())).issubset(set(spec.review_item_ids))
                for case in spec.additional_case_candidates
            )
        )


if __name__ == "__main__":
    unittest.main()


class ReviewDecisionRepositoryTests(unittest.TestCase):
    def _item(self) -> ReviewItemSnapshot:
        reference = ReviewSubjectReference(
            artifact_kind="test_spec",
            path="reports/test_spec.json",
            sha256="a" * 64,
            revision=3,
            source_path="src/control.c",
            source_sha256="b" * 64,
            function_id="fn-Control_Update",
            semantic_subject_key="expected/return",
        )
        return ReviewItemSnapshot(
            review_id=build_review_id(
                "expected_result",
                "fn-Control_Update",
                "TC-01",
                "expected/return",
            ),
            category="expected_result",
            function_id="fn-Control_Update",
            case_id="TC-01",
            semantic_subject_key="expected/return",
            subject_artifacts=(reference,),
        )

    def _repository(self, root: Path) -> tuple[ReviewDecisionRepository, ReviewItemSnapshot]:
        item = self._item()
        return (
            ReviewDecisionRepository(
                root,
                current_items=ReviewItemCollection((item,)),
                producer_version="0.1.0",
                producer_commit="test-commit",
            ),
            item,
        )

    def _record(
        self,
        repository: ReviewDecisionRepository,
        item: ReviewItemSnapshot,
        *,
        review_id: str | None = None,
        fingerprint: str | None = None,
        expected_revision: int = 0,
    ):
        return repository.record(
            review_id=review_id or item.review_id,
            resolution=ReviewResolution.APPROVED,
            reviewer="reviewer01",
            rationale="Reviewed evidence.",
            decided_at="2026-07-12T00:00:00+00:00",
            expected_revision=expected_revision,
            expected_subject_fingerprint=(
                fingerprint
                if fingerprint is not None
                else item.subject_fingerprint
            ),
        )

    def test_unknown_id_and_subject_guard_write_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, item = self._repository(root)
            path = root / "reports" / "review_decisions.json"

            unknown = self._record(repository, item, review_id="review-unknown")
            mismatch = self._record(repository, item, fingerprint="f" * 64)

            self.assertEqual(ReviewDecisionWriteStatus.UNKNOWN_REVIEW_ID, unknown.status)
            self.assertEqual(
                ReviewDecisionWriteStatus.SUBJECT_FINGERPRINT_MISMATCH,
                mismatch.status,
            )
            self.assertFalse(path.exists())
            self.assertIsNone(unknown.artifact)
            self.assertIsNone(mismatch.artifact)

    def test_write_uses_resolved_subjects_and_exact_final_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, item = self._repository(root)

            result = self._record(repository, item)

            self.assertEqual(ReviewDecisionWriteStatus.WRITTEN, result.status)
            self.assertIsNotNone(result.snapshot)
            self.assertIsNotNone(result.artifact)
            path = root / "reports" / "review_decisions.json"
            raw = path.read_bytes()
            self.assertEqual(raw, result.snapshot.raw_bytes)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), result.snapshot.sha256)
            self.assertEqual(result.snapshot.sha256, result.artifact.sha256)
            restored = ReviewDecisionSet.from_data(result.snapshot.payload["data"])
            stored = restored.decisions[0]
            self.assertEqual(item.subject_artifacts, stored.subject_artifacts)
            self.assertEqual(item.subject_fingerprint, stored.subject_fingerprint)
            self.assertEqual(1, restored.revision)

    def test_sequential_stale_writer_is_a_no_write_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, item = self._repository(root)
            first = self._record(repository, item)
            before = (root / "reports" / "review_decisions.json").read_bytes()

            stale = self._record(repository, item, expected_revision=0)

            self.assertEqual(ReviewDecisionWriteStatus.WRITTEN, first.status)
            self.assertEqual(ReviewDecisionWriteStatus.REVISION_CONFLICT, stale.status)
            self.assertEqual(1, stale.current_revision)
            self.assertEqual(
                before,
                (root / "reports" / "review_decisions.json").read_bytes(),
            )

    def test_concurrent_stale_writers_yield_exactly_one_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, item = self._repository(root)
            barrier = threading.Barrier(2)
            results = []
            errors = []

            def write() -> None:
                try:
                    barrier.wait(timeout=5)
                    results.append(self._record(repository, item))
                except BaseException as error:  # pragma: no cover - asserted below
                    errors.append(error)

            threads = [threading.Thread(target=write) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertEqual([], errors)
            self.assertEqual(2, len(results))
            self.assertEqual(
                [
                    ReviewDecisionWriteStatus.REVISION_CONFLICT,
                    ReviewDecisionWriteStatus.WRITTEN,
                ],
                sorted((item.status for item in results), key=str),
            )
            snapshot = repository.load()
            self.assertEqual(1, snapshot.decision_set.revision)
            self.assertEqual(1, len(snapshot.decision_set.decisions))

    def test_invalid_existing_ledger_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, item = self._repository(root)
            path = root / "reports" / "review_decisions.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"{not-json")

            result = self._record(repository, item)

            self.assertEqual(ReviewDecisionWriteStatus.INVALID_LEDGER, result.status)
            self.assertEqual(b"{not-json", path.read_bytes())

    def test_symlinked_reports_and_lock_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            reports = root / "reports"
            try:
                reports.symlink_to(Path(outside), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable")
            with self.assertRaisesRegex(ValueError, "symlink|reparse"):
                self._repository(root)

        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            repository, item = self._repository(root)
            reports = root / "reports"
            reports.mkdir(parents=True, exist_ok=True)
            lock_path = reports / ".review_decisions.json.lock"
            lock_path.symlink_to(Path(outside) / "lock")
            with self.assertRaisesRegex(ValueError, "symlink|reparse"):
                self._record(repository, item)
