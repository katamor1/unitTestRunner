from __future__ import annotations

import unittest

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


class TestInputFormContractTests(unittest.TestCase):
    def valid_payload(self) -> dict:
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

    def test_parses_valid_request_and_serializes_exact_wire_shape(self):
        request = parse_test_input_change_request(self.valid_payload())

        self.assertIsInstance(request, TestInputChangeRequest)
        self.assertEqual("MODE_AUTO", request.changes[0].values["value_expression"])
        self.assertEqual(self.valid_payload(), request.to_dict())
        with self.assertRaises(TypeError):
            request.changes[0].values["value_expression"] = "OTHER"  # type: ignore[index]

    def test_rejects_unknown_or_missing_properties_at_every_level(self):
        payload = self.valid_payload()
        payload["unexpected"] = True
        with self.assertRaisesRegex(TestInputFormError, "unknown properties"):
            parse_test_input_change_request(payload)

        payload = self.valid_payload()
        del payload["changes"]
        with self.assertRaisesRegex(TestInputFormError, "missing properties"):
            parse_test_input_change_request(payload)

        payload = self.valid_payload()
        payload["changes"][0]["unexpected"] = True
        with self.assertRaisesRegex(TestInputFormError, "unknown properties"):
            parse_test_input_change_request(payload)

        payload = self.valid_payload()
        del payload["changes"][0]["confirmed"]
        with self.assertRaisesRegex(TestInputFormError, "missing properties"):
            parse_test_input_change_request(payload)

    def test_rejects_wrong_version_invalid_identifiers_and_non_array_changes(self):
        payload = self.valid_payload()
        payload["schema_version"] = "1.1"
        with self.assertRaisesRegex(TestInputFormError, "schema_version"):
            parse_test_input_change_request(payload)

        payload = self.valid_payload()
        payload["changes"] = {}
        with self.assertRaisesRegex(TestInputFormError, "changes must be an array"):
            parse_test_input_change_request(payload)

        for field, invalid in (
            ("item_id", "item-not-a-hash"),
            ("subject_fingerprint", "A" * 64),
        ):
            with self.subTest(field=field):
                payload = self.valid_payload()
                payload["changes"][0][field] = invalid
                with self.assertRaises(TestInputFormError):
                    parse_test_input_change_request(payload)

    def test_rejects_duplicate_ids_and_bounded_collection_overflows(self):
        duplicate = self.valid_payload()["changes"][0]
        payload = self.valid_payload()
        payload["changes"].append(dict(duplicate))
        with self.assertRaisesRegex(TestInputFormError, "duplicate item_id"):
            parse_test_input_change_request(payload)

        payload = {"schema_version": "1.0", "changes": []}
        for index in range(1001):
            payload["changes"].append(
                {
                    "item_id": "item-" + f"{index:064x}",
                    "subject_fingerprint": "b" * 64,
                    "values": {},
                    "confirmed": False,
                }
            )
        with self.assertRaisesRegex(TestInputFormError, "at most 1000"):
            parse_test_input_change_request(payload)

        payload = self.valid_payload()
        payload["changes"][0]["values"] = {f"field_{index}": "x" for index in range(17)}
        with self.assertRaisesRegex(TestInputFormError, "at most 16"):
            parse_test_input_change_request(payload)

    def test_rejects_invalid_value_shapes_and_types(self):
        invalid_values = (None, [], {"value_expression": 1}, {"value_expression": None})
        for value in invalid_values:
            with self.subTest(value=value):
                payload = self.valid_payload()
                payload["changes"][0]["values"] = value
                with self.assertRaises(TestInputFormError):
                    parse_test_input_change_request(payload)

        payload = self.valid_payload()
        payload["changes"][0]["confirmed"] = 1
        with self.assertRaisesRegex(TestInputFormError, "confirmed must be a boolean"):
            parse_test_input_change_request(payload)

    def test_rejects_unapproved_control_names(self):
        payload = self.valid_payload()
        payload["changes"][0]["values"] = {"review_item_ids": "forbidden"}
        with self.assertRaisesRegex(TestInputFormError, "editable control"):
            parse_test_input_change_request(payload)

    def test_form_error_codes_are_closed_and_errors_expose_machine_fields(self):
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
        error = TestInputFormError("test_input_validation", "bad expression")
        self.assertEqual("test_input_validation", error.code)
        self.assertEqual("bad expression", error.message)
        self.assertEqual("bad expression", str(error))
        with self.assertRaises(ValueError):
            TestInputFormError("made_up", "bad")

    def test_output_models_serialize_to_the_transient_form_contract(self):
        suggestion = FormSuggestion("MODE_AUTO", "MODE_AUTO", "boundary_candidate", "high")
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
            warnings=({"code": "placeholder", "severity": "warning", "message": "入力が必要です。"},),
        )
        case = FormCase("TC_Control_Update_001", "additional_case_candidates", True, (item,))
        summary = FormSummary(1, 1, 1, 1, 1)
        document = TestInputFormDocument(3, "c" * 64, "Control_Update", summary, (case,))

        payload = document.to_dict()
        self.assertEqual("1.0", payload["schema_version"])
        self.assertEqual({"name": "Control_Update"}, payload["function"])
        self.assertEqual("TBD_VALID_VALUE", payload["cases"][0]["items"][0]["controls"][0]["value"])
        self.assertEqual([], payload["cases"][0]["items"][0]["controls"][0]["enum_values"])

        summary_only = TestInputFormDocument(3, "c" * 64, "Control_Update", summary, None).to_dict()
        self.assertNotIn("cases", summary_only)


