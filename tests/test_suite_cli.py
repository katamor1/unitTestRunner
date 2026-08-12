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


class SuiteCliTests(unittest.TestCase):
    def test_suite_register_list_and_dry_run_by_tag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_dir = root / "Control_Update"
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            run_cli(
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
            run_cli("--json", "build-probe", "--workspace", str(out_dir))

            registered = run_cli(
                "--json",
                "suite-register",
                "--suite",
                str(suite_path),
                "--workspace",
                str(out_dir),
                "--tags",
                "regression,selected",
                "--expected-revision",
                "0",
            )
            registered_payload = json.loads(registered.stdout)
            manifest = json.loads(suite_path.read_text(encoding="utf-8"))
            entry_id = manifest["data"]["entries"][0]["entry_id"]
            self.assertEqual(
                {"command", "outcome", "message", "artifacts", "diagnostics"},
                set(registered_payload),
            )
            self.assertEqual("passed", registered_payload["outcome"])
            self.assertEqual("suite_manifest", registered_payload["artifacts"][0]["kind"])

            listed = run_cli("--json", "suite-list", "--suite", str(suite_path), "--tag", "selected")
            listed_payload = json.loads(listed.stdout)
            self.assertEqual("passed", listed_payload["outcome"])
            self.assertEqual("suite_manifest", listed_payload["artifacts"][0]["kind"])
            self.assertIn(entry_id, listed_payload["message"])
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            completed = run_cli("--json", "suite-run", "--suite", str(suite_path), "--tag", "selected", "--plan")
            payload = json.loads(completed.stdout)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("planned", payload["outcome"])
            self.assertEqual([], payload["artifacts"])
            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            self.assertFalse((suite_path.parent / "reports" / "suite_run_report.json").exists())

    def test_suite_update_and_remove_require_the_current_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out_dir = root / "Control_Update"
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            run_cli(
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
            run_cli("--json", "build-probe", "--workspace", str(out_dir))
            run_cli(
                "--json",
                "suite-register",
                "--suite",
                str(suite_path),
                "--workspace",
                str(out_dir),
                "--tags",
                "selected",
                "--expected-revision",
                "0",
            )
            manifest = json.loads(suite_path.read_text(encoding="utf-8"))
            entry_id = manifest["data"]["entries"][0]["entry_id"]

            stale = run_cli(
                "--json",
                "suite-update",
                "--suite",
                str(suite_path),
                "--entry-id",
                entry_id,
                "--enabled",
                "false",
                "--expected-revision",
                "0",
                check=False,
            )
            self.assertNotEqual(0, stale.returncode)
            self.assertEqual("error", json.loads(stale.stdout)["outcome"])

            updated = run_cli(
                "--json",
                "suite-update",
                "--suite",
                str(suite_path),
                "--entry-id",
                entry_id,
                "--enabled",
                "false",
                "--expected-revision",
                "1",
            )
            self.assertEqual("passed", json.loads(updated.stdout)["outcome"])
            manifest = json.loads(suite_path.read_text(encoding="utf-8"))
            self.assertEqual(2, manifest["data"]["revision"])
            self.assertFalse(manifest["data"]["entries"][0]["enabled"])
            self.assertEqual(["selected"], manifest["data"]["entries"][0]["tags"])

            removed = run_cli(
                "--json",
                "suite-remove",
                "--suite",
                str(suite_path),
                "--entry-id",
                entry_id,
                "--expected-revision",
                "2",
            )
            self.assertEqual("passed", json.loads(removed.stdout)["outcome"])
            manifest = json.loads(suite_path.read_text(encoding="utf-8"))
            self.assertEqual(3, manifest["data"]["revision"])
            self.assertEqual([], manifest["data"]["entries"])


if __name__ == "__main__":
    unittest.main()
