from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from unit_test_runner.dossier.dossier_models import DossierNextAction, DossierUnresolvedItem

from .japanese import ja_label, md_cell, md_label_cell


_MD_REPORTS_BY_ARTIFACT = {
    "source_digest": "reports/source_digest.md",
    "function_location": "reports/function_location.md",
    "function_signature": "reports/function_signature.md",
    "global_access": "reports/global_access.md",
    "call_report": "reports/call_report.md",
    "coverage_design": "reports/coverage_design.md",
    "boundary_equivalence_candidates": "reports/boundary_equivalence_candidates.md",
    "test_case_design": "reports/test_case_design.md",
    "harness_skeleton_report": "reports/harness_skeleton_report.md",
    "build_workspace_report": "reports/build_workspace_report.md",
    "build_probe_report": "reports/build_probe_report.md",
    "build_completion_plan": "reports/build_completion_plan.md",
    "build_completion_iteration_report": "reports/build_completion_iteration_report.md",
    "test_execution_report": "reports/test_execution_report.md",
    "evidence_manifest": "reports/evidence_package.md",
}

_DEFAULT_ARTIFACT_PATHS = {
    "test_case_design": "reports/test_case_design.json",
    "harness_skeleton_report": "reports/harness_skeleton_report.json",
    "build_workspace_report": "reports/build_workspace_report.json",
    "build_probe_report": "reports/build_probe_report.json",
    "build_completion_plan": "reports/build_completion_plan.json",
    "test_execution_report": "reports/test_execution_report.json",
    "evidence_manifest": "reports/evidence_manifest.json",
}


def render_next_actions_markdown(
    actions: list[DossierNextAction],
    unresolved_items: list[DossierUnresolvedItem] | None = None,
    artifact_index: list[Any] | None = None,
    function_name: str | None = None,
) -> str:
    unresolved_by_id = {_field(item, "item_id"): item for item in unresolved_items or []}
    artifact_links = _artifact_links_by_kind(artifact_index or [])
    lines = [
        "# 次のアクション",
        "",
        "| ID | 優先度 | アクション | 対応対象・理由 | 操作・参照ファイル | 担当 | 期待成果物 |",
        "|---|---|---|---|---|---|---|",
    ]
    for action in actions:
        related_ids = action.related_unresolved_items or []
        related_items = [unresolved_by_id[item_id] for item_id in related_ids if item_id in unresolved_by_id]
        related = ", ".join(related_ids) if related_ids else "-"
        detail = action.description or related
        if related != "-" and related not in detail:
            detail = f"{related}: {detail}"
        links = _links_for_action(action, related_items, artifact_links, function_name)
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(action.action_id),
                    md_label_cell(action.priority),
                    md_cell(action.title),
                    md_cell(detail),
                    _links_cell(links),
                    md_label_cell(action.owner_role),
                    md_cell(action.expected_output),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _links_for_action(
    action: DossierNextAction,
    unresolved_items: list[Any],
    artifact_links: dict[str, list[str]],
    function_name: str | None,
) -> list[str]:
    links: list[str] = []
    for item in unresolved_items:
        for artifact in _list_field(item, "related_artifacts"):
            links.extend(artifact_links.get(artifact) or _fallback_artifact_links(artifact))
    if action.action_kind == "review_expected_result":
        links.extend(artifact_links.get("test_case_design") or _fallback_artifact_links("test_case_design"))
        if function_name:
            links.append(_markdown_link("生成テストソース", f"../generated/tests/test_{_safe_identifier(function_name)}.c"))
    elif action.action_kind == "review_stub_behavior":
        links.extend(artifact_links.get("harness_skeleton_report") or _fallback_artifact_links("harness_skeleton_report"))
        if function_name:
            links.append(_markdown_link("生成テストソース", f"../generated/tests/test_{_safe_identifier(function_name)}.c"))
        links.append(_markdown_link("生成スタブ", "../generated/stubs/"))
    elif action.action_kind in {"add_include_path", "resolve_pch_issue"}:
        links.extend(artifact_links.get("build_workspace_report") or _fallback_artifact_links("build_workspace_report"))
        links.extend(artifact_links.get("build_probe_report") or _fallback_artifact_links("build_probe_report"))
    elif action.action_kind == "rerun_tests":
        links.extend(artifact_links.get("test_execution_report") or _fallback_artifact_links("test_execution_report"))
        links.extend(artifact_links.get("evidence_manifest") or _fallback_artifact_links("evidence_manifest"))
    elif action.action_kind == "approve_dossier":
        links.append(_markdown_link("関数dossier", "function_dossier.md"))
        links.append(_markdown_link("レビュー確認リスト", "review_checklist.md"))
    return list(dict.fromkeys(links)) or [_markdown_link("関数dossier", "function_dossier.md")]


def _artifact_links_by_kind(artifact_index: list[Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for artifact in artifact_index:
        kind = _field(artifact, "artifact_kind")
        path = _field(artifact, "path")
        if not kind:
            continue
        links: list[str] = []
        md_path = _MD_REPORTS_BY_ARTIFACT.get(kind)
        if md_path:
            links.append(_markdown_link(_artifact_label(kind), _href_from_workspace_path(md_path)))
        if path:
            links.append(_markdown_link("JSON/成果物", _href_from_workspace_path(path)))
        result[kind] = list(dict.fromkeys(links))
    return result


def _fallback_artifact_links(kind: str) -> list[str]:
    links: list[str] = []
    md_path = _MD_REPORTS_BY_ARTIFACT.get(kind)
    if md_path:
        links.append(_markdown_link(_artifact_label(kind), _href_from_workspace_path(md_path)))
    json_path = _DEFAULT_ARTIFACT_PATHS.get(kind)
    if json_path:
        links.append(_markdown_link("JSON", _href_from_workspace_path(json_path)))
    return links


def _artifact_label(kind: str) -> str:
    label = ja_label(kind)
    if label == kind:
        return kind
    return label


def _links_cell(links: list[str]) -> str:
    return "<br>".join(links) if links else "-"


def _markdown_link(label: str, href: str | Path) -> str:
    clean_href = str(href).replace("\\", "/")
    safe_href = quote(clean_href, safe="/:#?&=%._-~")
    clean_label = str(label).replace("[", "【").replace("]", "】")
    return f"[{clean_label}]({safe_href})"


def _href_from_workspace_path(path: str | Path) -> str:
    text = str(path).replace("\\", "/")
    if text.startswith("reports/"):
        return text.removeprefix("reports/")
    if text.startswith("./reports/"):
        return text.removeprefix("./reports/")
    if text.startswith("../") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", text):
        return text
    return "../" + text


def _safe_identifier(value: str) -> str:
    safe = re.sub(r"\W+", "_", str(value)).strip("_")
    return safe or "unknown_function"


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _list_field(item: Any, name: str) -> list[str]:
    value = _field(item, name)
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []
