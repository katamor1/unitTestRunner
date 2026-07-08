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
        warnings.append(TestExecutionWarning("build_probe_not_successful", "ビルドプローブが成功していないため、テスト実行をブロックします。"))
        review_items.append(
            ExecutionReviewItem(
                "REVIEW_BUILD_001",
                "build_not_successful",
                None,
                "テスト実行前のビルドプローブが成功していません。",
                "生成テストを実行する前に、ビルドプローブ診断を解消してください。",
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
                "テスト実行ファイルが見つかりません。",
                "build-probe を成功させるか、--executable で生成済みランナーを指定してください。",
                "error",
            )
        )
        return "blocked", warnings, review_items
    return "ready", warnings, review_items
