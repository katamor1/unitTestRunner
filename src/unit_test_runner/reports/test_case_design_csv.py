from __future__ import annotations

import csv
import io


FIELDNAMES = [
    "id",
    "title",
    "target_function",
    "purpose",
    "priority",
    "case_kind",
    "input_assignments",
    "state_setups",
    "stub_setups",
    "expected_observations",
    "coverage_ids",
    "candidate_ids",
    "review_status",
    "confidence",
    "warnings",
]


def render_test_case_design_csv(payload: dict) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    for case in payload["test_cases"]:
        writer.writerow(
            {
                "id": case["test_case_id"],
                "title": case["title"],
                "target_function": case["target_function"],
                "purpose": case["purpose"],
                "priority": case["priority"],
                "case_kind": case["case_kind"],
                "input_assignments": "; ".join(f"{item['target_name']}={item['value_expression']}" for item in case["input_assignments"]),
                "state_setups": "; ".join(f"{item['variable_name']}={item['value_expression']}" for item in case["state_setups"]),
                "stub_setups": "; ".join(f"{item['stub_name']}.{item['setup_kind']}={item['value_expression'] or item['call_behavior'] or ''}" for item in case["stub_setups"]),
                "expected_observations": "; ".join(f"{item['observation_kind']}:{item['target_name'] or ''}={item['expected_expression'] or ''}" for item in case["expected_observations"]),
                "coverage_ids": "; ".join(item["coverage_id"] for item in case["coverage_links"]),
                "candidate_ids": "; ".join(case["candidate_links"]),
                "review_status": case["review_status"],
                "confidence": case["confidence"],
                "warnings": "; ".join(item["code"] for item in case["warnings"]),
            }
        )
    return output.getvalue()
