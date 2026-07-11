import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.test_design.test_case_design_generator import generate_test_case_design


class DependencyPolicyWorkflowTests(unittest.TestCase):
    def test_test_case_design_preserves_dependency_overrides(self):
        signature = {
            "source": {"path": "target.c", "sha256": "abc"},
            "function": {"name": "Target", "parameters": [], "return_type": {"raw": "int"}},
        }
        global_access = {"global_accesses": [], "file_scope_declarations": []}
        call_report = {"calls": [], "stub_candidates": []}
        coverage = {
            "coverage_items": [
                {
                    "coverage_id": "RET_001",
                    "coverage_type": "return_path",
                    "target_id": "RET_001",
                    "purpose": "return path",
                    "confidence": "high",
                }
            ]
        }
        boundary = {"candidates": [], "boundary_candidates": [], "equivalence_class_candidates": []}
        existing = {
            "test_cases": [
                {
                    "test_case_id": "TC_Target_001",
                    "dependency_overrides": [
                        {"callee": "Helper", "mode": "stub", "rationale": "force error", "review_required": False}
                    ],
                }
            ]
        }

        report = generate_test_case_design(
            signature,
            global_access,
            call_report,
            coverage,
            boundary,
            dependency_policy={"dependencies": [{"callee": "Helper"}]},
            existing_design=existing,
        )
        payload = report.to_dict()

        self.assertEqual("Helper", payload["test_cases"][0]["dependency_overrides"][0]["callee"])
        self.assertEqual("stub", payload["test_cases"][0]["dependency_overrides"][0]["mode"])

    def test_analyze_function_writes_dependency_policy_and_dossier_link(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "Control_Update"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC_ROOT)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unit_test_runner",
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
                    "--project",
                    "Control",
                    "--phase",
                    "design",
                    "--out",
                    str(out_dir),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            policy_path = out_dir / "reports" / "dependency_policy.json"
            markdown_path = out_dir / "reports" / "dependency_policy.md"
            dossier = json.loads((out_dir / "reports" / "function_dossier.json").read_text(encoding="utf-8"))
            design = json.loads((out_dir / "reports" / "test_case_design.json").read_text(encoding="utf-8"))

            self.assertTrue(policy_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertIn("dependency_policy", dossier)
            self.assertIn("dependency_overrides", design["test_cases"][0])


if __name__ == "__main__":
    unittest.main()
