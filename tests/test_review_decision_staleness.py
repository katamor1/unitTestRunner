from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.spec_support import valid_test_spec_payload
from unit_test_runner.dossier.review_assessment import (
    ReviewAssessmentStatus,
    assess_review_decisions,
)
from unit_test_runner.dossier.review_decision_models import (
    ReviewDecision,
    ReviewDecisionSet,
    ReviewItemCollection,
    ReviewItemSnapshot,
    ReviewResolution,
    ReviewSubjectReference,
    build_review_id,
)


FUNCTION_ID = "fn-control-update"
CATEGORY = "expected_result"
CASE_ID = "tc-control-update-001"
SEMANTIC_KEY = "expected/return"


def _reference(**overrides) -> ReviewSubjectReference:
    values = {
        "artifact_kind": "test_spec",
        "path": "reports/test_spec.json",
        "sha256": "a" * 64,
        "revision": 1,
        "source_path": "src/control.c",
        "source_sha256": "1" * 64,
        "function_id": FUNCTION_ID,
        "semantic_subject_key": SEMANTIC_KEY,
    }
    values.update(overrides)
    return ReviewSubjectReference(**values)


def _item(reference: ReviewSubjectReference | None = None, *, semantic_key: str = SEMANTIC_KEY) -> ReviewItemSnapshot:
    reference = reference or _reference(semantic_subject_key=semantic_key)
    return ReviewItemSnapshot(
        review_id=build_review_id(CATEGORY, FUNCTION_ID, CASE_ID, semantic_key),
        category=CATEGORY,
        function_id=FUNCTION_ID,
        case_id=CASE_ID,
        semantic_subject_key=semantic_key,
        subject_artifacts=(reference,),
    )


def _decision(
    item: ReviewItemSnapshot,
    *,
    resolution: ReviewResolution = ReviewResolution.APPROVED,
    subjects: tuple[ReviewSubjectReference, ...] | None = None,
) -> ReviewDecision:
    terminal = resolution is not ReviewResolution.OPEN
    return ReviewDecision(
        review_id=item.review_id,
        resolution=resolution,
        reviewer="reviewer01" if terminal else "",
        rationale="Reviewed exact subjects." if terminal else "",
        decided_at="2026-07-12T00:00:00+00:00" if terminal else None,
        subject_artifacts=subjects or item.subject_artifacts,
    )


def _set(*decisions: ReviewDecision) -> ReviewDecisionSet:
    return ReviewDecisionSet(revision=1, decisions=tuple(decisions))


class ReviewDecisionStalenessTests(unittest.TestCase):
    def test_only_exact_current_approved_or_waived_decisions_complete_review(self):
        for resolution, expected_status, complete in (
            (ReviewResolution.APPROVED, ReviewAssessmentStatus.APPROVED, True),
            (ReviewResolution.WAIVED, ReviewAssessmentStatus.WAIVED, True),
            (ReviewResolution.OPEN, ReviewAssessmentStatus.OPEN, False),
            (
                ReviewResolution.CHANGES_REQUESTED,
                ReviewAssessmentStatus.CHANGES_REQUESTED,
                False,
            ),
        ):
            with self.subTest(resolution=resolution):
                item = _item()
                result = assess_review_decisions(
                    ReviewItemCollection((item,)),
                    _set(_decision(item, resolution=resolution)),
                )
                self.assertEqual(expected_status, result.for_review_id(item.review_id).status)
                self.assertEqual(complete, result.review_complete)

    def test_missing_decision_is_blocking(self):
        item = _item()
        result = assess_review_decisions(ReviewItemCollection((item,)), None)
        self.assertEqual(
            ReviewAssessmentStatus.MISSING,
            result.for_review_id(item.review_id).status,
        )
        self.assertFalse(result.review_complete)

    def test_every_exact_subject_identity_change_is_stale(self):
        item = _item()
        original = item.subject_artifacts[0]
        changes = {
            "path": replace(original, path="reports/moved_test_spec.json"),
            "kind": replace(original, artifact_kind="function_signature"),
            "hash": replace(original, sha256="b" * 64),
            "revision": replace(original, revision=2),
            "source_path": replace(original, source_path="src/other.c"),
            "source_hash": replace(original, source_sha256="2" * 64),
            "function": replace(original, function_id="fn-other"),
            "semantic_key": replace(
                original,
                semantic_subject_key="expected/global/state",
            ),
        }
        for label, changed in changes.items():
            with self.subTest(field=label):
                result = assess_review_decisions(
                    ReviewItemCollection((item,)),
                    _set(_decision(item, subjects=(changed,))),
                )
                assessment = result.for_review_id(item.review_id)
                self.assertEqual(ReviewAssessmentStatus.STALE, assessment.status)
                self.assertTrue(assessment.reasons)
                self.assertFalse(result.review_complete)

    def test_changed_semantic_subject_creates_new_item_and_orphans_prior_decision(self):
        old_item = _item()
        new_key = "expected/global/state"
        new_item = _item(
            _reference(semantic_subject_key=new_key),
            semantic_key=new_key,
        )
        result = assess_review_decisions(
            ReviewItemCollection((new_item,)),
            _set(_decision(old_item)),
        )

        self.assertEqual((old_item.review_id,), result.orphan_review_ids)
        self.assertEqual(
            ReviewAssessmentStatus.MISSING,
            result.for_review_id(new_item.review_id).status,
        )
        self.assertFalse(result.review_complete)

    def test_current_subject_file_must_exist_parse_validate_and_match_exact_bytes(self):
        cases = ("missing", "hash_mismatch", "invalid_json", "schema_invalid")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                reports = root / "reports"
                reports.mkdir()
                path = reports / "test_spec.json"
                payload = valid_test_spec_payload()
                raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
                if case == "hash_mismatch":
                    path.write_bytes(raw + b" ")
                    reference_hash = hashlib.sha256(raw).hexdigest()
                elif case == "invalid_json":
                    bad = b"{not-json\n"
                    path.write_bytes(bad)
                    reference_hash = hashlib.sha256(bad).hexdigest()
                elif case == "schema_invalid":
                    bad = b"{}\n"
                    path.write_bytes(bad)
                    reference_hash = hashlib.sha256(bad).hexdigest()
                else:
                    reference_hash = hashlib.sha256(raw).hexdigest()
                reference = _reference(sha256=reference_hash)
                item = _item(reference)
                result = assess_review_decisions(
                    ReviewItemCollection((item,)),
                    _set(_decision(item)),
                    workspace=root,
                )
                assessment = result.for_review_id(item.review_id)
                self.assertEqual(ReviewAssessmentStatus.STALE, assessment.status)
                self.assertIn(f"subject_{case}", assessment.reasons)

    def test_valid_current_artifact_and_exact_decision_are_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "reports" / "test_spec.json"
            path.parent.mkdir()
            payload = valid_test_spec_payload()
            raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            path.write_bytes(raw)
            reference = _reference(sha256=hashlib.sha256(raw).hexdigest())
            item = _item(reference)

            result = assess_review_decisions(
                ReviewItemCollection((item,)),
                _set(_decision(item)),
                workspace=root,
            )

            self.assertEqual(
                ReviewAssessmentStatus.APPROVED,
                result.for_review_id(item.review_id).status,
            )
            self.assertTrue(result.review_complete)


if __name__ == "__main__":
    unittest.main()
