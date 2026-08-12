from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from argparse import _SubParsersAction
from dataclasses import fields
from importlib import resources
from inspect import signature
from pathlib import Path

from jsonschema import Draft202012Validator

from unit_test_runner.cli.artifacts import build_produced_artifact
from unit_test_runner.cli.outcomes import DomainOutcome
from unit_test_runner.cli.parser import build_parser
from unit_test_runner.cli.result import CLIResult
from unit_test_runner import contracts as contracts_module
from unit_test_runner.contracts import (
    ArtifactKind,
    LoadedArtifact,
    RunOutcome,
    load_artifact,
    validate_artifact,
    validate_cli_envelope,
)
from unit_test_runner.dossier.artifact_collector import collect_artifacts
from unit_test_runner.dossier.dossier_validator import validate_artifacts
from unit_test_runner.dossier.finalizer import finalize_function_dossier
from unit_test_runner.test_spec.repository import (
    load_test_spec,
    load_test_spec_snapshot,
)


EXPECTED_ARTIFACT_KINDS = {
    "function_dossier",
    "test_spec",
    "review_record",
    "build_probe_report",
    "test_run_report",
    "reanalysis_report",
    "suite_manifest",
    "suite_run_report",
}

EXPECTED_COMMANDS = {
    "doctor",
    "discover-projects",
    "map-source",
    "list-functions",
    "analyze-function",
    "finalize-dossier",
    "review-set",
    "get-test-input-form",
    "apply-test-input-form",
    "build-probe",
    "run-tests",
    "reanalyze-function",
    "apply-reanalysis",
    "suite-register",
    "suite-update",
    "suite-remove",
    "suite-list",
    "suite-run",
}


def subject() -> dict[str, str]:
    return {
        "source_path": "src/control.c",
        "source_sha256": "a" * 64,
        "function": "Control_Update",
        "project": "Control",
        "configuration": "Control - Win32 Debug",
    }


def dossier_data() -> dict[str, object]:
    return {
        "target": {},
        "project_membership": [],
        "build_context": {},
        "function": {},
        "test_design": {},
        "diagnostics": [],
        "workspace_root": ".",
        "created_at": "2026-08-11T00:00:00Z",
        "artifact_index": [],
        "summaries": {},
        "traceability": [],
        "review_items": [],
        "unresolved_items": [],
        "next_actions": [],
        "readiness": {},
        "warnings": [],
    }


def test_spec_data(revision: int = 1) -> dict[str, object]:
    return {
        "spec_id": "spec-control-update",
        "revision": revision,
        "source": {"path": "src/control.c", "sha256": "a" * 64},
        "function": {"name": "Control_Update"},
        "generated_from": [],
        "generation_policy": {},
        "test_cases": [],
        "additional_case_candidates": [],
        "coverage_summary": {},
        "unresolved_items": [],
        "warnings": [],
        "review_item_ids": [],
    }


def test_run_data(run_id: str = "run-0001", outcome: str = "passed") -> dict[str, object]:
    return {
        "run_id": run_id,
        "outcome": outcome,
        "executed": outcome != "planned",
        "test_spec_sha256": "b" * 64,
        "requested_case_ids": [],
        "started_case_ids": [],
        "completed_case_ids": [],
        "not_run_case_ids": [],
        "summary": {},
        "case_results": [],
        "warnings": [],
    }


def reanalysis_data() -> dict[str, object]:
    snapshot = {
        "snapshot_id": "snapshot-1",
        "function_name": "Control_Update",
        "source_path": "src/control.c",
        "source_sha256": "a" * 64,
        "build_context_hash": None,
        "created_at": None,
        "artifacts": {},
    }
    return {
        "change_impact": {
            "status": "unchanged",
            "previous_snapshot": snapshot,
            "current_snapshot": dict(snapshot),
            "source_changes": [],
            "interface_changes": [],
            "dependency_changes": [],
            "coverage_changes": [],
            "test_design_impacts": [],
            "regression_recommendation": None,
            "warnings": [],
        },
        "test_case_reconciliation": {
            "status": "unchanged",
            "preserved_test_cases": [],
            "updated_test_cases": [],
            "obsolete_test_cases": [],
            "blocked_test_cases": [],
            "new_test_case_candidates": [],
            "manual_merge_items": [],
            "warnings": [],
        },
        "regression_selection": {
            "status": "unchanged",
            "selected_test_cases": [],
            "skipped_test_cases": [],
            "new_required_test_cases": [],
            "blocked_test_cases": [],
            "selection_reason_summary": "",
            "warnings": [],
        },
    }


