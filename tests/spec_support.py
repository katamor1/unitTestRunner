from __future__ import annotations

"""Shared canonical TestSpec fixtures for test modules."""

import copy
import hashlib
import json
from dataclasses import dataclass
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


def raw_v01_provenance_fixtures(
    *,
    source_path: str,
    source_sha256: str,
    function_name: str,
    function_fields: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return complete raw v0.1 producer shapes for canonical fixture workspaces."""
    position = {"line": 1, "column": 1, "offset": 0}
    source_range = {"start": copy.deepcopy(position), "end": copy.deepcopy(position)}
    type_info = {
        "raw": "int",
        "normalized": "int",
        "base_type": "int",
        "qualifiers": [],
        "storage_class": None,
        "pointer_level": 0,
        "is_const_pointer": None,
        "is_struct": False,
        "is_union": False,
        "is_enum": False,
        "is_typedef_like": False,
        "is_function_pointer": False,
        "is_array": False,
        "array_dimensions": [],
        "confidence": "high",
    }
    overrides = copy.deepcopy(function_fields or {})
    return_type_override = overrides.pop("return_type", None)
    if isinstance(return_type_override, dict):
        type_info = _deep_fixture_merge(type_info, return_type_override)
    signature_function = {
        "name": function_name,
        "status": "parsed",
        "style": "ansi",
        "confidence": "high",
        "signature_range": source_range,
        "header_text_raw": f"int {function_name}(void)",
        "header_text_normalized": f"int {function_name}(void)",
        "storage_class": None,
        "calling_convention": None,
        "return_type": type_info,
        "parameters": [],
        "takes_no_parameters": True,
    }
    signature_function = _deep_fixture_merge(signature_function, overrides)
    signature_function["name"] = function_name
    signature_function["takes_no_parameters"] = not bool(
        signature_function.get("parameters")
    )
    source_identity = {"path": source_path, "sha256": source_sha256}
    function_identity = {"name": function_name, "status": "fixture"}
    return {
        "source_digest": {
            "schema_version": "0.1",
            "source": {
                "path": source_path,
                "encoding": "utf-8",
                "newline": "LF",
                "sha256": source_sha256,
                "line_count": 1,
                "warnings": [],
            },
            "masking": {"masked_source_path": None, "masked_ranges": []},
            "preprocessor": {"includes": [], "macros": [], "directives": []},
            "token_summary": {
                "identifier_count": 0,
                "keyword_count": 0,
                "number_count": 0,
                "operator_count": 0,
                "punctuation_count": 0,
                "unknown_count": 0,
            },
            "warnings": [],
            "tokens": [],
        },
        "function_location": {
            "schema_version": "0.1",
            "source": {"path": source_path},
            "function": {
                "name": function_name,
                "status": "not_found",
                "selected_candidate": None,
                "candidates": [],
                "candidate_count": 0,
            },
            "warnings": [],
        },
        "function_signature": {
            "schema_version": "0.1",
            "source": copy.deepcopy(source_identity),
            "function": signature_function,
            "warnings": [],
        },
        "global_access": {
            "schema_version": "0.1",
            "source": copy.deepcopy(source_identity),
            "function": copy.deepcopy(function_identity),
            "file_scope_declarations": [],
            "local_declarations": [],
            "parameter_accesses": [],
            "global_accesses": [],
            "unresolved_identifiers": [],
            "side_effect_candidates": [],
            "warnings": [],
        },
        "call_report": {
            "schema_version": "0.1",
            "source": copy.deepcopy(source_identity),
            "function": copy.deepcopy(function_identity),
            "calls": [],
            "stub_candidates": [],
            "side_effect_candidates": [],
            "unresolved_calls": [],
            "warnings": [],
        },
        "dependency_policy": {
            "schema_version": "0.1",
            "source": {"path": source_path},
            "function": copy.deepcopy(function_identity),
            "dependencies": [],
            "external_objects": [],
            "warnings": [],
        },
        "coverage_design": {
            "schema_version": "0.1",
            "source": copy.deepcopy(source_identity),
            "function": copy.deepcopy(function_identity),
            "branches": [],
            "switches": [],
            "loops": [],
            "ternaries": [],
            "return_paths": [],
            "condition_expressions": [],
            "coverage_items": [],
            "warnings": [],
        },
        "boundary_candidates": {
            "schema_version": "0.1",
            "source": copy.deepcopy(source_identity),
            "function": copy.deepcopy(function_identity),
            "input_candidates": [],
            "state_candidates": [],
            "stub_return_candidates": [],
            "equivalence_classes": [],
            "boundary_groups": [],
            "coverage_links": [],
            "warnings": [],
        },
    }


def complete_raw_v01_fixture(
    artifact_kind: str,
    payload: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    completed = _deep_fixture_merge(defaults, payload)
    if artifact_kind == "call_report":
        for collection in ("calls", "unresolved_calls"):
            completed[collection] = [
                _deep_fixture_merge(_function_call_fixture(item), item)
                for item in completed[collection]
            ]
    elif artifact_kind == "dependency_policy":
        completed["dependencies"] = [
            _deep_fixture_merge(_dependency_fixture(item), item)
            for item in completed["dependencies"]
        ]
    return completed


def _deep_fixture_merge(defaults: Any, supplied: Any) -> Any:
    if isinstance(defaults, dict) and isinstance(supplied, dict):
        merged = copy.deepcopy(defaults)
        for key, value in supplied.items():
            merged[key] = (
                _deep_fixture_merge(merged[key], value)
                if key in merged
                else copy.deepcopy(value)
            )
        return merged
    return copy.deepcopy(supplied)


def _function_call_fixture(item: dict[str, Any]) -> dict[str, Any]:
    position = {"line": 1, "column": 1, "offset": 0}
    source_range = {"start": copy.deepcopy(position), "end": copy.deepcopy(position)}
    return {
        "call_id": str(item.get("call_id") or "CALL_FIXTURE"),
        "name": str(item.get("name") or "FixtureCall"),
        "target_kind": str(item.get("target_kind") or "external_function"),
        "call_range": copy.deepcopy(source_range),
        "name_position": copy.deepcopy(position),
        "arguments": [],
        "return_usage": {
            "usage_kind": "ignored",
            "consumer_range": None,
            "assigned_to": None,
            "compared_with": None,
            "evidence": "fixture",
            "confidence": "high",
        },
        "nesting_level": 0,
        "conditional_context": None,
        "confidence": "high",
        "evidence": "fixture",
        "warnings": [],
        "link_provider": None,
        "link_providers": [],
    }


def _dependency_fixture(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "callee": str(item.get("callee") or "FixtureCall"),
        "target_kind": str(item.get("target_kind") or "external_function"),
        "configured_mode": "stub",
        "resolved_mode": "stub",
        "review_status": "resolved",
        "signature": {
            "resolution": "exact",
            "return_type_raw": "int",
            "return_type_canonical": "int",
            "return_type_category": "scalar",
            "calling_convention": None,
            "parameters": [],
            "prototype": None,
            "declaration_source": None,
            "definition_source": None,
            "conflicts": [],
            "confidence": "high",
        },
        "implementation_source": None,
        "related_call_ids": [],
        "rewrite_sites": [],
        "evidence": [],
        "shared_globals": [],
        "warnings": [],
    }


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
    fixture_payloads = raw_v01_provenance_fixtures(
        source_path=source_path,
        source_sha256=source_sha,
        function_name=function_name,
        function_fields=function_fields,
    )
    signature_payload = fixture_payloads["function_signature"]
    signature_path = reports / "function_signature.json"
    signature_path.write_text(
        json.dumps(signature_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
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
            artifact_payload = complete_raw_v01_fixture(
                artifact_kind,
                json.loads(artifact_path.read_text(encoding="utf-8")),
                fixture_payloads[artifact_kind],
            )
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


@dataclass(frozen=True)
class TestInputFormFixture:
    workspace: Path
    canonical_path: Path
    source_path: Path
    unresolved_case_id: str
    intentional_candidate_id: str
    concrete_case_id: str


def _fixture_parameter(
    index: int,
    name: str,
    type_raw: str,
    *,
    base_type: str,
    pointer_level: int = 0,
    is_enum: bool = False,
) -> dict[str, Any]:
    return {
        "index": index,
        "name": name,
        "type": {
            "raw": type_raw,
            "normalized": type_raw,
            "base_type": base_type,
            "qualifiers": [],
            "storage_class": None,
            "pointer_level": pointer_level,
            "is_const_pointer": False if pointer_level else None,
            "is_struct": False,
            "is_union": False,
            "is_enum": is_enum,
            "is_typedef_like": False,
            "is_function_pointer": False,
            "is_array": False,
            "array_dimensions": [],
            "confidence": "high",
        },
        "raw": f"{type_raw} {name}",
        "direction_hint": "in",
        "is_variadic": False,
        "is_void": False,
        "default_value": None,
        "confidence": "high",
        "warnings": [],
    }


def _fixture_input_candidate(
    candidate_id: str,
    target_name: str,
    value_expression: str,
    value_kind: str,
    *,
    purpose: str,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "target_name": target_name,
        "target_kind": "parameter",
        "value_expression": value_expression,
        "value_kind": value_kind,
        "source": "fixture_boundary_analysis",
        "related_condition_id": None,
        "related_coverage_ids": ["cov-unresolved"],
        "purpose": purpose,
        "confidence": "high",
        "review_required": False,
        "evidence": f"fixture evidence for {candidate_id}",
    }


def write_test_input_form_fixture(workspace: Path) -> TestInputFormFixture:
    """Write a freshness-valid canonical workspace for form query/apply tests."""
    from unit_test_runner.contracts import ContractMode
    from unit_test_runner.test_spec import (
        build_current_artifact_context,
        load_test_spec_snapshot,
        save_test_spec_snapshot,
    )

    workspace = Path(workspace).resolve()
    source_relative = "src/control.c"
    source_path = workspace / source_relative
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "enum ControlMode { MODE_AUTO = 0, MODE_MANUAL = 1 };\n"
        "int Control_Update(enum ControlMode mode, int flags, int *buffer)\n"
        "{\n"
        "    return (buffer == 0) ? flags : (int)mode;\n"
        "}\n",
        encoding="utf-8",
    )
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    function_fields = {
        "header_text_raw": "int Control_Update(enum ControlMode mode, int flags, int *buffer)",
        "header_text_normalized": "int Control_Update(enum ControlMode mode, int flags, int *buffer)",
        "parameters": [
            _fixture_parameter(
                0,
                "mode",
                "enum ControlMode",
                base_type="enum ControlMode",
                is_enum=True,
            ),
            _fixture_parameter(1, "flags", "int", base_type="int"),
            _fixture_parameter(
                2,
                "buffer",
                "int *",
                base_type="int",
                pointer_level=1,
            ),
        ],
    }
    fixture_payloads = raw_v01_provenance_fixtures(
        source_path=source_relative,
        source_sha256=source_sha,
        function_name="Control_Update",
        function_fields=function_fields,
    )
    boundary = fixture_payloads["boundary_candidates"]
    boundary["input_candidates"] = [
        _fixture_input_candidate(
            "CAND_MODE",
            "mode",
            "MODE_AUTO",
            "enum_member",
            purpose="Select automatic mode.",
        ),
        _fixture_input_candidate(
            "CAND_MODE_DUP",
            "mode",
            "MODE_AUTO",
            "enum_member",
            purpose="Duplicate evidence used to verify suggestion deduplication.",
        ),
        _fixture_input_candidate(
            "CAND_FLAGS_ZERO",
            "flags",
            "0",
            "boundary_at",
            purpose="Clear all flags.",
        ),
        _fixture_input_candidate(
            "CAND_FLAGS_ONE",
            "flags",
            "1",
            "boundary_at",
            purpose="Set the first flag.",
        ),
        _fixture_input_candidate(
            "CAND_BUFFER_NULL",
            "buffer",
            "NULL",
            "null_pointer",
            purpose="Exercise the null pointer path.",
        ),
    ]
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "boundary_equivalence_candidates.json").write_text(
        json.dumps(boundary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    concrete_case_id = "TC_Control_Update_Concrete"
    path = write_canonical_test_spec(
        workspace,
        source_path=source_relative,
        function_name="Control_Update",
        test_case_id=concrete_case_id,
        coverage_ids=("cov-concrete",),
        function_fields=function_fields,
    )
    current = load_test_spec_snapshot(path, mode=ContractMode.STRICT)
    context = build_current_artifact_context(workspace, current.spec)
    unresolved_case_id = "TC_Control_Update_Unresolved"
    intentional_candidate_id = "TC_Control_Update_ADD_001"
    current.spec.test_cases = [
        {
            "test_case_id": concrete_case_id,
            "title": "concrete sibling",
            "target_function": "Control_Update",
            "purpose": "Provide reviewed sibling input evidence.",
            "priority": "high",
            "case_kind": "branch",
            "input_assignments": [
                {
                    "target_kind": "parameter",
                    "target_name": "mode",
                    "value_expression": "MODE_MANUAL",
                    "value_kind": "enum_member",
                    "source_candidate_id": None,
                    "rationale": "Reviewed sibling value.",
                    "review_required": False,
                    "confidence": "high",
                }
            ],
            "state_setups": [],
            "stub_setups": [],
            "expected_observations": [
                {
                    "observation_kind": "return_value",
                    "target_name": "concrete_return",
                    "expected_expression": "0",
                    "source": "fixture_oracle",
                    "review_required": False,
                    "confidence": "high",
                    "note": None,
                }
            ],
            "preconditions": [],
            "execution_steps": [],
            "dependency_overrides": [],
            "coverage_links": [{"coverage_id": "cov-concrete"}],
        }
    ]
    current.spec.additional_case_candidates = [
        {
            "test_case_id": unresolved_case_id,
            "title": "generated unresolved main case",
            "target_function": "Control_Update",
            "purpose": "Exercise unresolved values through the editor.",
            "priority": "high",
            "case_kind": "branch",
            "input_assignments": [
                {
                    "target_kind": "parameter",
                    "target_name": "mode",
                    "value_expression": "TBD_VALID_VALUE",
                    "value_kind": "enum_member",
                    "source_candidate_id": "CAND_MODE",
                    "rationale": "Generated enum candidate.",
                    "review_required": True,
                    "confidence": "high",
                },
                {
                    "target_kind": "parameter",
                    "target_name": "flags",
                    "value_expression": "TODO_FLAGS",
                    "value_kind": "boundary_at",
                    "source_candidate_id": "CAND_FLAGS_ZERO",
                    "rationale": "Inconsistent confirmed placeholder fixture.",
                    "review_required": False,
                    "confidence": "medium",
                },
                {
                    "target_kind": "parameter",
                    "target_name": "buffer",
                    "value_expression": "UNKNOWN_BUFFER",
                    "value_kind": "null_pointer",
                    "source_candidate_id": "CAND_BUFFER_NULL",
                    "rationale": "Generated pointer candidate.",
                    "review_required": True,
                    "confidence": "high",
                },
            ],
            "state_setups": [
                {
                    "variable_name": "g_state",
                    "scope": "global",
                    "value_expression": "UNRESOLVED_STATE",
                    "setup_method_hint": "Assign before calling the function.",
                    "source_candidate_id": None,
                    "review_required": True,
                    "confidence": "medium",
                }
            ],
            "stub_setups": [],
            "expected_observations": [
                {
                    "observation_kind": "return_value",
                    "target_name": "return",
                    "expected_expression": "TBD_EXPECTED_RETURN_INT",
                    "source": "coverage_design",
                    "review_required": True,
                    "confidence": "medium",
                    "note": None,
                }
            ],
            "preconditions": [
                {
                    "description": "VC6 target configuration is selected.",
                    "source": "build_context",
                    "review_required": True,
                }
            ],
            "execution_steps": [
                {
                    "order": 1,
                    "action": "setup_state",
                    "detail": "Apply input assignments and state fixtures.",
                }
            ],
            "dependency_overrides": [
                {
                    "callee": "ReadSensor",
                    "mode": "inherit",
                    "rationale": "",
                    "review_required": True,
                }
            ],
            "coverage_links": [{"coverage_id": "cov-unresolved"}],
        },
        {
            "test_case_id": intentional_candidate_id,
            "title": "intentional extra candidate",
            "target_function": "Control_Update",
            "purpose": "Remain a candidate until explicitly selected by a future workflow.",
            "priority": "low",
            "case_kind": "branch",
            "input_assignments": [],
            "state_setups": [],
            "stub_setups": [],
            "expected_observations": [],
            "preconditions": [],
            "execution_steps": [],
            "dependency_overrides": [],
            "coverage_links": [{"coverage_id": "cov-unresolved"}],
        },
    ]
    current.spec.coverage_summary = {
        "total_coverage_items": 2,
        "covered_by_design_count": 2,
        "uncovered_coverage_ids": [],
        "coverage_to_test_cases": {
            "cov-concrete": [concrete_case_id],
            "cov-unresolved": [unresolved_case_id],
        },
    }
    _saved, _artifact = save_test_spec_snapshot(
        path,
        current.spec,
        expected_revision=current.spec.revision,
        current_context=context,
    )
    return TestInputFormFixture(
        workspace=workspace,
        canonical_path=path,
        source_path=source_path,
        unresolved_case_id=unresolved_case_id,
        intentional_candidate_id=intentional_candidate_id,
        concrete_case_id=concrete_case_id,
    )
