from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.contracts import (
    ArtifactKind,
    load_artifact,
    validate_payload,
    validate_payload_schema,
)
from unit_test_runner.contracts.registry import get_contract, iter_contract_versions
from unit_test_runner.test_spec import (
    ArtifactReference,
    CurrentArtifactContext,
    SourceReference,
    TestSpec,
    TestSpecContractError,
    create_test_spec_from_design,
    validate_test_spec,
)
from unit_test_runner.dossier.review_workflow import build_review_items

from tests.spec_support import copied_payload, current_context


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


class HostileList(list):
    pass


class BenignList(list):
    pass


class BenignDict(dict):
    pass


class ExplodingBoolDict(dict):
    def __bool__(self):
        raise RuntimeError("dict subclass truthiness must not run")


class ExplodingIterList(list):
    def __iter__(self):
        raise RuntimeError("list subclass iterator must not run")


class ExplodingDeepcopyString(str):
    def __deepcopy__(self, _memo):
        raise RuntimeError("scalar deepcopy hook must not run")


class CoercingString(str):
    def __str__(self):
        return "tc-control-update-001"


class CoercingCurrentVersionString(str):
    def __str__(self):
        return "1.1.0"


class CoercingShaString(str):
    def __str__(self):
        return "a" * 64


class ExplodingString(str):
    def __str__(self):
        raise RuntimeError("test_case_id coercion must not run")


class ExplodingHashString(str):
    def __hash__(self):
        raise RuntimeError("semantic identifier hashing must not run")

    def __eq__(self, _other):
        raise RuntimeError("semantic identifier equality must not run")


class ExplodingReplaceString(str):
    def replace(self, *_args, **_kwargs):
        raise RuntimeError("semantic path replacement must not run")


class ExplodingEqualityString(str):
    __hash__ = str.__hash__

    def __eq__(self, _other):
        raise RuntimeError("semantic equality must not run")


class ExplodingBoolString(str):
    def __bool__(self):
        raise RuntimeError("semantic truthiness must not run")


class CoercingInt(int):
    def __int__(self):
        return 1


