from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from unit_test_runner.cli.commands import handle_run_tests
from unit_test_runner.execution.blocker_models import (
    BlockerAction,
    BlockerPublicationDiagnostic,
    BlockerPublicationResult,
    ExecutionBlocker,
    TestExecutionBlockerReport,
)
from unit_test_runner.execution.blocker_report_writer import (
    publish_test_execution_blocker_report,
)
from unit_test_runner.execution.run_paths import create_run_paths


def run_args(workspace: Path) -> Namespace:
    return Namespace(
        command="run-tests",
        workspace=str(workspace),
        executable=None,
        run=True,
        dry_run=False,
        timeout=60,
        allow_placeholder_tests=True,
        treat_placeholder_as_inconclusive=True,
        run_id=None,
    )


def blocker_report(count: int = 2) -> TestExecutionBlockerReport:
    blockers = tuple(
        ExecutionBlocker(
            blocker_id=f"BLK-{index:03d}",
            code="unresolved_test_input",
            category="test_input",
            severity="error",
            summary=f"期待値 {index} が未確定です。",
            source_artifact="reports/test_spec.json",
            recommended_action=BlockerAction(
                "open_test_input_editor",
                "未確定項目を入力",
            ),
            next_steps=("値を入力する", "テストを再実行する"),
            case_id=f"TC_{index:03d}",
            item_id=f"item-{index:064x}",
            control_name="expected_expression",
            current_value="TBD_RETURN",
            source_pointer=f"/additional_case_candidates/{index - 1}/expected_observations/0/expected_expression",
        )
        for index in range(1, count + 1)
    )
    return TestExecutionBlockerReport(
        run_id="run-blocked",
        execution_report_path="runs/run-blocked/test_execution_report.json",
        execution_report_sha256="a" * 64,
        primary_action=BlockerAction(
            "open_test_input_editor",
            "未確定項目を入力",
            affected_count=count,
        ),
        blockers=blockers,
    )


def blocked_report(publication: BlockerPublicationResult) -> SimpleNamespace:
    return SimpleNamespace(
        status="blocked",
        executed=False,
        parsed_result=SimpleNamespace(
            total=0,
            passed=0,
            failed=0,
            inconclusive=0,
            crashed=0,
            not_run=0,
        ),
        run_paths=None,
        blocker_publication=publication,
    )


def manifest(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        summary=SimpleNamespace(test_execution_status=status),
        evidence_paths=None,
    )


class CliTestExecutionBlockerTests(unittest.TestCase):
    def test_blocked_cli_result_exposes_count_paths_and_human_action(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, "run-blocked")
            publication = publish_test_execution_blocker_report(
                workspace,
                paths,
                blocker_report(),
                subject={
                    "function_id": "fn_sample",
                    "source_path": "src/sample.c",
                    "source_sha256": "c" * 64,
                },
                producer_commit="test-commit",
            )
            report = blocked_report(publication)
            with mock.patch(
                "unit_test_runner.cli.commands.prepare_test_execution_evidence",
                return_value=(report, manifest("blocked")),
            ):
                result = handle_run_tests(run_args(workspace))

            envelope = result.to_dict()
            blockers = envelope["data"]["details"]["blockers"]
            self.assertEqual(2, blockers["count"])
            self.assertEqual("open_test_input_editor", blockers["primary_action"])
            self.assertEqual(
                "reports/test_execution_blockers.md",
                blockers["latest_markdown"],
            )
            self.assertEqual(35, envelope["data"]["exit_code"])
            self.assertEqual("blocked", envelope["data"]["outcome"])
            self.assertEqual([], envelope["data"]["errors"])
            self.assertIn("2件", result.render_human())
            self.assertIn("未確定項目を入力", result.render_human())
            artifact_paths = [item["path"] for item in envelope["data"]["artifacts"]]
            self.assertEqual(
                [
                    "runs/run-blocked/test_execution_blockers.json",
                    "runs/run-blocked/test_execution_blockers.md",
                    "reports/test_execution_blockers.json",
                    "reports/test_execution_blockers.md",
                ],
                artifact_paths,
            )

    def test_publication_diagnostic_keeps_exit_35_without_claiming_paths(self):
        publication = BlockerPublicationResult(
            report=blocker_report(1),
            diagnostics=(
                BlockerPublicationDiagnostic(
                    "blocker_report_write_failed",
                    "warning",
                    "disk unavailable",
                ),
            ),
        )
        report = blocked_report(publication)
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch(
            "unit_test_runner.cli.commands.prepare_test_execution_evidence",
            return_value=(report, manifest("blocked")),
        ):
            result = handle_run_tests(run_args(Path(temp_dir)))

        envelope = result.to_dict()
        blockers = envelope["data"]["details"]["blockers"]
        self.assertEqual(1, blockers["count"])
        self.assertNotIn("run_json", blockers)
        self.assertNotIn("latest_markdown", blockers)
        self.assertEqual(35, result.exit_code)
        self.assertEqual([], envelope["data"]["errors"])
        self.assertTrue(
            any(
                item["code"] == "blocker_report_write_failed"
                for item in envelope["data"]["diagnostics"]
            )
        )

    def test_nonblocked_cli_result_has_no_blocker_section_or_artifacts(self):
        report = SimpleNamespace(
            status="failed",
            executed=True,
            parsed_result=SimpleNamespace(
                total=1,
                passed=0,
                failed=1,
                inconclusive=0,
                crashed=0,
                not_run=0,
            ),
            run_paths=None,
            blocker_publication=None,
        )
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch(
            "unit_test_runner.cli.commands.prepare_test_execution_evidence",
            return_value=(report, manifest("failed")),
        ):
            result = handle_run_tests(run_args(Path(temp_dir)))

        self.assertNotIn("blockers", result.data)
        self.assertFalse(
            any("blocker" in artifact.kind for artifact in result.artifacts)
        )


if __name__ == "__main__":
    unittest.main()
