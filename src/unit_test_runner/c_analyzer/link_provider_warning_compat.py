from __future__ import annotations

from . import call_analyzer as analyzer
from .call_models import CallAnalyzerWarning

_ORIGINAL_ANALYZE_CALLS = analyzer.analyze_calls
_PATCHED = False


def apply_link_provider_warning_compat() -> None:
    global _PATCHED
    if _PATCHED:
        return
    analyzer.analyze_calls = _analyze_calls_with_distinct_library_warnings
    _PATCHED = True


def _analyze_calls_with_distinct_library_warnings(*args, **kwargs):
    report = _ORIGINAL_ANALYZE_CALLS(*args, **kwargs)
    report.warnings = [
        warning
        for warning in report.warnings
        if warning.code != "multiple_library_symbol_providers"
    ]
    warned: set[str] = set()
    for call in report.calls:
        if call.name in warned:
            continue
        libraries = {
            provider.library.as_posix().lower()
            for provider in call.link_providers
        }
        if len(libraries) <= 1:
            continue
        warned.add(call.name)
        report.warnings.append(
            CallAnalyzerWarning(
                "multiple_library_symbol_providers",
                f"Multiple linked libraries provide {call.name}; the first library in link order is selected as the primary provider.",
                line_number=call.name_position.line,
                column=call.name_position.column,
            )
        )
    return report
