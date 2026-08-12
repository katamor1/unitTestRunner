from __future__ import annotations

from typing import Any


def build_summaries(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    signature = payloads.get("function_signature", {})
    global_access = payloads.get("global_access", {})
    call_report = payloads.get("call_report", {})
    coverage_design = payloads.get("coverage_design", {})
    boundary = payloads.get("boundary_equivalence_candidates", {})
    test_design = payloads.get("test_spec", {})
    build_probe = payloads.get("build_probe_report", {})
    return {
        "function_summary": _function_summary(signature, payloads),
        "dependency_summary": {
            "global_read_count": _global_read_count(global_access),
            "global_write_count": _global_write_count(global_access),
            "external_call_count": len(call_report.get("calls", [])),
            "stub_candidate_count": len(call_report.get("stub_candidates", [])),
        },
        "coverage_summary": {
            "coverage_item_count": _count_coverage_items(coverage_design),
            "boundary_candidate_count": len(boundary.get("boundary_value_candidates", boundary.get("candidates", []))),
            "test_case_design_count": len(test_design.get("test_cases", [])),
        },
        "build_summary": {
            "build_probe_status": build_probe.get("function", {}).get("status", build_probe.get("status", "unknown")),
            "completion_status": "not_applicable",
        },
        "execution_summary": {
            "executed": False,
            "status": "not_run",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "inconclusive": 0,
            "evidence_status": "not_applicable",
        },
    }


def _function_summary(signature: dict[str, Any], payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    function = signature.get("function", {})
    parameters = function.get("parameters", signature.get("parameters", []))
    location = payloads.get("function_location", {}).get("location", {})
    return {
        "signature": function.get("signature") or signature.get("signature_text") or signature.get("declaration", ""),
        "return_type": function.get("return_type") or signature.get("return_type", ""),
        "parameter_count": len(parameters) if isinstance(parameters, list) else 0,
        "line_range": f"{location.get('start_line', '')}-{location.get('end_line', '')}" if location else "",
    }


def _global_read_count(global_access: dict[str, Any]) -> int:
    accesses = global_access.get("global_accesses", [])
    return sum(
        1
        for item in accesses
        if item.get("access_kind") in {"read", "read_write", "address_taken"}
    )


def _global_write_count(global_access: dict[str, Any]) -> int:
    accesses = global_access.get("global_accesses", [])
    return sum(
        1
        for item in accesses
        if item.get("access_kind") in {"write", "read_write"}
    )


def _count_coverage_items(payload: dict[str, Any]) -> int:
    total = 0
    for key in ("coverage_items", "branch_coverage_items", "condition_coverage_items", "return_coverage_items"):
        value = payload.get(key, [])
        if isinstance(value, list):
            total += len(value)
    return total
