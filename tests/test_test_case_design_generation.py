import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
PIPELINE = REPO_ROOT / "tests" / "fixtures" / "c_sources" / "analysis_pipeline" / "pipeline.c"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.c_analyzer.boundary_candidate_analyzer import generate_boundary_equivalence_candidates
from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.coverage_design_analyzer import analyze_coverage_design
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest
from unit_test_runner.test_design.test_case_design_generator import generate_test_case_design
from unit_test_runner.test_design.test_case_models import TestCaseGenerationPolicy


def run_module(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class TestCaseDesignGenerationTests(unittest.TestCase):
    def setUp(self):
        digest = build_source_digest(PIPELINE)
        location = locate_function(digest, "Control_Update")
        signature = extract_signature(digest, location)
        global_access = analyze_global_access(digest, location, signature)
        call_report = analyze_calls(digest, location, signature, global_access)
        coverage = analyze_coverage_design(digest, location, signature, global_access, call_report)
        boundary = generate_boundary_equivalence_candidates(signature, global_access, call_report, coverage)
        self.report = generate_test_case_design(signature, global_access, call_report, coverage, boundary)

    def test_generator_maps_coverage_candidates_and_placeholders_to_design_cases(self):
        payload = self.report.to_dict()

        self.assertEqual("generated", payload["function"]["status"])
        summary = payload["coverage_summary"]
        self.assertGreater(summary["total_coverage_items"], 0)
        self.assertEqual(summary["total_coverage_items"], summary["covered_by_design_count"])
        self.assertFalse(summary["uncovered_coverage_ids"])

        cases = payload["test_cases"]
        kinds = {case["case_kind"] for case in cases}
        self.assertIn("branch", kinds)
        self.assertIn("switch_case", kinds)
        self.assertIn("loop", kinds)
        self.assertIn("return_path", kinds)

        all_inputs = [assignment for case in cases for assignment in case["input_assignments"]]
        self.assertTrue(any(item["target_name"] == "sensor" and item["value_expression"] == "SENSOR_MIN" for item in all_inputs))
        self.assertTrue(any(item["target_name"] == "out_value" and item["value_expression"] == "NULL" for item in all_inputs))

        all_stubs = [stub for case in cases for stub in case["stub_setups"]]
        self.assertTrue(any(stub["stub_name"] == "CheckLimit" and stub["setup_kind"] == "return_value" for stub in all_stubs))
        self.assertTrue(any(stub["setup_kind"] == "call_count_observation" for stub in all_stubs))
        for case in cases:
            return_stub_names = [
                stub["stub_name"]
                for stub in case["stub_setups"]
                if stub["setup_kind"] == "return_value"
            ]
            self.assertEqual(
                len(return_stub_names),
                len(set(return_stub_names)),
                case["test_case_id"],
            )

        observations = [observation for case in cases for observation in case["expected_observations"]]
        self.assertTrue(any(observation["observation_kind"] == "return_value" and observation["expected_expression"] == "TBD_EXPECTED_RETURN" for observation in observations))
        self.assertTrue(any(observation["observation_kind"] == "coverage_target" for observation in observations))
        self.assertTrue(
            any(
                observation["observation_kind"] == "global_value"
                and observation["target_name"] == "g_error"
                and observation["expected_expression"] == "TBD_EXPECTED_GLOBAL_G_ERROR"
                for observation in observations
            )
        )
        self.assertTrue(
            any(
                observation["observation_kind"] == "char_array_string"
                and observation["target_name"] == "buffer"
                and observation["expected_expression"] == "TBD_EXPECTED_STRING_BUFFER"
                for observation in observations
            )
        )
        unresolved_kinds = {item["item_kind"] for item in payload["unresolved_items"]}
        self.assertIn("expected_return_unknown", unresolved_kinds)

    def test_generator_uses_stable_semantic_ids_when_coverage_order_changes(self):
        signature = {
            "source": {"path": "src/control.c", "sha256": "a" * 64},
            "function": {"name": "Control_Update", "parameters": []},
        }
        coverage_items = [
            {
                "coverage_id": "COV_BRANCH_TRUE",
                "coverage_type": "branch_true",
                "target_id": "BRANCH_SENSOR",
                "purpose": "sensor is valid",
                "condition_value": "true",
                "confidence": "high",
            },
            {
                "coverage_id": "COV_RETURN_ERROR",
                "coverage_type": "return_path",
                "target_id": "RETURN_ERROR",
                "purpose": "error return",
                "condition_value": "-1",
                "confidence": "high",
            },
        ]
        boundary = {
            "input_candidates": [
                {
                    "candidate_id": "CAND_SENSOR",
                    "target_name": "sensor",
                    "target_kind": "parameter",
                    "value_expression": "1",
                    "value_kind": "boundary_at",
                    "related_coverage_ids": ["COV_BRANCH_TRUE"],
                    "purpose": "valid sensor",
                    "confidence": "high",
                    "review_required": False,
                },
                {
                    "candidate_id": "CAND_ERROR",
                    "target_name": "sensor",
                    "target_kind": "parameter",
                    "value_expression": "-1",
                    "value_kind": "boundary_below",
                    "related_coverage_ids": ["COV_RETURN_ERROR"],
                    "purpose": "error sensor",
                    "confidence": "high",
                    "review_required": False,
                },
            ],
            "state_candidates": [],
            "stub_return_candidates": [],
        }
        boundary["input_candidates"].append(copy.deepcopy(boundary["input_candidates"][0]))
        policy = TestCaseGenerationPolicy(max_cases_per_coverage_item=0)

        def generate(items):
            return generate_test_case_design(
                signature,
                {"global_accesses": []},
                {"calls": []},
                {"coverage_items": items},
                boundary,
                policy=policy,
            ).to_dict()

        first = generate(coverage_items)
        second = generate(list(reversed(copy.deepcopy(coverage_items))))
        first_case_ids = {
            item["coverage_links"][0]["coverage_id"]: item["test_case_id"]
            for item in first["test_cases"]
        }
        second_case_ids = {
            item["coverage_links"][0]["coverage_id"]: item["test_case_id"]
            for item in second["test_cases"]
        }
        first_candidate_ids = {
            item["candidate_links"][0]: item["test_case_id"]
            for item in first["additional_case_candidates"]
        }
        second_candidate_ids = {
            item["candidate_links"][0]: item["test_case_id"]
            for item in second["additional_case_candidates"]
        }

        self.assertEqual(first_case_ids, second_case_ids)
        self.assertEqual(first_candidate_ids, second_candidate_ids)
        self.assertEqual(len(first_case_ids), len(set(first_case_ids.values())))
        self.assertEqual(len(first_candidate_ids), len(set(first_candidate_ids.values())))
        self.assertEqual(2, len(first["additional_case_candidates"]))

    def test_analyze_function_generates_test_case_design_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "Control_Update"
            completed = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(VC6_FIXTURE_ROOT),
                "--dsw",
                str(VC6_FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(out_dir),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual("passed", result["outcome"])
            reports = out_dir / "reports"
            for filename in ["test_spec.json", "test_spec.md", "test_spec.csv"]:
                self.assertTrue((reports / filename).exists(), filename)
            design = json.loads((reports / "test_spec.json").read_text(encoding="utf-8"))
            self.assertEqual("1.0.0", design["schema_version"])
            self.assertTrue(design["data"]["additional_case_candidates"])
            dossier = json.loads((reports / "function_dossier.json").read_text(encoding="utf-8"))
            self.assertEqual("function_dossier", dossier["artifact_kind"])
            self.assertEqual(design["subject"], dossier["subject"])


if __name__ == "__main__":
    unittest.main()
