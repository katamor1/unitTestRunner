import csv
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
from unit_test_runner.test_design.test_case_draft_generator import generate_test_case_draft
from unit_test_runner.test_design.test_case_draft_writer import write_test_case_draft_report


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


class TestCaseDraftStep12Tests(unittest.TestCase):
    def setUp(self):
        digest = build_source_digest(PIPELINE)
        location = locate_function(digest, "Control_Update")
        signature = extract_signature(digest, location)
        global_access = analyze_global_access(digest, location, signature)
        call_report = analyze_calls(digest, location, signature, global_access)
        coverage = analyze_coverage_design(digest, location, signature, global_access, call_report)
        boundary = generate_boundary_equivalence_candidates(signature, global_access, call_report, coverage)
        self.report = generate_test_case_draft(signature, global_access, call_report, coverage, boundary)

    def test_generator_maps_coverage_candidates_and_placeholders_to_draft_cases(self):
        payload = self.report.to_dict()

        self.assertEqual("generated", payload["function"]["status"])
        summary = payload["coverage_summary"]
        self.assertGreater(summary["total_coverage_items"], 0)
        self.assertEqual(summary["total_coverage_items"], summary["covered_by_draft_count"])
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

        observations = [observation for case in cases for observation in case["expected_observations"]]
        self.assertTrue(any(observation["observation_kind"] == "return_value" and observation["expected_expression"] == "TBD_EXPECTED_RETURN" for observation in observations))
        self.assertTrue(any(observation["observation_kind"] == "coverage_target" for observation in observations))
        unresolved_kinds = {item["item_kind"] for item in payload["unresolved_items"]}
        self.assertIn("expected_return_unknown", unresolved_kinds)

    def test_writer_outputs_json_markdown_and_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_test_case_draft_report(Path(temp_dir), self.report)

            self.assertTrue(paths["json"].exists())
            self.assertTrue(paths["markdown"].exists())
            self.assertTrue(paths["csv"].exists())
            json_payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual("generated", json_payload["function"]["status"])
            markdown = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("# Test Case Draft Report", markdown)
            with paths["csv"].open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(rows)
            self.assertIn("id", rows[0])
            self.assertIn("input_assignments", rows[0])
            self.assertIn("coverage_ids", rows[0])

    def test_analyze_function_generates_step12_artifacts(self):
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
            self.assertEqual("build_workspace_generated", result["status"])
            self.assertIn("Step 15", result["message"])
            reports = out_dir / "reports"
            for filename in ["test_case_draft.json", "test_case_draft.md", "test_case_draft.csv"]:
                self.assertTrue((reports / filename).exists(), filename)
            draft = json.loads((reports / "test_case_draft.json").read_text(encoding="utf-8"))
            self.assertTrue(draft["test_cases"])
            dossier = json.loads((reports / "function_dossier.json").read_text(encoding="utf-8"))
            self.assertIn("test_case_draft", dossier)

    def test_generate_test_draft_cli_supports_all_and_explicit_report_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "Control_Update"
            analyze = run_module(
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
            self.assertEqual(0, analyze.returncode, analyze.stderr)
            reports = out_dir / "reports"

            all_out = Path(temp_dir) / "draft-all"
            from_dossier = run_module(
                "--json",
                "generate-test-draft",
                "--dossier",
                str(reports / "function_dossier.json"),
                "--format",
                "all",
                "--out",
                str(all_out),
            )
            self.assertEqual(0, from_dossier.returncode, from_dossier.stderr)
            payload = json.loads(from_dossier.stdout)
            self.assertEqual("test_case_draft_generated", payload["status"])
            self.assertTrue(Path(payload["data"]["test_case_draft"]["json"]).exists())
            self.assertTrue(Path(payload["data"]["test_case_draft"]["markdown"]).exists())
            self.assertTrue(Path(payload["data"]["test_case_draft"]["csv"]).exists())

            explicit_json = Path(temp_dir) / "explicit_draft.json"
            explicit = run_module(
                "--json",
                "generate-test-draft",
                "--function-signature",
                str(reports / "function_signature.json"),
                "--global-access",
                str(reports / "global_access.json"),
                "--call-report",
                str(reports / "call_report.json"),
                "--coverage-design",
                str(reports / "coverage_design.json"),
                "--boundary-candidates",
                str(reports / "boundary_equivalence_candidates.json"),
                "--format",
                "json",
                "--out",
                str(explicit_json),
            )
            self.assertEqual(0, explicit.returncode, explicit.stderr)
            explicit_payload = json.loads(explicit.stdout)
            self.assertEqual(str(explicit_json), explicit_payload["data"]["test_case_draft"])
            self.assertTrue(json.loads(explicit_json.read_text(encoding="utf-8"))["test_cases"])


if __name__ == "__main__":
    unittest.main()
