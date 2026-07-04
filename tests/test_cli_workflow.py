import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


def run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


class CliWorkflowTests(unittest.TestCase):
    def test_cli_smoke_generates_function_dossier_without_modifying_source(self):
        source = FIXTURE_ROOT / "src" / "control.c"
        before = source.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            projects_json = temp / "projects.json"

            run_cli(
                "discover-projects",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--out",
                str(projects_json),
            )
            projects = json.loads(projects_json.read_text(encoding="utf-8"))
            self.assertEqual("Product", projects["workspace_name"])

            mapped = run_cli(
                "map-source",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
            )
            self.assertEqual(3, len(json.loads(mapped.stdout)["matches"]))

            listed = run_cli("list-functions", "--source", str(source))
            self.assertIn("Control_Update", [item["name"] for item in json.loads(listed.stdout)["functions"]])

            out_dir = temp / "Control_Update"
            run_cli(
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
                "--out",
                str(out_dir),
            )

            dossier_path = out_dir / "reports" / "function_dossier.json"
            self.assertTrue(dossier_path.exists())
            dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
            self.assertEqual("0.1", dossier["schema_version"])
            self.assertEqual("Control_Update", dossier["target"]["function"])
            self.assertIn("build_context", dossier)
            self.assertIn("function", dossier)
            self.assertIn("test_design", dossier)
            self.assertIn("diagnostics", dossier)
            self.assertTrue((out_dir / "input" / "request.json").exists())
            self.assertTrue((out_dir / "extracted" / "src" / "control.c").exists())
            self.assertTrue((out_dir / "reports" / "function_dossier.md").exists())
            self.assertTrue((out_dir / "reports" / "test_case_draft.csv").exists())

            probe = run_cli("build-probe", "--dossier", str(dossier_path), "--dry-run")
            probe_result = json.loads(probe.stdout)
            self.assertTrue(probe_result["dry_run"])
            self.assertIn(str(out_dir / "extracted" / "src" / "control.c"), probe_result["command"])
            self.assertTrue((out_dir / "generated" / "build" / "Makefile").exists())
            self.assertTrue((out_dir / "reports" / "build_probe.log").exists())

            draft = run_cli("generate-test-draft", "--dossier", str(dossier_path))
            self.assertEqual(
                str(out_dir / "reports" / "test_case_draft.csv"),
                json.loads(draft.stdout)["test_case_draft"],
            )

        self.assertEqual(before, source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
