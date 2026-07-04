from __future__ import annotations

from unit_test_runner.execution.execution_models import TestExecutionReport
from unit_test_runner.execution.test_result_writer import render_execution_markdown


def render_test_execution_markdown(report: TestExecutionReport) -> str:
    return render_execution_markdown(report)
