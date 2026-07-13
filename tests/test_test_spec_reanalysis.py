from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.dossier.workflow import analyze_function_workflow
from unit_test_runner.reanalysis.reanalysis_models import ReanalysisPolicy
from unit_test_runner.reanalysis.workflow import reanalyze_function_workflow
from unit_test_runner.reanalysis.workflow import _merge_reanalysis_candidate
from unit_test_runner.test_spec import TestSpec, validate_test_spec
from tests.spec_support import copied_payload, current_context


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


class TestSpecReanalysisTests(unittest.TestCase):
    def test_reanalysis_candidate_carries_current_design_and_preserved_review_references(self):
        previous = TestSpec.from_payload(copied_payload())
        previous.unresolved_items = [
            {
                "item_id": "review-input-001",
                "item_kind": "input_review",
                "description": "review input",
                "related_test_case_ids": ["tc-control-update-001"],
                "reason": "manual",
                "suggested_action": "review",
            }
        ]
        current = TestSpec.from_payload(copied_payload())
        current.test_cases = []
        current.additional_case_candidates = [
            {
                "test_case_id": "tc-current-candidate",
                "coverage_links": [{"coverage_id": "cov-normal"}],
                "review_item_ids": ["review-current"],
            }
        ]
        current.review_item_ids = ["review-current"]
        current.unresolved_items = [
            {
                "item_id": "review-current",
                "item_kind": "candidate_review",
                "description": "review candidate",
                "related_test_case_ids": ["tc-current-candidate"],
                "reason": "generated",
                "suggested_action": "review",
            }
        ]
        updated_design = previous.to_payload()["data"]

        candidate = _merge_reanalysis_candidate(current, previous, updated_design)

        self.assertNotIn(
            "tc-control-update-001",
            {item["test_case_id"] for item in candidate.test_cases},
        )
        self.assertEqual(
            {"tc-control-update-001", "tc-current-candidate"},
            {
                item["test_case_id"]
                for item in candidate.additional_case_candidates
            },
        )
        self.assertTrue({"review-current", "review-input-001", "review-oracle-001"}.issubset(candidate.review_item_ids))
        self.assertEqual(
            {"review-current", "review-input-001"},
            {item["item_id"] for item in candidate.unresolved_items},
        )
        self.assertEqual((), validate_test_spec(candidate, current_context=current_context()))

    def test_reanalysis_updates_canonical_spec_through_expected_revision_without_legacy_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            product = root / "product"
            shutil.copytree(FIXTURE, product)
            out = root / "Control_Update"
            analyze_function_workflow(
                product, product / "Product.dsw", "src/control.c", "Control_Update",
                "Win32 Debug", out, "Control", phase="design",
            )
            canonical = out / "reports" / "test_spec.json"
            before = json.loads(canonical.read_text(encoding="utf-8"))
            source = product / "src" / "control.c"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    "sensor_value < SENSOR_MIN", "sensor_value <= SENSOR_MIN"
                ),
                encoding="utf-8",
            )

            result = reanalyze_function_workflow(
                product, product / "Product.dsw", "src/control.c", "Control_Update",
                "Win32 Debug", out, project_name="Control",
                policy=ReanalysisPolicy(
                    generate_updated_test_case_design=True,
                    overwrite_test_case_design=True,
                ),
            )

            after = json.loads(canonical.read_text(encoding="utf-8"))
            self.assertEqual(2, after["data"]["revision"])
            self.assertNotEqual(before["data"]["source"]["sha256"], after["data"]["source"]["sha256"])
            self.assertEqual(
                canonical.resolve(),
                Path(result["test_spec_path"]).resolve(),
            )
            self.assertEqual(2, result["test_spec_revision"])
            self.assertFalse((out / "reports" / "updated_test_case_design.json").exists())
            self.assertFalse((out / "reports" / "test_case_design.json").exists())


if __name__ == "__main__":
    unittest.main()