def artifact_payload(kind: ArtifactKind) -> dict[str, object]:
    data: dict[str, object] = {"representative": True}
    if kind is ArtifactKind.FUNCTION_DOSSIER:
        data = dossier_data()
    elif kind is ArtifactKind.TEST_SPEC:
        data = test_spec_data()
    elif kind is ArtifactKind.TEST_RUN_REPORT:
        data = test_run_data()
    elif kind is ArtifactKind.REVIEW_RECORD:
        data = {
            "artifact_kind": "test_spec",
            "artifact_sha256": "b" * 64,
            "decision": "approved",
            "reviewer": "reviewer@example.com",
            "reviewed_at": "2026-08-11T00:00:00Z",
            "comment": "ready",
        }
    elif kind is ArtifactKind.BUILD_PROBE_REPORT:
        data = {
            "status": "not_run",
            "executed": False,
            "exit_code": None,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "commands": [],
            "diagnostics": [],
            "missing_includes": [],
            "unresolved_symbols": [],
            "pch_issues": [],
            "vc6_compatibility_issues": [],
            "log_files": [],
        }
    elif kind is ArtifactKind.REANALYSIS_REPORT:
        data = reanalysis_data()
    elif kind is ArtifactKind.SUITE_MANIFEST:
        data = {"suite_id": "default", "revision": 1, "entries": []}
    elif kind is ArtifactKind.SUITE_RUN_REPORT:
        fingerprints = {
            name: {"expected": "b" * 64, "actual": "b" * 64}
            for name in ("source_sha256", "test_spec_sha256", "harness_sha256")
        }
        data = {
            "outcome": "passed",
            "suite_id": "default",
            "manifest_revision": 1,
            "selector": {"kind": "all"},
            "policy": {
                "run_tests": True,
                "dry_run": False,
                "timeout_seconds": 60,
            },
            "summary": {
                "total": 1,
                "green": 1,
                "not_green": 0,
                "executed": 1,
                "planned": 0,
                "passed": 1,
                "failed": 0,
                "blocked": 0,
                "timed_out": 0,
                "cancelled": 0,
                "error": 0,
            },
            "results": [
                {
                    "entry_id": "control-update-000000000000",
                    "function": "Control_Update",
                    "subject": subject(),
                    "workspace": "workspaces/control-update",
                    "outcome": "passed",
                    "green_status": "green",
                    "executed": True,
                    "total_tests": 1,
                    "passed_tests": 1,
                    "failed_tests": 0,
                    "inconclusive_tests": 0,
                    "unresolved_review_count": 0,
                    "changed_fields": [],
                    "fingerprints": fingerprints,
                }
            ],
        }
    return {
        "schema_version": "1.0.0",
        "artifact_kind": kind.value,
        "subject": subject(),
        "data": data,
    }


