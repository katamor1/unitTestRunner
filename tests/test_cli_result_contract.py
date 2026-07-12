import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.cli.artifacts import ExpectedArtifact, ProducedArtifact
from unit_test_runner.cli.outcomes import DomainOutcome
from unit_test_runner.cli.result import CLIResult
from unit_test_runner.contracts import ArtifactKind, RunOutcome, validate_payload


class CliResultContractTests(unittest.TestCase):
    def test_cli_result_serializes_and_validates_one_v1_contract_envelope(self):
        produced = ProducedArtifact(
            kind=ArtifactKind.TEST_EXECUTION_REPORT.value,
            path="runs/run-001/test_execution_report.json",
            exists=True,
            sha256="a" * 64,
            schema_version="1.0.0",
        )
        expected = ExpectedArtifact(
            kind=ArtifactKind.TEST_SPEC.value,
            path="reports/test_spec.json",
        )
        result = CLIResult(
            status="tests_passed",
            exit_code=0,
            command="run-tests",
            message="Tests passed.",
            data={"run_id": "run-001"},
            warnings=["legacy dry-run alias was not used"],
            errors=[],
            outcome=DomainOutcome("test_run", RunOutcome.PASSED, True),
            artifacts=[produced],
            expected_artifacts=[expected],
            invocation_id="inv-001",
            producer_commit="6c3aecac794f18bffd4307213481cbfaf270cdba",
        )

        payload = result.to_dict()

        self.assertEqual(ArtifactKind.CLI_RESULT.value, payload["artifact_kind"])
        self.assertEqual("1.0.0", payload["schema_version"])
        self.assertEqual({"invocation_id": "inv-001"}, payload["subject"])
        self.assertEqual("unit-test-runner", payload["producer"]["name"])
        self.assertEqual("finished", payload["data"]["lifecycle"])
        self.assertEqual("passed", payload["data"]["outcome"])
        self.assertEqual("test_run", payload["data"]["outcome_kind"])
        self.assertTrue(payload["data"]["green"])
        self.assertEqual(0, payload["data"]["exit_code"])
        self.assertEqual({"run_id": "run-001"}, payload["data"]["details"])
        self.assertEqual([produced.to_dict()], payload["data"]["artifacts"])
        self.assertEqual([expected.to_dict()], payload["data"]["expected_artifacts"])
        self.assertEqual(
            [
                {
                    "code": "warning",
                    "severity": "warning",
                    "message": "legacy dry-run alias was not used",
                }
            ],
            payload["data"]["diagnostics"],
        )
        self.assertEqual([], payload["data"]["errors"])
        self.assertNotIn("status", payload)
        self.assertNotIn("command", payload)
        self.assertNotIn("reports", payload)
        self.assertEqual((), validate_payload(ArtifactKind.CLI_RESULT, payload))
        self.assertNotIn("tests_passed", json.dumps(payload, sort_keys=True))

    def test_cli_result_rejects_test_outcome_and_exit_code_disagreement(self):
        for outcome_kind, command in (("test_run", "run-tests"), ("suite_run", "suite-run")):
            with self.subTest(outcome_kind=outcome_kind):
                result = CLIResult(
                    status="failed",
                    exit_code=0,
                    command=command,
                    message="Tests failed.",
                    outcome=DomainOutcome(outcome_kind, RunOutcome.FAILED, False),
                    invocation_id=f"inv-002-{outcome_kind}",
                    producer_commit="6c3aecac794f18bffd4307213481cbfaf270cdba",
                )

                with self.assertRaisesRegex(ValueError, "exit_code"):
                    result.to_dict()

    def test_dossier_path_does_not_fabricate_produced_report_siblings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dossier = Path(temp_dir) / "reports" / "function_dossier.json"
            dossier.parent.mkdir(parents=True)
            dossier.write_text("{}", encoding="utf-8")
            result = CLIResult(
                status="dossier_finalized",
                exit_code=0,
                command="finalize-dossier",
                message="Dossier finalized.",
                data={"dossier": str(dossier)},
                outcome=DomainOutcome("command", RunOutcome.PASSED, None),
                invocation_id="inv-003",
                producer_commit="6c3aecac794f18bffd4307213481cbfaf270cdba",
            )

            payload = result.to_dict()

            self.assertEqual([], payload["data"]["artifacts"])
            self.assertEqual([], payload["data"]["expected_artifacts"])
            self.assertFalse((dossier.parent / "test_execution_report.md").exists())
            self.assertNotIn("reports", payload)


if __name__ == "__main__":
    unittest.main()
