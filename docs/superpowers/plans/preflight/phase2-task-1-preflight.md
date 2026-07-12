# Phase 2 Task 1 Source-Specific VC6 Compile Context Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and a fresh formal reviewer.

**Goal:** Resolve and propagate the exact VC6 compile context for each source and full configuration without leaking options between compile units.

**Architecture:** DSP parsing retains project, source, and source-configuration deltas separately. One resolver produces an immutable fingerprinted context consumed by analysis, extracted workspaces, Makefiles/DSPs, host verification, and each real dependency compile unit.

**Tech Stack:** Python, VC6 DSP/DSW parsing, C90/CP932, NMAKE/host compiler fixtures, JSON Schema.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Begin only after Phase 1 Task 8 is approved/merged and gate G1 passes.
- Branch: `codex/p2t1-source-compile-context`.
- This is the first Phase 2 implementation task. Task 7 follows it before Task 2.

## Deliverable map

- Extend `vc6/dsp_models.py` with `SourceConfigurationSettings`, project SUBTRACT data, source-configuration ADD/SUBTRACT, and exclusion state.
- Correct scope handling in `vc6/dsp_parser.py`; source clauses never mutate project settings.
- Parse semantic option units in `vc6/dsp_options.py`, pairing `/D`, `/I`, `/FI`, `/Yu`, `/Yc`, `/YX`, `/Tc`, and `/Tp` with arguments.
- Add `vc6/effective_compile_context.py` and one `resolve_effective_compile_context(project, source, exact_configuration)` API.
- Feed exact unit contexts through dossier/reanalysis, build models/workspace, Makefile and debug-DSP rendering, runtime compatibility, and host verification.
- Copy forced/PCH headers only through contained, identity-checked extracted paths.

## Resolution and propagation rules

- Resolution order is BASE, project ADD/SUBTRACT, then source ADD/SUBTRACT.
- Preserve ordered include/define sequences; the last effective singleton controls PCH/language options.
- Context output includes exact DSW/DSP/project/source/full configuration, exclusion, defines, includes, forced includes, PCH, language, raw options, warnings, and deterministic fingerprint.
- `CompileUnit` owns its own context ID, defines, includes, forced includes, PCH, language, and options. No global all-unit CFLAGS authority remains.
- The target and each real dependency resolve under their own source/project context. Excluded sources are not valid real implementations.
- Generated Makefile, actual compile invocation, host verification, and debug DSP must agree on each unit context.

## Contract and version decisions

- Advance `BUILD_CONTEXT` from 1.0.0 to 1.1.0 and retain the immutable 1.0 schema.
- Legacy 1.0 input without source settings remains explicit unknown/display-only; migration must not fabricate source context from project-global flags.
- Do not bump unrelated kinds.

## Strict RED map

| Test module/fixture | RED behavior required before implementation |
|---|---|
| `tests/test_vc6_dsp_parser.py` | Project, source, and source-configuration ADD/SUBTRACT/exclusion scopes remain separate. |
| `tests/test_vc6_source_compile_context.py` | Source A/B `/D`, `/I`, `/FI`, `/Yu` never leak; SUBTRACT removes only its semantic unit; Debug exclusion differs from Release. |
| `tests/fixtures/vc6_per_source_dependency_project/` | Target and real callee in distinct DSP/source contexts compile with distinct options; excluded implementation is rejected. |
| Build/verification/debug tests | Makefile, actual compile command, host verifier, and generated DSP reproduce the same context; forced/PCH headers are copied or explicitly blocked. |
| Contract/package tests | 1.0 strict-current rejects, display migration is lossless/non-fabricating, and 1.1 validates from source and installed wheel. |

## Boundaries and verification

- Do not add heuristic project/configuration selection (T7), active preprocessing (T2), type resolution (T3), typed lowering, cache, or progress.
- Run focused parser/options/workspace/build/verification/debug modules, then affected contract/package tests.
- Run every Python module separately and serially, compileall, CLI help, fixture compile/link where available, wheel/fresh-install schema checks, and `git diff --check`.
- Record exact compile commands/context fingerprints for both target and real dependency in the report.
- Leave clean and unmerged until fresh formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git switch -c codex/p2t1-source-compile-context
py -m unittest tests.test_vc6_dsp_parser -v
```
