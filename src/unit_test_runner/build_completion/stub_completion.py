from __future__ import annotations

from pathlib import Path
from typing import Any

from .completion_models import BuildCompletionPolicy, BuildCompletionWarning, CompletionAction, StubCompletionCandidate
from .symbol_normalizer import normalize_link_symbol


def plan_stub_completions(
    build_probe_report: dict[str, Any],
    call_report: dict[str, Any],
    policy: BuildCompletionPolicy | None = None,
) -> tuple[list[StubCompletionCandidate], list[CompletionAction], list[BuildCompletionWarning]]:
    actions: list[CompletionAction] = []
    warnings: list[BuildCompletionWarning] = []
    candidates = _stub_candidates(build_probe_report, call_report, actions, warnings, policy or BuildCompletionPolicy())
    return candidates, actions, warnings


def _stub_candidates(
    build_probe_report: dict[str, Any],
    call_report: dict[str, Any],
    actions: list[CompletionAction],
    warnings: list[BuildCompletionWarning],
    policy: BuildCompletionPolicy,
) -> list[StubCompletionCandidate]:
    calls = {call.get("name"): call for call in call_report.get("calls", [])}
    candidates: list[StubCompletionCandidate] = []
    for index, unresolved in enumerate(build_probe_report.get("unresolved_symbols", []), start=1):
        normalized = normalize_link_symbol(unresolved.get("symbol_name", ""))
        function_name = normalized.function_name_candidate
        call = calls.get(function_name)
        if call:
            strategy = "from_call_report"
            parameter_strategy = "from_call_arguments"
            confidence = "high"
            related_call_id = call.get("call_id")
            related_call_name = call.get("name")
        else:
            strategy = "default_int"
            parameter_strategy = "empty_parameter_list"
            confidence = "low"
            related_call_id = None
            related_call_name = None
            warnings.append(BuildCompletionWarning("unknown_symbol_stub_generated", f"Unknown symbol stub candidate requires review: {function_name}.", related_symbol=function_name))
        source = Path("generated/stubs") / f"stub_{function_name}.c"
        header = Path("generated/stubs") / f"stub_{function_name}.h"
        action_id = f"ACT_STUB_{index:03d}"
        if call or policy.generate_unknown_symbol_stubs:
            actions.append(
                CompletionAction(
                    action_id=action_id,
                    action_kind="generate_stub",
                    source_diagnostic_code=unresolved.get("diagnostic_code", "LNK"),
                    source_diagnostic_raw=unresolved.get("diagnostic_raw", ""),
                    description=f"Generate additional stub for {function_name}",
                    apply_mode="auto_safe",
                    safety_level="safe" if call else "moderate",
                    target_files=[source, header],
                    expected_effect=f"Resolve unresolved external symbol {function_name}",
                    review_required=True,
                )
            )
        candidates.append(
            StubCompletionCandidate(
                symbol_name=unresolved.get("symbol_name", ""),
                function_name_candidate=function_name,
                related_call_name=related_call_name,
                related_call_id=related_call_id,
                return_type_strategy=strategy,
                parameter_strategy=parameter_strategy,
                stub_source_path=source,
                stub_header_path=header,
                makefile_registration_required=True,
                confidence=confidence,
                review_required=True,
            )
        )
    return candidates
