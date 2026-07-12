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
            )

            registered = run_cli("--json", "suite-register", "--suite", str(suite_path), "--workspace", str(out_dir), "--tags", "regression,selected")
            registered_payload = json.loads(registered.stdout)
            entry_id = registered_payload["data"]["details"]["entry"]["entry_id"]

            listed = run_cli("--json", "suite-list", "--suite", str(suite_path), "--tag", "selected")
            listed_payload = json.loads(listed.stdout)
            self.assertEqual(
                [entry_id],
                [entry["entry_id"] for entry in listed_payload["data"]["details"]["entries"]],
            )
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            completed = run_cli("--json", "suite-run", "--suite", str(suite_path), "--tag", "selected", "--dry-run")
            payload = json.loads(completed.stdout)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("planned", payload["data"]["outcome"])
            self.assertEqual("plan", payload["data"]["details"]["mode"])
            self.assertEqual([], payload["data"]["artifacts"])
            self.assertEqual(3, len(payload["data"]["expected_artifacts"]))
            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            self.assertFalse((suite_path.parent / "reports" / "suite_run_report.json").exists())

    def test_suite_run_require_green_returns_test_failure_exit_for_dry_run(self):
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
            )
            run_cli("--json", "suite-register", "--suite", str(suite_path), "--workspace", str(out_dir), "--tags", "selected")

            completed = run_cli("--json", "suite-run", "--suite", str(suite_path), "--tag", "selected", "--dry-run", "--require-green", check=False)

            payload = json.loads(completed.stdout)
            self.assertEqual(0, completed.returncode)
            self.assertEqual("planned", payload["data"]["outcome"])
            self.assertEqual([], payload["data"]["artifacts"])
            self.assertEqual(3, len(payload["data"]["expected_artifacts"]))


if __name__ == "__main__":
    unittest.main()
