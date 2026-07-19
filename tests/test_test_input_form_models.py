from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from unit_test_runner.test_input_form import (
    FIELD_RULES,
    FORM_ERROR_CODES,
    FormCase,
    FormControl,
    FormItem,
    FormSuggestion,
    FormSummary,
    TestInputChangeRequest,
    TestInputFormDocument,
    TestInputFormError,
    editable_control_names,
    execution_value_required,
    label_for_parent,
    parse_test_input_change_request,
    required_for_confirmation,
)


class TestInputFormModelTests(unittest.TestCase):
    def valid_request(self) -> dict:
        return {
            "schema_version": "1.0",
            "changes": [
                {
                    "item_id": "item-" + "a" * 64,
                    "subject_fingerprint": "b" * 64,
                    "values": {"value_expression": "MODE_AUTO"},
                    "confirmed": True,
                }
            ],
        }

    def test_parses_a_valid_strict_request_and_freezes_values(self):
        request = parse_test_input_change_request(self.valid_request())

        self.assertIsInstance(request, TestInputChangeRequest)
        self.assertEqual("1.0", request.schema_version)
        self.assertEqual("MODE_AUTO", request.changes[0].values["value_expression"])
        with self.assertRaises(TypeError):
            request.changes[0].values["value_expression"] = "MODE_MANUAL"  # type: ignore[index]

    def test_rejects_extra_or_missing_properties_and_wrong_schema(self):
        invalid_values = []
        extra = self.valid_request()
        extra["unexpected"] = True
        invalid_values.append(extra)
        missing = self.valid_request()
        del missing["changes"]
        invalid_values.append(missing)
        wrong_schema = self.valid_request()
        wrong_schema["schema_version"] = "1.1"
        invalid_values.append(wrong_schema)
        extra_change = self.valid_request()
        extra_change["changes"][0]["unexpected"] = "x"
        invalid_values.append(extra_change)
        missing_change = self.valid_request()
        del missing_change["changes"][0]["confirmed"]
        invalid_values.append(missing_change)

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(TestInputFormError) as caught:
                parse_test_input_change_request(value)
            self.assertEqual("test_input_form_invalid", caught.exception.code)

    def test_rejects_invalid_ids_hashes_duplicates_and_limits(self):
        invalid_item = self.valid_request()
        invalid_item["changes"][0]["item_id"] = "item-not-a-digest"
        invalid_fingerprint = self.valid_request()
        invalid_fingerprint["changes"][0]["subject_fingerprint"] = "B" * 64
        duplicate = self.valid_request()
        duplicate["changes"].append(dict(duplicate["changes"][0]))
        too_many_changes = {"schema_version": "1.0", "changes": []}
        for index in range(1001):
            too_many_changes["changes"].append(
                {
                    "item_id": "item-" + f"{index:064x}",
                    "subject_fingerprint": "c" * 64,
                    "values": {},
                    "confirmed": False,
                }
            )
        too_many_leaves = self.valid_request()
        too_many_leaves["changes"][0]["values"] = {
            f"field_{index}": "x" for index in range(17)
        }

        for value in (
            invalid_item,
            invalid_fingerprint,
            duplicate,
            too_many_changes,
            too_many_leaves,
        ):
            with self.subTest(kind=type(value)), self.assertRaises(TestInputFormError) as caught:
                parse_test_input_change_request(value)
            self.assertEqual("test_input_form_invalid", caught.exception.code)

    def test_rejects_nonboolean_confirmation_invalid_leaf_names_and_value_types(self):
        nonboolean = self.valid_request()
        nonboolean["changes"][0]["confirmed"] = 1
        invalid_leaf = self.valid_request()
        invalid_leaf["changes"][0]["values"] = {"../value_expression": "0"}
        invalid_values = []
        for invalid in (1, True, [], {}, object()):
            value = self.valid_request()
            value["changes"][0]["values"] = {"value_expression": invalid}
            invalid_values.append(value)

        for value in (nonboolean, invalid_leaf, *invalid_values):
            with self.subTest(value=value), self.assertRaises(TestInputFormError):
                parse_test_input_change_request(value)

    def test_accepts_empty_changes_and_nullable_leaf_values(self):
        empty = parse_test_input_change_request(
            {"schema_version": "1.0", "changes": []}
        )
        nullable = self.valid_request()
        nullable["changes"][0]["values"] = {"note": None}

        self.assertEqual((), empty.changes)
        self.assertIsNone(
            parse_test_input_change_request(nullable).changes[0].values["note"]
        )

    def test_error_contract_uses_only_approved_machine_codes(self):
        self.assertEqual(
            {
                "test_input_form_invalid",
                "test_input_revision_conflict",
                "test_input_subject_conflict",
                "test_input_validation",
                "stale_test_spec",
            },
            set(FORM_ERROR_CODES),
        )
        error = TestInputFormError("test_input_validation", "bad input")
        self.assertEqual("test_input_validation", error.code)
        self.assertEqual("bad input", error.message)
        self.assertEqual("bad input", str(error))
        with self.assertRaises(ValueError):
            TestInputFormError("unknown", "bad input")

    def test_output_models_are_frozen_and_serialize_exact_wire_shape(self):
        suggestion = FormSuggestion("MODE_AUTO", "Automatic", "boundary", "high")
        control = FormControl(
            name="value_expression",
            control_kind="c_expression",
            required_for_confirmation=True,
            value="TBD_VALID_VALUE",
            suggestions=(suggestion,),
        )
        item = FormItem(
            item_id="item-" + "a" * 64,
            subject_fingerprint="b" * 64,
            kind="input_assignment",
            label="引数 mode",
            confirmed=False,
            blocking=True,
            editable=True,
            controls=(control,),
            warnings=({"code": "unresolved", "message": "value required"},),
        )
        case = FormCase(
            case_id="TC_Control_Update_001",
            location="additional_case_candidates",
            promotion_eligible=True,
            items=(item,),
        )
        summary = FormSummary(1, 1, 1, 1, 1)
        document = TestInputFormDocument(
            revision=3,
            spec_sha256="c" * 64,
            function_name="Control_Update",
            summary=summary,
            cases=(case,),
        )

        payload = document.to_dict()

        self.assertEqual(
            {
                "schema_version",
                "revision",
                "spec_sha256",
                "function",
                "summary",
                "cases",
            },
            set(payload),
        )
        self.assertEqual({"name": "Control_Update"}, payload["function"])
        self.assertEqual("MODE_AUTO", payload["cases"][0]["items"][0]["controls"][0]["suggestions"][0]["value"])
        self.assertEqual((), FormControl("mode", "enum", True, "inherit").enum_values)
        with self.assertRaises(FrozenInstanceError):
            document.revision = 4  # type: ignore[misc]
        with self.assertRaises(TypeError):
            item.warnings[0]["code"] = "changed"  # type: ignore[index]

        summary_only = TestInputFormDocument(
            revision=3,
            spec_sha256="c" * 64,
            function_name="Control_Update",
            summary=summary,
            cases=None,
        ).to_dict()
        self.assertNotIn("cases", summary_only)


