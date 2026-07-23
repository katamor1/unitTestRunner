from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from unit_test_runner.contracts import ArtifactKind, validate_payload
from unit_test_runner.execution.blocker_models import (
    BlockerAction,
    ExecutionBlocker,
    TestExecutionBlockerReport,
)
from unit_test_runner.execution.blocker_report_writer import (
    clear_latest_test_execution_blockers,
    publish_test_execution_blocker_report,
    render_test_execution_blockers_markdown,
)
from unit_test_runner.execution.run_paths import create_run_paths


def sample_subject() -> dict[str, str]:
    return {
        "function_id": "fn_sample",
        "source_path": "src/sample.c",
        "source_sha256": "c" * 64,
    }


def sample_blocker_report(**changes: object) -> TestExecutionBlockerReport:
    blocker = ExecutionBlocker(
        blocker_id="BLK-001",
        code="unresolved_test_input",
        category="test_input",
        severity="error",
        summary="期待値が未確定です。",
        source_artifact="reports/test_spec.json",
        recommended_action=BlockerAction("open_test_input_editor", "未確定項目を入力"),
        next_steps=("値を入力する", "テストを再実行する"),
        case_id="TC_001",
        item_id="item-" + "d" * 64,
        control_name="expected_expression",
        current_value="TBD_RETURN",
        source_pointer="/additional_case_candidates/0/expected_observations/0/expected_expression",
    )
    values = {
        "run_id": "run-001",
        "execution_report_path": "runs/run-001/test_execution_report.json",
        "execution_report_sha256": "a" * 64,
        "primary_action": BlockerAction(
            "open_test_input_editor", "未確定項目を入力", affected_count=1
        ),
        "blockers": (blocker,),
    }
    values.update(changes)
    return TestExecutionBlockerReport(**values)


