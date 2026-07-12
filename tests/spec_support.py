from __future__ import annotations

"""Shared canonical TestSpec fixtures for test modules."""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_SHA = "1" * 64
SIGNATURE_SHA = "2" * 64


def valid_test_spec_payload() -> dict:
    return {
        "artifact_kind": "test_spec",
        "schema_version": "1.1.0",
        "producer": {
            "name": "unit-test-runner",
            "version": "0.1.0",
            "commit": "test-commit",
        },
        "subject": {
            "function_id": "fn-control-update",
            "source_path": "src/control.c",
            "source_sha256": SOURCE_SHA,
        },
        "data": {
            "spec_id": "spec-control-update",
            "revision": 1,
            "source": {"path": "src/control.c", "sha256": SOURCE_SHA},
            "function": {
                "function_id": "fn-control-update",
                "name": "Control_Update",
                "signature_sha256": SIGNATURE_SHA,
            },
            "generated_from": [
                {
                    "artifact_kind": "function_signature",
                    "path": "reports/function_signature.json",
                    "sha256": "3" * 64,
                }
            ],
            "generation_policy": {"dependency_ids": ["dep-read-sensor"]},
            "test_cases": [
                {
                    "test_case_id": "tc-control-update-001",
                    "title": "normal case",
                    "target_function": "Control_Update",
                    "purpose": "normal path",
                    "priority": "high",
                    "case_kind": "branch",
                    "input_assignments": [
                        {
                            "target_name": "mode",
                            "value_expression": "MODE_AUTO",
                            "review_item_ids": ["review-input-001"],
                        }
                    ],
                    "stub_setups": [
                        {
                            "stub_name": "ReadSensor",
                            "related_dependency_id": "dep-read-sensor",
                            "value_expression": "SENSOR_OK",
                        }
                    ],
                    "expected_observations": [
                        {
                            "observation_kind": "return_value",
                            "expected_expression": "OK",
                            "review_item_ids": ["review-oracle-001"],
                        }
                    ],
                    "coverage_links": [{"coverage_id": "cov-normal"}],
                }
            ],
            "additional_case_candidates": [],
            "coverage_summary": {
                "total_coverage_items": 1,
                "covered_by_design_count": 1,
                "uncovered_coverage_ids": [],
                "coverage_to_test_cases": {
                    "cov-normal": ["tc-control-update-001"]
                },
            },
            "unresolved_items": [],
            "warnings": [],
            "review_item_ids": ["review-input-001", "review-oracle-001"],
        },
        "extensions": {},
    }


def copied_payload() -> dict:
    return copy.deepcopy(valid_test_spec_payload())


def current_context(workspace: Path | None = None):
    from unit_test_runner.test_spec import ArtifactReference, CurrentArtifactContext

    return CurrentArtifactContext(
        source_path="src/control.c",
        source_sha256=SOURCE_SHA,
        function_id="fn-control-update",
        function_name="Control_Update",
        signature_sha256=SIGNATURE_SHA,
        workspace_root=workspace,
        generated_from=(
            ArtifactReference(
                artifact_kind="function_signature",
                path="reports/function_signature.json",
                sha256="3" * 64,
            ),
        ),
    )


