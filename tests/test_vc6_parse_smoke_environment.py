import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def powershell_executable():
    return shutil.which("powershell") or shutil.which("pwsh")


class Vc6ParseSmokeEnvironmentTests(unittest.TestCase):
    def test_powershell_smoke_generates_reviewable_dsw_dsp_parse_outputs(self):
        powershell = powershell_executable()
        if not powershell:
            self.skipTest("PowerShell is required for the real-machine smoke script")

        script = REPO_ROOT / "scripts" / "run_vc6_parse_smoke.ps1"
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-OutRoot",
                    temp_dir,
                    "-PythonLauncher",
                    sys.executable,
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            out_root = Path(temp_dir)
            projects_json = out_root / "dsw_dsp_projects.json"
            projects_md = out_root / "dsw_dsp_projects.md"
            membership_all_json = out_root / "source_membership_all.json"
            membership_all_md = out_root / "source_membership_all.md"
            membership_filtered_json = out_root / "source_membership_devicecontrol_debug.json"

            for path in [projects_json, projects_md, membership_all_json, membership_all_md, membership_filtered_json]:
                self.assertTrue(path.exists(), f"missing smoke output: {path}")

            projects = json.loads(projects_json.read_text(encoding="utf-8"))
            workspace = projects["workspaces"][0]
            self.assertEqual(["DeviceControl", "FactoryTest"], [project["name"] for project in workspace["projects"]])
            device = workspace["projects"][0]
            self.assertEqual("DeviceControl/DeviceControl.dsp", device["dsp_path"])
            self.assertIn("DeviceControl - Win32 Debug", device["dsp_summary"]["configurations"])
            self.assertIn("DEVICE_CONTROL_FEATURE=1", device["dsp_summary"]["defines"])
            self.assertEqual(["FactoryTest"], [dependency["from_project"] for dependency in workspace["dependencies"]])

            all_membership = json.loads(membership_all_json.read_text(encoding="utf-8"))
            self.assertEqual("multiple_matches", all_membership["status"])
            self.assertEqual(["DeviceControl", "FactoryTest"], [match["project_name"] for match in all_membership["matches"]])

            filtered_membership = json.loads(membership_filtered_json.read_text(encoding="utf-8"))
            self.assertEqual("ok", filtered_membership["status"])
            self.assertEqual(["DeviceControl"], [match["project_name"] for match in filtered_membership["matches"]])
            self.assertEqual(["Win32 Debug"], filtered_membership["matches"][0]["configurations"])

            markdown = projects_md.read_text(encoding="utf-8")
            self.assertIn("# DSWプロジェクト検出レポート", markdown)
            self.assertIn("| DeviceControl | DeviceControl/DeviceControl.dsp | はい |", markdown)


if __name__ == "__main__":
    unittest.main()
