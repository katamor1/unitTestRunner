from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.spec_support import write_test_input_form_fixture
from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_input_form import (
    TestInputFormError,
    apply_test_input_form,
    build_test_input_form,
    parse_test_input_change_request,
)
from unit_test_runner.test_spec import load_test_spec_snapshot


def item_by(form, kind: str, label_suffix: str = ""):
    return next(
        item
        for case in form.cases or ()
        for item in case.items
        if item.kind == kind and item.label.endswith(label_suffix)
    )


def request_for(item, values: dict[str, str], confirmed: bool):
    return parse_test_input_change_request(
        {
            "schema_version": "1.0",
            "changes": [
                {
                    "item_id": item.item_id,
                    "subject_fingerprint": item.subject_fingerprint,
                    "values": values,
                    "confirmed": confirmed,
                }
            ],
        }
    )


class TestInputFormApplyTests(unittest.TestCase):
    def test_partial_save_changes_only_the_submitted_parent_and_increments_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            before = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            before_payload = before.spec.to_payload()
            form = build_test_input_form(fixture.workspace)
            mode = item_by(form, "input_assignment", "mode")

            result = apply_test_input_form(
                fixture.workspace,
                request_for(mode, {"value_expression": "MODE_AUTO"}, confirmed=False),
                expected_revision=before.spec.revision,
            )

            after = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            candidate = next(
                case
                for case in after.spec.additional_case_candidates
                if case["test_case_id"] == fixture.unresolved_case_id
            )
            mode_parent = next(
                item for item in candidate["input_assignments"] if item["target_name"] == "mode"
            )
            self.assertEqual(before.spec.revision + 1, result.revision)
            self.assertEqual(result.revision, after.spec.revision)
            self.assertEqual("MODE_AUTO", mode_parent["value_expression"])
            self.assertTrue(mode_parent["review_required"])
            self.assertEqual(1, result.updated_item_count)
            self.assertEqual(0, result.confirmed_item_count)

            before_candidate = next(
                case
                for case in before_payload["data"]["additional_case_candidates"]
                if case["test_case_id"] == fixture.unresolved_case_id
            )
            before_flags = next(
                item for item in before_candidate["input_assignments"] if item["target_name"] == "flags"
            )
            after_flags = next(
                item for item in candidate["input_assignments"] if item["target_name"] == "flags"
            )
            self.assertEqual(before_flags, after_flags)

    def test_same_save_concrete_value_and_confirmation_clears_review_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            form = build_test_input_form(fixture.workspace)
            mode = item_by(form, "input_assignment", "mode")

            result = apply_test_input_form(
                fixture.workspace,
                request_for(mode, {"value_expression": "MODE_AUTO"}, confirmed=True),
                expected_revision=form.revision,
            )

            saved = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            candidate = next(
                case
                for case in saved.spec.additional_case_candidates
                if case["test_case_id"] == fixture.unresolved_case_id
            )
            parent = next(
                item for item in candidate["input_assignments"] if item["target_name"] == "mode"
            )
            self.assertFalse(parent["review_required"])
            self.assertEqual(1, result.confirmed_item_count)

    def test_confirmation_only_uses_current_values_and_can_mark_an_item_unconfirmed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            form = build_test_input_form(fixture.workspace)
            precondition = item_by(form, "precondition")

            result = apply_test_input_form(
                fixture.workspace,
                request_for(precondition, {}, confirmed=False),
                expected_revision=form.revision,
            )

            self.assertEqual(1, result.updated_item_count)
            saved = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            candidate = next(
                case
                for case in saved.spec.additional_case_candidates
                if case["test_case_id"] == fixture.unresolved_case_id
            )
            self.assertTrue(candidate["preconditions"][0]["review_required"])

    def test_rejects_invalid_changes_without_modifying_canonical_bytes(self):
        scenarios = (
            ("confirmed unresolved", lambda form: request_for(item_by(form, "input_assignment", "mode"), {"value_expression": "TBD_STILL"}, True), "test_input_validation"),
            ("missing item", lambda form: parse_test_input_change_request({"schema_version": "1.0", "changes": [{"item_id": "item-" + "f" * 64, "subject_fingerprint": "e" * 64, "values": {}, "confirmed": False}]}), "test_input_validation"),
            ("fingerprint conflict", lambda form: parse_test_input_change_request({"schema_version": "1.0", "changes": [{"item_id": item_by(form, "input_assignment", "mode").item_id, "subject_fingerprint": "e" * 64, "values": {}, "confirmed": False}]}), "test_input_subject_conflict"),
            ("wrong leaf for item", lambda form: request_for(item_by(form, "input_assignment", "mode"), {"description": "not an input leaf"}, False), "test_input_validation"),
            ("noneditable item", lambda form: request_for(item_by(form, "execution_step"), {"detail": "changed"}, False), "test_input_validation"),
            ("oversized expression", lambda form: request_for(item_by(form, "input_assignment", "mode"), {"value_expression": "X" * 4097}, False), "test_input_validation"),
        )
        for name, request_builder, code in scenarios:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                fixture = write_test_input_form_fixture(Path(temp_dir))
                form = build_test_input_form(fixture.workspace)
                before = fixture.canonical_path.read_bytes()
                with self.assertRaises(TestInputFormError) as raised:
                    apply_test_input_form(
                        fixture.workspace,
                        request_builder(form),
                        expected_revision=form.revision,
                    )
                self.assertEqual(code, raised.exception.code)
                self.assertEqual(before, fixture.canonical_path.read_bytes())

    def test_rejects_stale_revision_and_stale_source_without_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            form = build_test_input_form(fixture.workspace)
            mode = item_by(form, "input_assignment", "mode")
            before = fixture.canonical_path.read_bytes()

            with self.assertRaises(TestInputFormError) as raised:
                apply_test_input_form(
                    fixture.workspace,
                    request_for(mode, {"value_expression": "MODE_AUTO"}, False),
                    expected_revision=form.revision - 1,
                )
            self.assertEqual("test_input_revision_conflict", raised.exception.code)
            self.assertEqual(before, fixture.canonical_path.read_bytes())

            fixture.source_path.write_text(
                fixture.source_path.read_text(encoding="utf-8") + "/* stale */\n",
                encoding="utf-8",
            )
            with self.assertRaises(TestInputFormError) as raised:
                apply_test_input_form(
                    fixture.workspace,
                    request_for(mode, {"value_expression": "MODE_AUTO"}, False),
                    expected_revision=form.revision,
                )
            self.assertEqual("stale_test_spec", raised.exception.code)
            self.assertEqual(before, fixture.canonical_path.read_bytes())

    def test_valid_first_change_and_invalid_second_change_are_atomic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            form = build_test_input_form(fixture.workspace)
            mode = item_by(form, "input_assignment", "mode")
            dependency = item_by(form, "dependency_override")
            request = parse_test_input_change_request(
                {
                    "schema_version": "1.0",
                    "changes": [
                        {
                            "item_id": mode.item_id,
                            "subject_fingerprint": mode.subject_fingerprint,
                            "values": {"value_expression": "MODE_AUTO"},
                            "confirmed": True,
                        },
                        {
                            "item_id": dependency.item_id,
                            "subject_fingerprint": dependency.subject_fingerprint,
                            "values": {"mode": "auto"},
                            "confirmed": True,
                        },
                    ],
                }
            )
            before = fixture.canonical_path.read_bytes()

            with self.assertRaises(TestInputFormError) as raised:
                apply_test_input_form(
                    fixture.workspace,
                    request,
                    expected_revision=form.revision,
                )

            self.assertEqual("test_input_validation", raised.exception.code)
            self.assertEqual(before, fixture.canonical_path.read_bytes())

    def test_form_save_does_not_mutate_formal_review_or_provenance_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            before = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            form = build_test_input_form(fixture.workspace)
            mode = item_by(form, "input_assignment", "mode")
            before_data = before.spec.to_payload()["data"]
            before_candidate = next(
                case
                for case in before_data["additional_case_candidates"]
                if case["test_case_id"] == fixture.unresolved_case_id
            )

            apply_test_input_form(
                fixture.workspace,
                request_for(mode, {"value_expression": "MODE_AUTO"}, True),
                expected_revision=form.revision,
            )

            after_data = load_test_spec_snapshot(
                fixture.canonical_path, mode=ContractMode.STRICT
            ).spec.to_payload()["data"]
            after_candidate = next(
                case
                for case in after_data["additional_case_candidates"]
                if case["test_case_id"] == fixture.unresolved_case_id
            )
            for key in (
                "review_item_ids",
                "unresolved_items",
                "source",
                "function",
                "generated_from",
                "coverage_summary",
                "warnings",
            ):
                self.assertEqual(before_data[key], after_data[key], key)
            for key in ("coverage_links", "candidate_links", "review_item_ids", "warnings"):
                self.assertEqual(before_candidate.get(key), after_candidate.get(key), key)

    def test_view_export_failure_keeps_saved_json_revision_and_returns_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            form = build_test_input_form(fixture.workspace)
            mode = item_by(form, "input_assignment", "mode")

            with patch(
                "unit_test_runner.test_input_form.service.export_test_spec_snapshot_views",
                side_effect=OSError("view disk unavailable"),
            ):
                result = apply_test_input_form(
                    fixture.workspace,
                    request_for(mode, {"value_expression": "MODE_AUTO"}, False),
                    expected_revision=form.revision,
                )

            saved = load_test_spec_snapshot(fixture.canonical_path, mode=ContractMode.STRICT)
            self.assertEqual(form.revision + 1, saved.spec.revision)
            self.assertEqual(saved.spec.revision, result.revision)
            self.assertFalse(result.views_written)
            self.assertEqual(1, len(result.artifacts))
            self.assertEqual("test_spec", result.artifacts[0].kind)
            self.assertTrue(
                any(warning["code"] == "test_spec_view_export_failed" for warning in result.warnings)
            )


if __name__ == "__main__":
    unittest.main()
