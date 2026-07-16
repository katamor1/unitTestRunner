from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from unit_test_runner.contracts import (
    ArtifactKind,
    migrate_payload,
    validate_payload,
    validate_payload_schema,
)
from unit_test_runner.contracts.registry import get_contract

from .models import ArtifactReference, CurrentArtifactContext, TestSpec
from .path_safety import assert_no_reparse_components, lexical_absolute
from .source_binding import declared_source_matches_selected


_TOP_LEVEL_PROVENANCE_FILES = (
    ("source_digest", "source_digest.json"),
    ("function_location", "function_location.json"),
    ("function_signature", "function_signature.json"),
    ("global_access", "global_access.json"),
    ("call_report", "call_report.json"),
    ("dependency_policy", "dependency_policy.json"),
    ("coverage_design", "coverage_design.json"),
    ("boundary_candidates", "boundary_equivalence_candidates.json"),
)
_REANALYSIS_PROVENANCE_FILES = tuple(
    item for item in _TOP_LEVEL_PROVENANCE_FILES if item[0] != "dependency_policy"
)
_PROVENANCE_LAYOUTS = (
    (Path("reports"), _TOP_LEVEL_PROVENANCE_FILES),
    (Path("reports/reanalysis/current"), _REANALYSIS_PROVENANCE_FILES),
)
_LEGACY_REQUIRED_FIELDS: dict[str, dict[str, type]] = {
    "source_digest": {
        "source": dict,
        "masking": dict,
        "preprocessor": dict,
        "token_summary": dict,
        "warnings": list,
    },
    "function_location": {"source": dict, "function": dict, "warnings": list},
    "function_signature": {"source": dict, "function": dict, "warnings": list},
    "global_access": {
        "source": dict,
        "function": dict,
        "global_accesses": list,
        "warnings": list,
    },
    "call_report": {
        "source": dict,
        "function": dict,
        "calls": list,
        "warnings": list,
    },
    "dependency_policy": {
        "source": dict,
        "function": dict,
        "dependencies": list,
        "warnings": list,
    },
    "coverage_design": {
        "source": dict,
        "function": dict,
        "coverage_items": list,
        "warnings": list,
    },
    "boundary_candidates": {
        "source": dict,
        "function": dict,
        "input_candidates": list,
        "warnings": list,
    },
}
_LEGACY_ALLOWED_FIELDS: dict[str, set[str]] = {
    "source_digest": {
        "schema_version", "source", "masking", "preprocessor",
        "token_summary", "warnings", "tokens",
    },
    "function_location": {"schema_version", "source", "function", "warnings"},
    "function_signature": {"schema_version", "source", "function", "warnings"},
    "global_access": {
        "schema_version", "source", "function", "file_scope_declarations",
        "local_declarations", "parameter_accesses", "global_accesses",
        "unresolved_identifiers", "side_effect_candidates", "warnings",
    },
    "call_report": {
        "schema_version", "source", "function", "calls", "stub_candidates",
        "side_effect_candidates", "unresolved_calls", "warnings",
    },
    "dependency_policy": {
        "schema_version", "source", "function", "dependencies",
        "external_objects", "warnings",
    },
    "coverage_design": {
        "schema_version", "source", "function", "branches", "switches",
        "loops", "ternaries", "return_paths", "condition_expressions",
        "coverage_items", "warnings",
    },
    "boundary_candidates": {
        "schema_version", "source", "function", "input_candidates",
        "state_candidates", "stub_return_candidates", "equivalence_classes",
        "boundary_groups", "coverage_links", "warnings",
    },
}


def _nullable(shape: Any) -> tuple[str, Any]:
    return ("nullable", shape)


