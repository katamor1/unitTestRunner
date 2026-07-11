import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path


class PrepareEvidenceNonDestructiveTests(unittest.TestCase):
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

    def _tree_hashes(self, root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_evidence_revision_ids_are_exclusive(self):
        from unit_test_runner.execution.evidence_paths import create_evidence_paths

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_evidence_paths(
                workspace,
                source_run_id="run-fixed",
                evidence_id="evidence-fixed",
            )
            marker = paths.root / "published.txt"
            marker.write_text("original\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                create_evidence_paths(
                    workspace,
                    source_run_id="run-fixed",
                    evidence_id="evidence-fixed",
                )

            self.assertEqual("original\n", marker.read_text(encoding="utf-8"))

    def test_prepare_evidence_requires_an_existing_terminal_run(self):
        from unit_test_runner.execution.test_execution import (
            prepare_evidence_from_existing_run,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            workspace.mkdir(exist_ok=True)

            with self.assertRaises(FileNotFoundError):
                prepare_evidence_from_existing_run(workspace)

            self.assertFalse((workspace / "runs").exists())
            self.assertFalse((workspace / "evidence").exists())
            self.assertFalse((workspace / "reports").exists())

    def test_prepare_evidence_cli_is_load_only_and_maps_no_run_to_input_error(self):
        from argparse import Namespace
        from unittest import mock

        from unit_test_runner.cli.commands import handle_prepare_evidence
        from unit_test_runner.cli.errors import CLIError
        from unit_test_runner.cli.exit_codes import EXIT_INPUT_ERROR

        with tempfile.TemporaryDirectory() as temp_dir:
            args = Namespace(
                command="prepare-evidence",
                workspace=temp_dir,
                run_id=None,
                out=None,
            )
            with mock.patch(
                "unit_test_runner.cli.commands.prepare_test_execution_evidence",
                side_effect=AssertionError("legacy combined path called"),
            ):
                with self.assertRaises(CLIError) as raised:
                    handle_prepare_evidence(args)

            self.assertEqual(EXIT_INPUT_ERROR, raised.exception.exit_code)
            self.assertIn("terminal", raised.exception.message)
            self.assertFalse((Path(temp_dir) / "reports").exists())
            self.assertFalse((Path(temp_dir) / "evidence").exists())

    def test_nonterminal_legacy_report_is_rejected_without_import_writes(self):
        from unit_test_runner.execution.test_execution import (
            prepare_evidence_from_existing_run,
            prepare_test_execution_evidence,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            self._prepare_workspace(workspace)
            prepare_test_execution_evidence(
                workspace,
                run_tests=False,
                dry_run=True,
            )
            legacy_path = workspace / "reports" / "test_execution_report.json"
            original = legacy_path.read_bytes()

            with self.assertRaisesRegex(ValueError, "not terminal"):
                prepare_evidence_from_existing_run(workspace)

            self.assertEqual(original, legacy_path.read_bytes())
            self.assertFalse((workspace / "runs").exists())
            self.assertFalse((workspace / "evidence").exists())
            self.assertFalse((workspace / "reports" / "latest_run.json").exists())
            self.assertFalse((workspace / "reports" / "latest_evidence.json").exists())

    def test_two_evidence_preparations_preserve_run_and_first_revision_hashes(self):
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import (
            execute_test_run,
            prepare_evidence_from_existing_run,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(
                TestRunRequest(
                    workspace=workspace,
                    executable=runner,
                    timeout_seconds=5,
                    allow_placeholder_tests=True,
                )
            )
            latest_run = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            run_id = latest_run["data"]["run_id"]
            run_root = workspace / "runs" / run_id
            original_run_hashes = self._tree_hashes(run_root)

            first_paths, first_report, first_manifest = prepare_evidence_from_existing_run(
                workspace
            )
            first_revision_hashes = self._tree_hashes(first_paths.root)
            second_paths, second_report, second_manifest = prepare_evidence_from_existing_run(
                workspace,
                run_id=run_id,
            )

            self.assertEqual("passed", first_report.status)
            self.assertEqual("passed", second_report.status)
            self.assertTrue(first_manifest.summary.test_green)
            self.assertTrue(first_manifest.summary.ready_for_review)
            self.assertTrue(second_manifest.summary.ready_for_review)
            self.assertNotEqual(first_paths.evidence_id, second_paths.evidence_id)
            self.assertEqual(original_run_hashes, self._tree_hashes(run_root))
            self.assertEqual(first_revision_hashes, self._tree_hashes(first_paths.root))
            self.assertEqual(
                {first_paths.evidence_id, second_paths.evidence_id},
                {path.name for path in (workspace / "evidence").iterdir()},
            )
            latest_evidence = json.loads(
                (workspace / "reports" / "latest_evidence.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(second_paths.evidence_id, latest_evidence["data"]["evidence_id"])
            self.assertEqual(run_id, latest_evidence["data"]["source_run_id"])
            self.assertFalse((workspace / "reports" / "evidence_manifest.json").exists())
            source_run = json.loads(first_paths.source_run.read_text(encoding="utf-8"))
            self.assertEqual("evidence_source_run", source_run["artifact_kind"])
            self.assertEqual(run_id, source_run["data"]["source_run_id"])
            self.assertEqual(
                original_run_hashes["test_execution_report.json"],
                source_run["data"]["execution_report"]["sha256"],
            )
            self.assertEqual(
                {
                    "runs/%s/logs/stdout.log" % run_id,
                    "runs/%s/logs/stderr.log" % run_id,
                    "runs/%s/logs/test_execution.log" % run_id,
                },
                {item["path"] for item in source_run["data"]["logs"]},
            )

    def test_latest_evidence_pointer_contract_rejects_flat_legacy_manifest_path(self):
        from unit_test_runner.contracts import ArtifactKind, validate_payload
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import (
            execute_test_run,
            prepare_evidence_from_existing_run,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(TestRunRequest(workspace, runner, 5, True))
            prepare_evidence_from_existing_run(workspace)
            pointer = json.loads(
                (workspace / "reports" / "latest_evidence.json").read_text(
                    encoding="utf-8"
                )
            )
            pointer["data"]["evidence_manifest"]["path"] = (
                "reports/evidence_manifest.json"
            )

            violations = validate_payload(ArtifactKind.LATEST_EVIDENCE_POINTER, pointer)

            self.assertTrue(violations)

    def test_prepare_evidence_cli_reports_the_explicit_older_source_run(self):
        from argparse import Namespace

        from unit_test_runner.cli.commands import handle_prepare_evidence
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import execute_test_run

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(
                TestRunRequest(workspace, runner, 5, True, run_id="run-older")
            )
            execute_test_run(
                TestRunRequest(workspace, runner, 5, True, run_id="run-newer")
            )

            result = handle_prepare_evidence(
                Namespace(
                    command="prepare-evidence",
                    workspace=str(workspace),
                    run_id="run-older",
                    out=None,
                )
            )

            execution = result.data["test_execution"]
            self.assertEqual("run-older", execution["run_id"])
            self.assertEqual(
                workspace / "runs" / "run-older" / "test_execution_report.json",
                Path(execution["json"]),
            )
            latest_evidence = json.loads(
                (workspace / "reports" / "latest_evidence.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                "run-older",
                latest_evidence["data"]["source_run_id"],
            )

    def test_legacy_dry_run_payload_does_not_reuse_latest_real_run_alias(self):
        from argparse import Namespace

        from unit_test_runner.cli.commands import handle_run_tests
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import execute_test_run

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(
                TestRunRequest(workspace, runner, 5, True, run_id="run-real")
            )

            result = handle_run_tests(
                Namespace(
                    command="run-tests",
                    workspace=str(workspace),
                    executable=None,
                    run=False,
                    dry_run=True,
                    timeout=5,
                    run_id=None,
                    allow_placeholder_tests=True,
                    treat_placeholder_as_inconclusive=True,
                )
            )

            execution = result.data["test_execution"]
            self.assertNotIn("run_id", execution)
            self.assertEqual(
                workspace / "reports" / "test_execution_report.json",
                Path(execution["json"]),
            )


if __name__ == "__main__":
    unittest.main()
