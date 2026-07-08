from __future__ import annotations

from unit_test_runner.dossier.dossier_models import FunctionDossier


def render_function_dossier_markdown(dossier: FunctionDossier) -> str:
    payload = dossier.to_dict()
    lines = [
        f"# 関数dossier: {dossier.function_name}",
        "",
        "## サマリ",
        f"- ソース: {payload['function'].get('source_path') or ''}",
        f"- 状態: {dossier.status}",
        f"- MVPレベル: {dossier.readiness.mvp_level}",
        f"- レビュー可能: {'はい' if dossier.readiness.ready_for_review else 'いいえ'}",
        "",
        "## 関数インターフェース",
        f"- シグネチャ: {dossier.summaries.get('function_summary', {}).get('signature', '')}",
        f"- 引数数: {dossier.summaries.get('function_summary', {}).get('parameter_count', 0)}",
        "",
        "## 依存関係",
        f"- グローバル読み取り: {dossier.summaries.get('dependency_summary', {}).get('global_read_count', 0)}",
        f"- グローバル書き込み: {dossier.summaries.get('dependency_summary', {}).get('global_write_count', 0)}",
        f"- 外部呼び出し: {dossier.summaries.get('dependency_summary', {}).get('external_call_count', 0)}",
        f"- スタブ候補: {dossier.summaries.get('dependency_summary', {}).get('stub_candidate_count', 0)}",
        "",
        "## カバレッジとテスト",
        f"- カバレッジ項目: {dossier.summaries.get('coverage_summary', {}).get('coverage_item_count', 0)}",
        f"- テストケース: {dossier.summaries.get('coverage_summary', {}).get('test_case_design_count', 0)}",
        "",
        "## ビルドと実行",
        f"- ビルドプローブ: {dossier.summaries.get('build_summary', {}).get('build_probe_status', 'unknown')}",
        f"- テスト実行: {dossier.summaries.get('execution_summary', {}).get('status', 'unknown')}",
        "",
        "## トレーサビリティ",
        "`traceability_matrix.csv` を参照してください。",
        "",
        "## 未解決項目",
        "| ID | 項目 | 影響 | 推奨アクション |",
        "|---|---|---|---|",
    ]
    for item in dossier.unresolved_items:
        lines.append(f"| {_markdown_cell(item.item_id)} | {_markdown_cell(item.item_kind)} | {_markdown_cell(item.impact)} | {_markdown_cell(item.suggested_action)} |")
    lines.extend(["", "## 次のアクション", "| ID | 優先度 | アクション | 対応対象・理由 | 担当ロール |", "|---|---|---|---|---|"])
    for action in dossier.next_actions:
        related = ", ".join(action.related_unresolved_items) if action.related_unresolved_items else "-"
        detail = action.description or related
        if related != "-" and related not in detail:
            detail = f"{related}: {detail}"
        lines.append(f"| {_markdown_cell(action.action_id)} | {_markdown_cell(action.priority)} | {_markdown_cell(action.title)} | {_markdown_cell(detail)} | {_markdown_cell(action.owner_role)} |")
    return "\n".join(lines) + "\n"


def _markdown_cell(value: str) -> str:
    text = str(value or "-").replace("\n", "<br>")
    return text.replace("|", "\\|")