def _closed(
    required: dict[str, Any],
    optional: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    return ("closed-object", required, optional or {})


_POSITION_SHAPE = {"line": int, "column": int, "offset": int}
_SHORT_POSITION_SHAPE = {"line": int, "column": int}
_RANGE_SHAPE = {"start": _POSITION_SHAPE, "end": _POSITION_SHAPE}
_MASKED_RANGE_SHAPE = {
    "kind": str,
    "start_line": int,
    "start_column": int,
    "end_line": int,
    "end_column": int,
    "preview": _nullable(str),
}
_FUNCTION_CANDIDATE_SHAPE = {
    "name": str,
    "kind": str,
    "confidence": str,
    "header_range": _RANGE_SHAPE,
    "body_range": _nullable(_RANGE_SHAPE),
    "full_range": _RANGE_SHAPE,
    "opening_brace": _nullable(_POSITION_SHAPE),
    "closing_brace": _nullable(_POSITION_SHAPE),
    "storage_class_hint": _nullable(str),
    "conditional_context": _nullable(dict),
    "signature_preview": str,
    "reason": str,
}
_SIGNATURE_PARAMETER_SHAPE = {
    "index": int,
    "name": _nullable(str),
    "type": dict,
    "raw": str,
    "direction_hint": str,
    "is_variadic": bool,
    "is_void": bool,
    "default_value": _nullable(str),
    "confidence": str,
    "warnings": list,
}
_VARIABLE_DECLARATION_SHAPE = {
    "name": str,
    "scope": str,
    "storage_class": _nullable(str),
    "type_raw": str,
    "declaration_range": _RANGE_SHAPE,
    "initializer_range": _nullable(_RANGE_SHAPE),
    "is_array": bool,
    "is_pointer": bool,
    "is_struct_like": bool,
    "confidence": str,
    "raw": str,
}
_GLOBAL_ACCESS_SHAPE = {
    "name": str,
    "access_kind": str,
    "scope": str,
    "position": _POSITION_SHAPE,
    "expression_range": _RANGE_SHAPE,
    "access_path": _nullable(str),
    "operator": _nullable(str),
    "confidence": str,
    "evidence": str,
    "related_declaration": _nullable(_VARIABLE_DECLARATION_SHAPE),
}
_IDENTIFIER_USE_SHAPE = {
    "name": str,
    "position": _POSITION_SHAPE,
    "context": str,
    "token_index": int,
    "resolved_as": str,
    "confidence": str,
}
_CALL_ARGUMENT_SHAPE = {
    "index": int,
    "raw": str,
    "expression_range": _RANGE_SHAPE,
    "identifiers": [_IDENTIFIER_USE_SHAPE],
    "argument_kind": str,
    "passing_mode_hint": str,
    "confidence": str,
    "warnings": list,
}
_RETURN_USAGE_SHAPE = {
    "usage_kind": str,
    "consumer_range": _nullable(_RANGE_SHAPE),
    "assigned_to": _nullable(str),
    "compared_with": _nullable(str),
    "evidence": str,
    "confidence": str,
}
_LINK_PROVIDER_SHAPE = {
    "library": str,
    "symbol": str,
    "provider_kind": str,
    "source": str,
    "link_order": int,
    "project_name": _nullable(str),
}
_FUNCTION_CALL_SHAPE = {
    "call_id": str,
    "name": str,
    "target_kind": str,
    "call_range": _RANGE_SHAPE,
    "name_position": _POSITION_SHAPE,
    "arguments": [_CALL_ARGUMENT_SHAPE],
    "return_usage": _RETURN_USAGE_SHAPE,
    "nesting_level": int,
    "conditional_context": _nullable(dict),
    "confidence": str,
    "evidence": str,
    "warnings": list,
    "link_provider": _nullable(_LINK_PROVIDER_SHAPE),
    "link_providers": [_LINK_PROVIDER_SHAPE],
}
_RESOLVED_PARAMETER_SHAPE = {
    "index": int,
    "name": _nullable(str),
    "type_raw": str,
    "pointer_level": int,
    "qualifiers": [str],
    "is_variadic": bool,
    "canonical_type": _nullable(str),
    "type_category": str,
}
_RESOLVED_SIGNATURE_SHAPE = {
    "resolution": str,
    "return_type_raw": _nullable(str),
    "return_type_canonical": _nullable(str),
    "return_type_category": str,
    "calling_convention": _nullable(str),
    "parameters": [_RESOLVED_PARAMETER_SHAPE],
    "prototype": _nullable(str),
    "declaration_source": _nullable(str),
    "definition_source": _nullable(str),
    "conflicts": [str],
    "confidence": str,
}
_DEPENDENCY_REWRITE_SITE_SHAPE = {
    "call_id": str,
    "start": _SHORT_POSITION_SHAPE,
    "end": _SHORT_POSITION_SHAPE,
}
_DEPENDENCY_EVIDENCE_SHAPE = {
    "kind": str,
    "detail": str,
    "source": str,
    "weight": int,
}
_DEPENDENCY_SHAPE = {
    "callee": str,
    "target_kind": str,
    "configured_mode": str,
    "resolved_mode": str,
    "review_status": str,
    "signature": _RESOLVED_SIGNATURE_SHAPE,
    "implementation_source": _nullable(str),
    "related_call_ids": [str],
    "rewrite_sites": [_DEPENDENCY_REWRITE_SITE_SHAPE],
    "evidence": [_DEPENDENCY_EVIDENCE_SHAPE],
    "shared_globals": [str],
    "warnings": [str],
}
_COVERAGE_ITEM_SHAPE = {
    "coverage_id": str,
    "coverage_type": str,
    "target_id": str,
    "purpose": str,
    "condition_value": _nullable(str),
    "required_state": _nullable(str),
    "related_variables": [str],
    "related_calls": [str],
    "review_required": bool,
    "confidence": str,
}
_INPUT_CANDIDATE_SHAPE = {
    "candidate_id": str,
    "target_name": str,
    "target_kind": str,
    "value_expression": str,
    "value_kind": str,
    "source": str,
    "related_condition_id": _nullable(str),
    "related_coverage_ids": [str],
    "purpose": str,
    "confidence": str,
    "review_required": bool,
    "evidence": str,
}
_LEGACY_PRIMARY_RECORD_SHAPES: dict[str, tuple[tuple[tuple[str, ...], Any], ...]] = {
    "source_digest": ((('masking', 'masked_ranges'), [_MASKED_RANGE_SHAPE]),),
    "function_location": (
        (("function", "selected_candidate"), _nullable(_FUNCTION_CANDIDATE_SHAPE)),
        (("function", "candidates"), [_FUNCTION_CANDIDATE_SHAPE]),
    ),
    "function_signature": (
        (("function", "signature_range"), _RANGE_SHAPE),
        (("function", "parameters"), [_SIGNATURE_PARAMETER_SHAPE]),
    ),
    "global_access": ((('global_accesses',), [_GLOBAL_ACCESS_SHAPE]),),
    "call_report": (
        (("calls",), [_FUNCTION_CALL_SHAPE]),
        (("unresolved_calls",), [_FUNCTION_CALL_SHAPE]),
    ),
    "dependency_policy": ((('dependencies',), [_DEPENDENCY_SHAPE]),),
    "coverage_design": ((('coverage_items',), [_COVERAGE_ITEM_SHAPE]),),
    "boundary_candidates": ((('input_candidates',), [_INPUT_CANDIDATE_SHAPE]),),
}


_RAW_WARNING_SHAPE = _closed(
    {"code": str, "message": str},
    {
        "line_number": int,
        "column": int,
        "text": str,
    },
)
_RAW_PREPROCESSOR_DIRECTIVE_SHAPE = {
    "kind": str,
    "line_number": int,
    "column": int,
    "raw": str,
    "argument": str,
    "active_state": str,
    "nesting_level": int,
}
_RAW_INCLUDE_SHAPE = {
    "target": str,
    "style": str,
    "line_number": int,
    "resolved_candidates": [str],
    "exists": _nullable(bool),
    "active_state": str,
}
_RAW_MACRO_SHAPE = {
    "name": str,
    "value": _nullable(str),
    "parameters": _nullable([str]),
    "line_number": int,
    "is_function_like": bool,
    "active_state": str,
}
_RAW_TOKEN_SHAPE = {
    "kind": str,
    "value": str,
    "line_number": int,
    "column": int,
    "start_offset": int,
    "end_offset": int,
}
_RAW_TOKEN_SUMMARY_SHAPE = {
    "identifier_count": int,
    "keyword_count": int,
    "number_count": int,
    "operator_count": int,
    "punctuation_count": int,
    "unknown_count": int,
}
_RAW_CONDITIONAL_CONTEXT_SHAPE = {
    "active_state": str,
    "nesting_level": int,
    "directives": [_RAW_PREPROCESSOR_DIRECTIVE_SHAPE],
}
_RAW_FUNCTION_CANDIDATE_SHAPE = {
    "name": str,
    "kind": str,
    "confidence": str,
    "header_range": _RANGE_SHAPE,
    "body_range": _nullable(_RANGE_SHAPE),
    "full_range": _RANGE_SHAPE,
    "opening_brace": _nullable(_POSITION_SHAPE),
    "closing_brace": _nullable(_POSITION_SHAPE),
    "storage_class_hint": _nullable(str),
    "conditional_context": _nullable(_RAW_CONDITIONAL_CONTEXT_SHAPE),
    "signature_preview": str,
    "reason": str,
}
_RAW_TYPE_INFO_SHAPE = {
    "raw": str,
    "normalized": str,
    "base_type": _nullable(str),
    "qualifiers": [str],
    "storage_class": _nullable(str),
    "pointer_level": int,
    "is_const_pointer": _nullable(bool),
    "is_struct": bool,
    "is_union": bool,
    "is_enum": bool,
    "is_typedef_like": bool,
    "is_function_pointer": bool,
    "is_array": bool,
    "array_dimensions": [str],
    "confidence": str,
}
_RAW_SIGNATURE_PARAMETER_SHAPE = {
    "index": int,
    "name": _nullable(str),
    "type": _RAW_TYPE_INFO_SHAPE,
    "raw": str,
    "direction_hint": str,
    "is_variadic": bool,
    "is_void": bool,
    "default_value": _nullable(str),
    "confidence": str,
    "warnings": [_RAW_WARNING_SHAPE],
}
_RAW_PARAMETER_ACCESS_SHAPE = {
    "parameter_name": str,
    "access_kind": str,
    "position": _POSITION_SHAPE,
    "expression_range": _RANGE_SHAPE,
    "access_path": _nullable(str),
    "direction_hint_before_body": str,
    "body_access_hint": str,
    "confidence": str,
    "evidence": str,
}
_RAW_GLOBAL_SIDE_EFFECT_SHAPE = {
    "kind": str,
    "name": _nullable(str),
    "position": _POSITION_SHAPE,
    "expression_range": _RANGE_SHAPE,
    "reason": str,
    "confidence": str,
    "evidence": str,
}
_RAW_CALL_ARGUMENT_SHAPE = {
    "index": int,
    "raw": str,
    "expression_range": _RANGE_SHAPE,
    "identifiers": [_IDENTIFIER_USE_SHAPE],
    "argument_kind": str,
    "passing_mode_hint": str,
    "confidence": str,
    "warnings": [_RAW_WARNING_SHAPE],
}
_RAW_FUNCTION_CALL_SHAPE = {
    "call_id": str,
    "name": str,
    "target_kind": str,
    "call_range": _RANGE_SHAPE,
    "name_position": _POSITION_SHAPE,
    "arguments": [_RAW_CALL_ARGUMENT_SHAPE],
    "return_usage": _RETURN_USAGE_SHAPE,
    "nesting_level": int,
    "conditional_context": _nullable(_RAW_CONDITIONAL_CONTEXT_SHAPE),
    "confidence": str,
    "evidence": str,
    "warnings": [_RAW_WARNING_SHAPE],
    "link_provider": _nullable(_LINK_PROVIDER_SHAPE),
    "link_providers": [_LINK_PROVIDER_SHAPE],
}
_RAW_STUB_CANDIDATE_SHAPE = {
    "name": str,
    "reason": str,
    "target_kind": str,
    "call_count": int,
    "return_value_control_needed": bool,
    "argument_capture_needed": bool,
    "side_effect_control_needed": bool,
    "related_calls": [str],
    "confidence": str,
    "tags": [str],
}
_RAW_CALL_SIDE_EFFECT_SHAPE = {
    "call_id": str,
    "call_name": str,
    "kind": str,
    "argument_index": _nullable(int),
    "related_identifier": _nullable(str),
    "reason": str,
    "confidence": str,
    "evidence": str,
}
_RAW_EXTERNAL_OBJECT_SHAPE = {
    "symbol": str,
    "type_raw": str,
    "configured_mode": str,
    "resolved_mode": str,
    "review_status": str,
    "declaration_header": _nullable(str),
    "definition_source": _nullable(str),
    "definition_candidates": [str],
    "evidence": [_DEPENDENCY_EVIDENCE_SHAPE],
    "warnings": [str],
}
_RAW_CONDITION_OPERAND_SHAPE = {
    "raw": str,
    "operand_kind": str,
    "resolved_as": str,
    "name": _nullable(str),
    "literal_value": _nullable(str),
    "position": _POSITION_SHAPE,
    "confidence": str,
}
_RAW_CONDITION_EXPRESSION_SHAPE = {
    "condition_id": str,
    "raw": str,
    "expression_range": _RANGE_SHAPE,
    "condition_kind": str,
    "operands": [_RAW_CONDITION_OPERAND_SHAPE],
    "operators": [str],
    "related_variables": [str],
    "related_calls": [str],
    "complexity": str,
    "active_state": str,
    "confidence": str,
    "warnings": [_RAW_WARNING_SHAPE],
}
_RAW_BRANCH_SHAPE = {
    "branch_id": str,
    "kind": str,
    "condition": _nullable(_RAW_CONDITION_EXPRESSION_SHAPE),
    "branch_range": _RANGE_SHAPE,
    "body_range": _nullable(_RANGE_SHAPE),
    "parent_branch_id": _nullable(str),
    "nesting_level": int,
    "has_else": bool,
    "else_branch_id": _nullable(str),
    "active_state": str,
    "confidence": str,
    "evidence": str,
}
_RAW_CASE_SHAPE = {
    "case_id": str,
    "label_raw": str,
    "label_kind": str,
    "label_value": _nullable(str),
    "case_range": _RANGE_SHAPE,
    "body_range": _nullable(_RANGE_SHAPE),
    "fallthrough_candidate": bool,
    "confidence": str,
}
_RAW_SWITCH_SHAPE = {
    "switch_id": str,
    "expression": _RAW_CONDITION_EXPRESSION_SHAPE,
    "switch_range": _RANGE_SHAPE,
    "cases": [_RAW_CASE_SHAPE],
    "has_default": bool,
    "active_state": str,
    "confidence": str,
}
_RAW_LOOP_SHAPE = {
    "loop_id": str,
    "kind": str,
    "condition": _nullable(_RAW_CONDITION_EXPRESSION_SHAPE),
    "initializer_raw": _nullable(str),
    "increment_raw": _nullable(str),
    "loop_range": _RANGE_SHAPE,
    "body_range": _nullable(_RANGE_SHAPE),
    "coverage_hints": [str],
    "active_state": str,
    "confidence": str,
}
_RAW_TERNARY_SHAPE = {
    "ternary_id": str,
    "condition": _RAW_CONDITION_EXPRESSION_SHAPE,
    "true_expression_raw": str,
    "false_expression_raw": str,
    "expression_range": _RANGE_SHAPE,
    "confidence": str,
}
_RAW_RETURN_PATH_SHAPE = {
    "return_id": str,
    "return_range": _RANGE_SHAPE,
    "expression_raw": _nullable(str),
    "return_kind": str,
    "related_variables": [str],
    "related_calls": [str],
    "active_state": str,
    "confidence": str,
    "evidence": str,
}
_RAW_STATE_CANDIDATE_SHAPE = {
    "candidate_id": str,
    "variable_name": str,
    "scope": str,
    "value_expression": str,
    "value_kind": str,
    "related_condition_id": _nullable(str),
    "related_coverage_ids": [str],
    "setup_hint": str,
    "confidence": str,
    "review_required": bool,
    "evidence": str,
}
_RAW_STUB_RETURN_CANDIDATE_SHAPE = {
    "candidate_id": str,
    "call_name": str,
    "value_expression": str,
    "value_kind": str,
    "related_call_id": _nullable(str),
    "related_condition_id": _nullable(str),
    "related_coverage_ids": [str],
    "purpose": str,
    "confidence": str,
    "review_required": bool,
    "evidence": str,
}
_RAW_EQUIVALENCE_CLASS_SHAPE = {
    "class_id": str,
    "target_name": str,
    "target_kind": str,
    "class_name": str,
    "representative_values": [str],
    "description": str,
    "related_conditions": [str],
    "related_coverage_ids": [str],
    "confidence": str,
    "review_required": bool,
}
_RAW_BOUNDARY_GROUP_SHAPE = {
    "group_id": str,
    "target_name": str,
    "boundary_expression": str,
    "operator": str,
    "candidates": [str],
    "related_condition_id": str,
    "confidence": str,
    "review_required": bool,
}
_RAW_COVERAGE_LINK_SHAPE = {
    "coverage_id": str,
    "candidate_ids": [str],
    "link_reason": str,
    "confidence": str,
}
_RAW_BOUNDARY_WARNING_SHAPE = _closed(
    {"code": str, "message": str},
    {"related_condition_id": str, "text": str},
)


_LEGACY_PAYLOAD_SHAPES: dict[str, Any] = {
    "source_digest": _closed(
        {
            "schema_version": str,
            "source": {
                "path": str,
                "encoding": str,
                "newline": _nullable(str),
                "sha256": str,
                "line_count": int,
                "warnings": [_RAW_WARNING_SHAPE],
            },
            "masking": {
                "masked_source_path": _nullable(str),
                "masked_ranges": [_MASKED_RANGE_SHAPE],
            },
            "preprocessor": {
                "includes": [_RAW_INCLUDE_SHAPE],
                "macros": [_RAW_MACRO_SHAPE],
                "directives": [_RAW_PREPROCESSOR_DIRECTIVE_SHAPE],
            },
            "token_summary": _RAW_TOKEN_SUMMARY_SHAPE,
            "warnings": [_RAW_WARNING_SHAPE],
        },
        {"tokens": [_RAW_TOKEN_SHAPE]},
    ),
    "function_location": {
        "schema_version": str,
        "source": {"path": str},
        "function": {
            "name": str,
            "status": str,
            "selected_candidate": _nullable(_RAW_FUNCTION_CANDIDATE_SHAPE),
            "candidates": [_RAW_FUNCTION_CANDIDATE_SHAPE],
            "candidate_count": int,
        },
        "warnings": [_RAW_WARNING_SHAPE],
    },
    "function_signature": {
        "schema_version": str,
        "source": {"path": str, "sha256": str},
        "function": {
            "name": str,
            "status": str,
            "style": str,
            "confidence": str,
            "signature_range": _RANGE_SHAPE,
            "header_text_raw": str,
            "header_text_normalized": str,
            "storage_class": _nullable(str),
            "calling_convention": _nullable(str),
            "return_type": _RAW_TYPE_INFO_SHAPE,
            "parameters": [_RAW_SIGNATURE_PARAMETER_SHAPE],
            "takes_no_parameters": bool,
        },
        "warnings": [_RAW_WARNING_SHAPE],
    },
    "global_access": {
        "schema_version": str,
        "source": {"path": str, "sha256": str},
        "function": {"name": str, "status": str},
        "file_scope_declarations": [_VARIABLE_DECLARATION_SHAPE],
        "local_declarations": [_VARIABLE_DECLARATION_SHAPE],
        "parameter_accesses": [_RAW_PARAMETER_ACCESS_SHAPE],
        "global_accesses": [_GLOBAL_ACCESS_SHAPE],
        "unresolved_identifiers": [_IDENTIFIER_USE_SHAPE],
        "side_effect_candidates": [_RAW_GLOBAL_SIDE_EFFECT_SHAPE],
        "warnings": [_RAW_WARNING_SHAPE],
    },
    "call_report": {
        "schema_version": str,
        "source": {"path": str, "sha256": str},
        "function": {"name": str, "status": str},
        "calls": [_RAW_FUNCTION_CALL_SHAPE],
        "stub_candidates": [_RAW_STUB_CANDIDATE_SHAPE],
        "side_effect_candidates": [_RAW_CALL_SIDE_EFFECT_SHAPE],
        "unresolved_calls": [_RAW_FUNCTION_CALL_SHAPE],
        "warnings": [_RAW_WARNING_SHAPE],
    },
    "dependency_policy": {
        "schema_version": str,
        "source": {"path": str},
        "function": {"name": str, "status": str},
        "dependencies": [_DEPENDENCY_SHAPE],
        "external_objects": [_RAW_EXTERNAL_OBJECT_SHAPE],
        "warnings": [str],
    },
    "coverage_design": {
        "schema_version": str,
        "source": {"path": str, "sha256": str},
        "function": {"name": str, "status": str},
        "branches": [_RAW_BRANCH_SHAPE],
        "switches": [_RAW_SWITCH_SHAPE],
        "loops": [_RAW_LOOP_SHAPE],
        "ternaries": [_RAW_TERNARY_SHAPE],
        "return_paths": [_RAW_RETURN_PATH_SHAPE],
        "condition_expressions": [_RAW_CONDITION_EXPRESSION_SHAPE],
        "coverage_items": [_COVERAGE_ITEM_SHAPE],
        "warnings": [_RAW_WARNING_SHAPE],
    },
    "boundary_candidates": {
        "schema_version": str,
        "source": {"path": str, "sha256": str},
        "function": {"name": str, "status": str},
        "input_candidates": [_INPUT_CANDIDATE_SHAPE],
        "state_candidates": [_RAW_STATE_CANDIDATE_SHAPE],
        "stub_return_candidates": [_RAW_STUB_RETURN_CANDIDATE_SHAPE],
        "equivalence_classes": [_RAW_EQUIVALENCE_CLASS_SHAPE],
        "boundary_groups": [_RAW_BOUNDARY_GROUP_SHAPE],
        "coverage_links": [_RAW_COVERAGE_LINK_SHAPE],
        "warnings": [_RAW_BOUNDARY_WARNING_SHAPE],
    },
}


def signature_sha256(payload: Mapping[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, Mapping) and isinstance(data.get("function"), Mapping):
        function = data["function"]
    else:
        function = payload.get("function")
    if not isinstance(function, Mapping):
        raise ValueError("Function signature artifact has no function object.")
    encoded = json.dumps(
        dict(function),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_function_id(source_path: str, function_name: str) -> str:
    normalized_path = _relative_path(source_path)
    name = str(function_name).strip()
    if not name:
        raise ValueError("Function name is required for stable identity.")
    suffix = hashlib.sha256(
        f"{normalized_path}\0{name}".encode("utf-8")
    ).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"fn_{slug or 'function'}_{suffix}"


def build_current_artifact_context(
    workspace: Path,
    spec: TestSpec,
) -> CurrentArtifactContext:
    workspace = lexical_absolute(workspace)
    assert_no_reparse_components(workspace, workspace)
    request_path = workspace / "input" / "request.json"
    request = _read_json(request_path) if request_path.is_file() else {}
    source_path = _relative_path(spec.source.path)
    if request.get("source") and _relative_path(str(request["source"])) != source_path:
        raise ValueError("Canonical test spec source differs from input/request.json.")
    source_candidates = [workspace / source_path, workspace / "extracted" / source_path]
    request_workspace = request.get("workspace")
    if isinstance(request_workspace, str) and request_workspace:
        declared_root = lexical_absolute(Path(request_workspace).expanduser())
        assert_no_reparse_components(declared_root, declared_root)
        declared_source = declared_root / source_path
        try:
            declared_source.relative_to(declared_root)
        except ValueError:
            pass
        else:
            source_candidates.insert(0, declared_source)
    source_file = _first_regular_from_scoped_roots(
        workspace,
        tuple(source_candidates),
        extra_root=(
            lexical_absolute(Path(request_workspace).expanduser())
            if isinstance(request_workspace, str) and request_workspace
            else None
        ),
    )
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    prefix, layout, references = _saved_provenance_layout(spec)
    expected_function = str(request.get("function") or spec.function.name)
    current_references: list[ArtifactReference] = []
    signature_payload: dict[str, Any] | None = None
    for artifact_kind, filename in layout:
        relative_path = (prefix / filename).as_posix()
        artifact_path = _contained_file(workspace, relative_path)
        raw_bytes = artifact_path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        reference = references[artifact_kind]
        if digest != reference.sha256:
            raise ValueError(
                f"Provenance hash mismatch for {artifact_kind}: {relative_path}"
            )
        payload = _validated_provenance_payload(
            artifact_kind,
            raw_bytes,
            source_path=source_path,
            source_sha256=source_hash,
            source_file=source_file,
            function_name=expected_function,
        )
        if artifact_kind == "function_signature":
            signature_payload = payload
        current_references.append(reference)
    if signature_payload is None:
        raise ValueError("Saved provenance has no function_signature artifact.")
    function = signature_payload.get("data")
    if isinstance(function, Mapping):
        function = function.get("function")
    else:
        function = signature_payload.get("function")
    if not isinstance(function, Mapping):
        raise ValueError("Function signature artifact has no current function identity.")
    function_name = str(function.get("name") or "")
    function_id = stable_function_id(source_path, function_name)
    return CurrentArtifactContext(
        source_path=source_path,
        source_sha256=source_hash,
        function_id=function_id,
        function_name=function_name,
        signature_sha256=signature_sha256(signature_payload),
        workspace_root=workspace,
        generated_from=tuple(current_references),
    )


def _saved_provenance_layout(
    spec: TestSpec,
) -> tuple[Path, tuple[tuple[str, str], ...], dict[str, ArtifactReference]]:
    actual = [(item.artifact_kind, item.path) for item in spec.generated_from]
    for prefix, layout in _PROVENANCE_LAYOUTS:
        expected = [(kind, (prefix / filename).as_posix()) for kind, filename in layout]
        if len(actual) == len(expected) and set(actual) == set(expected):
            references = {item.artifact_kind: item for item in spec.generated_from}
            if len(references) != len(spec.generated_from):
                break
            return prefix, layout, references
    raise ValueError(
        "Canonical test spec provenance must exactly match one known producing root "
        "with no missing, duplicate, extra, or redirected artifacts."
    )


def _validated_provenance_payload(
    artifact_kind: str,
    raw_bytes: bytes,
    *,
    source_path: str,
    source_sha256: str,
    source_file: Path,
    function_name: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Invalid {artifact_kind} provenance JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError(f"{artifact_kind} provenance root must be an object.")
    declared_kind = payload.get("artifact_kind")
    is_legacy = declared_kind is None
    if is_legacy:
        _validate_legacy_provenance_shape(artifact_kind, payload)
        normalized = payload
    else:
        if declared_kind != artifact_kind:
            raise ValueError(
                f"Provenance kind mismatch: expected {artifact_kind}, "
                f"received {declared_kind!r}."
            )
        try:
            kind = ArtifactKind(artifact_kind)
        except ValueError as error:
            raise ValueError(f"Unknown provenance artifact kind: {artifact_kind}") from error
        contract = get_contract(kind)
        version = str(payload.get("schema_version") or "")
        if version == contract.current_version:
            normalized = payload
        elif version in contract.compatible_source_versions:
            try:
                normalized = migrate_payload(
                    kind,
                    payload,
                    target_version=contract.current_version,
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid compatible {artifact_kind} provenance: {error}"
                ) from error
        else:
            raise ValueError(
                f"Unsupported {artifact_kind} provenance version: {version or '<missing>'}"
            )
        violations = validate_payload(kind, normalized)
        if violations:
            detail = "; ".join(
                f"{item.code} at {item.json_path}: {item.message}"
                for item in violations
            )
            raise ValueError(
                f"Invalid {artifact_kind} provenance contract: {detail}"
            )
    _validate_provenance_identity(
        artifact_kind,
        normalized,
        source_path=source_path,
        source_sha256=source_sha256,
        source_file=source_file,
        function_name=function_name,
    )
    if is_legacy:
        _validate_legacy_provenance_contract(
            artifact_kind,
            payload,
            source_path=source_path,
            source_sha256=source_sha256,
            function_name=function_name,
        )
    return normalized


def _validate_legacy_provenance_shape(
    artifact_kind: str,
    payload: Mapping[str, Any],
) -> None:
    if payload.get("schema_version") != "0.1":
        raise ValueError(
            f"Untyped {artifact_kind} provenance must be the explicit v0.1 shape."
        )
    requirements = _LEGACY_REQUIRED_FIELDS.get(artifact_kind)
    if requirements is None:
        raise ValueError(f"Unsupported legacy provenance kind: {artifact_kind}")
    invalid = [
        field
        for field, expected_type in requirements.items()
        if not isinstance(payload.get(field), expected_type)
    ]
    if invalid:
        raise ValueError(
            f"Legacy {artifact_kind} provenance has missing or invalid fields: "
            + ", ".join(invalid)
        )
    unknown = set(payload) - _LEGACY_ALLOWED_FIELDS[artifact_kind]
    if unknown:
        raise ValueError(
            f"Legacy {artifact_kind} provenance has unknown fields: "
            + ", ".join(sorted(unknown))
        )
    _validate_legacy_primary_records(artifact_kind, payload)
    function = payload.get("function")
    if artifact_kind == "function_location" and (
        not isinstance(function, Mapping)
        or not isinstance(function.get("candidates"), list)
    ):
        raise ValueError("Legacy function_location has no candidates array.")
    if artifact_kind == "function_signature" and (
        not isinstance(function, Mapping)
        or not isinstance(function.get("parameters"), list)
        or not isinstance(function.get("header_text_normalized"), str)
    ):
        raise ValueError("Legacy function_signature has no parsed signature identity.")
    authority_path = _first_provenance_authority_path(payload)
    if authority_path is not None:
        raise ValueError(
            f"Legacy {artifact_kind} provenance embeds review authority at {authority_path}."
        )


def _validate_legacy_primary_records(
    artifact_kind: str,
    payload: Mapping[str, Any],
) -> None:
    _validate_json_shape(
        dict(payload),
        _LEGACY_PAYLOAD_SHAPES[artifact_kind],
        "$",
        artifact_kind,
    )


def _validate_json_shape(
    value: Any,
    shape: Any,
    path: str,
    artifact_kind: str,
) -> None:
    if (
        isinstance(shape, tuple)
        and len(shape) == 2
        and shape[0] == "nullable"
    ):
        if value is None:
            return
        _validate_json_shape(value, shape[1], path, artifact_kind)
        return
    if (
        isinstance(shape, tuple)
        and len(shape) == 3
        and shape[0] == "closed-object"
    ):
        if type(value) is not dict:
            raise ValueError(
                f"Legacy {artifact_kind} provenance field {path} must be an object."
            )
        required, optional = shape[1], shape[2]
        missing = set(required) - set(value)
        unknown = set(value) - set(required) - set(optional)
        if missing or unknown:
            details: list[str] = []
            if missing:
                details.append("missing " + ", ".join(sorted(missing)))
            if unknown:
                details.append("unknown " + ", ".join(sorted(unknown)))
            raise ValueError(
                f"Legacy {artifact_kind} provenance record {path} has "
                + "; ".join(details)
                + "."
            )
        for field, child_shape in required.items():
            _validate_json_shape(
                value[field], child_shape, f"{path}.{field}", artifact_kind
            )
        for field, child_shape in optional.items():
            if field in value:
                _validate_json_shape(
                    value[field], child_shape, f"{path}.{field}", artifact_kind
                )
        return
    if isinstance(shape, list):
        if type(value) is not list:
            raise ValueError(
                f"Legacy {artifact_kind} provenance field {path} must be an array."
            )
        item_shape = shape[0]
        for index, item in enumerate(value):
            _validate_json_shape(
                item,
                item_shape,
                f"{path}[{index}]",
                artifact_kind,
            )
        return
    if isinstance(shape, dict):
        if type(value) is not dict:
            raise ValueError(
                f"Legacy {artifact_kind} provenance field {path} must be an object."
            )
        missing = set(shape) - set(value)
        unknown = set(value) - set(shape)
        if missing or unknown:
            details: list[str] = []
            if missing:
                details.append("missing " + ", ".join(sorted(missing)))
            if unknown:
                details.append("unknown " + ", ".join(sorted(unknown)))
            raise ValueError(
                f"Legacy {artifact_kind} provenance record {path} has "
                + "; ".join(details)
                + "."
            )
        for field, child_shape in shape.items():
            _validate_json_shape(
                value[field],
                child_shape,
                f"{path}.{field}",
                artifact_kind,
            )
        return
    if not isinstance(shape, type) or type(value) is not shape:
        expected = shape.__name__ if isinstance(shape, type) else "valid JSON"
        raise ValueError(
            f"Legacy {artifact_kind} provenance field {path} must be {expected}."
        )


def _validate_legacy_provenance_contract(
    artifact_kind: str,
    payload: Mapping[str, Any],
    *,
    source_path: str,
    source_sha256: str,
    function_name: str,
) -> None:
    kind = ArtifactKind(artifact_kind)
    data = copy.deepcopy(
        {
            key: value
            for key, value in payload.items()
            if key not in {"artifact_kind", "schema_version"}
        }
    )
    source = data.get("source")
    if isinstance(source, dict):
        source["path"] = source_path
    projection = {
        "artifact_kind": artifact_kind,
        "schema_version": get_contract(kind).current_version,
        "producer": {
            "name": "unit-test-runner-validation",
            "version": "validation-only",
            "commit": "validation-only",
        },
        "subject": {
            "function_id": stable_function_id(source_path, function_name),
            "source_path": source_path,
            "source_sha256": source_sha256,
        },
        "data": data,
        "extensions": {},
    }
    violations = validate_payload_schema(kind, projection)
    if violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}"
            for item in violations
        )
        raise ValueError(
            f"Invalid raw v0.1 {artifact_kind} provenance structure: {detail}"
        )


def _first_provenance_authority_path(value: Any, path: str = "$") -> str | None:
    authority_fields = {
        "approved",
        "approval",
        "approval_status",
        "is_approved",
        "review_decision",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in authority_fields:
                return child_path
            nested = _first_provenance_authority_path(child, child_path)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for index, child in enumerate(value):
            nested = _first_provenance_authority_path(child, f"{path}[{index}]")
            if nested is not None:
                return nested
    return None


def _validate_provenance_identity(
    artifact_kind: str,
    payload: Mapping[str, Any],
    *,
    source_path: str,
    source_sha256: str,
    source_file: Path,
    function_name: str,
) -> None:
    data = payload.get("data")
    identity = data if isinstance(data, Mapping) else payload
    source = identity.get("source")
    if not isinstance(source, Mapping) or not _declared_source_matches(
        str(source.get("path") or ""),
        source_path,
        source_file,
    ):
        raise ValueError(
            f"{artifact_kind} provenance source path does not match {source_path}."
        )
    declared_sha = str(source.get("sha256") or "")
    hash_required = artifact_kind not in {
        "function_location",
        "dependency_policy",
    }
    if (hash_required and not declared_sha) or (
        declared_sha and declared_sha != source_sha256
    ):
        raise ValueError(
            f"{artifact_kind} provenance source hash does not match current source."
        )
    if artifact_kind != "source_digest":
        function = identity.get("function")
        if not isinstance(function, Mapping) or str(function.get("name") or "") != function_name:
            raise ValueError(
                f"{artifact_kind} provenance function does not match {function_name}."
            )
    subject = payload.get("subject")
    if isinstance(subject, Mapping):
        subject_path = subject.get("source_path")
        if subject_path and _relative_path(str(subject_path)) != source_path:
            raise ValueError(f"{artifact_kind} subject source path is inconsistent.")
        subject_sha = subject.get("source_sha256")
        if subject_sha and str(subject_sha) != source_sha256:
            raise ValueError(f"{artifact_kind} subject source hash is inconsistent.")
        subject_function = subject.get("function_id")
        if (
            artifact_kind != "source_digest"
            and subject_function
            and str(subject_function) != stable_function_id(source_path, function_name)
        ):
            raise ValueError(f"{artifact_kind} subject function is inconsistent.")


def _declared_source_matches(
    declared: str,
    expected_relative: str,
    selected_source: Path,
) -> bool:
    return declared_source_matches_selected(
        declared,
        expected_relative,
        selected_source,
    )


def artifact_reference(
    workspace: Path,
    path: Path,
    *,
    artifact_kind: str,
) -> ArtifactReference:
    workspace = lexical_absolute(workspace)
    lexical_path = assert_no_reparse_components(path, workspace)
    relative = lexical_path.relative_to(workspace).as_posix()
    if not lexical_path.is_file():
        raise ValueError(f"Artifact reference must identify a regular non-symlink file: {path}")
    return ArtifactReference(
        artifact_kind=artifact_kind,
        path=relative,
        sha256=hashlib.sha256(lexical_path.read_bytes()).hexdigest(),
    )


def bind_test_spec_inputs(
    workspace: Path,
    spec: TestSpec,
    inputs: Mapping[str, Path | str],
) -> None:
    workspace = Path(workspace).resolve()
    _prefix, _layout, references = _saved_provenance_layout(spec)
    required = {"function_signature", "global_access", "call_report"}
    if "dependency_policy" in references:
        required.add("dependency_policy")
    if set(inputs) != required:
        raise ValueError(
            "Harness inputs must exactly include canonical provenance kinds: "
            + ", ".join(sorted(required))
        )
    for artifact_kind in sorted(required):
        reference = references[artifact_kind]
        supplied = Path(inputs[artifact_kind])
        if supplied.is_symlink():
            raise ValueError(f"Harness input must not be a symlink: {supplied}")
        supplied_path = supplied.resolve(strict=False)
        expected_path = (workspace / reference.path).resolve(strict=False)
        if supplied_path != expected_path or not supplied_path.is_file():
            raise ValueError(
                f"Harness {artifact_kind} input must be the exact canonical "
                f"provenance file: {reference.path}"
            )
        digest = hashlib.sha256(supplied_path.read_bytes()).hexdigest()
        if digest != reference.sha256:
            raise ValueError(
                f"Harness {artifact_kind} input hash does not match test_spec provenance."
            )


def _relative_path(value: str) -> str:
    text = str(value).replace("\\", "/")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", text):
        raise ValueError(f"Expected normalized relative path: {value}")
    return path.as_posix()


def _contained_file(workspace: Path, relative: str) -> Path:
    normalized = _relative_path(relative)
    return _first_regular_contained(workspace, (workspace / normalized,))


def _first_regular_contained(workspace: Path, candidates: tuple[Path, ...]) -> Path:
    for candidate in candidates:
        try:
            lexical = assert_no_reparse_components(candidate, workspace)
        except ValueError:
            raise
        if lexical.is_file():
            return lexical
    raise FileNotFoundError(
        "Current artifact file is missing or escapes the workspace: "
        + ", ".join(str(item) for item in candidates)
    )


def _first_regular_from_scoped_roots(
    workspace: Path,
    candidates: tuple[Path, ...],
    *,
    extra_root: Path | None,
) -> Path:
    roots = (workspace,) if extra_root is None else (workspace, extra_root)
    for candidate in candidates:
        lexical = lexical_absolute(candidate)
        containing_root = next(
            (
                lexical_absolute(root)
                for root in roots
                if _is_within(lexical, lexical_absolute(root))
            ),
            None,
        )
        if containing_root is None:
            continue
        assert_no_reparse_components(lexical, containing_root)
        if lexical.is_file():
            return lexical
    raise FileNotFoundError(
        "Current source artifact is missing or escapes declared roots: "
        + ", ".join(str(item) for item in candidates)
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Artifact root must be an object: {path}")
    return value
