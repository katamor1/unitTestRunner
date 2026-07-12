import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


from unit_test_runner.execution.run_paths import create_run_paths, validate_run_paths_available
from tests.spec_support import write_canonical_test_spec


class ExecutionRunHistoryTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _prepare_workspace(self, workspace: Path) -> Path:
        source = workspace / "source" / "sample.c"
        source.parent.mkdir(parents=True)
        source.write_text("int sample(void) { return 0; }\n", encoding="utf-8")
        write_canonical_test_spec(
            workspace,
            source_path="source/sample.c",
            function_name="sample",
            test_case_id="TC_sample_001",
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

    def _tree_snapshot(self, root: Path) -> dict[str, tuple[str, ...]]:
        entries: dict[str, tuple[str, ...]] = {}
        for current, directory_names, file_names in os.walk(root, followlinks=False):
            parent = Path(current)
            for name in sorted([*directory_names, *file_names]):
                path = parent / name
                relative = path.relative_to(root).as_posix()
                if path.is_symlink():
                    entries[relative] = ("symlink", os.readlink(path))
                elif path.is_dir():
                    entries[relative] = ("directory",)
                elif path.is_file():
                    entries[relative] = (
                        "file",
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                else:
                    entries[relative] = ("other",)
        return entries

    def test_create_run_paths_rejects_an_existing_run_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, run_id="run-fixed")
            marker = paths.root / "published.txt"
            marker.write_text("original\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                create_run_paths(workspace, run_id="run-fixed")

            self.assertEqual("original\n", marker.read_text(encoding="utf-8"))

    def test_create_run_paths_rejects_valid_and_broken_symlinked_runs_parent(self):
        for parent_kind in ("valid_outside", "broken_inside"):
            with self.subTest(parent_kind=parent_kind), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir).resolve()
                workspace = root / "workspace"
                workspace.mkdir()
                runs = workspace / "runs"
                if parent_kind == "valid_outside":
                    target = root / "outside-runs"
                    target.mkdir()
                else:
                    target = workspace / "missing-runs-target"
                runs.symlink_to(target, target_is_directory=True)
                before = self._tree_snapshot(root)

                with self.assertRaisesRegex(ValueError, "symlink"):
                    create_run_paths(workspace, run_id="run-fixed")

                self.assertEqual(before, self._tree_snapshot(root))

    def test_available_run_paths_use_the_resolved_workspace_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            workspace = root / "workspace"
            workspace.mkdir()
            workspace_alias = root / "workspace-alias"
            workspace_alias.symlink_to(workspace, target_is_directory=True)

            paths = validate_run_paths_available(workspace_alias, "run-fixed")

            self.assertEqual(workspace / "runs" / "run-fixed", paths.root)
            self.assertEqual(workspace / "runs" / "run-fixed" / "logs", paths.stdout_log.parent)
            self.assertFalse(paths.root.exists())

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
        from unit_test_runner.execution.test_execution import (
            execute_test_run,
            prepare_evidence_from_existing_run,
        )

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
            historical_source_hash = v1_report["subject"]["source_sha256"]
            legacy_payload["source"]["sha256"] = historical_source_hash
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
            source = workspace / "source" / "sample.c"
            source.write_text("int sample(void) { return 99; }\n", encoding="utf-8")
            self.assertNotEqual(
                historical_source_hash,
                hashlib.sha256(source.read_bytes()).hexdigest(),
            )
            legacy_paths = [
                source,
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
            self.assertEqual(
                historical_source_hash,
                migrated["subject"]["source_sha256"],
            )
            self.assertFalse(validate_payload(ArtifactKind.TEST_EXECUTION_REPORT, migrated))
            _, _, evidence_manifest = prepare_evidence_from_existing_run(
                workspace,
                imported_root.name,
            )
            self.assertEqual(
                "hash_mismatch",
                evidence_manifest.source_files[0].integrity_status,
            )
            self.assertFalse(evidence_manifest.summary.ready_for_review)
            pointer = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(imported_root.name, pointer["data"]["run_id"])

    def test_legacy_import_records_missing_logs_without_fabricating_empty_evidence(self):
        import shutil

        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.report_loader import load_execution_run
        from unit_test_runner.execution.test_execution import (
            execute_test_run,
            prepare_evidence_from_existing_run,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(
                TestRunRequest(workspace, runner, 5, True, run_id="seed-run")
            )
            seed_root = workspace / "runs" / "seed-run"
            v1_report = json.loads(
                (seed_root / "test_execution_report.json").read_text(encoding="utf-8")
            )
            legacy_payload = {"schema_version": "0.1", **v1_report["data"]}
            legacy_payload["source"]["sha256"] = v1_report["subject"][
                "source_sha256"
            ]
            self._write_json(
                workspace / "reports" / "test_execution_report.json",
                legacy_payload,
            )
            legacy_logs = workspace / "logs"
            legacy_logs.mkdir()
            shutil.copy2(
                seed_root / "logs" / "stdout.log",
                legacy_logs / "test_stdout.log",
            )
            shutil.copy2(
                seed_root / "logs" / "test_execution.log",
                legacy_logs / "test_execution.log",
            )
            shutil.rmtree(workspace / "runs")
            (workspace / "reports" / "latest_run.json").unlink()

            imported = load_execution_run(workspace)

            imported_root = workspace / "runs" / imported.run_id
            self.assertFalse((imported_root / "logs" / "stderr.log").exists())
            report_payload = json.loads(
                imported.report_path.read_text(encoding="utf-8")
            )
            evidence = {
                item["file_kind"]: item
                for item in report_payload["data"]["evidence_files"]
            }
            missing_stderr = evidence["execution_stderr_log"]
            self.assertFalse(missing_stderr["exists"])
            self.assertIsNone(missing_stderr["sha256"])
            self.assertEqual("missing", missing_stderr["integrity_status"])

            _, _, manifest = prepare_evidence_from_existing_run(
                workspace,
                imported.run_id,
            )
            manifest_logs = {item.file_kind: item for item in manifest.logs}
            self.assertEqual(
                "missing",
                manifest_logs["execution_stderr_log"].integrity_status,
            )
            self.assertFalse(manifest.summary.ready_for_review)

    def test_legacy_import_without_historical_logs_is_rejected_before_allocation(self):
        import shutil

        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.report_loader import load_execution_run
        from unit_test_runner.execution.test_execution import execute_test_run

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(
                TestRunRequest(workspace, runner, 5, True, run_id="seed-run")
            )
            seed_report = json.loads(
                (
                    workspace
                    / "runs"
                    / "seed-run"
                    / "test_execution_report.json"
                ).read_text(encoding="utf-8")
            )
            legacy_payload = {"schema_version": "0.1", **seed_report["data"]}
            legacy_payload["source"]["sha256"] = seed_report["subject"][
                "source_sha256"
            ]
            self._write_json(
                workspace / "reports" / "test_execution_report.json",
                legacy_payload,
            )
            shutil.rmtree(workspace / "runs")
            (workspace / "reports" / "latest_run.json").unlink()
            before = self._tree_snapshot(workspace)

            with self.assertRaisesRegex(ValueError, "historical execution log"):
                load_execution_run(workspace)

            self.assertEqual(before, self._tree_snapshot(workspace))

    def test_failed_evidence_publication_removes_unpublished_revision(self):
        from unittest import mock

        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import (
            execute_test_run,
            prepare_evidence_from_existing_run,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(
                TestRunRequest(workspace, runner, 5, True, run_id="stable-run")
            )
            prepare_evidence_from_existing_run(workspace, "stable-run")
            before = self._tree_snapshot(workspace)

            with mock.patch(
                "unit_test_runner.execution.test_execution.build_evidence_manifest_from_run",
                side_effect=ValueError("simulated evidence publication failure"),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "simulated evidence publication failure",
                ):
                    prepare_evidence_from_existing_run(workspace, "stable-run")

            self.assertEqual(before, self._tree_snapshot(workspace))

    def test_invalid_legacy_import_leaves_all_roots_and_pointers_unchanged(self):
        import shutil

        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.report_loader import load_execution_run
        from unit_test_runner.execution.test_execution import execute_test_run

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(
                TestRunRequest(workspace, runner, 5, True, run_id="seed-run")
            )
            seed_report = json.loads(
                (
                    workspace
                    / "runs"
                    / "seed-run"
                    / "test_execution_report.json"
                ).read_text(encoding="utf-8")
            )
            legacy_payload = {"schema_version": "0.1", **seed_report["data"]}
            self._write_json(
                workspace / "reports" / "test_execution_report.json",
                legacy_payload,
            )
            shutil.rmtree(workspace / "runs")
            (workspace / "reports" / "latest_run.json").unlink()
            sentinel = workspace / "evidence" / "existing" / "sentinel.txt"
            sentinel.parent.mkdir(parents=True)
            sentinel.write_text("preserve me\n", encoding="utf-8")
            before = self._tree_snapshot(workspace)

            with self.assertRaisesRegex(ValueError, "historical source SHA-256"):
                load_execution_run(workspace)

            self.assertEqual(before, self._tree_snapshot(workspace))

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

            self.assertEqual("passed", result.status)
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
