import copy
import json
import os
import tempfile
import unittest
from pathlib import Path


class EvidenceIntegrityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
