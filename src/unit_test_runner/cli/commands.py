from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from unit_test_runner import __version__
from unit_test_runner.build_probe import build_probe
from unit_test_runner.c_analyzer import list_functions
from unit_test_runner.dsw_parser import discover_dsw_workspaces, parse_dsw as parse_dsw_step03
from unit_test_runner.dossier import analyze_function_workflow, generate_test_draft_from_dossier
from unit_test_runner.reports.dsw_markdown import render_dsw_discovery_markdown
from unit_test_runner.reports.source_membership_markdown import render_source_membership_markdown
from unit_test_runner.vc6 import discover_workspace, map_source_to_projects
from unit_test_runner.vc6.dsp_parser import parse_dsp as parse_dsp_step04
from unit_test_runner.vc6.source_membership import map_source_membership

from .errors import CLIError
from .exit_codes import EXIT_NOT_FOUND, EXIT_OK, EXIT_OUTPUT_ERROR
from .result import CLIResult


def dispatch(args: argparse.Namespace) -> CLIResult:
    handlers = {
        "doctor": handle_doctor,
        "discover-projects": handle_discover_projects,
        "map-source": handle_map_source,
        "list-functions": handle_list_functions,
        "analyze-function": handle_analyze_function,
        "build-probe": handle_build_probe,
        "generate-test-draft": handle_generate_test_draft,
    }
    return handlers[args.command](args)


def handle_doctor(args: argparse.Namespace) -> CLIResult:
    supported = sys.version_info >= (3, 12)
    temp_dir = Path(tempfile.gettempdir())
    temp_writable = _is_writable_directory(temp_dir)
    checks = [
        {
            "id": "python_version",
            "status": "ok" if supported else "error",
            "message": "Python version is supported." if supported else "Python 3.12 or later is required.",
        },
        {
            "id": "temp_dir_writable",
            "status": "ok" if temp_writable else "error",
            "message": f"Temporary directory is writable: {temp_dir}" if temp_writable else f"Temporary directory is not writable: {temp_dir}",
        },
        {
            "id": "dependencies",
            "status": "ok",
            "message": "Runtime uses the Python standard library only.",
        },
    ]
    warnings = [] if supported and temp_writable else ["One or more doctor checks require attention."]
    return CLIResult(
        status="ok" if not warnings else "warning",
        exit_code=EXIT_OK,
        command="doctor",
        message="Environment check completed.",
        data={
            "version": __version__,
            "python": {
                "version": platform.python_version(),
                "supported": supported,
            },
            "os": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
            },
            "cwd": str(Path.cwd()),
            "temp_dir": str(temp_dir),
            "checks": checks,
        },
        warnings=warnings,
    )


def handle_discover_projects(args: argparse.Namespace) -> CLIResult:
    if args.dsw:
        workspace = _existing_dir(args.workspace, "workspace", args.command)
        dsw = _resolve_dsw(workspace, args.dsw, args.command)
        if args.with_dsp_details:
            result = _with_dsp_details(discover_dsw_workspaces(dsw).to_dict())
            if args.out:
                _write_discovery_report(Path(args.out), result, args.command)
            return CLIResult(
                status="ok",
                exit_code=EXIT_OK,
                command=args.command,
                message="Projects discovered.",
                data=result,
                human_output=_render_discovery_summary(result, Path(args.out) if args.out else None),
            )
        result = discover_workspace(workspace, dsw)
        if args.out:
            out = Path(args.out)
            if out.suffix.lower() == ".md":
                discovery = discover_dsw_workspaces(dsw)
                _write_discovery_report(out, discovery.to_dict(), args.command)
            else:
                _write_json(out, result, args.command)
        return CLIResult(
            status="ok",
            exit_code=EXIT_OK,
            command=args.command,
            message="Projects discovered.",
            data=result,
            legacy_payload=result,
            human_output=_render_discovery_summary(
                discover_dsw_workspaces(dsw).to_dict(),
                Path(args.out) if args.out else None,
            ),
        )

    workspace_arg = _existing_path(args.workspace, "workspace", args.command)
    try:
        discovery = discover_dsw_workspaces(workspace_arg)
    except FileNotFoundError as exc:
        raise CLIError(str(exc), EXIT_NOT_FOUND, args.command) from exc
    result = discovery.to_dict()
    if args.with_dsp_details:
        result = _with_dsp_details(result)
    if args.out:
        _write_discovery_report(Path(args.out), result, args.command)
    return CLIResult(
        status="ok",
        exit_code=EXIT_OK,
        command=args.command,
        message="Projects discovered.",
        data=result,
        human_output=_render_discovery_summary(result, Path(args.out) if args.out else None),
    )


