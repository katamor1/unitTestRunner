from __future__ import annotations

import re
from typing import Any


def _candidate(value: str, source: str, confidence: str = "medium") -> dict[str, Any]:
    return {"value": value, "source": source, "confidence": confidence, "review_required": True}


def generate_test_design(function: dict[str, Any]) -> dict[str, Any]:
    branch_items = [
        {
            "id": branch["id"],
            "description": f"Evaluate condition at line {branch['line']}: {branch['condition']}",
            "source": "branch",
            "confidence": "medium",
            "review_required": True,
        }
        for branch in function.get("branches", [])
    ]
    condition_items = []
    boundary_candidates = []
    equivalence_candidates = []

    for parameter in function.get("parameters", []):
        if parameter["is_pointer"]:
            equivalence_candidates.append(_candidate(f"{parameter['name']} = NULL", "parameter_type"))
            equivalence_candidates.append(_candidate(f"{parameter['name']} != NULL", "parameter_type"))
        elif parameter["type"] in ("int", "short", "long", "unsigned int", "unsigned short", "unsigned long"):
            equivalence_candidates.append(_candidate(f"{parameter['name']} = 0", "parameter_type", "low"))
            equivalence_candidates.append(_candidate(f"{parameter['name']} positive", "parameter_type", "low"))
            equivalence_candidates.append(_candidate(f"{parameter['name']} negative", "parameter_type", "low"))

    for branch in function.get("branches", []):
        condition = branch["condition"]
        for operator in ("&&", "||"):
            if operator in condition:
                condition_items.append(
                    {
                        "id": f"COND-{len(condition_items) + 1:03d}",
                        "description": f"Exercise both sides of compound condition: {condition}",
                        "source": "condition",
                        "confidence": "medium",
                        "review_required": True,
                    }
                )
        for left, operator, right in re.findall(r"([A-Za-z_]\w*)\s*(<=|>=|<|>|==|!=)\s*([A-Za-z_]\w*)", condition):
            if operator in ("<", "<=", ">", ">="):
                boundary_candidates.extend(
                    [
                        _candidate(f"{left} around {right} - 1", "comparison"),
                        _candidate(f"{left} around {right}", "comparison"),
                        _candidate(f"{left} around {right} + 1", "comparison"),
                    ]
                )
            if right.upper().endswith("FAIL") or right.upper() == "NULL":
                equivalence_candidates.append(_candidate(f"{left} == {right}", "comparison"))

    for case in function.get("cases", []):
        equivalence_candidates.append(_candidate(case["value"], "switch", "high"))

    stub_candidates = [
        {
            "name": call["name"],
            "line": call["line"],
            "source": "external_call",
            "confidence": "medium",
            "review_required": True,
        }
        for call in function.get("external_calls", [])
    ]

    return {
        "branch_coverage_items": branch_items,
        "condition_coverage_items": condition_items,
        "boundary_value_candidates": boundary_candidates,
        "equivalence_class_candidates": equivalence_candidates,
        "stub_candidates": stub_candidates,
    }


__all__ = ["generate_test_design"]
