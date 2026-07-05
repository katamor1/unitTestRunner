from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from unit_test_runner.harness.c90_writer import include_guard_for, write_c_file

from .completion_models import BuildCompletionPlan, BuildCompletionWarning, CompletionIteration, DiagnosticsSummary, StubCompletionCandidate


@dataclass
class CompletionApplyResult:
    applied_actions: list[str] = field(default_factory=list)
    skipped_actions: list[str] = field(default_factory=list)
    generated_files: list[Path] = field(default_factory=list)
    warnings: list[BuildCompletionWarning] = field(default_factory=list)


def apply_safe_completions(workspace: Path | str, plan: BuildCompletionPlan) -> CompletionApplyResult:
    workspace = Path(workspace).resolve()
    result = CompletionApplyResult()
    candidates = {candidate.function_name_candidate: candidate for candidate in plan.stub_completion_candidates}
    for action in plan.completion_actions:
        if action.action_kind != "generate_stub" or action.apply_mode != "auto_safe":
            result.skipped_actions.append(action.action_id)
            continue
        stub_name = _function_name_from_action(action)
        generated = _write_stub(
            workspace,
            stub_name,
            result,
            overwrite=plan.policy.overwrite_existing_generated_stubs,
            candidate=candidates.get(stub_name),
        )
        if generated:
            _register_stub_in_makefile(workspace, stub_name)
            result.applied_actions.append(action.action_id)
        else:
            result.skipped_actions.append(action.action_id)
    return result


def apply_result_to_iteration(workspace: Path, plan: BuildCompletionPlan, apply_result: CompletionApplyResult) -> CompletionIteration:
    summary = DiagnosticsSummary()
    return CompletionIteration(
        iteration_index=1,
        input_probe_report=Path("reports/build_probe_report.json"),
        completion_plan=Path("reports/build_completion_plan.json"),
        applied_actions=apply_result.applied_actions,
        skipped_actions=apply_result.skipped_actions,
        generated_files=apply_result.generated_files,
        probe_executed=False,
        probe_report=Path("reports/build_probe_report.json"),
        diagnostics_before=summary,
        diagnostics_after=None,
        progress="not_run",
    )


def _function_name_from_action(action) -> str:
    for path in action.target_files:
        name = Path(path).stem
        if name.startswith("stub_"):
            return name[5:]
    return action.description.rsplit(" ", 1)[-1]


def _write_stub(workspace: Path, function_name: str, result: CompletionApplyResult, overwrite: bool, candidate: StubCompletionCandidate | None = None) -> bool:
    source = workspace / "generated" / "stubs" / f"stub_{function_name}.c"
    header = workspace / "generated" / "stubs" / f"stub_{function_name}.h"
    if (source.exists() or header.exists()) and not overwrite:
        result.warnings.append(BuildCompletionWarning("existing_file_not_overwritten", f"Existing generated stub was not overwritten: {function_name}", related_symbol=function_name))
        return False
    guard = include_guard_for(header.name)
    parameters = _stub_parameter_list(candidate.parameter_count if candidate else 0)
    unused_parameters = _unused_parameter_lines(candidate.parameter_count if candidate else 0)
    header_text = f"""/* generated completion stub: review required */
#ifndef {guard}
#define {guard}

void Stub_{function_name}_Reset(void);
void Stub_{function_name}_SetReturn(int value);
int Stub_{function_name}_GetCallCount(void);
int {function_name}({parameters});

#endif
"""
    source_text = f"""/* generated completion stub: review required */
#include "stub_{function_name}.h"

static int stub_return_value;
static int stub_call_count;

void Stub_{function_name}_Reset(void)
{{
    stub_return_value = 0;
    stub_call_count = 0;
}}

void Stub_{function_name}_SetReturn(int value)
{{
    stub_return_value = value;
}}

int Stub_{function_name}_GetCallCount(void)
{{
    return stub_call_count;
}}

int {function_name}({parameters})
{{
{unused_parameters}    stub_call_count++;
    return stub_return_value;
}}
"""
    write_c_file(header, header_text, overwrite=True)
    write_c_file(source, source_text, overwrite=True)
    result.generated_files.extend([Path("generated/stubs") / header.name, Path("generated/stubs") / source.name])
    return True


def _stub_parameter_list(parameter_count: int) -> str:
    if parameter_count <= 0:
        return "void"
    return ", ".join(f"int arg{index}" for index in range(parameter_count))


def _unused_parameter_lines(parameter_count: int) -> str:
    if parameter_count <= 0:
        return ""
    return "".join(f"    (void)arg{index};\n" for index in range(parameter_count))


def _register_stub_in_makefile(workspace: Path, function_name: str) -> None:
    makefile = workspace / "build" / "Makefile"
    if not makefile.exists():
        return
    text = makefile.read_text(encoding="cp932")
    obj = f"obj\\stub_{function_name}.obj"
    source = f"generated\\stubs\\stub_{function_name}.c"
    if obj in text:
        return
    text += f"\n# completion stub: {function_name}\n{obj}: ..\\{source}\n\t$(CC) $(CFLAGS) /Fo\"{obj}\" /c \"..\\{source}\"\n"
    marker = "OBJS="
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(marker) and obj not in line:
            lines[index] = line + " " + obj
            break
    makefile.write_text("\n".join(lines) + "\n", encoding="cp932")
