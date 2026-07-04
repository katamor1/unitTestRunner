from __future__ import annotations

from typing import Any

from .execution_models import ExecutableInfo, ExecutionReviewItem, TestExecutionPolicy, TestExecutionWarning


def validate_execution_preconditions(
    build_probe_report: dict[str, Any],
    executable: ExecutableInfo,
    policy: TestExecutionPolicy,
) -> tuple[str, list[TestExecutionWarning], list[ExecutionReviewItem]]:
    warnings: list[TestExecutionWarning] = []
    review_items: list[ExecutionReviewItem] = []
    status = build_probe_report.get("function", {}).get("status", "unknown")
    if policy.require_successful_build_probe and status != "succeeded":
        warnings.append(TestExecutionWarning("build_probe_not_successful", "Build probe is not successful; test execution is blocked."))
        review_items.append(
            ExecutionReviewItem(
                "REVIEW_BUILD_001",
                "build_not_successful",
                None,
                "Build probe did not succeed before test execution.",
                "Resolve build probe diagnostics before running generated tests.",
                "error",
            )
        )
        return "blocked", warnings, review_items
    if policy.run_tests and not policy.dry_run and not executable.exists:
        warnings.extend(executable.warnings)
        review_items.append(
            ExecutionReviewItem(
                "REVIEW_EXECUTABLE_001",
                "executable_not_found",
                None,
                "Test executable was not found.",
                "Run build-probe successfully or pass --executable to a generated runner binary.",
                "error",
            )
        )
        return "blocked", warnings, review_items
    return "ready", warnings, review_items
