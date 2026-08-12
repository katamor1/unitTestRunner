import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.execution.runner_output_parser import parse_runner_output
from unit_test_runner.execution.executable_resolver import resolve_executable
from unit_test_runner.execution.execution_models import (
    TestCaseExecutionResult,
    TestExecutionPolicy,
)
from unit_test_runner.execution.precondition_validator import (
    validate_execution_preconditions,
)
from unit_test_runner.execution.test_execution import (
    _canonical_test_spec_review_items,
    _case_progress_ids,
    _case_results_from_design,
    select_test_case_ids,
)


class ExecutionEvidenceTests(unittest.TestCase):
    def test_build_probe_consumers_read_status_from_public_envelope_data(self):
        report = {
            "schema_version": "1.0.0",
            "artifact_kind": "build_probe_report",
            "subject": {
                "source_path": "src/control.c",
                "source_sha256": "a" * 64,
                "function": "Control_Update",
                "project": "Control",
                "configuration": "Control - Win32 Debug",
            },
            "data": {"status": "succeeded"},
        }

        executable = resolve_executable(
            REPO_ROOT,
            build_probe_report=report,
        )
        status, warnings, review_items = validate_execution_preconditions(
            report,
            executable,
            TestExecutionPolicy(run_tests=False, dry_run=True),
        )

        self.assertEqual("succeeded", executable.build_probe_status)
        self.assertEqual("ready", status)
        self.assertEqual([], warnings)
        self.assertEqual([], review_items)

    def test_explicit_case_and_tag_selectors_return_only_enabled_known_cases(self):
        data = {
            "test_cases": [
                {"test_case_id": "case-a", "tags": ["smoke"]},
                {"test_case_id": "case-b", "tags": ["regression"]},
            ]
        }

        self.assertEqual(
            ["case-b"],
            select_test_case_ids(data, "case_id", ["case-b"]),
        )
        self.assertEqual(
            ["case-a"],
            select_test_case_ids(data, "tag", ["smoke"]),
        )

    def test_unknown_empty_and_disabled_selectors_are_rejected(self):
        data = {
            "test_cases": [
                {"test_case_id": "case-a", "tags": ["smoke"]},
                {
                    "test_case_id": "case-b",
                    "tags": ["regression"],
                    "enabled": False,
                },
            ]
        }

        for kind, values in (
            ("case_id", []),
            ("case_id", ["missing"]),
            ("case_id", ["case-b"]),
            ("tag", ["missing"]),
            ("tag", ["regression"]),
        ):
            with self.subTest(kind=kind, values=values):
                with self.assertRaises(ValueError):
                    select_test_case_ids(data, kind, values)

    def test_all_selector_returns_every_enabled_case_in_spec_order(self):
        data = {
            "test_cases": [
                {"test_case_id": "case-a", "tags": []},
                {"test_case_id": "case-b", "enabled": False},
                {"test_case_id": "case-c", "tags": []},
            ]
        }

        self.assertEqual(
            ["case-a", "case-c"],
            select_test_case_ids(data, "all", []),
        )

    def test_resolved_review_provenance_and_optional_candidates_do_not_block_run(self):
        data = {
            "test_cases": [
                {
                    "test_case_id": "case-a",
                    "review_item_ids": ["review-case-a"],
                    "execution_steps": [
                        {
                            "action": "call_function",
                            "review_required": True,
                        }
                    ],
                    "expected_observations": [
                        {
                            "review_required": False,
                            "review_item_ids": ["review-oracle-a"],
                        }
                    ],
                }
            ],
            "additional_case_candidates": [
                {
                    "test_case_id": "candidate-b",
                    "review_item_ids": ["review-candidate-b"],
                }
            ],
            "unresolved_items": [
                {
                    "item_id": "resolved-history",
                    "blocking": False,
                    "related_test_case_ids": ["case-a"],
                },
                {
                    "item_id": "optional-candidate-unresolved",
                    "item_kind": "expected_return_unknown",
                    "related_test_case_ids": ["candidate-b"],
                }
            ],
            "review_item_ids": ["review-case-a", "review-candidate-b"],
        }

        self.assertEqual([], _canonical_test_spec_review_items(data))
        self.assertFalse(_case_results_from_design(data)[0].review_required)

        data["test_cases"][0]["expected_observations"][0]["review_required"] = True
        self.assertEqual(
            ["review-oracle-a"],
            [item.item_id for item in _canonical_test_spec_review_items(data)],
        )
        self.assertTrue(_case_results_from_design(data)[0].review_required)

    def test_runner_output_parser_extracts_cases_assertions_and_summary(self):
        parsed = parse_runner_output(
            """
[ RUN      ] TC_Control_Update_001
[       OK ] TC_Control_Update_001
UTR RUN TC_Control_Update_002
UTR ASSERT EQ_INT: test_Control_Update.c:120 actual_return
[  FAILED  ] TC_Control_Update_002
[ SUMMARY  ] total=2 passed=1 failed=1 skipped=0
"""
        )
        payload = parsed.to_dict()

        self.assertEqual(2, payload["summary"]["total"])
        self.assertEqual(1, payload["summary"]["passed"])
        self.assertEqual(1, payload["summary"]["failed"])
        self.assertEqual(1, payload["summary"]["assertion_failures"])
        cases = {case["test_case_id"]: case for case in payload["case_results"]}
        self.assertEqual("passed", cases["TC_Control_Update_001"]["status"])
        self.assertEqual("failed", cases["TC_Control_Update_002"]["status"])

    def test_runner_output_parser_treats_bare_run_markers_as_inconclusive(self):
        parsed = parse_runner_output(
            """
UTR RUN TC_Control_Update_001
UTR RUN TC_Control_Update_002
"""
        )
        payload = parsed.to_dict()

        self.assertEqual(2, payload["summary"]["total"])
        self.assertEqual(0, payload["summary"]["passed"])
        self.assertEqual(2, payload["summary"]["inconclusive"])
        self.assertEqual("low", payload["summary"]["parser_confidence"])
        cases = {case["test_case_id"]: case for case in payload["case_results"]}
        self.assertEqual("inconclusive", cases["TC_Control_Update_001"]["status"])
        self.assertEqual("inconclusive", cases["TC_Control_Update_002"]["status"])

    def test_runner_output_parser_requires_ok_markers_for_passed_cases(self):
        parsed = parse_runner_output(
            """
UTR RUN TC_Control_Update_001
UTR OK TC_Control_Update_001
UTR RUN TC_Control_Update_002
UTR OK TC_Control_Update_002
"""
        )
        payload = parsed.to_dict()

        self.assertEqual(2, payload["summary"]["total"])
        self.assertEqual(2, payload["summary"]["passed"])
        self.assertEqual(0, payload["summary"]["inconclusive"])
        cases = {case["test_case_id"]: case for case in payload["case_results"]}
        self.assertEqual("passed", cases["TC_Control_Update_001"]["status"])
        self.assertEqual("passed", cases["TC_Control_Update_002"]["status"])

    def test_run_report_separates_started_from_completed_cases(self):
        started, completed, not_run = _case_progress_ids(
            ["passed", "timed-out", "missing"],
            [
                TestCaseExecutionResult("passed", None, "passed", False),
                TestCaseExecutionResult("timed-out", None, "timeout", True),
            ],
        )

        self.assertEqual(["passed", "timed-out"], started)
        self.assertEqual(["passed"], completed)
        self.assertEqual(["missing"], not_run)


if __name__ == "__main__":
    unittest.main()
