import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.cli import exit_codes
from unit_test_runner.cli.commands import handle_run_tests, legacy_execution_exit


def run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", "--json", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class CliExecutionOutcomeTests(unittest.TestCase):
    def test_legacy_execution_exit_maps_every_terminal_status(self):
        cases = [
            ("passed", True, "tests_passed", exit_codes.EXIT_OK),
            ("failed", True, "tests_failed", exit_codes.EXIT_TESTS_FAILED),
            ("timed_out", True, "tests_timed_out", exit_codes.EXIT_TESTS_TIMED_OUT),
            ("timeout", True, "tests_timed_out", exit_codes.EXIT_TESTS_TIMED_OUT),
            ("blocked", False, "tests_blocked", exit_codes.EXIT_TESTS_BLOCKED),
            ("inconclusive", True, "tests_blocked", exit_codes.EXIT_TESTS_INCONCLUSIVE),
            ("cancelled", True, "tests_cancelled", exit_codes.EXIT_TESTS_CANCELLED),
            ("planned", False, "evidence_prepared", exit_codes.EXIT_OK),
            ("not_run", False, "evidence_prepared", exit_codes.EXIT_OK),
            ("error", False, "tests_error", exit_codes.EXIT_INTERNAL_ERROR),
            ("unexpected", False, "tests_error", exit_codes.EXIT_INTERNAL_ERROR),
        ]

        for status, executed, expected_status, expected_exit in cases:
            with self.subTest(status=status, executed=executed):
                self.assertEqual(
                    (expected_status, expected_exit),
                    legacy_execution_exit(status, executed),
                )

    def test_handle_run_tests_uses_report_status_for_json_and_process_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            args = Namespace(
                command="run-tests",
                workspace=temp_dir,
                executable=None,
                run=True,
                dry_run=False,
                timeout=60,
                allow_placeholder_tests=True,
                treat_placeholder_as_inconclusive=True,
            )
            for report_status, executed, expected_status, expected_exit in [
                ("passed", True, "passed", exit_codes.EXIT_OK),
                ("failed", True, "failed", exit_codes.EXIT_TESTS_FAILED),
                ("timeout", True, "timed_out", exit_codes.EXIT_TESTS_TIMED_OUT),
                ("blocked", False, "blocked", exit_codes.EXIT_TESTS_BLOCKED),
                ("inconclusive", True, "inconclusive", exit_codes.EXIT_TESTS_INCONCLUSIVE),
                ("not_run", False, "inconclusive", exit_codes.EXIT_TESTS_INCONCLUSIVE),
            ]:
                total = 1 if executed else 0
                report = SimpleNamespace(
                    status=report_status,
                    executed=executed,
                    parsed_result=SimpleNamespace(
                        total=total,
                        passed=total if report_status == "passed" else 0,
                        failed=total if report_status == "failed" else 0,
                        inconclusive=total if report_status in {"inconclusive", "not_run"} else 0,
                        crashed=0,
                        not_run=total if report_status == "not_run" else 0,
                    ),
                    run_paths=None,
                )
                manifest = SimpleNamespace(
                    summary=SimpleNamespace(test_execution_status=report_status),
                    evidence_paths=None,
                )
                with self.subTest(report_status=report_status):
                    with mock.patch(
                        "unit_test_runner.cli.commands.prepare_test_execution_evidence",
                        return_value=(report, manifest),
                    ):
                        result = handle_run_tests(args)
                    self.assertEqual(expected_status, result.status)
                    self.assertEqual(expected_exit, result.exit_code)
                    self.assertEqual(expected_status, result.data["test_execution"]["status"])

    @unittest.skipUnless(
        any(shutil.which(name) for name in ("gcc", "clang", "cc")),
        "host C compiler is required",
    )
    def test_failed_fixture_execution_returns_nonzero_cli_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "Control_Update"
            analyzed = run_cli(
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
                "build",
                "--out",
                str(output),
            )
            self.assertEqual(0, analyzed.returncode, analyzed.stderr or analyzed.stdout)
            built = run_cli(
                "build-probe",
                "--workspace",
                str(output),
                "--toolchain",
                "verification",
                "--run",
            )
            self.assertEqual(0, built.returncode, built.stderr or built.stdout)

            executed = run_cli(
                "run-tests",
                "--workspace",
                str(output),
                "--run",
                "--allow-placeholder-tests",
            )
            payload = json.loads(executed.stdout)

            self.assertNotEqual(0, executed.returncode)
            self.assertEqual(executed.returncode, payload["data"]["exit_code"])
            self.assertIn(payload["data"]["outcome"], {"failed", "blocked", "inconclusive"})
            self.assertNotEqual("passed", payload["data"]["details"]["test_execution"]["status"])


if __name__ == "__main__":
    unittest.main()
