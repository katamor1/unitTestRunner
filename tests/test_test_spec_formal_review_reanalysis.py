from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import unit_test_runner.reanalysis.workflow as workflow_module
from unit_test_runner.dossier import analyze_function_workflow
from unit_test_runner.reanalysis.reanalysis_models import (
    ReanalysisPolicy,
    TestCaseReconciliationReport,
)
from unit_test_runner.reanalysis.test_case_reconciler import reconcile_test_cases
from unit_test_runner.reanalysis.workflow import _merge_reanalysis_candidate
from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_spec import (
    StaleRevisionError,
    TestSpec,
    TestSpecContractError,
    build_current_artifact_context,
    load_test_spec,
    validate_test_spec,
)
from tests.spec_support import copied_payload, current_context


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


PROTECTED_CASE_FIELDS = (
    "title",
    "target_function",
    "purpose",
    "priority",
    "case_kind",
    "preconditions",
    "input_assignments",
    "state_setups",
    "stub_setups",
    "dependency_overrides",
    "execution_steps",
    "expected_observations",
    "candidate_links",
    "confidence",
    "warnings",
    "review_item_ids",
)


def candidate_case(case_id: str, oracle: str) -> dict:
    case = copy.deepcopy(copied_payload()["data"]["test_cases"][0])
    case["test_case_id"] = case_id
    case["title"] = "manual candidate"
    case["expected_observations"][0]["expected_expression"] = oracle
    case.pop("review_item_ids", None)
    return case


def spec_with_candidates(*cases: dict) -> TestSpec:
    payload = copied_payload()
    payload["data"]["additional_case_candidates"] = [
        copy.deepcopy(case) for case in cases
    ]
    return TestSpec.from_payload(payload)


