from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.spec_support import write_test_input_form_fixture
from unit_test_runner.test_input_form import TestInputFormError
from unit_test_runner.test_input_form.service import build_test_input_form
from unit_test_runner.test_input_form.validation import (
    c_expression_warnings,
    is_unresolved,
    normalize_c_expression,
    normalize_enum,
    normalize_multiline,
)


class TestInputFormQueryTests(unittest.TestCase):
    def build_fixture(self, root: Path):
        return write_test_input_form_fixture(root)

    def test_extracts_review_and_unresolved_items_and_groups_parent_controls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = self.build_fixture(Path(temp_dir))

            form = build_test_input_form(fixture.workspace)
            cases = {case.case_id: case for case in form.cases or ()}

            self.assertIn(fixture.unresolved_case_id, cases)
            self.assertNotIn(fixture.intentional_candidate_id, cases)
            main = cases[fixture.unresolved_case_id]
            by_kind = {}
            for item in main.items:
                by_kind.setdefault(item.kind, []).append(item)

            mode = next(
                item
                for item in by_kind["input_assignment"]
                if item.label.endswith("mode")
            )
            flags = next(
                item
                for item in by_kind["input_assignment"]
                if item.label.endswith("flags")
            )
            state = by_kind["state_setup"][0]
            execution = by_kind["execution_step"][0]

            self.assertFalse(mode.confirmed)
            self.assertTrue(mode.blocking)
            self.assertTrue(mode.editable)
            self.assertTrue(flags.confirmed)
            self.assertTrue(flags.blocking)
            self.assertTrue(is_unresolved(flags.controls[0].value))
            self.assertEqual(
                ["value_expression", "setup_method_hint"],
                [control.name for control in state.controls],
            )
            self.assertFalse(execution.editable)
            self.assertTrue(
                any(warning["code"] == "invalid_review_required" for warning in execution.warnings)
            )

    def test_summary_counts_unique_item_unions_not_controls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = self.build_fixture(Path(temp_dir))
            form = build_test_input_form(fixture.workspace)
            items = [item for case in form.cases or () for item in case.items]

            unresolved = {
                item.item_id
                for item in items
                if any(
                    control.required_for_confirmation and is_unresolved(control.value)
                    for control in item.controls
                )
            }
            unconfirmed = {item.item_id for item in items if not item.confirmed}
            blocking = {
                item.item_id
                for item in items
                if item.blocking
                and any(
                    control.required_for_confirmation and is_unresolved(control.value)
                    for control in item.controls
                )
            }
            warning = {item.item_id for item in items if item.warnings}
            attention = unresolved | unconfirmed | blocking | warning

            self.assertEqual(len(unresolved), form.summary.unresolved_count)
            self.assertEqual(len(unconfirmed), form.summary.unconfirmed_count)
            self.assertEqual(len(blocking), form.summary.execution_blocking_count)
            self.assertEqual(len(warning), form.summary.warning_count)
            self.assertEqual(len(attention), form.summary.attention_count)
            state = next(item for item in items if item.kind == "state_setup")
            self.assertEqual(2, len(state.controls))
            self.assertEqual(1, sum(item.item_id == state.item_id for item in items))

    def test_summary_only_omits_cases_but_performs_freshness_validation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = self.build_fixture(Path(temp_dir))

            summary = build_test_input_form(fixture.workspace, summary_only=True)

            self.assertIsNone(summary.cases)
            self.assertNotIn("cases", summary.to_dict())
            self.assertGreater(summary.summary.attention_count, 0)

            fixture.source_path.write_text(
                fixture.source_path.read_text(encoding="utf-8") + "/* stale */\n",
                encoding="utf-8",
            )
            with self.assertRaises(TestInputFormError) as raised:
                build_test_input_form(fixture.workspace, summary_only=True)
            self.assertEqual("stale_test_spec", raised.exception.code)

    def test_marks_only_generated_unresolved_main_candidate_as_promotion_eligible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = self.build_fixture(Path(temp_dir))
            form = build_test_input_form(fixture.workspace)

            cases = {case.case_id: case for case in form.cases or ()}
            self.assertTrue(cases[fixture.unresolved_case_id].promotion_eligible)
            self.assertNotIn(fixture.intentional_candidate_id, cases)

    def test_builds_deduplicated_evidence_backed_suggestions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = self.build_fixture(Path(temp_dir))
            form = build_test_input_form(fixture.workspace)
            items = [item for case in form.cases or () for item in case.items]
            inputs = {
                item.label.rsplit(" ", 1)[-1]: item.controls[0]
                for item in items
                if item.kind == "input_assignment"
            }

            mode_values = [item.value for item in inputs["mode"].suggestions]
            flag_values = [item.value for item in inputs["flags"].suggestions]
            buffer_values = [item.value for item in inputs["buffer"].suggestions]

            self.assertIn("MODE_AUTO", mode_values)
            self.assertIn("MODE_MANUAL", mode_values)
            self.assertEqual(1, mode_values.count("MODE_AUTO"))
            self.assertIn("0", flag_values)
            self.assertIn("1", flag_values)
            self.assertIn("NULL", buffer_values)
            for suggestion in (
                *inputs["mode"].suggestions,
                *inputs["flags"].suggestions,
                *inputs["buffer"].suggestions,
            ):
                self.assertTrue(suggestion.source)
                self.assertTrue(suggestion.confidence)

            expected = next(item for item in items if item.kind == "expected_observation")
            self.assertEqual((), expected.controls[0].suggestions)

    def test_validation_normalizes_values_and_returns_advisory_warnings(self):
        self.assertTrue(is_unresolved(None))
        self.assertTrue(is_unresolved("  tBd_value  "))
        self.assertFalse(is_unresolved("MODE_AUTO"))
        self.assertEqual("MODE_AUTO", normalize_c_expression("  MODE_AUTO  "))
        self.assertEqual("line1\nline2\n", normalize_multiline("line1\r\nline2\r"))
        self.assertEqual("stub", normalize_enum("stub", frozenset({"inherit", "real", "stub"})))

        with self.assertRaises(TestInputFormError):
            normalize_c_expression("1\n+ 2")
        with self.assertRaises(TestInputFormError):
            normalize_multiline("x\x00y")
        with self.assertRaises(TestInputFormError):
            normalize_enum("auto", frozenset({"inherit", "real", "stub"}))

        warnings = c_expression_warnings(
            '("text"',
            {"type_category": "scalar", "pointer_level": 0},
            (),
        )
        codes = {warning["code"] for warning in warnings}
        self.assertIn("unbalanced_expression", codes)
        self.assertIn("scalar_string_mismatch", codes)

        pointer_codes = {
            warning["code"]
            for warning in c_expression_warnings(
                "5",
                {"type_category": "pointer", "pointer_level": 1},
                (),
            )
        }
        self.assertIn("pointer_expression_suspect", pointer_codes)

        unknown_codes = {
            warning["code"]
            for warning in c_expression_warnings("UNSEEN_MACRO", None, ())
        }
        self.assertIn("unknown_identifier", unknown_codes)
        self.assertIn("missing_type_evidence", unknown_codes)

        non_c90_codes = {
            warning["code"]
            for warning in c_expression_warnings("true", {"type_category": "scalar"}, ())
        }
        self.assertIn("possible_non_c90_expression", non_c90_codes)


if __name__ == "__main__":
    unittest.main()
