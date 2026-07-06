from __future__ import annotations

import json
from pathlib import Path

from .completion_models import BuildCompletionIterationReport, BuildCompletionPlan


def write_completion_reports(workspace: Path, plan: BuildCompletionPlan, iteration: BuildCompletionIterationReport) -> dict[str, Path]:
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    plan_json = reports / "build_completion_plan.json"
    plan_md = reports / "build_completion_plan.md"
    iteration_json = reports / "build_completion_iteration_report.json"
    iteration_md = reports / "build_completion_iteration_report.md"
    history_json = reports / "completion_history.json"
    plan_json.write_text(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    plan_md.write_text(render_completion_plan_markdown(plan), encoding="utf-8")
    iteration_json.write_text(json.dumps(iteration.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    iteration_md.write_text(render_iteration_markdown(iteration), encoding="utf-8")
    history_json.write_text(json.dumps({"schema_version": "0.1", "iterations": [item.to_dict() for item in iteration.iterations]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "plan_json": plan_json,
        "plan_markdown": plan_md,
        "iteration_json": iteration_json,
        "iteration_markdown": iteration_md,
        "history_json": history_json,
    }


def render_completion_plan_markdown(plan: BuildCompletionPlan) -> str:
    payload = plan.to_dict()
    lines = [
        "# ビルド補完計画",
        "",
        "## 対象",
        f"- 関数: {plan.function_name}",
        f"- 状態: {plan.status}",
        "",
        "## 補完アクション",
        "| ID | 種別 | 説明 | 適用モード | 安全性 | レビュー要否 |",
        "|---|---|---|---|---|---|",
    ]
    for action in payload["completion_actions"]:
        lines.append(
            f"| {action['action_id']} | {action['action_kind']} | {action['description']} | {action['apply_mode']} | {action['safety_level']} | {'はい' if action['review_required'] else 'いいえ'} |"
        )
    lines.extend(["", "## include候補"])
    if plan.include_completion_candidates:
        lines.extend(["| include | 候補数 | 信頼度 |", "|---|---:|---|"])
        for item in payload["include_completion_candidates"]:
            lines.append(f"| {item['include_name']} | {len(item['candidate_paths'])} | {item['confidence']} |")
    else:
        lines.append("- なし")
    lines.extend(["", "## スタブ候補"])
    if plan.stub_completion_candidates:
        lines.extend(["| シンボル | 関数 | 戦略 | 信頼度 | レビュー要否 |", "|---|---|---|---|---|"])
        for item in payload["stub_completion_candidates"]:
            lines.append(
                f"| {item['symbol_name']} | {item['function_name_candidate']} | {item['return_type_strategy']} | {item['confidence']} | {'はい' if item['review_required'] else 'いいえ'} |"
            )
    else:
        lines.append("- なし")
    lines.extend(["", "## 手動対応"])
    if plan.manual_action_items:
        for item in payload["manual_action_items"]:
            lines.append(f"- {item['item_id']}: {item['suggested_action']}")
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"


def render_iteration_markdown(iteration: BuildCompletionIterationReport) -> str:
    payload = iteration.to_dict()
    lines = [
        "# ビルド補完イテレーションレポート",
        "",
        "## 対象",
        f"- 関数: {iteration.function_name}",
        f"- 状態: {iteration.status}",
        f"- 最終ビルドプローブ状態: {iteration.final_build_probe_status}",
        f"- 停止理由: {iteration.stop_reason}",
        "",
        "## イテレーション",
        "| 回 | 進捗 | プローブ実行 | 適用 | スキップ |",
        "|---:|---|---|---|---|",
    ]
    for item in payload["iterations"]:
        lines.append(
            f"| {item['iteration_index']} | {item['progress']} | {'はい' if item['probe_executed'] else 'いいえ'} | {len(item['applied_actions'])} | {len(item['skipped_actions'])} |"
        )
    return "\n".join(lines) + "\n"