class TestSpecFormalReviewReanalysisTests(unittest.TestCase):
    def test_reconciler_preserves_every_editable_case_field(self):
        previous = copied_payload()["data"]
        previous_case = previous["test_cases"][0]
        previous_case.update(
            {
                "preconditions": [{"expression": "manual-precondition"}],
                "state_setups": [
                    {"target_name": "g_state", "value_expression": "MANUAL_STATE"}
                ],
                "dependency_overrides": [
                    {"dependency_id": "dep-read-sensor", "mode": "stub"}
                ],
                "execution_steps": [{"expression": "manual-step"}],
                "candidate_links": ["manual-candidate"],
                "confidence": "manual-confidence",
                "warnings": [{"code": "manual-warning"}],
                "review_item_ids": ["review-oracle-001"],
            }
        )
        current = copy.deepcopy(previous)
        proposed = current["test_cases"][0]
        for field in PROTECTED_CASE_FIELDS:
            if field in proposed:
                proposed[field] = copy.deepcopy(proposed[field])
        proposed.update(
            {
                "title": "generated title",
                "target_function": "Generated_Function",
                "purpose": "generated purpose",
                "priority": "low",
                "case_kind": "generated-kind",
                "preconditions": [{"expression": "generated"}],
                "input_assignments": [
                    {"target_name": "mode", "value_expression": "GENERATED"}
                ],
                "state_setups": [
                    {"target_name": "g_state", "value_expression": "GENERATED"}
                ],
                "stub_setups": [
                    {"stub_name": "ReadSensor", "value_expression": "GENERATED"}
                ],
                "dependency_overrides": [
                    {"dependency_id": "dep-read-sensor", "mode": "real"}
                ],
                "execution_steps": [{"expression": "generated"}],
                "expected_observations": [
                    {
                        "observation_kind": "return_value",
                        "expected_expression": "GENERATED",
                    }
                ],
                "candidate_links": ["generated-candidate"],
                "confidence": "generated-confidence",
                "warnings": [{"code": "generated-warning"}],
                "review_item_ids": ["review-input-001"],
            }
        )

        _report, updated = reconcile_test_cases(
            previous,
            current,
            [],
            [],
            [],
            [],
            generate_updated_test_case_design=True,
        )

        self.assertIsNotNone(updated)
        merged = updated["test_cases"][0]
        for field in PROTECTED_CASE_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(previous_case.get(field), merged.get(field))

    def test_previous_only_candidate_survives_reanalysis_merge(self):
        previous_case = candidate_case("tc-previous-candidate", "MANUAL")
        previous = spec_with_candidates(previous_case)
        current = spec_with_candidates()

        merged = _merge_reanalysis_candidate(
            current,
            previous,
            previous.to_payload()["data"],
        )

        self.assertIn(
            "tc-previous-candidate",
            {
                case["test_case_id"]
                for case in merged.additional_case_candidates
            },
        )

    def test_same_id_candidate_preserves_manual_oracle(self):
        previous_case = candidate_case("tc-shared-candidate", "MANUAL_ORACLE")
        current_case = candidate_case("tc-shared-candidate", "GENERATED_ORACLE")
        previous = spec_with_candidates(previous_case)
        current = spec_with_candidates(current_case)

        merged = _merge_reanalysis_candidate(
            current,
            previous,
            previous.to_payload()["data"],
        )

        shared = next(
            case
            for case in merged.additional_case_candidates
            if case["test_case_id"] == "tc-shared-candidate"
        )
        self.assertEqual(
            "MANUAL_ORACLE",
            shared["expected_observations"][0]["expected_expression"],
        )

    def test_same_id_candidate_conflict_is_visible_as_blocking_review(self):
        previous = spec_with_candidates(
            candidate_case("tc-conflict-candidate", "MANUAL_ORACLE")
        )
        current = spec_with_candidates(
            candidate_case("tc-conflict-candidate", "GENERATED_ORACLE")
        )

        merged = _merge_reanalysis_candidate(
            current,
            previous,
            previous.to_payload()["data"],
        )

        conflicts = [
            item
            for item in merged.unresolved_items
            if item.get("item_kind") == "reanalysis_merge_conflict"
        ]
        self.assertTrue(conflicts)
        self.assertIn(
            "tc-conflict-candidate", conflicts[0]["related_test_case_ids"]
        )
        self.assertTrue(
            any(
                warning.get("code") == "reanalysis_merge_conflict"
                for warning in merged.warnings
            )
        )

    def test_candidate_conflict_is_visible_in_reconciliation_report(self):
        previous = spec_with_candidates(
            candidate_case("tc-report-conflict", "MANUAL_ORACLE")
        )
        current = spec_with_candidates(
            candidate_case("tc-report-conflict", "GENERATED_ORACLE")
        )
        report = TestCaseReconciliationReport(
            function_name="Control_Update", status="completed"
        )

        _merge_reanalysis_candidate(
            current,
            previous,
            previous.to_payload()["data"],
            reconciliation=report,
        )

        self.assertEqual("review_required", report.status)
        self.assertTrue(
            any(
                item.test_case_id == "tc-report-conflict"
                and item.field_name == "expected_observations"
                for item in report.manual_merge_items
            )
        )

    def test_repeated_candidate_conflict_has_one_stable_blocker_and_remains_valid(self):
        previous = spec_with_candidates(
            candidate_case("tc-repeat-conflict", "MANUAL_ORACLE")
        )
        current = spec_with_candidates(
            candidate_case("tc-repeat-conflict", "GENERATED_ORACLE")
        )
        first = _merge_reanalysis_candidate(
            current,
            previous,
            previous.to_payload()["data"],
        )

        second = _merge_reanalysis_candidate(
            current,
            first,
            first.to_payload()["data"],
        )

        blockers = [
            item
            for item in second.unresolved_items
            if item.get("item_kind") == "reanalysis_merge_conflict"
            and item.get("related_test_case_ids") == ["tc-repeat-conflict"]
        ]
        self.assertEqual(1, len(blockers))
        self.assertEqual(
            (), validate_test_spec(second, current_context=current_context())
        )

    def test_invalid_complete_merge_is_rejected_before_save_is_called(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "Control_Update"
            analyze_function_workflow(
                FIXTURE,
                FIXTURE / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                out,
                "Control",
                phase="design",
            )
            original_merge = workflow_module._merge_reanalysis_candidate

            def invalid_merge(*args, **kwargs):
                candidate = original_merge(*args, **kwargs)
                candidate.generation_policy["approval_status"] = "approved"
                return candidate

            with mock.patch.object(
                workflow_module,
                "_merge_reanalysis_candidate",
                side_effect=invalid_merge,
            ), mock.patch.object(
                workflow_module,
                "save_test_spec_snapshot",
                side_effect=AssertionError("invalid candidate reached save"),
            ) as save:
                with self.assertRaises(TestSpecContractError):
                    workflow_module.reanalyze_function_workflow(
                        FIXTURE,
                        FIXTURE / "Product.dsw",
                        "src/control.c",
                        "Control_Update",
                        "Win32 Debug",
                        out,
                        project_name="Control",
                        policy=ReanalysisPolicy(
                            generate_updated_test_case_design=True,
                            overwrite_test_case_design=True,
                        ),
                    )

            save.assert_not_called()

    def test_revision_conflict_preserves_concurrent_canonical_without_alternate_editable_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "Control_Update"
            analyze_function_workflow(
                FIXTURE,
                FIXTURE / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                out,
                "Control",
                phase="design",
            )
            canonical = out / "reports" / "test_spec.json"
            original_save = workflow_module.save_test_spec_snapshot
            concurrent_bytes = None

            def interleaved_save(path, candidate, *, expected_revision, current_context):
                nonlocal concurrent_bytes
                concurrent = load_test_spec(path, mode=ContractMode.STRICT)
                concurrent.generation_policy["concurrent_marker"] = "writer-b"
                concurrent_context = build_current_artifact_context(out, concurrent)
                original_save(
                    path,
                    concurrent,
                    expected_revision=concurrent.revision,
                    current_context=concurrent_context,
                )
                concurrent_bytes = canonical.read_bytes()
                return original_save(
                    path,
                    candidate,
                    expected_revision=expected_revision,
                    current_context=current_context,
                )

            with mock.patch.object(
                workflow_module,
                "save_test_spec_snapshot",
                side_effect=interleaved_save,
            ):
                with self.assertRaises(StaleRevisionError):
                    workflow_module.reanalyze_function_workflow(
                        FIXTURE,
                        FIXTURE / "Product.dsw",
                        "src/control.c",
                        "Control_Update",
                        "Win32 Debug",
                        out,
                        project_name="Control",
                        policy=ReanalysisPolicy(
                            generate_updated_test_case_design=True,
                            overwrite_test_case_design=True,
                        ),
                    )

            self.assertIsNotNone(concurrent_bytes)
            self.assertEqual(concurrent_bytes, canonical.read_bytes())
            self.assertFalse(
                (out / "reports" / "updated_test_case_design.json").exists()
            )
            self.assertFalse((out / "reports" / "test_case_design.json").exists())


if __name__ == "__main__":
    unittest.main()
