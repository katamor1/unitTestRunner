import json
import unittest
from importlib import resources

from jsonschema import Draft202012Validator

from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.contracts.registry import iter_contracts
from unit_test_runner.contracts.validator import validate_payload


SHA256 = "7b18e68b2afcf1b0f0a1b857c5d1fcb2cf9db4d1540d778a266dbeaa3aa176a8"


def generic_payload(kind: ArtifactKind) -> dict:
    return {
        "artifact_kind": kind.value,
        "schema_version": "1.0.0",
        "producer": {
            "name": "unit-test-runner",
            "version": "0.1.0",
            "commit": "test-commit",
        },
        "subject": {
            "function_id": "fn_contract_test",
            "source_path": "src/contract_test.c",
            "source_sha256": SHA256,
        },
        "data": {},
        "extensions": {},
    }


class PublicArtifactSchemaTests(unittest.TestCase):
    def test_schema_package_contains_exactly_one_file_per_kind_plus_common(self):
        root = resources.files("unit_test_runner.schemas")
        actual = {item.name for item in root.iterdir() if item.name.endswith(".json")}
        expected = {"common.schema.json"} | {
            contract.schema_resource for contract in iter_contracts()
        }

        self.assertEqual(expected, actual)

    def test_every_schema_is_valid_draft_2020_12_with_unique_id(self):
        root = resources.files("unit_test_runner.schemas")
        identifiers = []
        for item in root.iterdir():
            if not item.name.endswith(".json"):
                continue
            schema = json.loads(item.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self.assertEqual(
                "https://json-schema.org/draft/2020-12/schema",
                schema["$schema"],
            )
            identifiers.append(schema["$id"])

        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_generic_artifact_schemas_enforce_the_common_envelope(self):
        specialized = {ArtifactKind.CLI_RESULT, ArtifactKind.TEST_SPEC}
        for kind in ArtifactKind:
            if kind in specialized:
                continue
            with self.subTest(kind=kind.value):
                self.assertEqual((), validate_payload(kind, generic_payload(kind)))


if __name__ == "__main__":
    unittest.main()