class TestSpecContractTests(unittest.TestCase):
    @staticmethod
    def minimal_design(case_id="TC-01"):
        return {
            "generation_policy": {},
            "test_cases": [],
            "additional_case_candidates": [
                {
                    "test_case_id": case_id,
                    "coverage_links": [{"coverage_id": "COV-01"}],
                }
            ],
            "coverage_summary": {
                "total_coverage_items": 1,
                "covered_by_design_count": 1,
                "uncovered_coverage_ids": [],
                "coverage_to_test_cases": {"COV-01": [case_id]},
            },
            "unresolved_items": [],
            "warnings": [],
        }

    def test_generation_rejects_coerced_function_and_case_identity(self):
        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        with self.assertRaises(TypeError):
            create_test_spec_from_design(
                self.minimal_design(),
                {
                    "source": {"path": "src/control.c", "sha256": "1" * 64},
                    "function": {"name": 7},
                },
                source_path="src/control.c",
                generated_from=[reference],
            )

        for value in (
            7,
            HostileString("TC-01"),
            "TC\x00-01",
            "TC-\ud800",
        ):
            with self.subTest(candidate_case_id=repr(value)):
                with self.assertRaises((TypeError, ValueError, UnicodeError)):
                    create_test_spec_from_design(
                        self.minimal_design(case_id=value),
                        {
                            "source": {
                                "path": "src/control.c",
                                "sha256": "1" * 64,
                            },
                            "function": {"name": "Control_Update"},
                        },
                        source_path="src/control.c",
                        generated_from=[reference],
                    )

    def test_generation_rejects_coerced_source_sha_before_construction(self):
        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        signature_shapes = (
            (
                "legacy_flat",
                lambda source_sha: {
                    "source": {
                        "path": "src/control.c",
                        "sha256": source_sha,
                    },
                    "function": {"name": "Control_Update"},
                },
            ),
            (
                "current_envelope",
                lambda source_sha: {
                    "data": {
                        "source": {
                            "path": "src/control.c",
                            "sha256": source_sha,
                        },
                        "function": {"name": "Control_Update"},
                    }
                },
            ),
        )
        for shape, build_signature in signature_shapes:
            for source_sha in (
                CoercingShaString("attacker-controlled-sha"),
                ExplodingString("attacker-controlled-sha"),
            ):
                with self.subTest(shape=shape, source_sha=type(source_sha).__name__):
                    with self.assertRaises(TypeError):
                        create_test_spec_from_design(
                            self.minimal_design(),
                            build_signature(source_sha),
                            source_path="src/control.c",
                            generated_from=[reference],
                        )

    def test_generation_rejects_malformed_optional_fields_before_operations(self):
        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        signature = {
            "source": {"path": "src/control.c", "sha256": "1" * 64},
            "function": {"name": "Control_Update"},
        }
        for field in (
            "test_cases",
            "additional_case_candidates",
            "unresolved_items",
            "warnings",
        ):
            design = self.minimal_design()
            design[field] = 7
            with self.subTest(field=field):
                with self.assertRaises(TypeError) as raised:
                    create_test_spec_from_design(
                        design,
                        signature,
                        source_path="src/control.c",
                        generated_from=[reference],
                    )
                self.assertEqual(
                    f"test design {field} must be a list.",
                    str(raised.exception),
                )

        design = self.minimal_design()
        design["additional_case_candidates"][0]["review_status"] = []
        with self.assertRaises(TypeError) as raised:
            create_test_spec_from_design(
                design,
                signature,
                source_path="src/control.c",
                generated_from=[reference],
            )
        self.assertEqual(
            "review_status must be an exact string or null.",
            str(raised.exception),
        )

        malformed_source = {
            "source": ["not", "an", "object"],
            "function": {"name": "Control_Update"},
        }
        with self.assertRaises(TypeError) as raised:
            create_test_spec_from_design(
                self.minimal_design(),
                malformed_source,
                source_path="src/control.c",
                generated_from=[reference],
            )
        self.assertEqual(
            "Function signature source must be an object.",
            str(raised.exception),
        )

    def test_generation_rejects_string_subclass_semantic_inputs(self):
        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        with self.assertRaises(TypeError):
            create_test_spec_from_design(
                self.minimal_design(),
                {
                    "source": {"path": "src/control.c", "sha256": "1" * 64},
                    "function": {"name": HostileString("Control_Update")},
                },
                source_path="src/control.c",
                generated_from=[reference],
            )

        for field, value in (
            ("item_kind", HostileString("expected_return_unknown")),
            ("related_case", HostileString("TC-01")),
        ):
            with self.subTest(field=field):
                design = self.minimal_design()
                design["unresolved_items"] = [
                    {
                        "item_id": "RAW_001",
                        "item_kind": (
                            value
                            if field == "item_kind"
                            else "expected_return_unknown"
                        ),
                        "related_test_case_ids": [
                            value if field == "related_case" else "TC-01"
                        ],
                    }
                ]
                with self.assertRaises(TypeError):
                    create_test_spec_from_design(
                        design,
                        {
                            "source": {
                                "path": "src/control.c",
                                "sha256": "1" * 64,
                            },
                            "function": {"name": "Control_Update"},
                        },
                        source_path="src/control.c",
                        generated_from=[reference],
                    )

    def test_related_case_collection_has_one_exact_shared_semantic_contract(self):
        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        signature = {
            "source": {"path": "src/control.c", "sha256": "1" * 64},
            "function": {"name": "Control_Update"},
        }
        expected_by_shape = {}
        for label, related in (("missing", None), ("empty", []), ("case", ["TC-01"])):
            with self.subTest(valid_shape=label):
                design = self.minimal_design()
                unresolved = {
                    "item_id": "RAW_001",
                    "item_kind": "expected_return_unknown",
                }
                if related is not None:
                    unresolved["related_test_case_ids"] = related
                design["unresolved_items"] = [unresolved]
                spec = create_test_spec_from_design(
                    design,
                    signature,
                    source_path="src/control.c",
                    generated_from=[reference],
                )
                dossier_items, _ = build_review_items(
                    {"test_spec": spec.to_payload()["data"]}
                )
                self.assertEqual(
                    spec.review_item_ids,
                    [item.review_id for item in dossier_items],
                )
                expected_by_shape[label] = spec.review_item_ids
        self.assertEqual(expected_by_shape["missing"], expected_by_shape["empty"])
        self.assertNotEqual(expected_by_shape["empty"], expected_by_shape["case"])

        malformed_values = (
            None,
            "TC-01",
            ("TC-01",),
            HostileList(["TC-01"]),
            ["TC-01", 7],
            [""],
            ["TC\x00-01"],
            ["TC-\ud800"],
            [HostileString("TC-01")],
        )
        for related in malformed_values:
            with self.subTest(malformed=repr(related)):
                design = self.minimal_design()
                design["unresolved_items"] = [
                    {
                        "item_id": "RAW_001",
                        "item_kind": "expected_return_unknown",
                        "related_test_case_ids": related,
                    }
                ]
                with self.assertRaises((TypeError, ValueError, UnicodeError)):
                    create_test_spec_from_design(
                        design,
                        signature,
                        source_path="src/control.c",
                        generated_from=[reference],
                    )

                payload = {
                    "function": {
                        "function_id": "fn_control_update_cdd351ecf31d",
                        "name": "Control_Update",
                    },
                    "source": {"path": "src/control.c"},
                    "unresolved_items": [
                        {
                            "item_kind": "expected_return_unknown",
                            "related_test_case_ids": related,
                        }
                    ],
                    "test_cases": [],
                }
                with self.assertRaises((TypeError, ValueError, UnicodeError)):
                    build_review_items({"test_spec": payload})

    def test_equivalent_related_case_spellings_bind_to_exact_candidate(self):
        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        signature = {
            "source": {"path": "src/control.c", "sha256": "1" * 64},
            "function": {"name": "Control_Update"},
        }
        observed_review_ids = set()
        for label, related_case_id in (
            ("outer_whitespace", " TC-01 "),
            ("nfkc_fullwidth_hyphen", "TC－01"),
            ("separator_equivalent", "TC_01"),
        ):
            with self.subTest(spelling=label):
                design = self.minimal_design()
                design["unresolved_items"] = [
                    {
                        "item_id": "RAW_001",
                        "item_kind": "expected_return_unknown",
                        "related_test_case_ids": [related_case_id],
                    }
                ]
                spec = create_test_spec_from_design(
                    design,
                    signature,
                    source_path="src/control.c",
                    generated_from=[reference],
                )

                self.assertEqual(1, len(spec.review_item_ids))
                self.assertEqual(
                    spec.review_item_ids,
                    spec.additional_case_candidates[0]["review_item_ids"],
                )
                self.assertEqual(
                    ["TC-01"],
                    spec.unresolved_items[0]["related_test_case_ids"],
                )
                observed_review_ids.add(tuple(spec.review_item_ids))

        self.assertEqual(1, len(observed_review_ids))

    def test_equivalent_related_case_spellings_cannot_bypass_executable_blocker(self):
        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        signature = {
            "source": {"path": "src/control.c", "sha256": "1" * 64},
            "function": {"name": "Control_Update"},
        }
        for label, related_case_id in (
            ("outer_whitespace", " TC-01 "),
            ("nfkc_fullwidth_hyphen", "TC－01"),
            ("separator_equivalent", "TC_01"),
        ):
            with self.subTest(spelling=label):
                design = self.minimal_design()
                executable = design["additional_case_candidates"].pop()
                executable["expected_observations"] = [
                    {
                        "observation_kind": "return_value",
                        "expected_expression": "0",
                    }
                ]
                design["test_cases"] = [executable]
                design["unresolved_items"] = [
                    {
                        "item_id": "RAW_001",
                        "item_kind": "expected_return_unknown",
                        "related_test_case_ids": [related_case_id],
                    }
                ]

                with self.assertRaises(TestSpecContractError) as raised:
                    create_test_spec_from_design(
                        design,
                        signature,
                        source_path="src/control.c",
                        generated_from=[reference],
                    )
                self.assertIn(
                    "blocking_unresolved_executable",
                    {item.code for item in raised.exception.violations},
                )

    def test_generation_rejects_ambiguous_normalized_case_spellings(self):
        design = self.minimal_design()
        design["additional_case_candidates"].append(
            {
                "test_case_id": "TC_01",
                "coverage_links": [{"coverage_id": "COV-01"}],
            }
        )

        with self.assertRaisesRegex(ValueError, "Ambiguous test case IDs"):
            create_test_spec_from_design(
                design,
                {
                    "source": {"path": "src/control.c", "sha256": "1" * 64},
                    "function": {"name": "Control_Update"},
                },
                source_path="src/control.c",
                generated_from=[
                    ArtifactReference(
                        "function_signature",
                        "reports/function_signature.json",
                        "3" * 64,
                    )
                ],
            )

    def test_direct_load_blocks_semantically_equivalent_executable_references(self):
        for label, related_case_id in (
            ("outer_whitespace", " tc-control-update-001 "),
            ("nfkc_fullwidth_hyphen", "tc－control-update-001"),
            ("separator_equivalent", "tc_control-update-001"),
        ):
            with self.subTest(spelling=label):
                payload = copied_payload()
                payload["data"]["unresolved_items"] = [
                    {
                        "item_id": "review-semantic-blocking-001",
                        "severity": "blocking",
                        "related_test_case_ids": [related_case_id],
                    }
                ]
                payload["data"]["review_item_ids"].append(
                    "review-semantic-blocking-001"
                )

                with self.assertRaises(TestSpecContractError) as raised:
                    TestSpec.from_payload(payload)
                self.assertIn(
                    "blocking_unresolved_executable",
                    {item.code for item in raised.exception.violations},
                )

    def test_direct_load_rejects_semantically_duplicate_actual_case_ids_in_both_orders(self):
        for label, alternate_case_id in (
            ("outer_whitespace", " tc-control-update-001 "),
            ("nfkc_fullwidth_hyphen", "tc－control-update-001"),
            ("separator_equivalent", "tc_control-update-001"),
        ):
            for exact_collection in ("test_cases", "additional_case_candidates"):
                with self.subTest(
                    spelling=label,
                    exact_collection=exact_collection,
                ):
                    payload = copied_payload()
                    executable = payload["data"]["test_cases"][0]
                    candidate = dict(executable)
                    if exact_collection == "test_cases":
                        candidate["test_case_id"] = alternate_case_id
                    else:
                        executable["test_case_id"] = alternate_case_id
                    payload["data"]["additional_case_candidates"] = [candidate]

                    with self.assertRaises(TestSpecContractError) as raised:
                        TestSpec.from_payload(payload)
                    self.assertIn(
                        "duplicate_semantic_case_id",
                        {item.code for item in raised.exception.violations},
                    )

    def test_strict_unresolved_item_semantics_reject_malformed_fields_independent_of_blocking(self):
        malformed = (
            (
                "missing_item_kind",
                {"severity": "blocking"},
                "required_property",
            ),
            (
                "item_kind_string_subclass",
                {"item_kind": HostileString("expected_return_unknown")},
                "invalid_unresolved_item_kind",
            ),
            (
                "item_kind_empty",
                {"item_kind": ""},
                "invalid_unresolved_item_kind",
            ),
            (
                "item_kind_separator_only",
                {"item_kind": " _/ "},
                "invalid_unresolved_item_kind",
            ),
            (
                "item_kind_nul",
                {"item_kind": "expected\x00return"},
                "invalid_unresolved_item_kind",
            ),
            (
                "item_kind_non_utf8",
                {"item_kind": "expected\ud800return"},
                "invalid_unresolved_item_kind",
            ),
            (
                "present_null_case_list",
                {
                    "item_kind": "expected_return_unknown",
                    "related_test_case_ids": None,
                },
                "invalid_unresolved_case_references",
            ),
            (
                "present_string_case_list",
                {
                    "item_kind": "expected_return_unknown",
                    "related_test_case_ids": "tc-control-update-001",
                },
                "invalid_unresolved_case_references",
            ),
            (
                "case_list_subclass",
                {
                    "item_kind": "expected_return_unknown",
                    "related_test_case_ids": HostileList(["tc-control-update-001"]),
                },
                "invalid_unresolved_case_references",
            ),
            (
                "non_string_case_id",
                {
                    "item_kind": "expected_return_unknown",
                    "related_test_case_ids": [7],
                },
                "invalid_case_reference",
            ),
            (
                "case_id_string_subclass",
                {
                    "item_kind": "expected_return_unknown",
                    "related_test_case_ids": [
                        HostileString("tc-control-update-001")
                    ],
                },
                "invalid_case_reference",
            ),
            (
                "case_id_nul",
                {
                    "item_kind": "expected_return_unknown",
                    "severity": "warning",
                    "related_test_case_ids": ["tc\x00-control-update-001"],
                },
                "invalid_case_reference",
            ),
            (
                "case_id_non_utf8",
                {
                    "item_kind": "expected_return_unknown",
                    "severity": "warning",
                    "related_test_case_ids": ["tc-\ud800-control-update-001"],
                },
                "invalid_case_reference",
            ),
            (
                "warning_blank_case_id",
                {
                    "item_kind": "expected_return_unknown",
                    "severity": "warning",
                    "related_test_case_ids": [""],
                },
                "invalid_case_reference",
            ),
            (
                "warning_separator_only_case_id",
                {
                    "item_kind": "expected_return_unknown",
                    "severity": "warning",
                    "related_test_case_ids": [" _/ "],
                },
                "invalid_case_reference",
            ),
        )
        for label, unresolved_item, expected_code in malformed:
            payload = copied_payload()
            payload["data"]["unresolved_items"] = [unresolved_item]
            for boundary in ("validate_payload", "TestSpec.from_payload"):
                with self.subTest(case=label, boundary=boundary):
                    if boundary == "validate_payload":
                        codes = {
                            item.code
                            for item in validate_payload(
                                ArtifactKind.TEST_SPEC,
                                payload,
                            )
                        }
                    else:
                        try:
                            TestSpec.from_payload(payload)
                        except TestSpecContractError as error:
                            codes = {item.code for item in error.violations}
                        else:
                            codes = set()
                    self.assertIn(expected_code, codes)

    def test_schema_invalid_collection_types_are_structured_at_public_boundaries(self):
        malformed = (
            ("unresolved_number", ("unresolved_items",), 7),
            ("unresolved_boolean", ("unresolved_items",), True),
            ("test_cases_number", ("test_cases",), 7),
            (
                "additional_candidates_number",
                ("additional_case_candidates",),
                3.14,
            ),
            ("review_ids_number", ("review_item_ids",), 7),
            ("generation_policy_number", ("generation_policy",), 7),
            (
                "input_assignments_number",
                ("test_cases", 0, "input_assignments"),
                7,
            ),
            (
                "state_setups_boolean",
                ("test_cases", 0, "state_setups"),
                True,
            ),
            (
                "stub_setups_number",
                ("test_cases", 0, "stub_setups"),
                3.14,
            ),
            (
                "expected_observations_number",
                ("test_cases", 0, "expected_observations"),
                7,
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "test_spec.json"
            for label, field_path, malformed_value in malformed:
                payload = copied_payload()
                target = payload["data"]
                for path_part in field_path[:-1]:
                    target = target[path_part]
                target[field_path[-1]] = malformed_value
                expected_path = "$.data" + "".join(
                    (
                        f"[{path_part}]"
                        if isinstance(path_part, int)
                        else f".{path_part}"
                    )
                    for path_part in field_path
                )

                with self.subTest(case=label, boundary="validate_payload"):
                    violations = validate_payload(ArtifactKind.TEST_SPEC, payload)
                    self.assertIn(
                        ("schema_error", expected_path),
                        {(item.code, item.json_path) for item in violations},
                    )

                with self.subTest(case=label, boundary="TestSpec.from_payload"):
                    with self.assertRaises(TestSpecContractError) as raised:
                        TestSpec.from_payload(payload)
                    self.assertTrue(
                        raised.exception.violations,
                        "The model boundary must return structured violations.",
                    )
                    self.assertIn(
                        "schema_error",
                        {item.code for item in raised.exception.violations},
                    )

                with self.subTest(case=label, boundary="load_artifact"):
                    artifact_path.write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    loaded = load_artifact(
                        artifact_path,
                        expected_kind=ArtifactKind.TEST_SPEC,
                    )
                    self.assertIn(
                        ("schema_error", expected_path),
                        {
                            (item.code, item.json_path)
                            for item in loaded.violations
                        },
                    )

    def test_strict_case_ids_are_validated_before_string_coercion(self):
        malformed = (
            ("string_subclass", HostileString("tc-control-update-001")),
            ("coercing_string", CoercingString("attacker-case")),
            ("exploding_string", ExplodingString("tc-control-update-001")),
        )
        for label, malformed_case_id in malformed:
            payload = copied_payload()
            payload["data"]["test_cases"][0]["test_case_id"] = malformed_case_id
            for boundary in ("validate_payload", "TestSpec.from_payload"):
                with self.subTest(case=label, boundary=boundary):
                    if boundary == "validate_payload":
                        codes = {
                            item.code
                            for item in validate_payload(
                                ArtifactKind.TEST_SPEC,
                                payload,
                            )
                        }
                    else:
                        try:
                            TestSpec.from_payload(payload)
                        except TestSpecContractError as error:
                            codes = {item.code for item in error.violations}
                        else:
                            codes = set()
                    self.assertIn("invalid_case_id", codes)

        payload = copied_payload()
        self.assertEqual((), validate_payload(ArtifactKind.TEST_SPEC, payload))
        loaded = TestSpec.from_payload(payload)
        review_items, unresolved = build_review_items(
            {"test_spec": loaded.to_payload()["data"]}
        )
        self.assertIsInstance(review_items, list)
        self.assertIsInstance(unresolved, list)

    def test_raw_model_scalars_are_validated_before_construction(self):
        malformed = (
            ("producer_empty_list", ("producer",), []),
            ("extensions_empty_list", ("extensions",), []),
            ("spec_id", ("data", "spec_id"), 7),
            ("revision_bool", ("data", "revision"), True),
            ("source_path", ("data", "source", "path"), 7),
            (
                "function_id",
                ("data", "function", "function_id"),
                7,
            ),
            ("function_name", ("data", "function", "name"), 7),
            (
                "generated_kind",
                ("data", "generated_from", 0, "artifact_kind"),
                7,
            ),
            (
                "generated_path",
                ("data", "generated_from", 0, "path"),
                7,
            ),
            (
                "generated_sha",
                ("data", "generated_from", 0, "sha256"),
                7,
            ),
            ("review_id", ("data", "review_item_ids", 0), 7),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "test_spec.json"
            for label, field_path, malformed_value in malformed:
                payload = copied_payload()
                target = payload
                for path_part in field_path[:-1]:
                    target = target[path_part]
                target[field_path[-1]] = malformed_value

                with self.subTest(case=label, boundary="validate_payload"):
                    self.assertIn(
                        "schema_error",
                        {
                            item.code
                            for item in validate_payload(
                                ArtifactKind.TEST_SPEC,
                                payload,
                            )
                        },
                    )

                for validate in (True, False):
                    with self.subTest(
                        case=label,
                        boundary="TestSpec.from_payload",
                        validate=validate,
                    ):
                        with self.assertRaises(TestSpecContractError) as raised:
                            TestSpec.from_payload(payload, validate=validate)
                        self.assertIn(
                            "schema_error",
                            {item.code for item in raised.exception.violations},
                        )

                with self.subTest(case=label, boundary="load_artifact"):
                    artifact_path.write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    loaded = load_artifact(
                        artifact_path,
                        expected_kind=ArtifactKind.TEST_SPEC,
                    )
                    self.assertIn(
                        "schema_error",
                        {item.code for item in loaded.violations},
                    )

    def test_schema_version_is_exact_before_public_validation(self):
        for malformed_version in (
            CoercingCurrentVersionString("1.1.0"),
            ExplodingString("1.1.0"),
        ):
            payload = copied_payload()
            payload["schema_version"] = malformed_version
            for boundary in (validate_payload_schema, validate_payload):
                with self.subTest(
                    version=type(malformed_version).__name__,
                    boundary=boundary.__name__,
                ):
                    self.assertIn(
                        "schema_error",
                        {
                            item.code
                            for item in boundary(ArtifactKind.TEST_SPEC, payload)
                        },
                    )
            with self.subTest(
                version=type(malformed_version).__name__,
                boundary="TestSpec.from_payload",
            ):
                with self.assertRaises(TestSpecContractError) as raised:
                    TestSpec.from_payload(payload)
                self.assertIn(
                    "schema_error",
                    {item.code for item in raised.exception.violations},
                )

        current = copied_payload()
        self.assertEqual(
            (),
            validate_payload_schema(ArtifactKind.TEST_SPEC, current),
        )
        self.assertEqual((), validate_payload(ArtifactKind.TEST_SPEC, current))
        self.assertEqual("1.1.0", TestSpec.from_payload(current).schema_version)

        unknown = copied_payload()
        unknown["schema_version"] = "9.9.9"
        for boundary in (validate_payload_schema, validate_payload):
            with self.subTest(version="unknown", boundary=boundary.__name__):
                self.assertIn(
                    "unsupported_version",
                    {
                        item.code
                        for item in boundary(ArtifactKind.TEST_SPEC, unknown)
                    },
                )
        with self.assertRaises(TestSpecContractError) as raised:
            TestSpec.from_payload(unknown)
        self.assertIn(
            "unsupported_version",
            {item.code for item in raised.exception.violations},
        )

        missing = copied_payload()
        missing.pop("schema_version")
        expected_missing = {
            ("unsupported_version", "$.schema_version"),
            ("required_property", "$"),
        }
        for boundary in (validate_payload_schema, validate_payload):
            with self.subTest(version="missing", boundary=boundary.__name__):
                self.assertEqual(
                    expected_missing,
                    {
                        (item.code, item.json_path)
                        for item in boundary(ArtifactKind.TEST_SPEC, missing)
                    },
                )

        aggregate = copied_payload()
        aggregate["data"]["test_cases"][0]["approved"] = True
        self.assertTrue(
            {"unknown_property", "embedded_review_authority"}.issubset(
                {
                    item.code
                    for item in validate_payload(ArtifactKind.TEST_SPEC, aggregate)
                }
            )
        )

    def test_in_memory_test_spec_scalars_reject_hostile_subclasses(self):
        def unresolved_severity(payload, value):
            payload["data"]["unresolved_items"] = [
                {
                    "item_kind": "expected_return_unknown",
                    "severity": value,
                }
            ]

        mutations = (
            (
                "spec_id",
                lambda payload, value: payload["data"].__setitem__(
                    "spec_id", value
                ),
                ExplodingString("spec-control-update"),
                "invalid_spec_id",
            ),
            (
                "revision",
                lambda payload, value: payload["data"].__setitem__(
                    "revision", value
                ),
                CoercingInt(1),
                "invalid_revision",
            ),
            (
                "source_path",
                lambda payload, value: payload["data"]["source"].__setitem__(
                    "path", value
                ),
                ExplodingString("src/control.c"),
                "invalid_source_identity",
            ),
            (
                "source_path_nul",
                lambda payload, value: payload["data"]["source"].__setitem__(
                    "path", value
                ),
                "src/con\x00trol.c",
                "invalid_source_identity",
            ),
            (
                "source_path_non_utf8",
                lambda payload, value: payload["data"]["source"].__setitem__(
                    "path", value
                ),
                "src/\ud800.c",
                "invalid_source_identity",
            ),
            (
                "source_sha",
                lambda payload, value: payload["data"]["source"].__setitem__(
                    "sha256", value
                ),
                ExplodingString("1" * 64),
                "invalid_source_identity",
            ),
            (
                "function_id",
                lambda payload, value: payload["data"]["function"].__setitem__(
                    "function_id", value
                ),
                ExplodingString("fn-control-update"),
                "invalid_function_identity",
            ),
            (
                "function_id_nul",
                lambda payload, value: payload["data"]["function"].__setitem__(
                    "function_id", value
                ),
                "fn\x00-control-update",
                "invalid_function_identity",
            ),
            (
                "function_name",
                lambda payload, value: payload["data"]["function"].__setitem__(
                    "name", value
                ),
                ExplodingString("Control_Update"),
                "invalid_function_identity",
            ),
            (
                "function_name_non_utf8",
                lambda payload, value: payload["data"]["function"].__setitem__(
                    "name", value
                ),
                "Control_\ud800",
                "invalid_function_identity",
            ),
            (
                "signature_sha",
                lambda payload, value: payload["data"]["function"].__setitem__(
                    "signature_sha256", value
                ),
                ExplodingString("2" * 64),
                "invalid_function_identity",
            ),
            (
                "generated_kind",
                lambda payload, value: payload["data"]["generated_from"][
                    0
                ].__setitem__("artifact_kind", value),
                ExplodingString("function_signature"),
                "invalid_generated_reference",
            ),
            (
                "generated_path",
                lambda payload, value: payload["data"]["generated_from"][
                    0
                ].__setitem__("path", value),
                ExplodingString("reports/function_signature.json"),
                "invalid_generated_reference",
            ),
            (
                "generated_sha",
                lambda payload, value: payload["data"]["generated_from"][
                    0
                ].__setitem__("sha256", value),
                ExplodingString("3" * 64),
                "invalid_generated_reference",
            ),
            (
                "review_id",
                lambda payload, value: payload["data"][
                    "review_item_ids"
                ].__setitem__(0, value),
                ExplodingString("review-input-001"),
                "invalid_review_id",
            ),
            (
                "review_id_nul",
                lambda payload, value: payload["data"][
                    "review_item_ids"
                ].__setitem__(0, value),
                "review\x00-input-001",
                "invalid_review_id",
            ),
            (
                "review_id_non_utf8",
                lambda payload, value: payload["data"][
                    "review_item_ids"
                ].__setitem__(0, value),
                "review-\ud800-input-001",
                "invalid_review_id",
            ),
            (
                "target_function",
                lambda payload, value: payload["data"]["test_cases"][0].__setitem__(
                    "target_function", value
                ),
                ExplodingString("Control_Update"),
                "invalid_target_function",
            ),
            (
                "coverage_id",
                lambda payload, value: payload["data"]["test_cases"][0][
                    "coverage_links"
                ][0].__setitem__("coverage_id", value),
                ExplodingString("cov-normal"),
                "invalid_coverage_id",
            ),
            (
                "unresolved_severity",
                unresolved_severity,
                ExplodingString("warning"),
                "invalid_unresolved_severity",
            ),
            (
                "expected_expression",
                lambda payload, value: payload["data"]["test_cases"][0][
                    "expected_observations"
                ][0].__setitem__("expected_expression", value),
                ExplodingString("OK"),
                "unresolved_executable_value",
            ),
            (
                "setup_kind",
                lambda payload, value: payload["data"]["test_cases"][0][
                    "stub_setups"
                ][0].__setitem__("setup_kind", value),
                ExplodingString("return_value"),
                "invalid_setup_kind",
            ),
        )
        for label, mutate, malformed_value, expected_code in mutations:
            payload = copied_payload()
            mutate(payload, malformed_value)
            for boundary in ("validate_payload", "TestSpec.from_payload"):
                with self.subTest(case=label, boundary=boundary):
                    if boundary == "validate_payload":
                        codes = {
                            item.code
                            for item in validate_payload(
                                ArtifactKind.TEST_SPEC,
                                payload,
                            )
                        }
                    else:
                        try:
                            TestSpec.from_payload(payload)
                        except TestSpecContractError as error:
                            codes = {item.code for item in error.violations}
                        else:
                            codes = set()
                    self.assertIn(expected_code, codes)

    def test_hostile_id_hash_and_equality_are_not_invoked_before_semantics(self):
        mutations = (
            (
                "test_case_id",
                lambda payload, value: payload["data"]["test_cases"][0].__setitem__(
                    "test_case_id", value
                ),
                "invalid_case_id",
            ),
            (
                "review_item_id",
                lambda payload, value: payload["data"][
                    "review_item_ids"
                ].__setitem__(0, value),
                "invalid_review_id",
            ),
        )
        for label, mutate, expected_code in mutations:
            payload = copied_payload()
            mutate(payload, ExplodingHashString("attacker-controlled-id"))
            with self.subTest(case=label):
                codes = {
                    item.code
                    for item in validate_payload(ArtifactKind.TEST_SPEC, payload)
                }
                self.assertIn(expected_code, codes)

    def test_test_spec_shadow_preserves_schema_and_semantic_diagnostics(self):
        payload = copied_payload()
        payload["data"]["review_item_ids"][0] = ExplodingHashString(
            "review-input-001"
        )
        payload["data"].pop("warnings")

        schema_codes = {
            item.code
            for item in validate_payload_schema(ArtifactKind.TEST_SPEC, payload)
        }
        self.assertTrue(
            {"schema_error", "required_property"}.issubset(schema_codes)
        )

        combined_codes = {
            item.code for item in validate_payload(ArtifactKind.TEST_SPEC, payload)
        }
        self.assertTrue(
            {
                "schema_error",
                "required_property",
                "invalid_review_id",
            }.issubset(combined_codes)
        )

    def test_test_spec_shadow_blocks_hostile_common_scalar_hooks(self):
        mutations = (
            (
                "coverage_id_hash",
                lambda payload: payload["data"]["test_cases"][0][
                    "coverage_links"
                ][0].__setitem__(
                    "coverage_id",
                    ExplodingHashString("cov-normal"),
                ),
                "invalid_coverage_id",
            ),
            (
                "source_path_replace",
                lambda payload: payload["data"]["source"].__setitem__(
                    "path",
                    ExplodingReplaceString("src/control.c"),
                ),
                "invalid_source_identity",
            ),
            (
                "source_sha_equality",
                lambda payload: payload["data"]["source"].__setitem__(
                    "sha256",
                    ExplodingEqualityString("1" * 64),
                ),
                "invalid_source_identity",
            ),
            (
                "subject_path_truthiness",
                lambda payload: payload["subject"].__setitem__(
                    "source_path",
                    ExplodingBoolString("src/control.c"),
                ),
                "schema_error",
            ),
        )
        for label, mutate, expected_code in mutations:
            payload = copied_payload()
            mutate(payload)
            with self.subTest(case=label):
                self.assertIn(
                    expected_code,
                    {
                        item.code
                        for item in validate_payload(ArtifactKind.TEST_SPEC, payload)
                    },
                )

    def test_dossier_rejects_malformed_direct_test_spec_collections(self):
        for field in (
            "test_cases",
            "additional_case_candidates",
            "unresolved_items",
        ):
            payload = copied_payload()["data"]
            payload[field] = 7
            with self.subTest(field=field):
                review_items, unresolved = build_review_items(
                    {"test_spec": payload}
                )
                self.assertEqual([], review_items)
                self.assertEqual(1, len(unresolved))
                self.assertEqual("manual_final_review", unresolved[0].item_kind)

    def test_top_level_list_subclasses_use_builtin_storage_at_all_boundaries(self):
        malformed = copied_payload()
        malformed["data"]["test_cases"] = ExplodingIterList([7])
        with self.subTest(boundary="validate_payload", shape="malformed"):
            violations = validate_payload(ArtifactKind.TEST_SPEC, malformed)
            self.assertIn("schema_error", {item.code for item in violations})
        with self.subTest(boundary="TestSpec.from_payload", shape="malformed"):
            with self.assertRaises(TestSpecContractError) as raised:
                TestSpec.from_payload(malformed)
            self.assertIn(
                "schema_error",
                {item.code for item in raised.exception.violations},
            )

        valid = copied_payload()
        valid_cases = valid["data"]["test_cases"]
        valid["data"]["test_cases"] = ExplodingIterList(valid_cases)
        with self.subTest(boundary="validate_payload", shape="valid"):
            self.assertEqual((), validate_payload(ArtifactKind.TEST_SPEC, valid))
        with self.subTest(boundary="TestSpec.from_payload", shape="valid"):
            self.assertEqual(
                "tc-control-update-001",
                TestSpec.from_payload(valid).test_cases[0]["test_case_id"],
            )

        benign = copied_payload()
        benign["data"]["test_cases"] = BenignList(
            benign["data"]["test_cases"]
        )
        with self.subTest(boundary="benign_list_subclass"):
            self.assertEqual((), validate_payload(ArtifactKind.TEST_SPEC, benign))
            self.assertEqual(1, len(TestSpec.from_payload(benign).test_cases))

        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        design = self.minimal_design()
        design["additional_case_candidates"] = ExplodingIterList(
            design["additional_case_candidates"]
        )
        with self.subTest(boundary="generation", shape="valid"):
            generated = create_test_spec_from_design(
                design,
                {
                    "source": {
                        "path": "src/control.c",
                        "sha256": "1" * 64,
                    },
                    "function": {"name": "Control_Update"},
                },
                source_path="src/control.c",
                generated_from=[reference],
            )
            self.assertEqual(1, len(generated.additional_case_candidates))

        dossier_payload = copied_payload()["data"]
        dossier_payload["test_cases"] = ExplodingIterList([7])
        with self.subTest(boundary="dossier", shape="malformed"):
            review_items, unresolved = build_review_items(
                {"test_spec": dossier_payload}
            )
            self.assertEqual([], review_items)
            self.assertEqual(1, len(unresolved))
            self.assertEqual("manual_final_review", unresolved[0].item_kind)

    def test_nested_container_subclasses_are_materialized_at_consumer_boundaries(self):
        def nested_payload():
            payload = copied_payload()
            data = BenignDict(payload["data"])
            payload["data"] = data

            policy = BenignDict(data["generation_policy"])
            policy["dependency_ids"] = ExplodingIterList(
                policy["dependency_ids"]
            )
            data["generation_policy"] = policy

            case = BenignDict(data["test_cases"][0])
            data["test_cases"][0] = case
            assignment = BenignDict(case["input_assignments"][0])
            assignment["review_item_ids"] = ExplodingIterList(
                assignment["review_item_ids"]
            )
            case["input_assignments"] = ExplodingIterList([assignment])
            case["stub_setups"] = BenignList(case["stub_setups"])
            observation = BenignDict(case["expected_observations"][0])
            observation["review_item_ids"] = ExplodingIterList(
                observation["review_item_ids"]
            )
            case["expected_observations"] = ExplodingIterList([observation])
            case["coverage_links"] = ExplodingIterList(
                [BenignDict(case["coverage_links"][0])]
            )

            coverage = BenignDict(data["coverage_summary"])
            coverage_map = BenignDict(coverage["coverage_to_test_cases"])
            coverage_map["cov-normal"] = ExplodingIterList(
                coverage_map["cov-normal"]
            )
            coverage["coverage_to_test_cases"] = coverage_map
            coverage["uncovered_coverage_ids"] = ExplodingIterList(
                coverage["uncovered_coverage_ids"]
            )
            data["coverage_summary"] = coverage
            return payload

        valid = nested_payload()
        with self.subTest(boundary="validate_payload", shape="valid_nested"):
            self.assertEqual((), validate_payload(ArtifactKind.TEST_SPEC, valid))
        with self.subTest(boundary="TestSpec.from_payload", shape="valid_nested"):
            spec = TestSpec.from_payload(valid)
            self.assertIs(type(spec.generation_policy["dependency_ids"]), list)
            self.assertIs(
                type(spec.test_cases[0]["expected_observations"]),
                list,
            )

        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        data = valid["data"]
        design = BenignDict(
            {
                "generation_policy": data["generation_policy"],
                "test_cases": data["test_cases"],
                "additional_case_candidates": [],
                "coverage_summary": data["coverage_summary"],
                "unresolved_items": [],
                "warnings": [],
            }
        )
        with self.subTest(boundary="generation", shape="valid_nested"):
            generated = create_test_spec_from_design(
                design,
                {
                    "source": {
                        "path": "src/control.c",
                        "sha256": "1" * 64,
                    },
                    "function": {"name": "Control_Update"},
                },
                source_path="src/control.c",
                generated_from=[reference],
            )
            self.assertEqual(1, len(generated.test_cases))

        with self.subTest(boundary="dossier", shape="valid_nested"):
            review_items, unresolved = build_review_items(
                {"test_spec": valid["data"]}
            )
            self.assertEqual([], review_items)
            self.assertEqual("manual_final_review", unresolved[-1].item_kind)

        malformed = nested_payload()
        malformed["data"]["test_cases"][0][
            "expected_observations"
        ] = ExplodingIterList([7])
        with self.subTest(boundary="validate_payload", shape="malformed_nested"):
            violations = validate_payload(ArtifactKind.TEST_SPEC, malformed)
            self.assertIn("schema_error", {item.code for item in violations})
        with self.subTest(
            boundary="TestSpec.from_payload",
            shape="malformed_nested",
        ):
            with self.assertRaises(TestSpecContractError) as raised:
                TestSpec.from_payload(malformed)
            self.assertIn(
                "schema_error",
                {item.code for item in raised.exception.violations},
            )

        malformed_design = self.minimal_design()
        malformed_case = malformed_design["additional_case_candidates"].pop()
        malformed_case["expected_observations"] = ExplodingIterList([7])
        malformed_design["test_cases"] = [malformed_case]
        with self.subTest(boundary="generation", shape="malformed_nested"):
            with self.assertRaises(TestSpecContractError) as raised:
                create_test_spec_from_design(
                    malformed_design,
                    {
                        "source": {
                            "path": "src/control.c",
                            "sha256": "1" * 64,
                        },
                        "function": {"name": "Control_Update"},
                    },
                    source_path="src/control.c",
                    generated_from=[reference],
                )
            self.assertIn(
                "schema_error",
                {item.code for item in raised.exception.violations},
            )

        with self.subTest(boundary="dossier", shape="malformed_nested"):
            review_items, unresolved = build_review_items(
                {"test_spec": malformed["data"]}
            )
            self.assertEqual([], review_items)
            self.assertEqual("manual_final_review", unresolved[-1].item_kind)

    def test_exact_related_case_list_policy_is_scoped_to_unresolved_items(self):
        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        signature = {
            "source": {"path": "src/control.c", "sha256": "1" * 64},
            "function": {"name": "Control_Update"},
        }
        unresolved = {
            "item_kind": "expected_return_unknown",
            "related_test_case_ids": ExplodingIterList(
                ["tc-control-update-001"]
            ),
        }

        model_payload = copied_payload()
        model_payload["data"]["unresolved_items"] = [unresolved]
        with self.subTest(boundary="model_validate_false", field="unresolved"):
            with self.assertRaises(TestSpecContractError):
                TestSpec.from_payload(model_payload, validate=False)

        non_list_payload = copied_payload()
        non_list_payload["data"]["unresolved_items"] = [
            {
                "item_kind": "expected_return_unknown",
                "related_test_case_ids": "tc-control-update-001",
            }
        ]
        with self.subTest(
            boundary="model_validate_false",
            field="unresolved_non_list",
        ):
            with self.assertRaises(TestSpecContractError):
                TestSpec.from_payload(non_list_payload, validate=False)

        generation_design = self.minimal_design()
        generation_design["unresolved_items"] = [unresolved]
        with self.subTest(boundary="generation", field="unresolved"):
            with self.assertRaises(TypeError):
                create_test_spec_from_design(
                    generation_design,
                    signature,
                    source_path="src/control.c",
                    generated_from=[reference],
                )

        dossier_payload = copied_payload()["data"]
        dossier_payload["unresolved_items"] = [unresolved]
        with self.subTest(boundary="dossier", field="unresolved"):
            with self.assertRaises(TypeError):
                build_review_items({"test_spec": dossier_payload})

        extension_payload = copied_payload()
        extension_payload["extensions"]["vendor"] = {
            "related_test_case_ids": BenignList(["opaque-extension-value"])
        }
        with self.subTest(boundary="model", field="opaque_extension"):
            extension_spec = TestSpec.from_payload(extension_payload)
            self.assertEqual(
                ["opaque-extension-value"],
                extension_spec.extensions["vendor"]["related_test_case_ids"],
            )

        warning = {
            "related_test_case_ids": BenignList(["opaque-warning-value"])
        }
        warning_design = self.minimal_design()
        warning_design["warnings"] = [warning]
        with self.subTest(boundary="generation", field="opaque_warning"):
            warning_spec = create_test_spec_from_design(
                warning_design,
                signature,
                source_path="src/control.c",
                generated_from=[reference],
            )
            self.assertEqual(
                ["opaque-warning-value"],
                warning_spec.warnings[0]["related_test_case_ids"],
            )

        dossier_warning_payload = copied_payload()["data"]
        dossier_warning_payload["warnings"] = [warning]
        with self.subTest(boundary="dossier", field="opaque_warning"):
            review_items, unresolved_items = build_review_items(
                {"test_spec": dossier_warning_payload}
            )
            self.assertEqual([], review_items)
            self.assertEqual(
                "manual_final_review",
                unresolved_items[-1].item_kind,
            )

    def test_direct_model_enforces_exact_unresolved_case_list_before_materialization(self):
        invalid = TestSpec.from_payload(copied_payload())
        invalid.unresolved_items = [
            {
                "item_kind": "expected_return_unknown",
                "related_test_case_ids": ExplodingIterList(
                    ["tc-control-update-001"]
                ),
            }
        ]

        with self.subTest(boundary="validate_test_spec"):
            violations = validate_test_spec(invalid)
            self.assertIn(
                "invalid_unresolved_case_references",
                {item.code for item in violations},
            )
        with self.subTest(boundary="to_payload"):
            with self.assertRaises(TypeError) as raised:
                invalid.to_payload()
            self.assertIn("exact list", str(raised.exception))

        valid = TestSpec.from_payload(copied_payload())
        valid.unresolved_items = [
            {
                "item_kind": "expected_return_unknown",
                "related_test_case_ids": [],
            }
        ]
        with self.subTest(boundary="exact_builtin_list"):
            payload = valid.to_payload()
            self.assertIs(
                type(
                    payload["data"]["unresolved_items"][0][
                        "related_test_case_ids"
                    ]
                ),
                list,
            )
            self.assertEqual((), validate_test_spec(valid))

        opaque = TestSpec.from_payload(copied_payload())
        opaque.warnings = [
            {
                "related_test_case_ids": ExplodingIterList(
                    ["opaque-warning-value"]
                )
            }
        ]
        opaque.extensions = {
            "vendor": {
                "related_test_case_ids": ExplodingIterList(
                    ["opaque-extension-value"]
                )
            }
        }
        with self.subTest(boundary="opaque_same_name_fields"):
            self.assertEqual((), validate_test_spec(opaque))
            payload = opaque.to_payload()
            self.assertIs(
                type(payload["data"]["warnings"][0]["related_test_case_ids"]),
                list,
            )
            self.assertIs(
                type(
                    payload["extensions"]["vendor"][
                        "related_test_case_ids"
                    ]
                ),
                list,
            )

    def test_direct_exact_list_violation_preserves_other_diagnostics(self):
        spec = TestSpec.from_payload(copied_payload())
        spec.spec_id = 7
        spec.revision = 0
        spec.source = SourceReference(
            "C:/absolute/control.c",
            spec.source.sha256,
        )
        spec.test_cases[0]["approved"] = True
        spec.unresolved_items = [
            {
                "item_kind": "expected_return_unknown",
                "related_test_case_ids": ExplodingIterList(
                    ["tc-control-update-001"]
                ),
            }
        ]

        actual = {
            (item.code, item.json_path)
            for item in validate_test_spec(spec)
        }

        self.assertTrue(
            {
                (
                    "invalid_unresolved_case_references",
                    "$.data.unresolved_items[0].related_test_case_ids",
                ),
                ("schema_error", "$.data.spec_id"),
                ("schema_error", "$.data.revision"),
                ("invalid_spec_id", "$.data.spec_id"),
                ("invalid_relative_path", "$.data.source.path"),
                ("unknown_property", "$.data.test_cases[0]"),
                (
                    "embedded_review_authority",
                    "$.data.test_cases[0].approved",
                ),
            }.issubset(actual),
            actual,
        )

    def test_direct_model_materializes_container_subclasses_before_use(self):
        producer_spec = TestSpec.from_payload(copied_payload())
        producer = ExplodingBoolDict(producer_spec.producer)
        producer_spec.producer = producer
        with self.subTest(field="producer", boundary="to_payload"):
            payload = producer_spec.to_payload()
            self.assertIs(type(payload["producer"]), dict)
            self.assertEqual(dict.items(producer), payload["producer"].items())
            self.assertIs(producer_spec.producer, producer)
        with self.subTest(field="producer", boundary="validate_test_spec"):
            self.assertEqual(
                (),
                validate_test_spec(
                    producer_spec,
                    current_context=current_context(),
                ),
            )
            self.assertIs(producer_spec.producer, producer)

        generated_spec = TestSpec.from_payload(copied_payload())
        original_reference = generated_spec.generated_from[0]
        generated_from = ExplodingIterList(generated_spec.generated_from)
        generated_spec.generated_from = generated_from
        with self.subTest(field="generated_from", boundary="to_payload"):
            payload = generated_spec.to_payload()
            self.assertIs(type(payload["data"]["generated_from"]), list)
            self.assertEqual(
                [original_reference.to_dict()],
                payload["data"]["generated_from"],
            )
            self.assertIs(generated_spec.generated_from, generated_from)
            self.assertIs(generated_from[0], original_reference)
        with self.subTest(
            field="generated_from",
            boundary="validate_test_spec",
        ):
            self.assertEqual(
                (),
                validate_test_spec(
                    generated_spec,
                    current_context=current_context(),
                ),
            )
            self.assertIs(generated_spec.generated_from, generated_from)

        base_context = current_context()
        context_generated_from = ExplodingIterList(
            base_context.generated_from
        )
        hostile_context = CurrentArtifactContext(
            source_path=base_context.source_path,
            source_sha256=base_context.source_sha256,
            function_id=base_context.function_id,
            function_name=base_context.function_name,
            signature_sha256=base_context.signature_sha256,
            workspace_root=base_context.workspace_root,
            generated_from=context_generated_from,
        )
        with self.subTest(
            field="context.generated_from",
            boundary="validate_test_spec",
        ):
            self.assertEqual(
                (),
                validate_test_spec(
                    TestSpec.from_payload(copied_payload()),
                    current_context=hostile_context,
                ),
            )
            self.assertIs(
                hostile_context.generated_from,
                context_generated_from,
            )

        falsey_spec = TestSpec.from_payload(copied_payload())
        falsey_producer = []
        falsey_spec.producer = falsey_producer
        with self.subTest(field="producer", shape="falsey_non_dict"):
            payload = falsey_spec.to_payload()
            self.assertIs(type(payload["producer"]), list)
            self.assertEqual([], payload["producer"])
            self.assertIs(falsey_spec.producer, falsey_producer)
            self.assertIn(
                "schema_error",
                {item.code for item in validate_test_spec(falsey_spec)},
            )

        empty_spec = TestSpec.from_payload(copied_payload())
        empty_producer = {}
        empty_spec.producer = empty_producer
        with self.subTest(field="producer", shape="empty_dict_default"):
            payload = empty_spec.to_payload()
            self.assertEqual("unit-test-runner", payload["producer"]["name"])
            self.assertIs(empty_spec.producer, empty_producer)

    def test_materialized_scalars_do_not_invoke_deepcopy_hooks(self):
        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        signature = {
            "source": {"path": "src/control.c", "sha256": "1" * 64},
            "function": {"name": "Control_Update"},
        }

        invalid_design = self.minimal_design(
            ExplodingDeepcopyString("TC-01")
        )
        with self.subTest(boundary="generation", field="test_case_id"):
            with self.assertRaises(TypeError) as raised:
                create_test_spec_from_design(
                    invalid_design,
                    signature,
                    source_path="src/control.c",
                    generated_from=[reference],
                )
            self.assertIn("exact string", str(raised.exception))

        extension_scalar = ExplodingDeepcopyString("opaque-extension-value")
        extension_payload = copied_payload()
        extension_payload["extensions"]["vendor"] = {
            "value": extension_scalar
        }
        with self.subTest(boundary="model_and_to_payload", field="extension"):
            spec = TestSpec.from_payload(extension_payload)
            self.assertIs(spec.extensions["vendor"]["value"], extension_scalar)
            self.assertIs(
                spec.to_payload()["extensions"]["vendor"]["value"],
                extension_scalar,
            )

        warning_scalar = ExplodingDeepcopyString("opaque-warning-value")
        warning_design = self.minimal_design()
        warning_design["warnings"] = [{"value": warning_scalar}]
        with self.subTest(boundary="generation", field="warning"):
            spec = create_test_spec_from_design(
                warning_design,
                signature,
                source_path="src/control.c",
                generated_from=[reference],
            )
            self.assertIs(spec.warnings[0]["value"], warning_scalar)
            self.assertIs(
                spec.to_payload()["data"]["warnings"][0]["value"],
                warning_scalar,
            )

    def test_setup_and_expression_values_fail_closed_across_consumers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "test_spec.json"
            malformed = (
                (
                    "setup_list",
                    lambda payload: payload["data"]["test_cases"][0][
                        "stub_setups"
                    ][0].__setitem__("setup_kind", []),
                    "invalid_setup_kind",
                ),
                (
                    "setup_object",
                    lambda payload: payload["data"]["test_cases"][0][
                        "stub_setups"
                    ][0].__setitem__("setup_kind", {}),
                    "invalid_setup_kind",
                ),
                (
                    "expression_number",
                    lambda payload: payload["data"]["test_cases"][0][
                        "expected_observations"
                    ][0].__setitem__("expected_expression", 7),
                    "unresolved_executable_value",
                ),
                (
                    "severity_list",
                    lambda payload: payload["data"].__setitem__(
                        "unresolved_items",
                        [
                            {
                                "item_kind": "expected_return_unknown",
                                "severity": [],
                            }
                        ],
                    ),
                    "invalid_unresolved_severity",
                ),
            )
            for label, mutate, expected_code in malformed:
                payload = copied_payload()
                mutate(payload)
                for boundary in (
                    "validate_payload",
                    "TestSpec.from_payload",
                    "load_artifact",
                ):
                    with self.subTest(case=label, boundary=boundary):
                        if boundary == "validate_payload":
                            codes = {
                                item.code
                                for item in validate_payload(
                                    ArtifactKind.TEST_SPEC,
                                    payload,
                                )
                            }
                        elif boundary == "TestSpec.from_payload":
                            try:
                                TestSpec.from_payload(payload)
                            except TestSpecContractError as error:
                                codes = {item.code for item in error.violations}
                            else:
                                codes = set()
                        else:
                            artifact_path.write_text(
                                json.dumps(payload),
                                encoding="utf-8",
                            )
                            loaded = load_artifact(
                                artifact_path,
                                expected_kind=ArtifactKind.TEST_SPEC,
                            )
                            codes = {item.code for item in loaded.violations}
                        self.assertIn(expected_code, codes)

        for expression in (
            "",
            "   ",
            " tbd oracle ",
            " unknown result ",
            " unresolved value ",
            " todo define oracle ",
            ExplodingString("OK"),
        ):
            with self.subTest(consumer="dossier", expression=repr(expression)):
                dossier_payload = copied_payload()["data"]
                dossier_payload["test_cases"][0]["expected_observations"][0][
                    "expected_expression"
                ] = expression
                _review_items, unresolved = build_review_items(
                    {"test_spec": dossier_payload}
                )
                self.assertTrue(
                    any(
                        "tc-control-update-001" in item.related_test_cases
                        for item in unresolved
                    )
                )

        reference = ArtifactReference(
            "function_signature",
            "reports/function_signature.json",
            "3" * 64,
        )
        generation_mutations = (
            (
                "setup_list",
                lambda case: case.__setitem__(
                    "stub_setups",
                    [{"setup_kind": [], "value_expression": "OK"}],
                ),
                "invalid_setup_kind",
            ),
            (
                "setup_object",
                lambda case: case.__setitem__(
                    "stub_setups",
                    [{"setup_kind": {}, "value_expression": "OK"}],
                ),
                "invalid_setup_kind",
            ),
            (
                "expression_bomb",
                lambda case: case.__setitem__(
                    "expected_observations",
                    [
                        {
                            "observation_kind": "return_value",
                            "expected_expression": ExplodingString("OK"),
                        }
                    ],
                ),
                "unresolved_executable_value",
            ),
        )
        for label, mutate, expected_code in generation_mutations:
            with self.subTest(consumer="generation", case=label):
                design = self.minimal_design()
                case = design["additional_case_candidates"][0]
                mutate(case)
                with self.assertRaises(TestSpecContractError) as raised:
                    create_test_spec_from_design(
                        design,
                        {
                            "source": {
                                "path": "src/control.c",
                                "sha256": "1" * 64,
                            },
                            "function": {"name": "Control_Update"},
                        },
                        source_path="src/control.c",
                        generated_from=[reference],
                    )
                self.assertIn(
                    expected_code,
                    {item.code for item in raised.exception.violations},
                )

    def test_strict_unresolved_valid_shape_is_shared_with_dossier(self):
        for label, related_case_ids in (
            ("missing_related_list", None),
            ("exact_related_list", ["tc_control-update-001"]),
        ):
            with self.subTest(shape=label):
                payload = copied_payload()
                unresolved_item = {
                    "item_kind": " expected_return_unknown ",
                    "severity": "warning",
                }
                if related_case_ids is not None:
                    unresolved_item["related_test_case_ids"] = related_case_ids
                payload["data"]["unresolved_items"] = [unresolved_item]

                self.assertEqual(
                    (),
                    validate_payload(ArtifactKind.TEST_SPEC, payload),
                )
                loaded = TestSpec.from_payload(payload)
                review_items, unresolved = build_review_items(
                    {"test_spec": loaded.to_payload()["data"]}
                )

                self.assertIsInstance(review_items, list)
                self.assertTrue(unresolved)
                if related_case_ids is not None:
                    self.assertEqual(
                        related_case_ids,
                        loaded.unresolved_items[0]["related_test_case_ids"],
                    )

    def test_generation_does_not_preserve_nested_raw_review_authority(self):
        design = self.minimal_design()
        design["additional_case_candidates"][0]["input_assignments"] = [
            {
                "target_name": "mode",
                "value_expression": "MODE_AUTO",
                "review_item_ids": ["RAW_REVIEW_001"],
            }
        ]

        spec = create_test_spec_from_design(
            design,
            {
                "source": {"path": "src/control.c", "sha256": "1" * 64},
                "function": {"name": "Control_Update"},
            },
            source_path="src/control.c",
            generated_from=[
                ArtifactReference(
                    "function_signature",
                    "reports/function_signature.json",
                    "3" * 64,
                )
            ],
        )

        self.assertEqual([], spec.review_item_ids)
        self.assertNotIn("RAW_REVIEW_001", str(spec.to_payload()))

    def test_generation_and_dossier_share_semantic_review_identity(self):
        design = {
            "generation_policy": {},
            "test_cases": [],
            "additional_case_candidates": [
                {
                    "test_case_id": "TC-01",
                    "coverage_links": [{"coverage_id": "COV-01"}],
                }
            ],
            "coverage_summary": {
                "total_coverage_items": 1,
                "covered_by_design_count": 1,
                "uncovered_coverage_ids": [],
                "coverage_to_test_cases": {"COV-01": ["TC-01"]},
            },
            "unresolved_items": [
                {
                    "item_id": "UNRESOLVED_LEGACY_001",
                    "item_kind": "expected_return_unknown",
                    "description": "Localized display text is not identity.",
                    "related_test_case_ids": ["TC-01"],
                    "reason": "Static analysis cannot prove the oracle.",
                    "suggested_action": "Review the function specification.",
                }
            ],
            "warnings": [],
        }
        signature = {
            "source": {"path": "src/control.c", "sha256": "1" * 64},
            "function": {"name": "Control_Update"},
        }

        spec = create_test_spec_from_design(
            design,
            signature,
            source_path="src/control.c",
            generated_from=[
                ArtifactReference(
                    "function_signature",
                    "reports/function_signature.json",
                    "3" * 64,
                )
            ],
        )
        dossier_items, _unresolved = build_review_items(
            {"test_spec": spec.to_payload()["data"]}
        )

        self.assertEqual(1, len(spec.review_item_ids))
        self.assertEqual(
            spec.review_item_ids,
            spec.additional_case_candidates[0]["review_item_ids"],
        )
        self.assertEqual(spec.review_item_ids, [dossier_items[0].review_id])
        self.assertNotIn("UNRESOLVED_LEGACY_001", spec.review_item_ids)

    def test_only_test_spec_advances_to_v1_1(self):
        self.assertEqual("1.1.0", get_contract(ArtifactKind.TEST_SPEC).current_version)
        self.assertEqual("1.0.0", get_contract(ArtifactKind.CLI_RESULT).current_version)
        self.assertEqual("1.0.0", get_contract(ArtifactKind.TEST_SPEC, "1.0.0").current_version)
        versions = {
            item.current_version
            for item in iter_contract_versions()
            if item.kind is ArtifactKind.TEST_SPEC
        }
        self.assertEqual({"1.0.0", "1.1.0"}, versions)

    def assert_violation(self, payload: dict, code: str) -> None:
        spec = TestSpec.from_payload(payload, validate=False)
        violations = validate_test_spec(spec, current_context=current_context())
        self.assertIn(code, {item.code for item in violations}, violations)

    def test_valid_contract_has_no_violations(self):
        spec = TestSpec.from_payload(copied_payload())

        self.assertEqual((), validate_test_spec(spec, current_context=current_context()))
        self.assertNotIn("review_status", str(spec.to_payload()))

    def test_duplicate_case_id_across_executable_and_candidate_is_rejected(self):
        payload = copied_payload()
        payload["data"]["additional_case_candidates"].append(
            {
                "test_case_id": "tc-control-update-001",
                "coverage_links": [{"coverage_id": "cov-normal"}],
            }
        )

        self.assert_violation(payload, "duplicate_id")

    def test_dangling_coverage_review_and_dependency_references_are_rejected(self):
        payload = copied_payload()
        case = payload["data"]["test_cases"][0]
        case["coverage_links"][0]["coverage_id"] = "cov-missing"
        case["input_assignments"][0]["review_item_ids"] = ["review-missing"]
        case["stub_setups"][0]["related_dependency_id"] = "dep-missing"

        spec = TestSpec.from_payload(payload, validate=False)
        codes = {
            item.code
            for item in validate_test_spec(spec, current_context=current_context())
        }

        self.assertTrue(
            {"invalid_coverage_reference", "invalid_review_reference", "invalid_dependency_reference"}.issubset(codes),
            codes,
        )

    def test_embedded_approval_or_review_status_authority_is_rejected(self):
        for field, value in (("approved", True), ("approval", "accepted"), ("review_status", "approved")):
            with self.subTest(field=field):
                payload = copied_payload()
                payload["data"]["test_cases"][0][field] = value
                self.assert_violation(payload, "embedded_review_authority")

    def test_unresolved_executable_value_and_oracle_are_rejected(self):
        for path, value in (("value_expression", "TBD_INPUT"), ("expected_expression", None)):
            with self.subTest(field=path):
                payload = copied_payload()
                case = payload["data"]["test_cases"][0]
                target = case["input_assignments"][0] if path == "value_expression" else case["expected_observations"][0]
                target[path] = value
                self.assert_violation(payload, "unresolved_executable_value")

    def test_stale_source_and_signature_are_compared_to_explicit_context(self):
        payload = copied_payload()
        payload["data"]["source"]["sha256"] = "a" * 64
        payload["subject"]["source_sha256"] = "a" * 64
        payload["data"]["function"]["signature_sha256"] = "b" * 64

        spec = TestSpec.from_payload(payload, validate=False)
        codes = {
            item.code
            for item in validate_test_spec(spec, current_context=current_context())
        }

        self.assertIn("stale_source", codes)
        self.assertIn("stale_signature", codes)

    def test_generated_from_references_are_compared_to_explicit_current_artifacts(self):
        spec = TestSpec.from_payload(copied_payload())
        base = current_context()
        context = CurrentArtifactContext(
            source_path=base.source_path,
            source_sha256=base.source_sha256,
            function_id=base.function_id,
            function_name=base.function_name,
            signature_sha256=base.signature_sha256,
            generated_from=(
                ArtifactReference(
                    artifact_kind="function_signature",
                    path="reports/function_signature.json",
                    sha256="f" * 64,
                ),
            ),
        )

        codes = {item.code for item in validate_test_spec(spec, current_context=context)}

        self.assertIn("stale_generated_from", codes)


if __name__ == "__main__":
    unittest.main()