def write_canonical_test_spec(
    workspace: Path,
    *,
    source_path: str,
    function_name: str,
    test_case_id: str,
    coverage_ids: tuple[str, ...] = (),
    expected_expression: str = "0",
    function_fields: dict[str, Any] | None = None,
) -> Path:
    """Write a minimal, freshness-checkable canonical TestSpec test fixture."""
    from unit_test_runner.test_spec import (
        ArtifactReference,
        CurrentArtifactContext,
        TestSpec,
        save_test_spec,
        signature_sha256,
        stable_function_id,
    )

    workspace = Path(workspace).resolve()
    source = workspace / source_path
    if not source.is_file():
        raise FileNotFoundError(source)
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    signature_function = {
        "name": function_name,
        "header_text_normalized": f"int {function_name}(void)",
        "parameters": [],
    }
    signature_function.update(function_fields or {})
    signature_function["name"] = function_name
    signature_payload = {
        "schema_version": "0.1",
        "source": {"path": source_path, "sha256": source_sha},
        "function": signature_function,
        "warnings": [],
    }
    signature_path = reports / "function_signature.json"
    signature_path.write_text(
        json.dumps(signature_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    source_identity = {"path": source_path, "sha256": source_sha}
    function_identity = {"name": function_name, "status": "fixture"}
    fixture_payloads = {
        "source_digest": {
            "schema_version": "0.1",
            "source": source_identity,
            "masking": {},
            "preprocessor": {},
            "token_summary": {},
            "warnings": [],
        },
        "function_location": {
            "schema_version": "0.1",
            "source": {"path": source_path},
            "function": {**function_identity, "candidates": []},
            "warnings": [],
        },
        "global_access": {
            "schema_version": "0.1",
            "source": source_identity,
            "function": function_identity,
            "global_accesses": [],
            "warnings": [],
        },
        "call_report": {
            "schema_version": "0.1",
            "source": source_identity,
            "function": function_identity,
            "calls": [],
            "warnings": [],
        },
        "dependency_policy": {
            "schema_version": "0.1",
            "source": {"path": source_path},
            "function": function_identity,
            "dependencies": [],
            "warnings": [],
        },
        "coverage_design": {
            "schema_version": "0.1",
            "source": source_identity,
            "function": function_identity,
            "coverage_items": [],
            "warnings": [],
        },
        "boundary_candidates": {
            "schema_version": "0.1",
            "source": source_identity,
            "function": function_identity,
            "input_candidates": [],
            "warnings": [],
        },
    }
    function_id = stable_function_id(source_path, function_name)
    signature_hash = signature_sha256(signature_payload)
    reference = ArtifactReference(
        artifact_kind="function_signature",
        path="reports/function_signature.json",
        sha256=hashlib.sha256(signature_path.read_bytes()).hexdigest(),
    )
    references = [reference]
    for artifact_kind, filename in (
        ("source_digest", "source_digest.json"),
        ("function_location", "function_location.json"),
        ("global_access", "global_access.json"),
        ("call_report", "call_report.json"),
        ("dependency_policy", "dependency_policy.json"),
        ("coverage_design", "coverage_design.json"),
        ("boundary_candidates", "boundary_equivalence_candidates.json"),
    ):
        artifact_path = reports / filename
        if artifact_path.is_file():
            artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact_payload.setdefault("schema_version", "0.1")
            artifact_payload.setdefault("source", copy.deepcopy(source_identity))
            artifact_payload.setdefault("function", copy.deepcopy(function_identity))
            artifact_payload.setdefault("warnings", [])
        else:
            artifact_payload = copy.deepcopy(fixture_payloads[artifact_kind])
        artifact_path.write_text(
            json.dumps(artifact_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        references.append(
            ArtifactReference(
                artifact_kind=artifact_kind,
                path=f"reports/{filename}",
                sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            )
        )
    payload = copied_payload()
    payload["subject"] = {
        "function_id": function_id,
        "source_path": source_path,
        "source_sha256": source_sha,
    }
    data = payload["data"]
    data["spec_id"] = f"spec-{function_id}"
    data["source"] = {"path": source_path, "sha256": source_sha}
    data["function"] = {
        "function_id": function_id,
        "name": function_name,
        "signature_sha256": signature_hash,
    }
    data["generated_from"] = [item.to_dict() for item in references]
    data["generation_policy"] = {"dependency_ids": []}
    data["review_item_ids"] = []
    data["unresolved_items"] = []
    data["warnings"] = []
    data["additional_case_candidates"] = []
    data["test_cases"] = [
        {
            "test_case_id": test_case_id,
            "title": "fixture case",
            "target_function": function_name,
            "purpose": "fixture execution",
            "priority": "high",
            "case_kind": "branch",
            "input_assignments": [],
            "stub_setups": [],
            "expected_observations": [
                {
                    "observation_kind": "return_value",
                    "expected_expression": expected_expression,
                }
            ],
            "coverage_links": [
                {"coverage_id": coverage_id} for coverage_id in coverage_ids
            ],
        }
    ]
    data["coverage_summary"] = {
        "total_coverage_items": len(coverage_ids),
        "covered_by_design_count": len(coverage_ids),
        "uncovered_coverage_ids": [],
        "coverage_to_test_cases": {
            coverage_id: [test_case_id] for coverage_id in coverage_ids
        },
    }
    context = CurrentArtifactContext(
        source_path=source_path,
        source_sha256=source_sha,
        function_id=function_id,
        function_name=function_name,
        signature_sha256=signature_hash,
        workspace_root=workspace,
        generated_from=tuple(references),
    )
    path = reports / "test_spec.json"
    save_test_spec(
        path,
        TestSpec.from_payload(payload),
        expected_revision=None,
        current_context=context,
    )
    return path
