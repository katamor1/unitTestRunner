from __future__ import annotations

import importlib
import importlib.util
import unittest
from unittest import mock

from unit_test_runner.test_spec.identity import stable_function_id


class HostileString(str):
    def __contains__(self, _item):
        return False

    def replace(self, *_args, **_kwargs):
        return "src/attacker.c"

    def strip(self, *_args, **_kwargs):
        return "attacker"

    def lower(self):
        return "attacker"

    def encode(self, *_args, **_kwargs):
        return b"attacker"


class ReviewDecisionIdentityTests(unittest.TestCase):
    @staticmethod
    def module():
        return importlib.import_module("unit_test_runner.review_ids")

    def test_public_review_id_module_is_discoverable(self):
        self.assertIsNotNone(
            importlib.util.find_spec("unit_test_runner.review_ids")
        )

    def test_function_id_literal_vectors_and_legacy_delegation(self):
        review_ids = self.module()
        vectors = (
            ("src\\制御.c", "Control_Update", "fn_control_update_84fcdd81a442"),
            ("src/./制御.c", "Control_Update", "fn_control_update_84fcdd81a442"),
            ("src/control.c", "Control_Update", "fn_control_update_cdd351ecf31d"),
            ("src/control.c", "control_update", "fn_control_update_b0fd58394269"),
            ("src/control.c", "制御", "fn_function_bbf8b675d675"),
        )

        for source_path, function_name, expected in vectors:
            with self.subTest(source_path=source_path, function_name=function_name):
                self.assertEqual(
                    expected,
                    review_ids.build_function_id(source_path, function_name),
                )
                self.assertEqual(
                    expected,
                    stable_function_id(source_path, function_name),
                )

    def test_function_id_rejects_noncanonical_or_non_utf8_inputs(self):
        build = self.module().build_function_id
        invalid_paths = (
            "",
            "/src/control.c",
            "\\\\server\\share\\control.c",
            "C:/src/control.c",
            "./D:/src/control.c",
            "src/../control.c",
            "src/\x00control.c",
            1,
            "src/\ud800.c",
        )
        invalid_names = ("", "  ", "Control\x00Update", 1, "\ud800")

        for value in invalid_paths:
            with self.subTest(path=repr(value)):
                with self.assertRaises((TypeError, ValueError, UnicodeError)):
                    build(value, "Control_Update")
        for value in invalid_names:
            with self.subTest(name=repr(value)):
                with self.assertRaises((TypeError, ValueError, UnicodeError)):
                    build("src/control.c", value)

    def test_public_builders_reject_string_subclasses_before_invoking_them(self):
        review_ids = self.module()
        for label, source_path, function_name in (
            ("function path", HostileString("src/control.c"), "Control_Update"),
            ("function name", "src/control.c", HostileString("Control_Update")),
        ):
            with self.subTest(label=label):
                with self.assertRaises(TypeError):
                    review_ids.build_function_id(source_path, function_name)
                with self.assertRaises(TypeError):
                    stable_function_id(source_path, function_name)

        valid = [
            "expected_result_review",
            "fn_control_update_cdd351ecf31d",
            "TC-01",
            "expected_return_unknown",
        ]
        for index, label in enumerate(
            ("category", "function_id", "case_id", "semantic_subject_key")
        ):
            with self.subTest(label=label):
                values = list(valid)
                values[index] = HostileString(values[index])
                with self.assertRaises(TypeError):
                    review_ids.build_review_id(*values)

    def test_review_id_literal_vectors(self):
        build = self.module().build_review_id

        self.assertEqual(
            "review-expected-result-93cdf75d71c9e7d5",
            build(
                " expected＿result ",
                "Control_Update",
                "TC-01",
                " return／value ",
            ),
        )
        self.assertEqual(
            "review-expected-result-08d00d45f722bfbe",
            build(
                "expected-result",
                "control_update",
                "TC-01",
                "return/value",
            ),
        )
        self.assertEqual(
            "review-review-cce6c22d9cd872b6",
            build(" 検査 ", "fn_制御_abcdef", " TC－01 ", " 境界 値 "),
        )

    def test_review_id_normalization_case_and_subject_semantics(self):
        build = self.module().build_review_id
        normalized = build(
            " expected＿result ",
            " Control_Update ",
            " TC－01 ",
            " return／value ",
        )
        equivalent = build(
            "expected/result",
            "Control_Update",
            "TC-01",
            "return/value",
        )

        self.assertEqual(normalized, equivalent)
        self.assertNotEqual(
            equivalent,
            build("expected/result", "control_update", "TC-01", "return/value"),
        )
        self.assertNotEqual(
            equivalent,
            build("expected/result", "Control_Update", "TC-01", "global/value"),
        )

    def test_semantic_case_id_token_matches_review_id_case_semantics(self):
        semantic_token = self.module().semantic_case_id_token
        expected = semantic_token("TC-01")

        self.assertEqual("TC/01", expected)
        for value in (" TC-01 ", "TC－01", "TC_01"):
            with self.subTest(value=value):
                self.assertEqual(expected, semantic_token(value))

    def test_review_id_none_case_is_distinct_and_blank_case_is_rejected(self):
        build = self.module().build_review_id
        without_case = build(
            "evidence_review",
            "fn_control_update_cdd351ecf31d",
            None,
            "final_dossier_review",
        )
        with_case = build(
            "evidence_review",
            "fn_control_update_cdd351ecf31d",
            "TC-01",
            "final_dossier_review",
        )

        self.assertNotEqual(without_case, with_case)
        with self.assertRaises(ValueError):
            build(
                "evidence_review",
                "fn_control_update_cdd351ecf31d",
                " ＿ ",
                "final_dossier_review",
            )

    def test_review_id_rejects_type_nul_and_non_utf8_inputs(self):
        build = self.module().build_review_id
        valid = (
            "expected_result_review",
            "fn_control_update_cdd351ecf31d",
            "TC-01",
            "expected_return_unknown",
        )
        mutations = (
            (0, ""),
            (0, 1),
            (1, None),
            (1, "fn\x00bad"),
            (2, 1),
            (3, "\ud800"),
            (3, "semantic\x00subject"),
        )

        for index, value in mutations:
            with self.subTest(index=index, value=repr(value)):
                args = list(valid)
                args[index] = value
                with self.assertRaises((TypeError, ValueError, UnicodeError)):
                    build(*args)

    def test_registry_normalizes_keys_and_raises_typed_collision(self):
        review_ids = self.module()
        registry = review_ids.StableReviewIdRegistry()
        first = registry.register(
            category=" expected＿result ",
            function_id=" Control_Update ",
            case_id=" TC－01 ",
            semantic_subject_key=" return／value ",
        )
        equivalent = registry.register(
            category="expected/result",
            function_id="Control_Update",
            case_id="TC-01",
            semantic_subject_key="return/value",
        )
        self.assertEqual(first, equivalent)

        with mock.patch.object(
            review_ids,
            "build_review_id",
            return_value="review-forced-collision",
        ):
            collision_registry = review_ids.StableReviewIdRegistry()
            collision_registry.register(
                category="category-a",
                function_id="fn-a",
                case_id=None,
                semantic_subject_key="subject-a",
            )
            with self.assertRaises(review_ids.ReviewIdCollisionError) as raised:
                collision_registry.register(
                    category="category-b",
                    function_id="fn-a",
                    case_id=None,
                    semantic_subject_key="subject-b",
                )
            self.assertEqual(
                "review-forced-collision",
                collision_registry.register(
                    category="category-a",
                    function_id="fn-a",
                    case_id=None,
                    semantic_subject_key="subject-a",
                ),
            )

        error = raised.exception
        self.assertEqual("review-forced-collision", error.review_id)
        self.assertIsInstance(error.existing_key, review_ids.ReviewSemanticKey)
        self.assertIsInstance(error.candidate_key, review_ids.ReviewSemanticKey)
        self.assertNotEqual(error.existing_key, error.candidate_key)


if __name__ == "__main__":
    unittest.main()
