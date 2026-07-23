from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from unit_test_runner.execution.blocker_analyzer import (
    BlockerAnalysisInput,
    analyze_test_execution_blockers,
)
from unit_test_runner.execution.execution_models import (
    ExecutableInfo,
    TestCaseExecutionResult,
    TestExecutionPolicy,
    TestExecutionReport,
    TestExecutionWarning,
    TestResultSummary,
)
from unit_test_runner.execution.run_paths import create_run_paths


def blocked_report(executable: ExecutableInfo | None = None) -> TestExecutionReport:
    return TestExecutionReport(
        source_path=Path("src/sample.c"),
        function_name="sample",
        status="blocked",
        executed=False,
        executable=executable,
        command=None,
        command_result=None,
        parsed_result=TestResultSummary(),
        case_results=[],
        unresolved_review_items=[],
        evidence_files=[],
        warnings=[],
        policy=TestExecutionPolicy(run_tests=True, dry_run=False),
        schema_version="1.0.0",
    )


def candidate_spec(
    *,
    input_value: object,
    expected_value: object,
    confirmed: bool,
    case_id: str = "TC_001",
) -> dict[str, Any]:
    review_required = not confirmed
    return {
        "function": {"name": "sample"},
        "test_cases": [],
        "additional_case_candidates": [
            {
                "test_case_id": case_id,
                "input_assignments": [
                    {
                        "target_kind": "parameter",
                        "target_name": "mode",
                        "source_candidate_id": "CAND_INPUT_001",
                        "value_expression": input_value,
                        "review_required": review_required,
                    }
                ],
                "state_setups": [],
                "stub_setups": [],
                "expected_observations": [
                    {
                        "observation_kind": "return_value",
                        "target_name": "return",
                        "source": "generated",
                        "expected_expression": expected_value,
                        "review_required": review_required,
                    }
                ],
                "preconditions": [],
                "execution_steps": [],
                "dependency_overrides": [],
            }
        ],
        "unresolved_items": [],
        "review_item_ids": [],
    }


def make_input(
    *,
    workspace: Path = Path("/workspace"),
    report: TestExecutionReport | None = None,
    test_spec: dict[str, Any] | None = None,
    harness_report: dict[str, Any] | None = None,
    build_probe_report: dict[str, Any] | None = None,
    build_workspace_report: dict[str, Any] | None = None,
) -> BlockerAnalysisInput:
    return BlockerAnalysisInput(
        workspace=workspace,
        run_id="run-001",
        execution_report_path=Path("runs/run-001/test_execution_report.json"),
        execution_report_sha256="a" * 64,
        report=report or blocked_report(),
        test_spec=test_spec or {"test_cases": [], "additional_case_candidates": []},
        harness_report=harness_report
        or {"function": {"status": "generated"}, "generated_files": []},
        build_probe_report=build_probe_report
        or {
            "function": {"name": "sample", "status": "succeeded"},
            "diagnostics": [],
        },
        build_workspace_report=build_workspace_report
        or {"function": {"name": "sample", "status": "generated"}},
    )


