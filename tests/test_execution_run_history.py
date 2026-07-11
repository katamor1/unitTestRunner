import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


from unit_test_runner.execution.run_paths import create_run_paths


class ExecutionRunHistoryTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _prepare_workspace(self, workspace: Path) -> Path:
        source = workspace / "source" / "sample.c"
        source.parent.mkdir(parents=True)
        source.write_text("int sample(void) { return 0; }\n", encoding="utf-8")
        self._write_json(
            workspace / "reports" / "test_case_design.json",
            {
                "function": {"name": "sample"},
                "test_cases": [
                    {
                        "test_case_id": "TC_sample_001",
                        "coverage_links": [],
                        "review_status": "reviewed",
                        "expected_observations": [{"expected_expression": "0"}],
                    }
                ],
            },
        )
        self._write_json(
            workspace / "reports" / "harness_skeleton_report.json",
            {"unresolved_placeholders": [], "generated_files": []},
        )
        self._write_json(
            workspace / "reports" / "build_probe_report.json",
            {"function": {"name": "sample", "status": "succeeded"}},
        )
        self._write_json(
            workspace / "reports" / "build_workspace_report.json",
            {
                "function": {"name": "sample"},
                "source": {"path": "source/sample.c"},
                "copied_files": [],
            },
        )
        if os.name == "nt":
            runner = workspace / "fixture-runner.cmd"
            runner.write_text(
                "@echo off\n"
                "echo UTR RUN TC_sample_001\n"
                "echo UTR OK TC_sample_001\n",
                encoding="ascii",
            )
        else:
            runner = workspace / "fixture-runner.sh"
            runner.write_text(
                "#!/bin/sh\n"
                "echo 'UTR RUN TC_sample_001'\n"
                "echo 'UTR OK TC_sample_001'\n",
                encoding="ascii",
            )
            runner.chmod(0o755)
        return runner

    def test_create_run_paths_rejects_an_existing_run_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, run_id="run-fixed")
            marker = paths.root / "published.txt"
            marker.write_text("original\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                create_run_paths(workspace, run_id="run-fixed")

            self.assertEqual("original\n", marker.read_text(encoding="utf-8"))

    def test_two_executions_preserve_both_runs_and_only_advance_latest_pointer(self):
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import execute_test_run

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            request = TestRunRequest(
                workspace=workspace,
                executable=runner,
                timeout_seconds=5,
                allow_placeholder_tests=True,
            )

            first_report = execute_test_run(request)
            first_pointer = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            first_id = first_pointer["data"]["run_id"]
            first_path = workspace / "runs" / first_id / "test_execution_report.json"
            first_hash = hashlib.sha256(first_path.read_bytes()).hexdigest()

            second_report = execute_test_run(request)
            latest_pointer = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            second_id = latest_pointer["data"]["run_id"]

            self.assertEqual("passed", first_report.status)
            self.assertEqual("passed", second_report.status)
            self.assertNotEqual(first_id, second_id)
            self.assertEqual(
                {first_id, second_id},
                {path.name for path in (workspace / "runs").iterdir()},
            )
            self.assertEqual(
                first_hash,
                hashlib.sha256(first_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(second_id, latest_pointer["data"]["run_id"])
            self.assertEqual(
                f"runs/{second_id}/test_execution_report.json",
                latest_pointer["data"]["execution_report"]["path"],
            )

    def test_legacy_v01_report_import_preserves_sources_and_migrates_only_copy(self):
        import shutil

        from unit_test_runner.contracts import ArtifactKind, validate_payload
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.report_loader import load_test_execution_report
        from unit_test_runner.execution.test_execution import execute_test_run

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            seed_report = execute_test_run(
                TestRunRequest(
                    workspace=workspace,
                    executable=runner,
                    timeout_seconds=5,
                    allow_placeholder_tests=True,
                    run_id="seed-run",
                )
            )
            self.assertEqual("passed", seed_report.status)
            seed_root = workspace / "runs" / "seed-run"
            v1_report = json.loads(
                (seed_root / "test_execution_report.json").read_text(encoding="utf-8")
            )
            legacy_payload = {"schema_version": "0.1", **v1_report["data"]}
            self._write_json(
                workspace / "reports" / "test_execution_report.json",
                legacy_payload,
            )
            v1_result = json.loads(
                (seed_root / "test_result.json").read_text(encoding="utf-8")
            )
            self._write_json(
                workspace / "reports" / "test_result.json",
                {"schema_version": "0.1", **v1_result["data"]},
            )
            shutil.copy2(
                seed_root / "test_result.csv",
                workspace / "reports" / "test_result.csv",
            )
            (workspace / "logs").mkdir()
            shutil.copy2(seed_root / "logs" / "stdout.log", workspace / "logs" / "test_stdout.log")
            shutil.copy2(seed_root / "logs" / "stderr.log", workspace / "logs" / "test_stderr.log")
            shutil.copy2(seed_root / "logs" / "test_execution.log", workspace / "logs" / "test_execution.log")
            shutil.rmtree(workspace / "runs")
            (workspace / "reports" / "latest_run.json").unlink()
            legacy_paths = [
                workspace / "reports" / "test_execution_report.json",
                workspace / "reports" / "test_result.json",
                workspace / "reports" / "test_result.csv",
                workspace / "logs" / "test_stdout.log",
                workspace / "logs" / "test_stderr.log",
                workspace / "logs" / "test_execution.log",
            ]
            original_bytes = {path: path.read_bytes() for path in legacy_paths}

            imported = load_test_execution_report(workspace)

            self.assertEqual("passed", imported.status)
            self.assertEqual(
                original_bytes,
                {path: path.read_bytes() for path in legacy_paths},
            )
            imported_roots = list((workspace / "runs").iterdir())
            self.assertEqual(1, len(imported_roots))
            imported_root = imported_roots[0]
            self.assertTrue(imported_root.name.startswith("imported-"))
            for relative in (
                "test_execution_report.json",
                "test_result.json",
                "test_result.csv",
                "logs/stdout.log",
                "logs/stderr.log",
                "logs/test_execution.log",
            ):
                self.assertTrue((imported_root / relative).is_file(), relative)
            migrated = json.loads(
                (imported_root / "test_execution_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("1.0.0", migrated["schema_version"])
            self.assertEqual(
                "0.1",
                migrated["extensions"]["migration"]["source_version"],
            )
            self.assertFalse(validate_payload(ArtifactKind.TEST_EXECUTION_REPORT, migrated))
            pointer = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(imported_root.name, pointer["data"]["run_id"])

    def test_actual_run_tests_command_publishes_an_immutable_run(self):
        from argparse import Namespace

        from unit_test_runner.cli.commands import handle_run_tests

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            result = handle_run_tests(
                Namespace(
                    command="run-tests",
                    workspace=str(workspace),
                    executable=str(runner),
                    run=True,
                    dry_run=False,
                    timeout=5,
                    run_id=None,
                    allow_placeholder_tests=True,
                    treat_placeholder_as_inconclusive=True,
                )
            )

            self.assertEqual("tests_passed", result.status)
            latest_run = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            run_id = latest_run["data"]["run_id"]
            self.assertTrue(
                (workspace / "runs" / run_id / "test_execution_report.json").is_file()
            )
            self.assertTrue((workspace / "reports" / "latest_evidence.json").is_file())

    def test_latest_run_pointer_contract_rejects_flat_legacy_report_path(self):
        from unit_test_runner.contracts import ArtifactKind, validate_payload
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import execute_test_run

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(TestRunRequest(workspace, runner, 5, True))
            pointer = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            pointer["data"]["execution_report"]["path"] = (
                "reports/test_execution_report.json"
            )

            violations = validate_payload(ArtifactKind.LATEST_RUN_POINTER, pointer)

            self.assertTrue(violations)

    def test_timeout_is_published_as_canonical_timed_out_outcome(self):
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import execute_test_run

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            self._prepare_workspace(workspace)
            if os.name == "nt":
                runner = workspace / "timeout-runner.cmd"
                runner.write_text(
                    f'@echo off\n"{sys.executable}" -c "import time; time.sleep(10)"\n',
                    encoding="utf-8",
                )
            else:
                runner = workspace / "timeout-runner.sh"
                runner.write_text(
                    f'#!/bin/sh\n"{sys.executable}" -c "import time; time.sleep(10)"\n',
                    encoding="utf-8",
                )
                runner.chmod(0o755)

            report = execute_test_run(TestRunRequest(workspace, runner, 1, True))

            self.assertEqual("timed_out", report.status)
            pointer = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            payload = json.loads(
                (workspace / pointer["data"]["execution_report"]["path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("timed_out", payload["data"]["function"]["status"])


if __name__ == "__main__":
    unittest.main()
