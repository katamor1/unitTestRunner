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
    test_design = payloads.get("test_spec", {})
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
                    bool(case.get("review_item_ids")),
                    test_case_id=test_case_id,
                    coverage_id=coverage_id,
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