def handle_map_source(args: argparse.Namespace) -> CLIResult:
    dsw = _existing_file(args.dsw, "dsw", args.command)
    if args.workspace:
        workspace = _workspace_from_args(args.workspace, dsw)
        matches = map_source_to_projects(workspace, dsw, args.source, args.project)
        if args.configuration:
            matches = [match for match in matches if match["configuration"] == args.configuration]
        payload = {"matches": matches}
        if args.out:
            _write_json(Path(args.out), payload, args.command)
        return CLIResult(
            status="ok",
            exit_code=EXIT_OK,
            command=args.command,
            message="Source mapping completed.",
            data=payload,
            legacy_payload=payload,
        )

    membership = map_source_membership(dsw, args.source, args.project, args.configuration)
    payload = membership.to_dict()
    if args.out:
        _write_source_membership_report(Path(args.out), payload, args.command)
    return CLIResult(
        status=membership.status,
        exit_code=EXIT_OK,
        command=args.command,
        message="Source mapping completed.",
        data=payload,
        human_output=_render_source_membership_summary(payload, Path(args.out) if args.out else None),
    )


def handle_list_functions(args: argparse.Namespace) -> CLIResult:
    source = _existing_file(args.source, "source", args.command)
    payload = {"functions": list_functions(source)}
    return CLIResult(
        status="ok",
        exit_code=EXIT_OK,
        command=args.command,
        message="Functions listed.",
        data=payload,
        legacy_payload=payload,
    )


def handle_analyze_function(args: argparse.Namespace) -> CLIResult:
    dsw = _existing_file(args.dsw, "dsw", args.command)
    workspace = _workspace_from_args(args.workspace, dsw)
    _existing_source(workspace, args.source, args.command)
    try:
        dossier = analyze_function_workflow(
            workspace,
            dsw,
            args.source,
            args.function,
            args.configuration,
            args.out,
            args.project,
        )
    except ValueError as exc:
        raise CLIError(str(exc), EXIT_NOT_FOUND, args.command) from exc
    payload = {
        "dossier": str(Path(args.out) / "reports" / "function_dossier.json"),
        "target": dossier["target"],
        "source_digest": dossier.get("source_digest"),
        "function_location": dossier.get("function_location"),
    }
    return CLIResult(
        status="located",
        exit_code=EXIT_OK,
        command=args.command,
        message="Function location generated. Step 07 Signature Extractor is required for detailed signature analysis.",
        data=payload,
        legacy_payload=payload,
    )


def handle_build_probe(args: argparse.Namespace) -> CLIResult:
    dossier = _existing_file(args.dossier, "dossier", args.command)
    payload = build_probe(dossier, args.vc6_bin, args.dry_run)
    if args.out:
        _write_json(Path(args.out), payload, args.command)
    return CLIResult(
        status="ok",
        exit_code=EXIT_OK,
        command=args.command,
        message="Build probe completed.",
        data=payload,
        legacy_payload=payload,
    )


def handle_generate_test_draft(args: argparse.Namespace) -> CLIResult:
    dossier = _existing_file(args.dossier, "dossier", args.command)
    path = generate_test_draft_from_dossier(dossier)
    if args.out:
        path = _copy_test_draft(path, Path(args.out), args.format, args.command)
    payload = {"test_case_draft": str(path)}
    return CLIResult(
        status="ok",
        exit_code=EXIT_OK,
        command=args.command,
        message="Test draft generated.",
        data=payload,
        legacy_payload=payload,
    )


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            return True
    except OSError:
        return False


