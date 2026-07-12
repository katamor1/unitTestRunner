import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


def run_cli(*args, check=True):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


class ReanalysisCliTests(unittest.TestCase):
    def test_reanalyze_function_generates_reports_without_overwriting_previous_design(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            product = temp / "product"
            shutil.copytree(FIXTURE_ROOT, product)
            out_dir = temp / "Control_Update"

            run_cli(
                "--json",
                "analyze-function",
                "--workspace",
                str(product),
                "--dsw",
                str(product / "Product.dsw"),
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
            design_path = out_dir / "reports" / "test_case_design.json"
            previous_design = json.loads(design_path.read_text(encoding="utf-8"))
            previous_design["test_cases"][0]["review_status"] = "approved"
            previous_design["test_cases"][0]["expected_observations"][0]["expected_expression"] = "CONTROL_OK"
            design_path.write_text(json.dumps(previous_design, indent=2) + "\n", encoding="utf-8")

            source_path = product / "src" / "control.c"
            source_text = source_path.read_text(encoding="utf-8")
            source_path.write_text(source_text.replace("sensor_value < SENSOR_MIN", "sensor_value <= SENSOR_MIN"), encoding="utf-8")

            completed = run_cli(
                "--json",
                "reanalyze-function",
                "--workspace",
                str(product),
                "--dsw",
                str(product / "Product.dsw"),
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

            payload = json.loads(completed.stdout)
            self.assertEqual("passed", payload["data"]["outcome"])
            reports = payload["data"]["details"]["reports"]
            for key in (
                "change_impact_report_json",
                "change_impact_report_md",
                "test_case_reconciliation_report_json",
                "test_case_reconciliation_report_md",
                "regression_selection_json",
                "regression_selection_csv",
            ):
                self.assertTrue(Path(reports[key]).exists(), key)
            self.assertTrue((out_dir / "reports" / "reanalysis" / "current" / "coverage_design.json").exists())
            after_design = json.loads(design_path.read_text(encoding="utf-8"))
            self.assertEqual("approved", after_design["test_cases"][0]["review_status"])
            self.assertFalse((out_dir / "reports" / "updated_test_case_design.json").exists())

    def test_analyze_function_reuse_existing_tests_rejects_run_tests(self):
        for rejected_flag in ("--run-tests", "--finalize-dossier"):
            completed = run_cli(
                "--json",
                "analyze-function",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--out",
                str(Path(tempfile.gettempdir()) / "unitTestRunner-invalid-reuse"),
                "--reuse-existing-tests",
                rejected_flag,
                check=False,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("cannot be combined", completed.stdout)

    def test_reanalyze_function_uses_explicit_previous_dossier_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            product = temp / "product"
            shutil.copytree(FIXTURE_ROOT, product)
            previous_out = temp / "previous"
            current_out = temp / "current"

            run_cli(
                "--json",
                "analyze-function",
                "--workspace",
                str(product),
                "--dsw",
                str(product / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(previous_out),
            )
            source_path = product / "src" / "control.c"
            source_text = source_path.read_text(encoding="utf-8")
            source_path.write_text(source_text.replace("sensor_value < SENSOR_MIN", "sensor_value <= SENSOR_MIN"), encoding="utf-8")
            run_cli(
                "--json",
                "analyze-function",
                "--workspace",
                str(product),
                "--dsw",
                str(product / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(current_out),
            )

            run_cli(
                "--json",
                "reanalyze-function",
                "--workspace",
                str(product),
                "--dsw",
                str(product / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(current_out),
                "--previous-dossier",
                str(previous_out / "reports" / "function_dossier.json"),
                "--previous-test-case-design",
                str(previous_out / "reports" / "test_case_design.json"),
            )

            impact = json.loads((current_out / "reports" / "change_impact_report.json").read_text(encoding="utf-8"))
            self.assertTrue(any(item["change_kind"] == "source_hash_changed" for item in impact["source_changes"]))

    def test_reanalyze_function_reads_finalized_previous_dossier_artifact_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            product = temp / "product"
            shutil.copytree(FIXTURE_ROOT, product)
            previous_out = temp / "previous"
            current_out = temp / "current"

            run_cli(
                "--json",
                "analyze-function",
                "--workspace",
                str(product),
                "--dsw",
                str(product / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(previous_out),
                "--finalize-dossier",
            )
            previous_digest = json.loads((previous_out / "reports" / "source_digest.json").read_text(encoding="utf-8"))
            source_path = product / "src" / "control.c"
            source_text = source_path.read_text(encoding="utf-8")
            source_path.write_text(source_text.replace("sensor_value < SENSOR_MIN", "sensor_value <= SENSOR_MIN"), encoding="utf-8")

            run_cli(
                "--json",
                "reanalyze-function",
                "--workspace",
                str(product),
                "--dsw",
                str(product / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(current_out),
                "--previous-dossier",
                str(previous_out / "reports" / "function_dossier.json"),
                "--previous-test-case-design",
                str(previous_out / "reports" / "test_case_design.json"),
            )

            impact = json.loads((current_out / "reports" / "change_impact_report.json").read_text(encoding="utf-8"))
            self.assertEqual(previous_digest["source"]["sha256"], impact["previous_snapshot"]["source_sha256"])
            self.assertIn("source_digest", impact["previous_snapshot"]["artifacts"])
            self.assertIn("function_signature", impact["previous_snapshot"]["artifacts"])

    def test_reconcile_test_cases_cli_writes_updated_design_when_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            previous_design = temp / "previous_design.json"
            current_design = temp / "current_design.json"
            previous_coverage = temp / "previous_coverage.json"
            current_coverage = temp / "current_coverage.json"
            boundary = temp / "boundary.json"
            out = temp / "test_case_reconciliation_report.json"
            previous_design.write_text(
                json.dumps(
                    {
                        "function": {"name": "Control_Update"},
                        "test_cases": [
                            {
                                "test_case_id": "TC_Control_Update_001",
                                "review_status": "approved",
                                "expected_observations": [{"expected_expression": "CONTROL_OK"}],
                                "coverage_links": [{"coverage_id": "BR_001"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            current_design.write_text(
                json.dumps(
                    {
                        "function": {"name": "Control_Update"},
                        "test_cases": [{"test_case_id": "TC_Control_Update_999", "coverage_links": [{"coverage_id": "BR_002"}]}],
                    }
                ),
                encoding="utf-8",
            )
            previous_coverage.write_text(json.dumps({"coverage_items": [{"coverage_id": "BR_001", "coverage_type": "branch", "target_id": "COND_001", "purpose": "a >= 0"}], "condition_expressions": [{"condition_id": "COND_001", "raw": "a >= 0"}]}), encoding="utf-8")
            current_coverage.write_text(json.dumps({"coverage_items": [{"coverage_id": "BR_002", "coverage_type": "branch", "target_id": "COND_002", "purpose": "a > 0"}], "condition_expressions": [{"condition_id": "COND_002", "raw": "a > 0"}]}), encoding="utf-8")
            boundary.write_text(json.dumps({"schema_version": "0.1"}), encoding="utf-8")

            completed = run_cli(
                "--json",
                "reconcile-test-cases",
                "--previous-test-case-design",
                str(previous_design),
                "--previous-coverage-design",
                str(previous_coverage),
                "--current-test-case-design",
                str(current_design),
                "--current-coverage-design",
                str(current_coverage),
                "--current-boundary-candidates",
                str(boundary),
                "--out",
                str(out),
                "--generate-updated-test-case-design",
            )

            payload = json.loads(completed.stdout)
            updated_path = Path(payload["data"]["details"]["reports"]["updated_test_case_design_json"])
            self.assertTrue(out.exists())
            self.assertTrue(updated_path.exists())


if __name__ == "__main__":
    unittest.main()
