from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from tests.spec_support import write_test_input_form_fixture
from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_input_form import (
    apply_test_input_form,
    build_test_input_form,
    parse_test_input_change_request,
)
from unit_test_runner.test_spec import (
    build_current_artifact_context,
    load_test_spec_snapshot,
    save_test_spec_snapshot,
)


def all_items(form):
    return [item for case in form.cases or () for item in case.items]


def ready_candidate_request(form, unresolved_case_id: str):
    target_case = next(case for case in form.cases or () if case.case_id == unresolved_case_id)
    concrete_by_kind = {
        ("input_assignment", "mode"): "MODE_AUTO",
        ("input_assignment", "flags"): "0",
        ("input_assignment", "buffer"): "NULL",
        ("state_setup", ""): "STATE_READY",
        ("expected_observation", ""): "0",
    }
    changes = []
    for item in target_case.items:
        if not item.blocking:
            continue
        values = {}
        for control in item.controls:
            if not control.required_for_confirmation:
                continue
            suffix = item.label.rsplit(" ", 1)[-1] if item.kind == "input_assignment" else ""
            values[control.name] = concrete_by_kind[(item.kind, suffix)]
        changes.append(
            {
                "item_id": item.item_id,
                "subject_fingerprint": item.subject_fingerprint,
                "values": values,
                "confirmed": True,
            }
        )
    return parse_test_input_change_request({"schema_version": "1.0", "changes": changes})


class TestInputFormReclassificationTests(unittest.TestCase):
    def test_candidate_promotes_only_after_every_execution_parent_is_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            first_form = build_test_input_form(fixture.workspace)
            mode = next(
                item
                for item in all_items(first_form)
                if item.kind == "input_assignment" and item.label.endswith("mode")
            )
            partial = parse_test_input_change_request(
                {
                    "schema_version": "1.0",
                    "changes": [
                        {
                            "item_id": mode.item_id,
                            "subject_fingerprint": mode.subject_fingerprint,
                            "values": {"value_expression": "MODE_AUTO"},
                            "confirmed": True,
                        }
                    ],
                }
            )

            partial_result = apply_test_input_form(
                fixture.workspace, partial, expected_revision=first_form.revision
            )
            self.assertEqual((), partial_result.promoted_case_ids)
            partial_saved = load_test_spec_snapshot(
                fixture.canonical_path, mode=ContractMode.STRICT
            )
            self.assertIn(
                fixture.unresolved_case_id,
                [case["test_case_id"] for case in partial_saved.spec.additional_case_candidates],
            )

            ready_form = build_test_input_form(fixture.workspace)
            before_ids = {
                item.item_id
                for case in ready_form.cases or ()
                if case.case_id == fixture.unresolved_case_id
                for item in case.items
            }
            result = apply_test_input_form(
                fixture.workspace,
                ready_candidate_request(ready_form, fixture.unresolved_case_id),
                expected_revision=ready_form.revision,
            )

            self.assertEqual((fixture.unresolved_case_id,), result.promoted_case_ids)
            saved = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            executable_ids = [case["test_case_id"] for case in saved.spec.test_cases]
            candidate_ids = [case["test_case_id"] for case in saved.spec.additional_case_candidates]
            self.assertEqual(
                [fixture.concrete_case_id, fixture.unresolved_case_id],
                executable_ids,
            )
            self.assertEqual([fixture.intentional_candidate_id], candidate_ids)
            after_form = build_test_input_form(fixture.workspace)
            after_ids = {
                item.item_id
                for case in after_form.cases or ()
                if case.case_id == fixture.unresolved_case_id
                for item in case.items
            }
            self.assertTrue(after_ids.issubset(before_ids))

    def test_intentional_candidate_never_promotes_and_history_summaries_stay_unchanged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            before = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            before_coverage = copy.deepcopy(before.spec.coverage_summary)
            before_unresolved = copy.deepcopy(before.spec.unresolved_items)
            form = build_test_input_form(fixture.workspace)

            result = apply_test_input_form(
                fixture.workspace,
                ready_candidate_request(form, fixture.unresolved_case_id),
                expected_revision=form.revision,
            )

            saved = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            self.assertNotIn(fixture.intentional_candidate_id, result.promoted_case_ids)
            self.assertIn(
                fixture.intentional_candidate_id,
                [case["test_case_id"] for case in saved.spec.additional_case_candidates],
            )
            self.assertEqual(before_coverage, saved.spec.coverage_summary)
            self.assertEqual(before_unresolved, saved.spec.unresolved_items)

    def test_touched_unsafe_executable_case_demotes_but_untouched_cases_do_not_move(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            current = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            context = build_current_artifact_context(fixture.workspace, current.spec)
            concrete = current.spec.test_cases[0]
            concrete["input_assignments"][0]["review_required"] = True
            concrete["preconditions"] = [
                {
                    "source": "fixture",
                    "description": "Keep this nonexecution review item visible.",
                    "review_required": True,
                }
            ]
            save_test_spec_snapshot(
                fixture.canonical_path,
                current.spec,
                expected_revision=current.spec.revision,
                current_context=context,
            )
            form = build_test_input_form(fixture.workspace)
            concrete_case = next(
                case for case in form.cases or () if case.case_id == fixture.concrete_case_id
            )
            mode = next(item for item in concrete_case.items if item.kind == "input_assignment")

            request = parse_test_input_change_request(
                {
                    "schema_version": "1.0",
                    "changes": [
                        {
                            "item_id": mode.item_id,
                            "subject_fingerprint": mode.subject_fingerprint,
                            "values": {"value_expression": "TBD_REGRESSION"},
                            "confirmed": False,
                        }
                    ],
                }
            )
            result = apply_test_input_form(
                fixture.workspace, request, expected_revision=form.revision
            )

            self.assertEqual((fixture.concrete_case_id,), result.demoted_case_ids)
            saved = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            self.assertNotIn(
                fixture.concrete_case_id,
                [case["test_case_id"] for case in saved.spec.test_cases],
            )
            self.assertEqual(
                [fixture.unresolved_case_id, fixture.intentional_candidate_id, fixture.concrete_case_id],
                [case["test_case_id"] for case in saved.spec.additional_case_candidates],
            )

    def test_nonexecution_edit_does_not_demote_executable_case(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            current = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            context = build_current_artifact_context(fixture.workspace, current.spec)
            current.spec.test_cases[0]["preconditions"] = [
                {
                    "source": "fixture",
                    "description": "Original precondition.",
                    "review_required": True,
                }
            ]
            save_test_spec_snapshot(
                fixture.canonical_path,
                current.spec,
                expected_revision=current.spec.revision,
                current_context=context,
            )
            form = build_test_input_form(fixture.workspace)
            concrete_case = next(
                case for case in form.cases or () if case.case_id == fixture.concrete_case_id
            )
            precondition = next(item for item in concrete_case.items if item.kind == "precondition")
            request = parse_test_input_change_request(
                {
                    "schema_version": "1.0",
                    "changes": [
                        {
                            "item_id": precondition.item_id,
                            "subject_fingerprint": precondition.subject_fingerprint,
                            "values": {"description": "Updated precondition."},
                            "confirmed": True,
                        }
                    ],
                }
            )

            result = apply_test_input_form(
                fixture.workspace, request, expected_revision=form.revision
            )

            self.assertEqual((), result.demoted_case_ids)
            saved = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            self.assertIn(
                fixture.concrete_case_id,
                [case["test_case_id"] for case in saved.spec.test_cases],
            )


if __name__ == "__main__":
    unittest.main()