def _existing_file(value: str | Path, label: str, command: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists() or not path.is_file():
        raise CLIError(f"{label} file not found: {path}", EXIT_NOT_FOUND, command)
    return path.resolve()


def _existing_dir(value: str | Path, label: str, command: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists() or not path.is_dir():
        raise CLIError(f"{label} directory not found: {path}", EXIT_NOT_FOUND, command)
    return path.resolve()


def _existing_path(value: str | Path, label: str, command: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists():
        raise CLIError(f"{label} path not found: {path}", EXIT_NOT_FOUND, command)
    return path.resolve()


def _existing_source(workspace: Path, source: str, command: str) -> Path:
    path = Path(source)
    if not path.is_absolute():
        path = workspace / source
    return _existing_file(path, "source", command)


def _workspace_from_args(workspace: str | None, dsw: Path) -> Path:
    if workspace:
        return _existing_dir(workspace, "workspace", "workspace")
    return dsw.parent.resolve()


def _resolve_dsw(workspace: Path, value: str | None, command: str) -> Path:
    if value:
        path = Path(value)
        if not path.is_absolute():
            path = workspace / value
        return _existing_file(path, "dsw", command)
    candidates = sorted(workspace.glob("*.dsw"))
    if len(candidates) != 1:
        raise CLIError(f"Expected exactly one .dsw under workspace, found {len(candidates)}.", EXIT_NOT_FOUND, command)
    return candidates[0].resolve()


def _write_json(path: Path, value: dict[str, Any], command: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        raise CLIError(f"Failed to write output file {path}: {exc}", EXIT_OUTPUT_ERROR, command) from exc


def _write_discovery_report(path: Path, value: dict[str, Any], command: str) -> None:
    if path.suffix.lower() == ".md":
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_dsw_discovery_markdown(value), encoding="utf-8")
        except OSError as exc:
            raise CLIError(f"Failed to write output file {path}: {exc}", EXIT_OUTPUT_ERROR, command) from exc
        return
    _write_json(path, value, command)


def _write_source_membership_report(path: Path, value: dict[str, Any], command: str) -> None:
    if path.suffix.lower() == ".md":
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_source_membership_markdown(value), encoding="utf-8")
        except OSError as exc:
            raise CLIError(f"Failed to write output file {path}: {exc}", EXIT_OUTPUT_ERROR, command) from exc
        return
    _write_json(path, value, command)


def _render_discovery_summary(value: dict[str, Any], output_path: Path | None) -> str:
    lines: list[str] = []
    for workspace in value.get("workspaces", []):
        lines.extend(
            [
                f"DSW parsed: {workspace.get('dsw_path', '')}",
                f"Projects: {len(workspace.get('projects', []))}",
                f"Dependencies: {len(workspace.get('dependencies', []))}",
                f"Warnings: {len(workspace.get('warnings', []))}",
            ]
        )
    if output_path is not None:
        lines.append(f"Output: {output_path}")
    return "\n".join(lines) + "\n"


def _render_source_membership_summary(value: dict[str, Any], output_path: Path | None) -> str:
    matches = value.get("matches", [])
    lines = [
        f"Source mapped: {value.get('source', {}).get('input', '')}",
        f"Matches: {len(matches)}",
    ]
    if len(matches) == 1:
        lines.append(f"Project: {matches[0].get('project_name', '')}")
        lines.append(f"Configurations: {len(matches[0].get('configurations', []))}")
    elif len(matches) > 1:
        lines.append("Multiple projects contain this source. Specify --project or --configuration.")
    lines.append(f"Warnings: {len(value.get('warnings', []))}")
    if output_path is not None:
        lines.append(f"Output: {output_path}")
    return "\n".join(lines) + "\n"


def _with_dsp_details(value: dict[str, Any]) -> dict[str, Any]:
    for workspace in value.get("workspaces", []):
        for project in workspace.get("projects", []):
            absolute = project.get("dsp_path_absolute")
            if not absolute:
                continue
            try:
                dsp = parse_dsp_step04(Path(absolute), Path(workspace["root_dir"]))
            except OSError as exc:
                project["dsp_summary"] = {"error": str(exc)}
                continue
            files = dsp.files
            source_count = len([item for item in files if item.file_kind == "source"])
            header_count = len([item for item in files if item.file_kind == "header"])
            resource_count = len([item for item in files if item.file_kind == "resource"])
            defines = sorted({define for cfg in dsp.configurations for define in cfg.build_settings.defines})
            include_dirs = sorted({item.normalized for cfg in dsp.configurations for item in cfg.build_settings.include_dirs})
            project["dsp_summary"] = {
                "project_name": dsp.name,
                "configurations": [configuration.full_name for configuration in dsp.configurations],
                "source_file_count": source_count,
                "header_file_count": header_count,
                "resource_file_count": resource_count,
                "defines": defines,
                "include_dirs": include_dirs,
                "warnings": [warning.to_dict() for warning in dsp.warnings],
            }
    return value


def _copy_test_draft(source: Path, target: Path, output_format: str, command: str) -> Path:
    if output_format != "csv":
        raise CLIError(f"Unsupported draft output format for current implementation: {output_format}", EXIT_OUTPUT_ERROR, command)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target
    except OSError as exc:
        raise CLIError(f"Failed to write test draft {target}: {exc}", EXIT_OUTPUT_ERROR, command) from exc
