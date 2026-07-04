from __future__ import annotations

from unit_test_runner.build_completion.completion_models import BuildCompletionPlan
from unit_test_runner.build_completion.completion_report_writer import render_completion_plan_markdown


def render_build_completion_markdown(plan: BuildCompletionPlan) -> str:
    return render_completion_plan_markdown(plan)