class V01PublicContractTests(unittest.TestCase):
    def test_strict_only_contract_api_has_no_compatibility_metadata(self) -> None:
        self.assertFalse(hasattr(contracts_module, "ContractMode"))
        self.assertNotIn("mode", signature(load_artifact).parameters)
        self.assertEqual(
            ("kind", "payload", "violations"),
            tuple(field.name for field in fields(LoadedArtifact)),
        )

    def test_strict_only_workflow_api_has_no_ignored_schema_knobs(self) -> None:
        for function in (
            load_test_spec,
            load_test_spec_snapshot,
            collect_artifacts,
            validate_artifacts,
            finalize_function_dossier,
        ):
            parameters = signature(function).parameters
            self.assertNotIn("mode", parameters, function.__name__)
            self.assertNotIn(
                "strict_schema_version",
                parameters,
                function.__name__,
            )
        self.assertNotIn("policy", signature(finalize_function_dossier).parameters)
        finalize_args = build_parser().parse_args(
            ["finalize-dossier", "--workspace", "workspace"]
        )
        self.assertFalse(hasattr(finalize_args, "allow_missing_optional_artifacts"))

    def test_public_artifact_kind_set_is_exact(self) -> None:
        self.assertEqual(EXPECTED_ARTIFACT_KINDS, {item.value for item in ArtifactKind})
        self.assertEqual(
            {
                "planned",
                "passed",
                "failed",
                "blocked",
                "timed_out",
                "cancelled",
                "error",
            },
            {item.value for item in RunOutcome},
        )

    def test_schema_package_contains_only_public_contracts(self) -> None:
        root = resources.files("unit_test_runner.schemas")
        actual = {
            item.name
            for item in root.iterdir()
            if item.name.endswith(".json")
        }
        expected = {"common.schema.json", "cli_envelope.schema.json"} | {
            f"{kind}.schema.json" for kind in EXPECTED_ARTIFACT_KINDS
        }
        self.assertEqual(expected, actual)

    def test_schemas_are_draft_2020_12_and_refs_resolve(self) -> None:
        root = resources.files("unit_test_runner.schemas")
        documents = {
            item.name: json.loads(item.read_text(encoding="utf-8"))
            for item in root.iterdir()
            if item.name.endswith(".json")
        }
        identifiers: set[str] = set()
        for name, schema in documents.items():
            Draft202012Validator.check_schema(schema)
            self.assertEqual(
                "https://json-schema.org/draft/2020-12/schema",
                schema["$schema"],
                name,
            )
            self.assertNotIn(schema["$id"], identifiers)
            identifiers.add(schema["$id"])
            for reference in self._references(schema):
                target = reference.split("#", 1)[0]
                if target:
                    self.assertIn(target, documents, f"{name}: {reference}")

    def test_every_public_artifact_validates_strictly(self) -> None:
        for kind in ArtifactKind:
            payload = artifact_payload(kind)
            self.assertEqual((), validate_artifact(kind, payload), kind)

            old = dict(payload)
            old["schema_version"] = "1.1.0"
            self.assertTrue(validate_artifact(kind, old), kind)

            wrong = dict(payload)
            wrong["artifact_kind"] = next(
                item.value for item in ArtifactKind if item is not kind
            )
            self.assertTrue(validate_artifact(kind, wrong), kind)

    def test_cli_envelope_shape_is_exact(self) -> None:
        result = CLIResult(
            status="ok",
            exit_code=0,
            command="doctor",
            message="ready",
            outcome=DomainOutcome("command", RunOutcome.PASSED, True),
            diagnostics=[{"code": "ready", "level": "info", "message": "ready"}],
        )
        payload = result.to_dict()
        self.assertEqual(
            {"command", "outcome", "message", "artifacts", "diagnostics"},
            set(payload),
        )
        self.assertEqual("passed", payload["outcome"])
        self.assertEqual((), validate_cli_envelope(payload))

    def test_cli_result_rejects_outcome_exit_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "outcome.*exit"):
            CLIResult(
                status="error",
                exit_code=0,
                command="run-tests",
                message="failed",
                outcome=DomainOutcome("test_run", RunOutcome.FAILED, False),
            ).to_dict()
        with self.assertRaisesRegex(ValueError, "outcome.*exit"):
            CLIResult(
                status="error",
                exit_code=2,
                command="doctor",
                message="ready",
                outcome=DomainOutcome("command", RunOutcome.PASSED, True),
            ).to_dict()

    def test_produced_artifact_reloads_bytes_and_reports_exact_public_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "function_dossier.json"
            raw = json.dumps(
                artifact_payload(ArtifactKind.FUNCTION_DOSSIER),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            path.write_bytes(raw)

            produced = build_produced_artifact(
                root,
                path,
                kind=ArtifactKind.FUNCTION_DOSSIER.value,
            )

            self.assertEqual(
                {
                    "kind": "function_dossier",
                    "path": "function_dossier.json",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
                produced.to_dict(),
            )

    def test_supported_cli_command_set_is_exact(self) -> None:
        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, _SubParsersAction)
        )
        self.assertEqual(EXPECTED_COMMANDS, set(subparsers.choices))

    @classmethod
    def _references(cls, value: object):
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str):
                yield reference
            for child in value.values():
                yield from cls._references(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._references(child)


if __name__ == "__main__":
    unittest.main()
