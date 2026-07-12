import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.spec_support import write_canonical_test_spec


class EvidenceIntegrityTests(unittest.TestCase):
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

    def test_required_log_hash_mismatch_blocks_review_but_not_test_green(self):
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import (
            execute_test_run,
            prepare_evidence_from_existing_run,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            execute_test_run(
                TestRunRequest(workspace, runner, 5, True)
            )
            pointer = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            run_id = pointer["data"]["run_id"]
            combined_log = workspace / "runs" / run_id / "logs" / "test_execution.log"
            combined_log.write_text(
                combined_log.read_text(encoding="utf-8") + "tampered\n",
                encoding="utf-8",
            )

            paths, _, manifest = prepare_evidence_from_existing_run(workspace)

            logs = {item.file_kind: item for item in manifest.logs}
            self.assertEqual("hash_mismatch", logs["execution_log"].integrity_status)
            self.assertTrue(logs["execution_log"].exists)
            self.assertEqual("valid", logs["execution_stdout_log"].integrity_status)
            self.assertFalse(manifest.summary.ready_for_review)
            self.assertTrue(manifest.summary.test_green)
            serialized = json.loads(paths.evidence_manifest.read_text(encoding="utf-8"))
            self.assertFalse(serialized["data"]["summary"]["ready_for_review"])
            self.assertTrue(serialized["data"]["summary"]["test_green"])
            self.assertIn(
                "hash_mismatch",
                paths.evidence_package.read_text(encoding="utf-8"),
            )

    def test_evidence_contract_requires_integrity_and_test_green_fields(self):
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
            paths, _, _ = prepare_evidence_from_existing_run(workspace)
            payload = json.loads(paths.evidence_manifest.read_text(encoding="utf-8"))

            removals = (
                ("exists", lambda item: item["data"]["source_files"][0]),
                (
                    "integrity_status",
                    lambda item: item["data"]["source_files"][0],
                ),
                ("test_green", lambda item: item["data"]["summary"]),
            )
            for field, container in removals:
                with self.subTest(field=field):
                    mutated = copy.deepcopy(payload)
                    container(mutated).pop(field)
                    violations = validate_payload(
                        ArtifactKind.EVIDENCE_MANIFEST,
                        mutated,
                    )
                    self.assertTrue(
                        any(
                            violation.code == "required_property"
                            and field in violation.message
                            for violation in violations
                        ),
                        violations,
                    )

    def test_semantic_contract_rejects_inconsistent_evidence_and_run_outcome(self):
        from unit_test_runner.contracts import ArtifactKind, validate_payload
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import (
            execute_test_run,
            prepare_evidence_from_existing_run,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner = self._prepare_workspace(workspace)
            report = execute_test_run(TestRunRequest(workspace, runner, 5, True))
            paths, _, _ = prepare_evidence_from_existing_run(workspace)
            evidence_payload = json.loads(
                paths.evidence_manifest.read_text(encoding="utf-8")
            )
            self.assertIsNotNone(report.run_paths)
            execution_payload = json.loads(
                report.run_paths.execution_report.read_text(encoding="utf-8")
            )

            failed_green = copy.deepcopy(evidence_payload)
            failed_green["data"]["summary"]["test_execution_status"] = "failed"
            failed_green["data"]["summary"]["test_green"] = True
            violations = validate_payload(
                ArtifactKind.EVIDENCE_MANIFEST,
                failed_green,
            )
            self.assertTrue(
                any(
                    item.code == "inconsistent_summary"
                    and item.json_path == "$.data.summary.test_green"
                    for item in violations
                ),
                violations,
            )

            for integrity_status in ("missing", "hash_mismatch"):
                with self.subTest(integrity_status=integrity_status):
                    invalid_ready = copy.deepcopy(evidence_payload)
                    required_file = invalid_ready["data"]["source_files"][0]
                    required_file["integrity_status"] = integrity_status
                    required_file["exists"] = integrity_status != "missing"
                    if integrity_status == "missing":
                        required_file["sha256"] = None
                    invalid_ready["data"]["summary"]["ready_for_review"] = True
                    violations = validate_payload(
                        ArtifactKind.EVIDENCE_MANIFEST,
                        invalid_ready,
                    )
                    self.assertTrue(
                        any(
                            item.code == "inconsistent_readiness"
                            and item.json_path
                            == "$.data.summary.ready_for_review"
                            for item in violations
                        ),
                        violations,
                    )

            noncanonical = copy.deepcopy(execution_payload)
            noncanonical["data"]["function"]["status"] = "timeout"
            violations = validate_payload(
                ArtifactKind.TEST_EXECUTION_REPORT,
                noncanonical,
            )
            self.assertTrue(
                any(
                    item.code == "invalid_run_outcome"
                    and item.json_path == "$.data.function.status"
                    for item in violations
                ),
                violations,
            )

    def test_missing_required_build_reports_remain_explicit_and_block_review(self):
        from unit_test_runner.contracts import (
            ArtifactKind,
            ContractMode,
            load_artifact,
        )
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import (
            execute_test_run,
            prepare_evidence_from_existing_run,
        )

        expected_reports = {
            "build_workspace_report.json": "build_workspace_report",
            "build_probe_report.json": "build_probe_report",
        }
        for filename, file_kind in expected_reports.items():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                runner = self._prepare_workspace(workspace)
                execute_test_run(TestRunRequest(workspace, runner, 5, True))
                (workspace / "reports" / filename).unlink()

                paths, _, manifest = prepare_evidence_from_existing_run(workspace)

                reports = {item.file_kind: item for item in manifest.build_reports}
                self.assertIn(file_kind, reports)
                self.assertTrue(reports[file_kind].required)
                self.assertFalse(reports[file_kind].exists)
                self.assertIsNone(reports[file_kind].sha256)
                self.assertEqual("missing", reports[file_kind].integrity_status)
                self.assertFalse(manifest.summary.ready_for_review)
                loaded = load_artifact(
                    paths.evidence_manifest,
                    expected_kind=ArtifactKind.EVIDENCE_MANIFEST,
                    mode=ContractMode.STRICT,
                )
                self.assertEqual((), loaded.violations)

    def test_green_evidence_requires_consistent_passing_counts(self):
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
            paths, _, _ = prepare_evidence_from_existing_run(workspace)
            payload = json.loads(paths.evidence_manifest.read_text(encoding="utf-8"))

            mutations = {
                "failed": {"failed_tests": 1},
                "inconclusive": {"inconclusive_tests": 1},
                "not_all_passed": {"passed_tests": 0},
                "empty": {"total_tests": 0, "passed_tests": 0},
            }
            for name, values in mutations.items():
                with self.subTest(name=name):
                    mutated = copy.deepcopy(payload)
                    mutated["data"]["summary"].update(values)

                    violations = validate_payload(
                        ArtifactKind.EVIDENCE_MANIFEST,
                        mutated,
                    )

                    self.assertIn(
                        (
                            "inconsistent_summary",
                            "$.data.summary.test_green",
                            "blocking",
                        ),
                        {
                            (item.code, item.json_path, item.severity)
                            for item in violations
                        },
                    )

            overcounted = copy.deepcopy(payload)
            overcounted["data"]["summary"]["failed_tests"] = 1
            violations = validate_payload(
                ArtifactKind.EVIDENCE_MANIFEST,
                overcounted,
            )
            self.assertIn(
                ("inconsistent_summary", "$.data.summary.total_tests"),
                {(item.code, item.json_path) for item in violations},
            )


if __name__ == "__main__":
    unittest.main()