class ExecutionBlockerReportWriterTests(unittest.TestCase):
    def test_blocked_report_publishes_history_and_latest_views(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, "run-001")
            paths.execution_report.write_text("{}", encoding="utf-8")
            result = publish_test_execution_blocker_report(
                workspace,
                paths,
                sample_blocker_report(),
                subject=sample_subject(),
                producer_commit="test-commit",
            )

            self.assertEqual(paths.blocker_report_json, result.run_json)
            self.assertEqual(paths.blocker_report_markdown, result.run_markdown)
            self.assertTrue(
                (workspace / "reports" / "test_execution_blockers.json").is_file()
            )
            self.assertTrue(
                (workspace / "reports" / "test_execution_blockers.md").is_file()
            )
            payload = json.loads(
                paths.blocker_report_json.read_text(encoding="utf-8")
            )
            self.assertEqual(
                "test_execution_blocker_report", payload["artifact_kind"]
            )
            self.assertEqual(
                (),
                validate_payload(ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT, payload),
            )
            self.assertEqual((), result.diagnostics)

    def test_nonblocked_cleanup_removes_only_latest_views(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            history = workspace / "runs" / "run-old"
            history.mkdir(parents=True)
            (history / "test_execution_blockers.json").write_text(
                "history", encoding="utf-8"
            )
            reports = workspace / "reports"
            reports.mkdir()
            (reports / "test_execution_blockers.json").write_text(
                "latest", encoding="utf-8"
            )
            (reports / "test_execution_blockers.md").write_text(
                "latest", encoding="utf-8"
            )

            result = clear_latest_test_execution_blockers(workspace)

            self.assertFalse((reports / "test_execution_blockers.json").exists())
            self.assertFalse((reports / "test_execution_blockers.md").exists())
            self.assertTrue((history / "test_execution_blockers.json").exists())
            self.assertEqual((), result.diagnostics)

    def test_markdown_escapes_dynamic_text_and_displays_log_excerpt_safely(self):
        unsafe = ExecutionBlocker(
            blocker_id="BLK-001",
            code="runner_reported_blocked",
            category="runner",
            severity="error",
            summary="<script>alert(1)</script> | blocked",
            source_artifact="runs/run-001/logs/test_execution.log",
            recommended_action=BlockerAction(
                "open_execution_log", "ログを開く | now"
            ),
            next_steps=("review <state>",),
            current_value="value`with`ticks",
            log_excerpt="<secret>\n~~~\nline",
        )
        report = sample_blocker_report(
            primary_action=BlockerAction("open_execution_log", "ログを開く | now", 1),
            blockers=(unsafe,),
        )

        markdown = render_test_execution_blockers_markdown(report)

        self.assertNotIn("<script>", markdown)
        self.assertIn("&lt;script&gt;", markdown)
        self.assertIn("value&#96;with&#96;ticks", markdown)
        self.assertIn("    &lt;secret&gt;", markdown)

    def test_existing_history_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, "run-001")
            paths.blocker_report_json.write_text("original", encoding="utf-8")

            result = publish_test_execution_blocker_report(
                workspace,
                paths,
                sample_blocker_report(),
                subject=sample_subject(),
                producer_commit="test-commit",
            )

            self.assertEqual("original", paths.blocker_report_json.read_text())
            self.assertEqual("blocker_report_write_failed", result.diagnostics[0].code)
            self.assertIsNone(result.run_json)

    def test_history_markdown_failure_preserves_canonical_json_and_clears_latest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, "run-001")
            reports = workspace / "reports"
            reports.mkdir()
            (reports / "test_execution_blockers.json").write_text(
                "stale", encoding="utf-8"
            )
            (reports / "test_execution_blockers.md").write_text(
                "stale", encoding="utf-8"
            )

            with mock.patch(
                "unit_test_runner.execution.blocker_report_writer._atomic_write_text",
                side_effect=OSError("markdown failed"),
            ):
                result = publish_test_execution_blocker_report(
                    workspace,
                    paths,
                    sample_blocker_report(),
                    subject=sample_subject(),
                    producer_commit="test-commit",
                )

            self.assertEqual(paths.blocker_report_json, result.run_json)
            self.assertIsNone(result.run_markdown)
            self.assertTrue(paths.blocker_report_json.is_file())
            self.assertFalse((reports / "test_execution_blockers.json").exists())
            self.assertFalse((reports / "test_execution_blockers.md").exists())
            self.assertEqual("blocker_report_write_failed", result.diagnostics[0].code)

    def test_latest_sync_failure_keeps_history_and_removes_partial_latest_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, "run-001")
            real_copy = __import__(
                "unit_test_runner.execution.blocker_report_writer",
                fromlist=["_atomic_copy"],
            )._atomic_copy
            calls = 0

            def fail_second_copy(source: Path, destination: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("latest markdown failed")
                real_copy(source, destination)

            with mock.patch(
                "unit_test_runner.execution.blocker_report_writer._atomic_copy",
                side_effect=fail_second_copy,
            ):
                result = publish_test_execution_blocker_report(
                    workspace,
                    paths,
                    sample_blocker_report(),
                    subject=sample_subject(),
                    producer_commit="test-commit",
                )

            self.assertEqual(paths.blocker_report_json, result.run_json)
            self.assertEqual(paths.blocker_report_markdown, result.run_markdown)
            self.assertIsNone(result.latest_json)
            self.assertIsNone(result.latest_markdown)
            self.assertEqual("blocker_latest_sync_failed", result.diagnostics[0].code)
            self.assertFalse(
                (workspace / "reports" / "test_execution_blockers.json").exists()
            )
            self.assertFalse(
                (workspace / "reports" / "test_execution_blockers.md").exists()
            )

    def test_cleanup_removes_regular_half_of_partial_pair_even_if_other_is_invalid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            reports.mkdir()
            latest_json = reports / "test_execution_blockers.json"
            latest_json.write_text("stale", encoding="utf-8")
            (reports / "test_execution_blockers.md").mkdir()

            result = clear_latest_test_execution_blockers(workspace)

            self.assertFalse(latest_json.exists())
            self.assertTrue(result.diagnostics)
            self.assertEqual("blocker_latest_cleanup_failed", result.diagnostics[0].code)

    def test_symlinked_reports_directory_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "outside"
            outside.mkdir()
            try:
                (workspace / "reports").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable")

            result = clear_latest_test_execution_blockers(workspace)

            self.assertTrue(result.diagnostics)
            self.assertEqual("blocker_latest_cleanup_failed", result.diagnostics[0].code)
            self.assertEqual([], list(outside.iterdir()))

    def test_history_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            safe = create_run_paths(workspace, "run-001")
            escaped = type(safe)(
                run_id=safe.run_id,
                root=safe.root,
                execution_report=safe.execution_report,
                blocker_report_json=root / "outside.json",
                blocker_report_markdown=safe.blocker_report_markdown,
                result_json=safe.result_json,
                result_csv=safe.result_csv,
                stdout_log=safe.stdout_log,
                stderr_log=safe.stderr_log,
                combined_log=safe.combined_log,
            )

            result = publish_test_execution_blocker_report(
                workspace,
                escaped,
                sample_blocker_report(),
                subject=sample_subject(),
                producer_commit="test-commit",
            )

            self.assertFalse((root / "outside.json").exists())
            self.assertEqual("blocker_report_write_failed", result.diagnostics[0].code)


if __name__ == "__main__":
    unittest.main()