class FieldCatalogTests(unittest.TestCase):
    def test_catalog_exposes_exact_approved_collections_and_controls(self):
        self.assertEqual(
            {
                "input_assignments": ("value_expression",),
                "state_setups": ("value_expression", "setup_method_hint"),
                "stub_setups": ("value_expression", "call_behavior"),
                "expected_observations": ("expected_expression", "note"),
                "preconditions": ("description",),
                "execution_steps": ("detail",),
                "dependency_overrides": ("mode", "rationale"),
            },
            {
                collection: tuple(control.name for control in rule.controls)
                for collection, rule in FIELD_RULES.items()
            },
        )

    def test_catalog_never_exposes_identity_provenance_or_review_authority(self):
        forbidden = {
            "test_case_id",
            "spec_id",
            "revision",
            "schema_version",
            "source",
            "function",
            "generated_from",
            "coverage_links",
            "candidate_links",
            "review_item_ids",
            "review_status",
            "review_decision",
            "candidate_id",
            "call_id",
            "warnings",
            "evidence",
        }
        editable = {
            name
            for rule in FIELD_RULES.values()
            for name in editable_control_names(rule)
        }
        self.assertTrue(forbidden.isdisjoint(editable))

    def test_dependency_mode_enum_and_dynamic_rationale_requirement(self):
        rule = FIELD_RULES["dependency_overrides"]
        controls = {control.name: control for control in rule.controls}

        self.assertEqual(("inherit", "real", "stub"), controls["mode"].enum_values)
        self.assertTrue(required_for_confirmation(rule, controls["mode"], {"mode": "inherit"}))
        self.assertFalse(required_for_confirmation(rule, controls["rationale"], {"mode": "inherit"}))
        self.assertTrue(required_for_confirmation(rule, controls["rationale"], {"mode": "real"}))
        self.assertTrue(required_for_confirmation(rule, controls["rationale"], {"mode": "stub"}))

    def test_stub_execution_requirement_is_total_and_setup_kind_sensitive(self):
        rule = FIELD_RULES["stub_setups"]
        self.assertFalse(execution_value_required(rule, {"setup_kind": "call_count_observation"}))
        self.assertFalse(execution_value_required(rule, {"setup_kind": "argument_capture"}))
        self.assertTrue(execution_value_required(rule, {"setup_kind": "return_value"}))
        self.assertTrue(execution_value_required(rule, {}))

    def test_every_catalog_rule_has_total_required_execution_label_and_editable_contracts(self):
        parents = {
            "input_assignments": {"target_name": "mode", "target_kind": "parameter"},
            "state_setups": {"variable_name": "g_state", "scope": "global"},
            "stub_setups": {"stub_name": "ReadSensor", "setup_kind": "return_value"},
            "expected_observations": {"target_name": "return", "observation_kind": "return_value"},
            "preconditions": {"source": "build_context"},
            "execution_steps": {"order": 1, "action": "call_function"},
            "dependency_overrides": {"callee": "ReadSensor", "mode": "inherit"},
        }
        expected_execution = {
            "input_assignments": True,
            "state_setups": True,
            "stub_setups": True,
            "expected_observations": True,
            "preconditions": False,
            "execution_steps": False,
            "dependency_overrides": False,
        }

        for collection, rule in FIELD_RULES.items():
            parent = parents[collection]
            with self.subTest(collection=collection):
                self.assertEqual(expected_execution[collection], execution_value_required(rule, parent))
                self.assertTrue(label_for_parent(rule, parent))
                self.assertEqual(
                    frozenset(control.name for control in rule.controls),
                    editable_control_names(rule),
                )
                for control in rule.controls:
                    self.assertIsInstance(
                        required_for_confirmation(rule, control, parent), bool
                    )


if __name__ == "__main__":
    unittest.main()
