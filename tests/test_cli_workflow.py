import json
import hashlib
import os
import shutil
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
    def test_reanalysis_of_same_workspace_rebinds_dossier_subject_to_current_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "fixture"
            shutil.copytree(FIXTURE_ROOT, workspace)
            output = root / "Control_Update"
            command = (
                "--json",
                "analyze-function",
                "--workspace",
                str(workspace),
                "--dsw",
                str(workspace / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--phase",
                "analysis",
                "--out",
                str(output),
            )

            run_cli(*command)
            dossier_path = output / "reports" / "function_dossier.json"
            first = json.loads(dossier_path.read_text(encoding="utf-8"))

            source = workspace / "src" / "control.c"
            source.write_bytes(source.read_bytes() + b"\n/* current source revision */\n")
            run_cli(*command)
            second = json.loads(dossier_path.read_text(encoding="utf-8"))

            expected_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertNotEqual(
                first["subject"]["source_sha256"],
                second["subject"]["source_sha256"],
            )
            self.assertEqual(expected_sha256, second["subject"]["source_sha256"])

    def test_cli_accepts_vc6_full_configuration_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_path = Path(temp_dir) / "mapping.json"
            mapped = run_cli(
                "--json",
                "map-source",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--project",
                "Control",
                "--configuration",
                "Control - Win32 Debug",
                "--out",
                str(mapping_path),
            )
            envelope = json.loads(mapped.stdout)
            self.assertEqual("passed", envelope["outcome"])
            matches = json.loads(mapping_path.read_text(encoding="utf-8"))["matches"]
            self.assertEqual(1, len(matches))
            self.assertEqual(["Win32 Debug"], matches[0]["configurations"])
            self.assertEqual(
                "Control - Win32 Debug",
                matches[0]["configuration_details"][0]["full_name"],
            )

            out_dir = Path(temp_dir) / "Control_Update"
            analyzed = run_cli(
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
                "Control - Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(out_dir),
                "--phase",
                "harness",
            )
            self.assertEqual("passed", json.loads(analyzed.stdout)["outcome"])
            dossier = json.loads((out_dir / "reports" / "function_dossier.json").read_text(encoding="utf-8"))
            self.assertEqual("1.0.0", dossier["schema_version"])
            self.assertEqual("Control - Win32 Debug", dossier["subject"]["configuration"])
            self.assertEqual("Control - Win32 Debug", dossier["data"]["target"]["configuration"])

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
            self.assertEqual(1, len(projects["workspaces"]))
            self.assertTrue(projects["workspaces"][0]["dsw_path"].endswith("Product.dsw"))

            mapping_path = temp / "mapping.json"
            mapped = run_cli(
                "--json",
                "map-source",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--project",
                "Control",
                "--out",
                str(mapping_path),
            )
            self.assertEqual("passed", json.loads(mapped.stdout)["outcome"])
            matches = json.loads(mapping_path.read_text(encoding="utf-8"))["matches"]
            self.assertEqual(1, len(matches))
            self.assertEqual(2, sum(len(item["configurations"]) for item in matches))

            listed = run_cli("list-functions", "--source", str(source))
            self.assertIn("Control_Update", listed.stdout)

            out_dir = temp / "Control_Update"
            analyzed = run_cli(
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
                "--out",
                str(out_dir),
                "--phase",
                "harness",
            )
            analysis_envelope = json.loads(analyzed.stdout)
            self.assertEqual("passed", analysis_envelope["outcome"])
            self.assertEqual(
                {"function_dossier", "test_spec"},
                {item["kind"] for item in analysis_envelope["artifacts"]},
            )

            dossier_path = out_dir / "reports" / "function_dossier.json"
            self.assertTrue(dossier_path.exists())
            dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
            self.assertEqual("1.0.0", dossier["schema_version"])
            self.assertEqual("function_dossier", dossier["artifact_kind"])
            self.assertEqual("Control_Update", dossier["subject"]["function"])
            self.assertEqual("Control_Update", dossier["data"]["target"]["function"])
            self.assertIn("build_context", dossier["data"])
            self.assertIn("function", dossier["data"])
            self.assertIn("test_design", dossier["data"])
            self.assertIn("diagnostics", dossier["data"])
            self.assertTrue((out_dir / "input" / "request.json").exists())
            self.assertTrue((out_dir / "extracted" / "src" / "control.c").exists())
            self.assertTrue((out_dir / "reports" / "function_dossier.md").exists())
            self.assertTrue((out_dir / "reports" / "test_spec.csv").exists())

            probe = run_cli(
                "--json",
                "build-probe",
                "--workspace",
                str(out_dir),
                "--dry-run",
            )
            probe_envelope = json.loads(probe.stdout)
            self.assertEqual("passed", probe_envelope["outcome"])
            self.assertEqual(
                ["build_probe_report"],
                [item["kind"] for item in probe_envelope["artifacts"]],
            )
            probe_result = json.loads(
                (out_dir / "reports" / "build_probe_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(probe_result["data"]["executed"])
            self.assertTrue((out_dir / "build" / "Makefile").exists())
            self.assertTrue((out_dir / "logs" / "build.log").exists())
            self.assertTrue((out_dir / "reports" / "test_spec.json").is_file())

        self.assertEqual(before, source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
