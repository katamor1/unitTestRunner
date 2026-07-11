from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Any

from unit_test_runner.c_analyzer.call_models import CallAnalyzerWarning
from unit_test_runner.vc6.coff_archive import LibrarySymbolCache
from unit_test_runner.vc6.link_context import LinkContext, LinkContextWarning
from unit_test_runner.vc6.link_library_resolver import resolve_link_context

from . import workflow as _workflow

_CURRENT_LINK_CONTEXT: ContextVar[LinkContext | None] = ContextVar("unit_test_runner_link_context", default=None)
_PROCESS_LIBRARY_CACHE = LibrarySymbolCache()
_ORIGINAL_SELECT_PROJECT_CONTEXT = _workflow.select_project_context
_ORIGINAL_BUILD_SOURCE_DIGEST = _workflow.build_source_digest
_ORIGINAL_ANALYZE_CALLS = _workflow.analyze_calls
_PATCHED = False


def apply_link_context_compat() -> None:
    global _PATCHED
    if _PATCHED:
        return
    _workflow.select_project_context = _select_project_context_with_links
    _workflow.build_source_digest = _build_source_digest_with_links
    _workflow.analyze_calls = _analyze_calls_with_links
    _PATCHED = True


def clear_link_context() -> None:
    _CURRENT_LINK_CONTEXT.set(None)


def _select_project_context_with_links(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str | Path,
    configuration: str,
    project_name: str | None = None,
):
    project, config, memberships = _ORIGINAL_SELECT_PROJECT_CONTEXT(
        workspace_root,
        dsw_path,
        source,
        configuration,
        project_name,
    )
    try:
        context = resolve_link_context(
            workspace_root,
            dsw_path,
            project["project_name"],
            config.get("full_name") or configuration,
            cache=_PROCESS_LIBRARY_CACHE,
        )
    except (OSError, ValueError) as exc:
        context = LinkContext(
            warnings=[
                LinkContextWarning(
                    "link_context_resolution_failed",
                    f"Link context resolution failed: {exc}",
                    project.get("project_name"),
                    config.get("full_name") or configuration,
                    None,
                )
            ]
        )
    _CURRENT_LINK_CONTEXT.set(context)
    diagnostics = config.setdefault("diagnostics", [])
    diagnostics.extend(_diagnostic_payload(warning) for warning in context.warnings)
    return project, config, memberships


def _build_source_digest_with_links(source_path: Path | str, build_context: dict[str, Any] | None = None):
    if build_context is not None:
        _apply_context_to_build_context(build_context, _CURRENT_LINK_CONTEXT.get())
    return _ORIGINAL_BUILD_SOURCE_DIGEST(source_path, build_context)


def _analyze_calls_with_links(digest, function_location, function_signature, global_access, *args, **kwargs):
    if args or "link_providers_by_name" in kwargs or "link_warnings" in kwargs:
        return _ORIGINAL_ANALYZE_CALLS(digest, function_location, function_signature, global_access, *args, **kwargs)
    context = _CURRENT_LINK_CONTEXT.get()
    if context is None:
        return _ORIGINAL_ANALYZE_CALLS(digest, function_location, function_signature, global_access)
    warnings = [CallAnalyzerWarning(item.code, item.message) for item in context.warnings]
    return _ORIGINAL_ANALYZE_CALLS(
        digest,
        function_location,
        function_signature,
        global_access,
        link_providers_by_name=context.providers_by_name,
        link_warnings=warnings,
    )


def _apply_context_to_build_context(build_context: dict[str, Any], context: LinkContext | None) -> None:
    context = context or LinkContext()
    build_context["link_libraries"] = [library.to_dict() for library in context.libraries]
    build_context["library_dirs"] = [path.as_posix() for path in context.library_dirs]
    build_context["link_context_warnings"] = [warning.to_dict() for warning in context.warnings]


def _diagnostic_payload(warning: LinkContextWarning) -> dict[str, Any]:
    return {
        "severity": "warning",
        "code": warning.code,
        "message": warning.message,
        "project_name": warning.project_name,
        "configuration": warning.configuration,
        "library_candidate": warning.library_candidate,
    }
