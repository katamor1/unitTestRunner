import unittest
from importlib import resources


from unit_test_runner.contracts import ArtifactKind, ContractMode, RunOutcome
from unit_test_runner.contracts.registry import get_contract, iter_contracts


class ContractRegistryTests(unittest.TestCase):
    def test_registry_contains_one_current_contract_for_every_artifact_kind(self):
        contracts = tuple(iter_contracts())

        self.assertEqual(set(ArtifactKind), {contract.kind for contract in contracts})
        self.assertEqual(len(ArtifactKind), len(contracts))
        for kind in ArtifactKind:
            contract = get_contract(kind)
            self.assertEqual("1.0.0", contract.current_version)
            self.assertEqual(f"{kind.value}.schema.json", contract.schema_resource)
            self.assertTrue(
                resources.files("unit_test_runner.schemas")
                .joinpath(contract.schema_resource)
                .is_file()
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
