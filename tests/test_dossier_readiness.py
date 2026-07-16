from __future__ import annotations

import unittest
from pathlib import Path

from unit_test_runner.contracts import RunOutcome
from unit_test_runner.dossier.dossier_models import (
    DossierArtifact,
)
from unit_test_runner.dossier.readiness import assess_readiness
from unit_test_runner.dossier.review_assessment import (
    ReviewAssessment,
    ReviewAssessmentStatus,
    ReviewItemAssessment,
)


CORE_KINDS = ("source_digest", "function_location", "function_signature")


def _artifact(
    kind: str,
    *,
    exists: bool = True,
    status: str = "valid",
    required_level: str = "mvp1_required",
    migrated: bool = False,
    modified_at: str | None = "2026-07-12T00:00:00+00:00",
) -> DossierArtifact:
    return DossierArtifact(
        artifact_id=f"ART_{kind}",
        artifact_kind=kind,
        path=Path("reports") / f"{kind}.json",
        exists=exists,
        sha256="a" * 64 if exists else None,
        schema_version="1.0.0" if exists else None,
        produced_by_item="test",
        required_level=required_level,
        contract_status=status,
        contract_violations=[],
        compatible_migrated=migrated,
        modified_at=modified_at,
    )


def _core_artifacts(**overrides) -> list[DossierArtifact]:
    return [_artifact(kind, **overrides) for kind in CORE_KINDS]


def _review(status: ReviewAssessmentStatus) -> ReviewAssessment:
    item = ReviewItemAssessment(
        review_id="review-item-001",
        status=status,
        resolution=None,
        reasons=(),
        subject_fingerprint="b" * 64,
    )
    return ReviewAssessment(ledger_revision=1, items=(item,), orphan_review_ids=())


class DossierSemanticReadinessTests(unittest.TestCase):
    def test_every_run_outcome_is_reviewable_but_only_passed_is_green(self):
        for outcome in RunOutcome:
            with self.subTest(outcome=outcome):
                readiness = assess_readiness(
                    _core_artifacts(),
                    [],
                    [],
                    review_assessment=_review(ReviewAssessmentStatus.APPROVED),
                    execution_outcome=outcome,
                    evidence_integrity=True,
                )
                self.assertTrue(readiness.ready_for_review)
                self.assertTrue(readiness.review_complete)
                self.assertTrue(readiness.evidence_ready)
                self.assertEqual(outcome is RunOutcome.PASSED, readiness.test_green)

    def test_four_axes_remain_independent(self):
        readiness = assess_readiness(
            _core_artifacts(),
            [],
            [],
            review_assessment=_review(ReviewAssessmentStatus.MISSING),
            execution_outcome=RunOutcome.FAILED,
            evidence_integrity=True,
        )
        self.assertTrue(readiness.ready_for_review)
        self.assertFalse(readiness.review_complete)
        self.assertTrue(readiness.evidence_ready)
        self.assertFalse(readiness.test_green)

    def test_existence_and_mtime_never_advance_semantic_readiness(self):
        merely_existing = _core_artifacts(status="missing", exists=True)
        old = assess_readiness(merely_existing, [], [])
        for artifact in merely_existing:
            artifact.modified_at = "2099-01-01T00:00:00+00:00"
        newer = assess_readiness(merely_existing, [], [])

        self.assertFalse(old.ready_for_review)
        self.assertEqual(old.to_dict(), newer.to_dict())

    def test_contract_state_not_exists_flag_is_the_authority(self):
        exists = assess_readiness(_core_artifacts(exists=True), [], [])
        synthetic_no_exists = assess_readiness(_core_artifacts(exists=False), [], [])
        self.assertEqual(exists.ready_for_review, synthetic_no_exists.ready_for_review)
        self.assertTrue(exists.ready_for_review)

    def test_optional_absence_affects_only_declared_optional_dependency(self):
        base = _core_artifacts()
        optional = _artifact(
            "optional_notes",
            exists=False,
            status="missing",
            required_level="optional",
        )
        required = _artifact(
            "function_signature",
            exists=False,
            status="missing",
            required_level="mvp1_required",
        )

        with_optional = assess_readiness([*base, optional], [], [])
        with_required_missing = assess_readiness(
            [item for item in base if item.artifact_kind != "function_signature"]
            + [required],
            [],
            [],
        )

        self.assertTrue(with_optional.ready_for_review)
        self.assertFalse(with_required_missing.ready_for_review)
        self.assertFalse(with_optional.blocked)

    def test_compatible_migrated_artifact_is_display_only(self):
        artifacts = _core_artifacts()
        artifacts[-1] = _artifact("function_signature", migrated=True)

        readiness = assess_readiness(artifacts, [], [])

        self.assertFalse(readiness.ready_for_review)
        self.assertIn(
            "function_signature is compatible-migrated display-only",
            readiness.blocked_reasons,
        )


if __name__ == "__main__":
    unittest.main()
