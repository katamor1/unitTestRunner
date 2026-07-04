from __future__ import annotations


CASE_KIND_BY_COVERAGE_TYPE = {
    "branch_true": "branch",
    "branch_false": "branch",
    "condition_true": "condition",
    "condition_false": "condition",
    "switch_case": "switch_case",
    "switch_default": "switch_case",
    "loop_zero": "loop",
    "loop_one": "loop",
    "loop_many": "loop",
    "return_path": "return_path",
    "ternary_true": "branch",
    "ternary_false": "branch",
    "review": "review",
}


def case_kind_for_coverage(coverage_type: str) -> str:
    return CASE_KIND_BY_COVERAGE_TYPE.get(coverage_type, "review")


def title_for_coverage(function_name: str, coverage_item: dict) -> str:
    return f"{function_name}: {coverage_item.get('coverage_type', 'coverage')} {coverage_item.get('coverage_id', '')}"


def priority_for_coverage(coverage_type: str) -> str:
    if coverage_type in {"branch_true", "branch_false", "switch_case", "switch_default", "return_path"}:
        return "high"
    if coverage_type.startswith("loop_") or coverage_type.startswith("condition_"):
        return "medium"
    return "low"