class TestInputFieldCatalogTests(unittest.TestCase):
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
        self.assertEqual(
            frozenset({"inherit", "real", "stub"}),
            FIELD_RULES["dependency_overrides"].controls[0].enum_values,
        )

    def test_catalog_total_functions_cover_dynamic_required_and_execution_rules(self):
        dependency = FIELD_RULES["dependency_overrides"]
        mode, rationale = dependency.controls
        self.assertTrue(required_for_confirmation(dependency, mode, {"mode": "inherit"}))
        self.assertFalse(required_for_confirmation(dependency, rationale, {"mode": "inherit"}))
        self.assertTrue(required_for_confirmation(dependency, rationale, {"mode": "real"}))
        self.assertTrue(required_for_confirmation(dependency, rationale, {"mode": "stub"}))

        stub = FIELD_RULES["stub_setups"]
        value_control = stub.controls[0]
        self.assertFalse(required_for_confirmation(stub, value_control, {"setup_kind": "argument_capture"}))
        self.assertFalse(execution_value_required(stub, {"setup_kind": "call_count_observation"}))
        self.assertFalse(execution_value_required(stub, {"setup_kind": "argument_capture"}))
        self.assertTrue(execution_value_required(stub, {"setup_kind": "return_value"}))

        for rule in FIELD_RULES.values():
            with self.subTest(collection=rule.collection):
                parent = self._sample_parent(rule.collection)
                self.assertIsInstance(label_for_parent(rule, parent), str)
                self.assertTrue(label_for_parent(rule, parent))
                self.assertEqual(
                    frozenset(control.name for control in rule.controls),
                    editable_control_names(rule),
                )
                for control in rule.controls:
                    self.assertIsInstance(required_for_confirmation(rule, control, parent), bool)
                self.assertIsInstance(execution_value_required(rule, parent), bool)

    def test_catalog_does_not_expose_identity_provenance_or_review_authority(self):
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
            "warnings",
            "candidate_id",
            "call_id",
            "related_call_id",
            "source_candidate_id",
        }
        editable = frozenset(
            name
            for rule in FIELD_RULES.values()
            for name in editable_control_names(rule)
        )
        self.assertTrue(forbidden.isdisjoint(editable))

    @staticmethod
    def _sample_parent(collection: str) -> dict:
        return {
            "input_assignments": {"target_kind": "parameter", "target_name": "mode"},
            "state_setups": {"scope": "global", "variable_name": "g_mode"},
            "stub_setups": {"stub_name": "ReadSensor", "setup_kind": "return_value"},
            "expected_observations": {"observation_kind": "return_value", "target_name": "return"},
            "preconditions": {"source": "build_context"},
            "execution_steps": {"order": 1, "action": "setup_state"},
            "dependency_overrides": {"callee": "ReadSensor", "mode": "inherit"},
        }[collection]


if __name__ == "__main__":
    unittest.main()
