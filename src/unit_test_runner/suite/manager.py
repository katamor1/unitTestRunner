from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.execution import prepare_test_execution_evidence
from unit_test_runner.vc6.debug_workspace_writer import write_vc6_debug_suite

from .models import SuiteEntry, SuiteManifest, SuiteRunEntryResult, SuiteRunPolicy, SuiteRunReport
from .report_writer import write_suite_run_report


def default_suite_manifest_path(output_root: Path | str) -> Path:
    return Path(output_root) / "suites" / "default" / "suite_manifest.json"


def load_suite_manifest(suite_path: Path | str) -> SuiteManifest:
    suite_path = Path(suite_path)
    if not suite_path.exists():
        return SuiteManifest(suite_id=_suite_id_from_path(suite_path), source_root=None, dsw_path=None)
    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    return SuiteManifest.from_dict(payload, suite_id=_suite_id_from_path(suite_path))


def save_suite_manifest(suite_path: Path | str, manifest: SuiteManifest) -> None:
    suite_path = Path(suite_path)
    suite_path.parent.mkdir(parents=True, exist_ok=True)
    suite_path.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def register_workspace(
    suite_path: Path | str,
    workspace: Path | str,
    tags: list[str] | tuple[str, ...] | None = None,
    source_root: Path | str | None = None,
    dsw_path: Path | str | None = None,
) -> SuiteManifest:
    suite_path = Path(suite_path).resolve()
    workspace = _existing_dir(workspace, "workspace")
    reports = workspace / "reports"
    dossier_path = _existing_file(reports / "function_dossier.json", "function_dossier")
    dossier = _read_json(dossier_path)
    manifest = load_suite_manifest(suite_path)
    if source_root:
        manifest.source_root = Path(source_root).resolve()
    if dsw_path:
        manifest.dsw_path = Path(dsw_path).resolve()
    target = _target_from_dossier(dossier)
    entry = SuiteEntry(
        entry_id=_entry_id(target),
        enabled=True,
        tags=_normalize_tags(tags),
        function=target,
        workspace=workspace,
        dossier=dossier_path,
        test_execution_report=reports / "test_execution_report.json",
        registered_at=datetime.now(timezone.utc).isoformat(),
    )
    manifest.entries = [existing for existing in manifest.entries if existing.entry_id != entry.entry_id]
    manifest.entries.append(entry)
    save_suite_manifest(suite_path, manifest)
    _refresh_vc6_debug_suite(suite_path, manifest)
    return manifest


def remove_entry(suite_path: Path | str, entry_id: str) -> SuiteManifest:
    suite_path = Path(suite_path).resolve()
    manifest = load_suite_manifest(suite_path)
    manifest.entries = [entry for entry in manifest.entries if entry.entry_id != entry_id]
    save_suite_manifest(suite_path, manifest)
    _refresh_vc6_debug_suite(suite_path, manifest)
    return manifest


def list_entries(suite_path: Path | str, tag: str | None = None) -> list[SuiteEntry]:
    entries = load_suite_manifest(suite_path).entries
    if tag:
        return [entry for entry in entries if tag in entry.tags]
    return entries


def run_suite(
    suite_path: Path | str,
    *,
    entry_ids: list[str] | None = None,
    tag: str | None = None,
    all_entries: bool = False,
    policy: SuiteRunPolicy | None = None,
) -> tuple[SuiteRunReport, dict[str, Path]]:
    suite_path = Path(suite_path).resolve()
    policy = policy or SuiteRunPolicy()
    manifest = load_suite_manifest(suite_path)
    _refresh_vc6_debug_suite(suite_path, manifest)
    selected = _select_entries(manifest.entries, entry_ids=entry_ids, tag=tag, all_entries=all_entries)
    results: list[SuiteRunEntryResult] = []
    for entry in selected:
        result = _run_entry(entry, policy)
        results.append(result)
        if policy.fail_fast and result.green_status != "green":
            break
    summary = _summary(results)
    status = "failed" if (policy.require_green and summary["not_green"] > 0) else "completed"
    report = SuiteRunReport(
        suite_id=manifest.suite_id,
        status=status,
        selector=_selector_payload(entry_ids=entry_ids, tag=tag, all_entries=all_entries),
        policy=policy,
        results=results,
        summary=summary,
    )
    return report, write_suite_run_report(suite_path, report)