class ExecutionBlockerAnalyzerTests(unittest.TestCase):
    def test_build_errors_become_individual_direct_blockers(self):
        value = make_input(
            build_probe_report={
                "function": {"name": "sample", "status": "failed"},
                "diagnostics": [
                    {
                        "code": "unresolved_symbol",
                        "severity": "error",
                        "message": "_Helper is unresolved",
                        "file": "obj/sample.obj",
                        "line_number": None,
                    },
                    {
                        "code": "missing_include",
                        "severity": "error",
                        "message": "missing.h was not found",
                        "file": "src/sample.c",
                        "line_number": 4,
                    },
                ],
            }
        )

        result = analyze_test_execution_blockers(value)

        self.assertEqual(2, result.blocker_count)
        self.assertEqual(
            ["BLK-001", "BLK-002"],
            [item.blocker_id for item in result.blockers],
        )
        self.assertTrue(all(item.category == "build" for item in result.blockers))
        self.assertEqual("open_build_probe_report", result.primary_action.code)
        self.assertEqual(2, result.primary_action.affected_count)
        self.assertEqual(
            ["obj/sample.obj", "src/sample.c"],
            [item.related_file for item in result.blockers],
        )

    def test_missing_executable_is_reported_when_build_is_succeeded(self):
        executable = ExecutableInfo(
            path=Path("bin/utr_runner.exe"),
            exists=False,
            sha256=None,
            generated_from=None,
            build_probe_status="succeeded",
            warnings=[
                TestExecutionWarning("executable_not_found", "Runner was not found.")
            ],
        )
        result = analyze_test_execution_blockers(
            make_input(report=blocked_report(executable))
        )

        self.assertEqual("executable_not_found", result.blockers[0].code)
        self.assertEqual("choose_or_build_executable", result.primary_action.code)
        self.assertEqual("bin/utr_runner.exe", result.blockers[0].current_value)

    def test_unknown_block_always_produces_one_fallback_item(self):
        result = analyze_test_execution_blockers(
            make_input(
                test_spec={
                    "test_cases": [{"test_case_id": "TC_001"}],
                    "additional_case_candidates": [],
                }
            )
        )

        self.assertEqual(1, result.blocker_count)
        self.assertEqual("execution_blocked_unknown", result.blockers[0].code)
        self.assertEqual("open_execution_report", result.primary_action.code)

    def test_non_error_build_diagnostics_are_not_direct_blockers(self):
        result = analyze_test_execution_blockers(
            make_input(
                build_probe_report={
                    "function": {"name": "sample", "status": "failed"},
                    "diagnostics": [
                        {
                            "code": "note",
                            "severity": "warning",
                            "message": "not blocking",
                        }
                    ],
                }
            )
        )

        self.assertEqual(1, result.blocker_count)
        self.assertEqual("build_probe_not_successful", result.blockers[0].code)

    def test_distinct_build_diagnostic_locations_have_stable_report_order(self):
        diagnostic = {
            "code": "missing_include",
            "severity": "error",
            "message": "missing.h was not found",
            "file": "src/z.c",
            "line_number": 9,
        }
        value = make_input(
            build_probe_report={
                "function": {"name": "sample", "status": "failed"},
                "diagnostics": [
                    diagnostic,
                    diagnostic,
                    {
                        "code": "compile_error",
                        "severity": "error",
                        "message": "bad source",
                        "file": "src/a.c",
                        "line_number": 1,
                    },
                ],
            }
        )

        first = analyze_test_execution_blockers(value)
        second = analyze_test_execution_blockers(value)

        self.assertEqual(3, first.blocker_count)
        self.assertEqual(
            ["/diagnostics/0", "/diagnostics/1", "/diagnostics/2"],
            [item.source_pointer for item in first.blockers],
        )
        self.assertEqual(first, second)

    def test_long_build_message_is_bounded_and_marked_truncated(self):
        result = analyze_test_execution_blockers(
            make_input(
                build_probe_report={
                    "function": {"name": "sample", "status": "failed"},
                    "diagnostics": [
                        {
                            "code": "compile_error",
                            "severity": "error",
                            "message": "x" * 5000,
                        }
                    ],
                }
            )
        )

        self.assertEqual(4096, len(result.blockers[0].summary))
        self.assertTrue(result.blockers[0].truncated)

    def test_absolute_external_diagnostic_file_is_not_navigable(self):
        result = analyze_test_execution_blockers(
            make_input(
                build_probe_report={
                    "function": {"name": "sample", "status": "failed"},
                    "diagnostics": [
                        {
                            "code": "compile_error",
                            "severity": "error",
                            "message": "bad source",
                            "file": "/outside/secret.c",
                        }
                    ],
                }
            )
        )

        self.assertIsNone(result.blockers[0].related_file)

    def test_windows_drive_relative_diagnostic_file_is_not_navigable(self):
        result = analyze_test_execution_blockers(
            make_input(
                build_probe_report={
                    "function": {"name": "sample", "status": "failed"},
                    "diagnostics": [
                        {
                            "code": "compile_error",
                            "severity": "error",
                            "message": "bad source",
                            "file": r"C:outside\secret.c",
                        }
                    ],
                }
            )
        )

        self.assertIsNone(result.blockers[0].related_file)

    def test_no_executable_cases_expand_to_unresolved_required_leaves(self):
        result = analyze_test_execution_blockers(
            make_input(
                test_spec=candidate_spec(
                    input_value="UNRESOLVED_MODE",
                    expected_value="UNRESOLVED_RETURN",
                    confirmed=False,
                )
            )
        )

        self.assertEqual(
            {"expected_expression", "value_expression"},
            {item.control_name for item in result.blockers},
        )
        self.assertEqual(
            ["BLK-001", "BLK-002"],
            [item.blocker_id for item in result.blockers],
        )
        self.assertTrue(
            all(item.code == "unresolved_test_input" for item in result.blockers)
        )
        self.assertTrue(
            all(
                item.source_artifact == "reports/test_spec.json"
                for item in result.blockers
            )
        )
        self.assertNotIn(
            "no_executable_test_cases",
            [item.code for item in result.blockers],
        )
        self.assertEqual("open_test_input_editor", result.primary_action.code)

    def test_concrete_but_unconfirmed_parent_is_one_blocker_per_parent(self):
        result = analyze_test_execution_blockers(
            make_input(
                test_spec=candidate_spec(
                    input_value="MODE_AUTO",
                    expected_value="OK",
                    confirmed=False,
                )
            )
        )

        self.assertEqual(2, result.blocker_count)
        self.assertTrue(
            all(item.code == "unconfirmed_test_input" for item in result.blockers)
        )
        self.assertTrue(all(item.control_name is None for item in result.blockers))

    def test_unrelated_formal_review_item_is_not_a_direct_blocker(self):
        spec = candidate_spec(
            input_value="MODE_AUTO",
            expected_value="OK",
            confirmed=True,
        )
        spec["review_item_ids"] = ["review-documentation-only"]

        result = analyze_test_execution_blockers(make_input(test_spec=spec))

        self.assertEqual("no_executable_test_cases", result.blockers[0].code)
        self.assertNotIn(
            "review_decision_required",
            [item.code for item in result.blockers],
        )

    def test_runner_block_uses_case_evidence(self):
        report = blocked_report()
        report.executed = True
        report.case_results = [
            TestCaseExecutionResult(
                test_case_id="TC_001",
                generated_function_name="test_TC_001",
                status="blocked",
                exit_related=False,
                evidence="Runner prerequisite was not met.",
            )
        ]

        result = analyze_test_execution_blockers(make_input(report=report))

        self.assertEqual("runner_reported_blocked", result.blockers[0].code)
        self.assertEqual("TC_001", result.blockers[0].case_id)
        self.assertEqual("open_execution_log", result.primary_action.code)

    def test_runner_duplicate_cases_are_deduplicated_and_evidence_is_bounded(self):
        report = blocked_report()
        report.executed = True
        report.case_results = [
            TestCaseExecutionResult(
                test_case_id="TC_001",
                generated_function_name="test_TC_001",
                status="blocked",
                exit_related=False,
                evidence="z" * 5000,
            ),
            TestCaseExecutionResult(
                test_case_id="TC_001",
                generated_function_name="test_TC_001",
                status="blocked",
                exit_related=False,
                evidence="duplicate",
            ),
        ]

        result = analyze_test_execution_blockers(make_input(report=report))

        self.assertEqual(1, result.blocker_count)
        self.assertEqual(4096, len(result.blockers[0].summary))
        self.assertTrue(result.blockers[0].truncated)

    def test_unresolved_prefixes_and_empty_values_share_input_editor_action(self):
        for raw in (
            "",
            "TBD_VALUE",
            "TODO_VALUE",
            "UNKNOWN_VALUE",
            "UNRESOLVED_VALUE",
        ):
            with self.subTest(raw=raw):
                result = analyze_test_execution_blockers(
                    make_input(
                        test_spec=candidate_spec(
                            input_value=raw,
                            expected_value="OK",
                            confirmed=False,
                        )
                    )
                )
                input_blocker = next(
                    item
                    for item in result.blockers
                    if item.control_name == "value_expression"
                )
                self.assertEqual("unresolved_test_input", input_blocker.code)
                self.assertEqual(
                    "open_test_input_editor",
                    result.primary_action.code,
                )

    def test_unmapped_harness_placeholder_is_reported_when_placeholders_are_forbidden(self):
        report = blocked_report()
        report.policy.allow_placeholder_tests = False

        result = analyze_test_execution_blockers(
            make_input(
                report=report,
                test_spec={
                    "test_cases": [{"test_case_id": "TC_READY"}],
                    "additional_case_candidates": [],
                },
                harness_report={
                    "function": {"name": "sample", "status": "partial"},
                    "generated_files": [],
                    "unresolved_placeholders": [
                        {
                            "placeholder_id": "UP_OTHER",
                            "placeholder_kind": "expected_return",
                            "name": "TBD_EXPECTED_RETURN_INT",
                            "related_test_case_id": "TC_OTHER",
                            "reason": "Expected result is unresolved.",
                            "suggested_action": "Review the expected result.",
                        }
                    ],
                },
            )
        )

        self.assertEqual("placeholder_tests_not_allowed", result.blockers[0].code)
        self.assertEqual("TC_OTHER", result.blockers[0].case_id)

    def test_runner_without_structured_case_uses_bounded_log_excerpt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            paths = create_run_paths(workspace, run_id="run-001")
            paths.combined_log.write_text("L" * 9000, encoding="utf-8")
            report = blocked_report()
            report.executed = True
            report.run_paths = paths

            result = analyze_test_execution_blockers(
                make_input(workspace=workspace, report=report)
            )

        self.assertEqual("runner_reported_blocked", result.blockers[0].code)
        self.assertEqual(8192, len(result.blockers[0].log_excerpt or ""))
        self.assertTrue(result.blockers[0].truncated)
        self.assertEqual(
            "runs/run-001/logs/test_execution.log",
            result.blockers[0].source_artifact,
        )

    def test_stale_harness_precedes_test_input_causes(self):
        result = analyze_test_execution_blockers(
            make_input(
                test_spec=candidate_spec(
                    input_value="UNRESOLVED_MODE",
                    expected_value="UNRESOLVED_RETURN",
                    confirmed=False,
                ),
                harness_report={
                    "function": {"status": "stale"},
                    "generated_files": [],
                    "unresolved_placeholders": [],
                },
            )
        )

        self.assertEqual("harness_missing_or_stale", result.blockers[0].code)
        self.assertEqual("generate_harness", result.primary_action.code)

    def test_missing_listed_test_source_is_a_harness_blocker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            result = analyze_test_execution_blockers(
                make_input(
                    workspace=workspace,
                    harness_report={
                        "function": {"name": "sample", "status": "generated"},
                        "generated_files": [
                            {
                                "path": "generated/tests/test_sample.c",
                                "file_kind": "test_source",
                            }
                        ],
                        "unresolved_placeholders": [],
                    },
                )
            )

        self.assertEqual("harness_missing_or_stale", result.blockers[0].code)
        self.assertEqual("generate_harness", result.primary_action.code)


if __name__ == "__main__":
    unittest.main()
