from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.dossier.workflow import analyze_function_workflow
from unit_test_runner.dossier.finalizer import finalize_function_dossier
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

    def test_reanalysis_writes_candidate_without_mutating_canonical_spec(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            product = root / "product"
            shutil.copytree(FIXTURE, product)
            out = root / "Control_Update"
            analyze_function_workflow(
                product, product / "Product.dsw", "src/control.c", "Control_Update",
                "Win32 Debug", out, "Control", phase="design",
            )
            finalize_function_dossier(out, "Control_Update")
            canonical = out / "reports" / "test_spec.json"
            before_bytes = canonical.read_bytes()
            before = json.loads(before_bytes.decode("utf-8"))
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
                ),
            )

            candidate_path = Path(result["reports"]["candidate_test_spec_json"])
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            self.assertEqual(before_bytes, canonical.read_bytes())
            self.assertEqual(before["data"]["revision"], candidate["data"]["revision"])
            self.assertNotEqual(
                before["data"]["source"]["sha256"],
                candidate["data"]["source"]["sha256"],
            )
            self.assertEqual(
                canonical.resolve(),
                Path(result["test_spec_path"]).resolve(),
            )
            self.assertEqual(1, result["test_spec_revision"])
            self.assertFalse((out / "reports" / "updated_test_case_design.json").exists())
            self.assertFalse((out / "reports" / "test_case_design.json").exists())

    def test_source_change_without_coverage_mapping_recommends_all_existing_cases_without_selecting_them(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            product = root / "product"
            shutil.copytree(FIXTURE, product)
            out = root / "Control_Update"
            analyze_function_workflow(
                product, product / "Product.dsw", "src/control.c", "Control_Update",
                "Win32 Debug", out, "Control", phase="design",
            )
            canonical_path = out / "reports" / "test_spec.json"
            canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
            known_coverage_id = next(
                iter(canonical["data"]["coverage_summary"]["coverage_to_test_cases"])
            )
            canonical["data"]["test_cases"] = [
                {
                    "test_case_id": "tc-existing-001",
                    "title": "existing one",
                    "target_function": "Control_Update",
                    "purpose": "existing regression coverage",
                    "priority": "high",
                    "case_kind": "branch",
                    "input_assignments": [],
                    "stub_setups": [],
                    "expected_observations": [
                        {"observation_kind": "return_value", "expected_expression": "0"}
                    ],
                    "coverage_links": [{"coverage_id": known_coverage_id}],
                },
                {
                    "test_case_id": "tc-existing-002",
                    "title": "existing two",
                    "target_function": "Control_Update",
                    "purpose": "existing regression coverage",
                    "priority": "medium",
                    "case_kind": "branch",
                    "input_assignments": [],
                    "stub_setups": [],
                    "expected_observations": [
                        {"observation_kind": "return_value", "expected_expression": "0"}
                    ],
                    "coverage_links": [],
                },
            ]
            canonical_path.write_text(
                json.dumps(canonical, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            finalize_function_dossier(out, "Control_Update")
            source = product / "src" / "control.c"
            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            result = reanalyze_function_workflow(
                product, product / "Product.dsw", "src/control.c", "Control_Update",
                "Win32 Debug", out, project_name="Control",
            )

            recommendation = result["change_impact"].regression_recommendation
            self.assertEqual("run_all_existing_tests", recommendation.recommendation_kind)
            self.assertEqual(0, recommendation.selected_count)
            self.assertIn(
                f"all {len(canonical['data']['test_cases'])} existing test cases",
                recommendation.reason,
            )
            self.assertEqual([], result["regression_selection"].selected_test_cases)


if __name__ == "__main__":
    unittest.main()