def _run_entry(entry: SuiteEntry, policy: SuiteRunPolicy) -> SuiteRunEntryResult:
    try:
        report, _ = prepare_test_execution_evidence(
            entry.workspace,
            run_tests=policy.run_tests,
            dry_run=policy.dry_run or not policy.run_tests,
            timeout_seconds=policy.timeout_seconds,
        )
        parsed = report.parsed_result
        total = parsed.total if parsed else len(report.case_results)
        passed = parsed.passed if parsed else 0
        failed = parsed.failed if parsed else 0
        inconclusive = parsed.inconclusive if parsed else 0
        unresolved = len(report.unresolved_review_items)
        green = _is_green(report.status, report.executed, total, failed, inconclusive, unresolved)
        return SuiteRunEntryResult(
            entry_id=entry.entry_id,
            function_name=entry.function.get("name", ""),
            workspace=entry.workspace,
            execution_status=report.status,
            green_status="green" if green else "not_green",
            executed=report.executed,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            inconclusive_tests=inconclusive,
            unresolved_review_count=unresolved,
            report_path=entry.workspace / "reports" / "test_execution_report.json",
        )
    except Exception as exc:
        return SuiteRunEntryResult(
            entry_id=entry.entry_id,
            function_name=entry.function.get("name", ""),
            workspace=entry.workspace,
            execution_status="error",
            green_status="not_green",
            executed=False,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            inconclusive_tests=0,
            unresolved_review_count=0,
            report_path=entry.workspace / "reports" / "test_execution_report.json",
            error=str(exc),
        )


def _is_green(status: str, executed: bool, total: int, failed: int, inconclusive: int, unresolved: int) -> bool:
    return executed and status == "passed" and total > 0 and failed == 0 and inconclusive == 0 and unresolved == 0


def _select_entries(
    entries: list[SuiteEntry],
    *,
    entry_ids: list[str] | None,
    tag: str | None,
    all_entries: bool,
) -> list[SuiteEntry]:
    enabled = [entry for entry in entries if entry.enabled]
    if all_entries:
        return enabled
    if tag:
        return [entry for entry in enabled if tag in entry.tags]
    if entry_ids:
        requested = set(entry_ids)
        return [entry for entry in enabled if entry.entry_id in requested]
    raise ValueError("suite-run requires --entry-id, --tag, or --all.")


def _summary(results: list[SuiteRunEntryResult]) -> dict[str, int]:
    green = len([result for result in results if result.green_status == "green"])
    return {
        "total": len(results),
        "green": green,
        "not_green": len(results) - green,
        "executed": len([result for result in results if result.executed]),
        "failed": len([result for result in results if result.execution_status in {"failed", "error", "blocked", "timeout"}]),
    }


def _selector_payload(*, entry_ids: list[str] | None, tag: str | None, all_entries: bool) -> dict[str, Any]:
    if all_entries:
        return {"kind": "all"}
    if tag:
        return {"kind": "tag", "tag": tag}
    return {"kind": "entry_id", "entry_ids": entry_ids or []}


def _target_from_dossier(dossier: dict[str, Any]) -> dict[str, str]:
    target = dossier.get("target") if isinstance(dossier.get("target"), dict) else {}
    function = dossier.get("function") if isinstance(dossier.get("function"), dict) else {}
    name = target.get("function") or function.get("name")
    source = target.get("source") or function.get("source_path")
    if not name or not source:
        raise ValueError("function_dossier.json must contain target.function and target.source.")
    return {
        "name": str(name),
        "source": str(source),
        "project": str(target.get("project") or ""),
        "configuration": str(target.get("configuration") or ""),
    }


def _entry_id(target: dict[str, str]) -> str:
    seed = "|".join([target.get("name", ""), target.get("source", ""), target.get("project", ""), target.get("configuration", "")])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"{_safe_id(target.get('name', 'function'))}-{digest}"


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value) or "function"


def _normalize_tags(tags: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    for tag in tags or []:
        text = str(tag).strip()
        if text and text not in result:
            result.append(text)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _existing_dir(path: Path | str, label: str) -> Path:
    value = Path(path).expanduser().resolve()
    if not value.is_dir():
        raise ValueError(f"{label} directory not found: {value}")
    return value


def _existing_file(path: Path | str, label: str) -> Path:
    value = Path(path).expanduser().resolve()
    if not value.is_file():
        raise ValueError(f"{label} file not found: {value}")
    return value


def _suite_id_from_path(suite_path: Path) -> str:
    return suite_path.parent.name or "default"


def _refresh_vc6_debug_suite(suite_path: Path, manifest: SuiteManifest) -> None:
    try:
        write_vc6_debug_suite(suite_path, manifest)
    except Exception:
        # The suite manifest must remain usable even when an entry has not reached the build phase yet.
        return
