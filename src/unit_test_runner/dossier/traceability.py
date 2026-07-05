from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .dossier_models import TraceabilityLink


TRACEABILITY_FIELDS = [
    "source_kind",
    "source_id",
    "relation",
    "target_kind",
    "target_id",
    "test_case_id",
    "coverage_id",
    "candidate_id",
    "stub_name",
    "execution_status",
    "review_required",
    "confidence",
]


def build_traceability(payloads: dict[str, dict[str, Any]]) -> list[TraceabilityLink]:
    links: list[TraceabilityLink] = []
    test_design = payloads.get("test_case_design", {})
    execution_cases = {
        item.get("test_case_id"): item
        for item in payloads.get("test_execution_report", {}).get("case_results", [])
        if item.get("test_case_id")
    }
    for case_index, case in enumerate(test_design.get("test_cases", []), start=1):
        test_case_id = case.get("test_case_id") or case.get("id") or f"TC_{case_index:03d}"
        coverage_links = case.get("coverage_links", [])
        if not coverage_links and case.get("coverage"):
            coverage_links = [{"coverage_id": case.get("coverage")}]
        for coverage_index, coverage in enumerate(coverage_links, start=1):
            coverage_id = coverage.get("coverage_id") or coverage.get("id") or f"COV_{coverage_index:03d}"
            links.append(
                TraceabilityLink(
                    f"TRACE_COVERAGE_{len(links) + 1:03d}",
                    "test_case",
                    test_case_id,
                    "coverage_item",
                    coverage_id,
                    "covers",
                    "high",
                    bool(case.get("review_status") == "review_required"),
                    test_case_id=test_case_id,
                    coverage_id=coverage_id,
                )
            )
        execution = execution_cases.get(test_case_id)
        if execution:
            links.append(
                TraceabilityLink(
                    f"TRACE_EXEC_{len(links) + 1:03d}",
                    "test_case",
                    test_case_id,
                    "execution_result",
                    test_case_id,
                    "executed_as",
                    "high",
                    bool(execution.get("review_required")),
                    test_case_id=test_case_id,
                    execution_status=execution.get("status"),
                )
            )
    completion = payloads.get("build_completion_plan", {})
    for stub_index, stub in enumerate(completion.get("stub_completion_candidates", []), start=1):
        function_name = stub.get("function_name_candidate") or stub.get("symbol_name") or f"stub_{stub_index:03d}"
        links.append(
            TraceabilityLink(
                f"TRACE_STUB_{len(links) + 1:03d}",
                "external_call",
                stub.get("related_call_name") or function_name,
                "stub_candidate",
                function_name,
                "uses_stub",
                stub.get("confidence", "low"),
                bool(stub.get("review_required", True)),
                stub_name=function_name,
            )
        )
    if not links:
        links.append(TraceabilityLink("TRACE_GAP_001", "dossier", "artifact_set", "review", "manual_traceability_review", "blocked_by", "low", True))
    return links


def write_traceability_csv(path: Path, links: list[TraceabilityLink]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACEABILITY_FIELDS)
        writer.writeheader()
        for link in links:
            payload = link.to_dict()
            writer.writerow({field: payload.get(field, "") for field in TRACEABILITY_FIELDS})
