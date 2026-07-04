from __future__ import annotations

from typing import Any


def build_summaries(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    signature = payloads.get("function_signature", {})
    global_access = payloads.get("global_access", {})
    call_report = payloads.get("call_report", {})
    coverage_design = payloads.get("coverage_design", {})
    boundary = payloads.get("boundary_equivalence_candidates", {})
    draft = payloads.get("test_case_draft", {})
    build_probe = payloads.get("build_probe_report", {})
    completion = payloads.get("build_completion_plan", {})
    execution = payloads.get("test_execution_report", {})
    evidence = payloads.get("evidence_manifest", {})
    return {
        "function_summary": _function_summary(signature, payloads),
        "dependency_summary": {
            "global_read_count": len(global_access.get("reads", global_access.get("globals_read", []))),
            "global_write_count": len(global_access.get("writes", global_access.get("globals_written", []))),
            "external_call_count": len(call_report.get("calls", [])),
            "stub_candidate_count": len(completion.get("stub_completion_candidates", [])),
        },
        "coverage_summary": {
            "coverage_item_count": _count_coverage_items(coverage_design),
            "boundary_candidate_count": len(boundary.get("boundary_value_candidates", boundary.get("candidates", []))),
            "test_case_draft_count": len(draft.get("test_cases", [])),
        },
        "build_summary": {
            "build_probe_status": build_probe.get("function", {}).get("status", build_probe.get("status", "unknown")),
            "completion_status": completion.get("function", {}).get("status", completion.get("status", "unknown")),
        },
        "execution_summary": {
            "executed": execution.get("executed", False),
            "status": execution.get("function", {}).get("status", execution.get("status", "unknown")),
            "total": execution.get("parsed_result", {}).get("total", 0),
            "passed": execution.get("parsed_result", {}).get("passed", 0),
            "failed": execution.get("parsed_result", {}).get("failed", 0),
            "inconclusive": execution.get("parsed_result", {}).get("inconclusive", 0),
            "evidence_status": evidence.get("summary", {}).get("test_execution_status", "unknown"),
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


def _count_coverage_items(payload: dict[str, Any]) -> int:
    total = 0
    for key in ("coverage_items", "branch_coverage_items", "condition_coverage_items", "return_coverage_items"):
        value = payload.get(key, [])
        if isinstance(value, list):
            total += len(value)
    return total
