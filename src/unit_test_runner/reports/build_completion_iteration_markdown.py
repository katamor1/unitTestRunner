from __future__ import annotations

from unit_test_runner.build_completion.completion_models import BuildCompletionIterationReport
from unit_test_runner.build_completion.completion_report_writer import render_iteration_markdown


def render_build_completion_iteration_markdown(iteration: BuildCompletionIterationReport) -> str:
    return render_iteration_markdown(iteration)
