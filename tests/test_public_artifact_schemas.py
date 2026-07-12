import json
import unittest
from importlib import resources

from jsonschema import Draft202012Validator

from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.contracts.registry import iter_contract_versions
from unit_test_runner.contracts.validator import validate_payload


SHA256 = "7b18e68b2afcf1b0f0a1b857c5d1fcb2cf9db4d1540d778a266dbeaa3aa176a8"
def generic_payload(kind: ArtifactKind) -> dict:
    return {
        "artifact_kind": kind.value,
        "schema_version": next(
            contract.current_version
            for contract in iter_contract_versions()
            if contract.kind is kind
            and contract.schema_resource == f"{kind.value}.schema.json"
        ),
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


def schema_references(value):
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str):
            yield reference
        for child in value.values():
            yield from schema_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from schema_references(child)


class PublicArtifactSchemaTests(unittest.TestCase):
    def test_schema_package_contains_exactly_one_file_per_kind_plus_common(self):
        root = resources.files("unit_test_runner.schemas")
        actual = {item.name for item in root.iterdir() if item.name.endswith(".json")}
        expected = {"common.schema.json"} | {
            contract.schema_resource for contract in iter_contract_versions()
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

    def test_every_schema_reference_resolves_to_a_packaged_definition(self):
        root = resources.files("unit_test_runner.schemas")
        documents = {
            item.name: json.loads(item.read_text(encoding="utf-8"))
            for item in root.iterdir()
            if item.name.endswith(".json")
        }
        for resource_name, schema in documents.items():
            for reference in schema_references(schema):
                with self.subTest(resource=resource_name, reference=reference):
                    target_name, separator, fragment = reference.partition("#")
                    target = documents[target_name or resource_name]
                    if not separator or not fragment:
                        continue
                    self.assertTrue(fragment.startswith("/$defs/"), reference)
                    definition_name = fragment.removeprefix("/$defs/")
                    self.assertIn(definition_name, target["$defs"])

    def test_every_artifact_schema_rejects_unmodeled_empty_data(self):
        for kind in ArtifactKind:
            with self.subTest(kind=kind.value):
                violations = validate_payload(kind, generic_payload(kind))
                self.assertTrue(
                    any(
                        item.code == "required_property"
                        and item.json_path == "$.data"
                        for item in violations
                    ),
                    violations,
                )


if __name__ == "__main__":
    unittest.main()
