from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tests.spec_support import write_canonical_test_spec
from unit_test_runner.execution.execution_models import TestRunRequest
from unit_test_runner.execution.test_execution import (
    execute_test_run,
    prepare_test_execution_evidence,
)
from unit_test_runner.test_spec import (
    build_current_artifact_context,
    load_test_spec,
    save_test_spec,
)
from unit_test_runner.contracts import ContractMode


class ExecutionBlockerLifecycleTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _prepare_workspace(self, workspace: Path) -> tuple[Path, Path, str]:
        source = workspace / "src" / "sample.c"
        source.parent.mkdir(parents=True)
        source.write_text("int sample(void) { return 0; }\n", encoding="utf-8")
        case_id = "TC_sample_001"
        spec_path = write_canonical_test_spec(
            workspace,
            source_path="src/sample.c",
            function_name="sample",
            test_case_id=case_id,
        )
        spec = load_test_spec(spec_path, mode=ContractMode.STRICT)
        candidate = spec.test_cases.pop()
        candidate["expected_observations"][0]["expected_expression"] = "TBD_RETURN"
        candidate["expected_observations"][0]["review_required"] = True
        spec.additional_case_candidates = [candidate]
        save_test_spec(
            spec_path,
            spec,
            expected_revision=spec.revision,
            current_context=build_current_artifact_context(workspace, spec),
        )
        self._write_json(
            workspace / "reports" / "harness_skeleton_report.json",
            {
                "function": {"name": "sample", "status": "generated"},
                "unresolved_placeholders": [],
                "generated_files": [],
            },
        )
        self._write_json(
            workspace / "reports" / "build_probe_report.json",
            {"function": {"name": "sample", "status": "succeeded"}, "diagnostics": []},
        )
        self._write_json(
            workspace / "reports" / "build_workspace_report.json",
            {
                "function": {"name": "sample", "status": "generated"},
                "source": {"path": "src/sample.c"},
                "copied_files": [],
            },
        )
        if os.name == "nt":
            runner = workspace / "runner.cmd"
            runner.write_text(
                "@echo off\n"
                f"echo UTR RUN {case_id}\n"
                f"echo UTR OK {case_id}\n",
                encoding="ascii",
            )
        else:
            runner = workspace / "runner.sh"
            runner.write_text(
                "#!/bin/sh\n"
                f"echo 'UTR RUN {case_id}'\n"
                f"echo 'UTR OK {case_id}'\n",
                encoding="ascii",
            )
            runner.chmod(0o755)
        return runner, spec_path, case_id

    def _resolve_candidate(self, workspace: Path, spec_path: Path) -> None:
        spec = load_test_spec(spec_path, mode=ContractMode.STRICT)
        candidate = spec.additional_case_candidates.pop()
        observation = candidate["expected_observations"][0]
        observation["expected_expression"] = "0"
        observation["review_required"] = False
        spec.test_cases = [candidate]
        save_test_spec(
            spec_path,
            spec,
            expected_revision=spec.revision,
            current_context=build_current_artifact_context(workspace, spec),
        )

    def test_blocked_run_publishes_history_and_later_run_clears_latest_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner, spec_path, _case_id = self._prepare_workspace(workspace)

            first = execute_test_run(
                TestRunRequest(workspace, runner, 5, True, run_id="run-blocked")
            )
            self.assertEqual("blocked", first.status)
            self.assertIsNotNone(first.blocker_publication)
            self.assertNotIn("blocker_publication", first.to_dict())
            assert first.run_paths is not None
            self.assertTrue(first.run_paths.blocker_report_json.is_file())
            self.assertTrue(first.run_paths.blocker_report_markdown.is_file())
            latest_json = workspace / "reports" / "test_execution_blockers.json"
            latest_markdown = workspace / "reports" / "test_execution_blockers.md"
            self.assertTrue(latest_json.is_file())
            self.assertTrue(latest_markdown.is_file())
            pointer = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            self.assertIn("blocker_report", pointer["data"])
            history_bytes = first.run_paths.blocker_report_json.read_bytes()

            self._resolve_candidate(workspace, spec_path)
            second = execute_test_run(
                TestRunRequest(workspace, runner, 5, True, run_id="run-passed")
            )

            self.assertEqual("passed", second.status)
            self.assertFalse(latest_json.exists())
            self.assertFalse(latest_markdown.exists())
            self.assertEqual(history_bytes, first.run_paths.blocker_report_json.read_bytes())
            pointer = json.loads(
                (workspace / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("blocker_report", pointer["data"])

    def test_blocker_analysis_failure_preserves_blocked_outcome_and_clears_latest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner, _spec_path, _case_id = self._prepare_workspace(workspace)
            reports = workspace / "reports"
            (reports / "test_execution_blockers.json").write_text(
                "stale", encoding="utf-8"
            )
            (reports / "test_execution_blockers.md").write_text(
                "stale", encoding="utf-8"
            )

            with mock.patch(
                "unit_test_runner.execution.test_execution.analyze_test_execution_blockers",
                side_effect=ValueError("analysis failed"),
            ):
                report = execute_test_run(
                    TestRunRequest(
                        workspace, runner, 5, True, run_id="run-blocked"
                    )
                )

            self.assertEqual("blocked", report.status)
            self.assertIsNotNone(report.blocker_publication)
            assert report.blocker_publication is not None
            self.assertEqual(
                "blocker_report_write_failed",
                report.blocker_publication.diagnostics[0].code,
            )
            self.assertFalse((reports / "test_execution_blockers.json").exists())
            self.assertFalse((reports / "test_execution_blockers.md").exists())
            pointer = json.loads(
                (reports / "latest_run.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("blocker_report", pointer["data"])


    def test_prepare_execution_evidence_preserves_publication_and_manifest_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            runner, _spec_path, _case_id = self._prepare_workspace(workspace)

            report, manifest = prepare_test_execution_evidence(
                workspace,
                executable=runner,
                run_tests=True,
                dry_run=False,
                timeout_seconds=5,
                allow_placeholder_tests=True,
                run_id="run-blocked",
            )

            self.assertEqual("blocked", report.status)
            self.assertIsNotNone(report.blocker_publication)
            kinds = {item.file_kind for item in manifest.test_reports}
            self.assertIn("test_execution_blocker_report", kinds)
            self.assertIn("test_execution_blocker_report_markdown", kinds)


if __name__ == "__main__":
    unittest.main()
