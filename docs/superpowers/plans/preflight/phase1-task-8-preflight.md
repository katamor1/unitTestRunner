# Phase 1 Task 8 Public Policy, Completion, and Traceability Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, `superpowers:systematic-debugging` for failures, and a fresh formal reviewer.

**Goal:** Close Phase 1 by making every public option behavioral or removed, every public phase independently valid, the completion loop truthful, traceability exact, and subprocess outcomes uniform.

**Architecture:** Fixed option semantics feed exact produced-artifact inventories; an iteration ledger records only probes that ran; traceability validates artifact identities and endpoints; all subprocess categories use the common process-tree contract.

**Tech Stack:** Python CLI/argparse, JSON contracts, process-tree control, TypeScript adapter/help tests, `unittest`.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Start only after Phase 1 Tasks 5-7 are formally approved and merged.
- Branch: `codex/p1t8-phase1-policy-traceability`.
- This task closes Phase 1. Do not absorb Phase 2 VC6 semantic work or Phase 3 progress/cancellation coordinator UX.

## Fixed public-option decisions

- Any explicit `--emit-json/md/csv` flags select views; canonical downstream JSON is always generated. No flags preserve the documented default. Only written files are claimed.
- Dossier include/detail flags change actual content and output selection.
- `--allow-missing-optional-artifacts` defaults false and waives only schema-declared optional absence.
- Harness without `--overwrite` preserves existing human-owned bytes and mtime; with it, only declared generated targets may change.
- `--allow-placeholder-tests=false` blocks before spawning. True may execute but always yields inconclusive. Remove `--treat-placeholder-as-inconclusive` and immutable-log overwrite policy.
- `--analyze-build-errors` controls structured classification; `--apply-safe-completions` deterministically requires or implies it.
- Remove `prepare-evidence --out`; immutable evidence revision storage is the only destination.
- `--run-probe-after-apply` and `--max-iterations` drive actual probes. Validate max >= 1 and reject meaningless combinations.
- Delete later-phase/dead options instead of advertising inert behavior.

## Contract and version decisions

- Preserve Task 5 TestSpec and Task 6 decision/readiness authority plus Task 7 validated adapter.
- If traceability/policy serialization changes `FUNCTION_DOSSIER`, advance from 1.1.0 to 1.2.0, retaining 1.1 and 1.0 schemas.
- If a new serialized execution-policy shape changes `TEST_EXECUTION_REPORT`, advance only that kind by one minor and retain prior schemas; avoid the bump if data stays outside the contract.
- CLI envelope remains 1.0.0. Exact produced bytes and hashes remain the only artifact claims.

## Independent phase, completion, and traceability rules

- `analyze-function --phase analysis` cannot call TestSpec/harness writers and returns only real analysis-produced artifacts.
- Completion iterations are exactly: probe; optionally apply one safe set; optionally rerun; classify succeeded/improved/unchanged/regressed-or-unsafe/max-reached; stop deterministically. Never persist an iteration that did not execute.
- Validate `source -> condition -> candidate -> case -> generated C symbol -> execution case`. Every edge has unique `link_id`, exact endpoints, relation, and source/target artifact hashes.
- Reject missing endpoint, duplicate ID, wrong kind/path/hash/revision, cross-function, and cross-source-hash links. CSV includes `link_id` and only validated edges.
- Legacy build probe, completion reruns, VC6/NMAKE, host compiler/linker, test executable, and producer-commit lookup use the common process abstraction. Timeout preserves partial logs, maps to `TIMED_OUT`, kills/reaps descendants, and abort cleanup re-raises.

## Strict RED map

| Test module/area | RED behavior required before implementation |
|---|---|
| `tests/test_public_policy_options.py` | Complete on/off/removed parser matrix, exact emitted file set, dossier detail effects, optional-only allowance, overwrite protection, placeholder spawn behavior, build-diagnostic control. |
| `tests/test_analysis_phase_contract.py` | Analysis phase never calls TestSpec/harness writers and returns a valid exact inventory. |
| `tests/test_build_completion_loop.py` | Success, improved-then-success, unchanged, regressed/unsafe, and max-reached histories match actual probe counts and stop reasons. |
| `tests/test_traceability_integrity.py` | Complete chain accepted; duplicate/missing/wrong-hash/cross-function/cross-source rejected; CSV has link IDs. |
| `tests/test_process_control.py` and category tests | Timeout partial logs, descendants, and abort cleanup cover every subprocess category; product search finds no raw `subprocess.run` bypass. |
| TypeScript adapter/help/doc tests | Removed options reject, retained options and exact artifact sets stay synchronized, no filename/save authority returns. |

Required integration cases also prove placeholder-disabled skips process spawn, placeholder-enabled zero exit stays inconclusive, wrong evidence destinations are unavailable, and evidence preparation leaves immutable run/report/log bytes unchanged.

## Implementation slices and review checkpoints

1. Freeze parser/help behavior with a complete public-option disposition table.
2. Implement emit/dossier/optional/overwrite/placeholder/build-analysis behavior.
3. Make analysis-only and every public phase independently contract-valid.
4. Implement actual-iteration completion loop and persisted stop reasons.
5. Validate the full hash-bound traceability graph and CSV.
6. Route all subprocess categories through the process-tree abstraction.
7. Synchronize Task 7 TypeScript adapter/help/docs.
8. Run Phase 1 acceptance and fresh formal review.

## Phase 1 acceptance gate

- Focused Task 8 and related Task 1-7 regressions pass.
- Every Python test module passes separately and serially in its own process; record full totals.
- `py -m compileall -q src tests`, CLI help and removed-option snapshots pass.
- Product search finds zero raw `subprocess.run` bypasses.
- VS Code tests, compile/build, and package checks pass.
- Any schema changes pass wheel/fresh-install registry and migration tests.
- `git diff --check` passes.
- Recheck G1: schemas/semantic validators, immutable execution/evidence, exit/envelope equality, exact artifacts, canonical TestSpec, stale-aware decisions, independent axes, live-or-removed options, valid analysis/completion/traceability.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git log -1 --oneline
git switch -c codex/p1t8-phase1-policy-traceability
py -m unittest tests.test_cli_entry_point_contract -v
```

Leave the task branch clean and unmerged until a fresh reviewer approves the complete diff and the Phase 1 acceptance gate passes.
