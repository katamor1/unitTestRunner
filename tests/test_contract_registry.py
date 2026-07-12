import json
import unittest
from importlib import resources


from unit_test_runner.contracts import ArtifactKind, ContractMode, RunOutcome
from unit_test_runner.contracts.registry import get_contract, iter_contracts
from unit_test_runner.contracts import validator as contract_validator


class ContractRegistryTests(unittest.TestCase):
    def test_registry_contains_one_current_contract_for_every_artifact_kind(self):
        contracts = tuple(iter_contracts())

        self.assertEqual(set(ArtifactKind), {contract.kind for contract in contracts})
        self.assertEqual(len(ArtifactKind), len(contracts))
        for kind in ArtifactKind:
            contract = get_contract(kind)
            expected_version = (
                "1.1.0"
                if kind in {
                    ArtifactKind.TEST_SPEC,
                    ArtifactKind.REVIEW_DECISIONS,
                    ArtifactKind.FUNCTION_DOSSIER,
                    ArtifactKind.DOSSIER_MANIFEST,
                }
                else "1.0.0"
            )
            self.assertEqual(expected_version, contract.current_version)
            self.assertEqual(f"{kind.value}.schema.json", contract.schema_resource)
            self.assertTrue(
                resources.files("unit_test_runner.schemas")
                .joinpath(contract.schema_resource)
                .is_file()
            )

    def test_registry_uses_artifact_specific_data_contracts_and_semantic_hooks(self):
        root = resources.files("unit_test_runner.schemas")
        common = json.loads(
            root.joinpath("common.schema.json").read_text(encoding="utf-8")
        )
        for kind in ArtifactKind:
            with self.subTest(kind=kind.value):
                contract = get_contract(kind)
                self.assertNotEqual("common.schema.json", contract.schema_resource)
                self.assertEqual(kind.value, contract.semantic_validator)
                schema = json.loads(
                    root.joinpath(contract.schema_resource).read_text(encoding="utf-8")
                )
                overlays = [
                    item
                    for item in schema.get("allOf", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("properties"), dict)
                ]
                self.assertTrue(overlays, contract.schema_resource)
                data_contract = overlays[-1]["properties"].get("data")
                self.assertIsInstance(data_contract, dict, contract.schema_resource)
                self.assertTrue(
                    data_contract.get("$ref")
                    or data_contract.get("required")
                    or data_contract.get("properties"),
                    contract.schema_resource,
                )
                self.assertNotEqual(
                    "common.schema.json#/$defs/reservedData",
                    data_contract.get("$ref"),
                    contract.schema_resource,
                )
                terminal_contract = data_contract
                reference = data_contract.get("$ref")
                if isinstance(reference, str) and reference.startswith(
                    "common.schema.json#/$defs/"
                ):
                    terminal_contract = common["$defs"][
                        reference.removeprefix("common.schema.json#/$defs/")
                    ]
                self.assertNotEqual(
                    {"not": {}},
                    terminal_contract,
                    contract.schema_resource,
                )

    def test_semantic_dispatch_is_total_for_every_registered_hook(self):
        registered_names = getattr(
            contract_validator,
            "semantic_validator_names",
            lambda: frozenset(),
        )()

        self.assertEqual(
            {contract.semantic_validator for contract in iter_contracts()},
            set(registered_names),
        )

    def test_public_enums_have_stable_machine_values(self):
        self.assertEqual({"compatible", "strict"}, {item.value for item in ContractMode})
        self.assertEqual(
            {
                "planned",
                "passed",
                "failed",
                "blocked",
                "inconclusive",
                "cancelled",
                "timed_out",
                "error",
            },
            {item.value for item in RunOutcome},
        )


if __name__ == "__main__":
    unittest.main()
