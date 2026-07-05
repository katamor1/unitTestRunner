from __future__ import annotations

import csv
from io import StringIO


def render_regression_selection_csv(payload: dict) -> str:
    output = StringIO()
    fieldnames = ["test_case_id", "selection_status", "priority", "reasons", "related_changes", "review_required"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for bucket in ("selected_test_cases", "skipped_test_cases", "new_required_test_cases", "blocked_test_cases"):
        for case in payload.get(bucket, []):
            writer.writerow(
                {
                    "test_case_id": case["test_case_id"],
                    "selection_status": case["selection_status"],
                    "priority": case["priority"],
                    "reasons": "; ".join(case["reasons"]),
                    "related_changes": "; ".join(case["related_changes"]),
                    "review_required": str(case["review_required"]).lower(),
                }
            )
    return output.getvalue()
