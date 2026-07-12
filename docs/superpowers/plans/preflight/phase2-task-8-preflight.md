# Phase 2 Task 8 Host and Protected VC6 Certification Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, `superpowers:verification-before-completion`, and a fresh formal reviewer.

**Goal:** Certify the complete Phase 2 semantic pipeline with a deterministic reviewed fixture, mandatory host public-CLI E2E, and protected exact-SHA VC6-native release evidence.

**Architecture:** Checked product/review/negative fixture variants drive only public CLI subprocesses through discovery, analysis, reviewed contracts, harness, compile/link, execution, and immutable evidence. PR host verification and protected VC6 release certification are distinct, explicit gates recorded in one acceptance matrix.

**Tech Stack:** Public CLI v1, C90/CP932/CRLF fixtures, host compiler, VC6/NMAKE self-hosted workflow, GitHub Actions, immutable evidence.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Execute last in Phase 2, only after approved/merged P2 T9.
- Branch: `codex/p2t8-vc6-certification`.
- This task certifies existing semantics; it does not add Phase 3 GUI/coordinator/accessibility work.

## Deterministic reviewed fixture

- Create `tests/fixtures/vc6_execution_project/{product,reviewed,negative}` and a checked manifest of product hashes/revision.
- Cover exact Debug/Release DSPs, per-source settings, PCH, CP932 and space/Japanese paths, typedef/enum/struct/union, pointer/array/member, extern global, same-TU static target, one real dependency, and one typed stub.
- `reviewed` contains current canonical TestSpec and ReviewDecisions bound to stable semantic IDs and exact hashes, with no embedded authority.
- Keep all-pass reviewed data separate from schema/freshness/review-valid `wrong_oracle`, crash, and timeout variants.

## Host public-CLI E2E

- Drive discover/map exact target, analyze/design, load reviewed spec/decisions, harness, verification compile/link, run, and evidence through public CLI subprocesses rather than helpers.
- Validate every `CLI_RESULT` and process exit.
- Positive Debug and Release are passed/GREEN/0 with zero unresolved/placeholders, exact semantic IDs in C/evidence, complete hashes, strict CP932/CRLF/C90, no lossy patterns, unchanged product hashes, and no product-tree outputs.
- Wrong oracle exits tests-failed 32 with immutable evidence. Crash isolation attributes only the crashing case and continues later execution. Timeout is `timed_out` and leaves no descendants.
- Host compiler availability is mandatory in CI; a skipped host E2E is not a PR pass.

## Protected VC6-native workflow

- Add a schedule/manual-only self-hosted workflow with protected environment and Windows/X64/VC6 labels.
- Use read-only permissions, credential-free checkout, no untrusted PR/fork execution, no cancellation of active certification, explicit job/step timeouts, and exact approved main/release-candidate SHA verification.
- Use a clean external output root; verify `cl.exe` 12.00, NMAKE, and vcvars; exercise PCH, CP932 paths, Debug/Release, generated EXE, wrong oracle, crash, timeout, and no-orphan behavior.
- Always upload reports, logs, tool versions, and fixture manifest. Release certification applies only to the exact release SHA; an earlier scheduled GREEN is insufficient.

## Contract and acceptance decisions

- Do not invent an acceptance ArtifactKind or gratuitously bump a production schema.
- If a production shape truly gains compiler/fixture revision, advance only that kind and retain lossless migration; otherwise use existing contracts and the tracked acceptance matrix.
- `docs/vc6_acceptance_matrix.md` has one row per scalar, NULL, typedef, aggregate, pointer/array, static target, extern global, real+stub dependency, PCH, CP932 path, Debug/Release, wrong oracle=32, crash, timeout/no orphan, immutable evidence, and unchanged product.
- Each row records semantic/test ID, fixture revision/hash, host PR gate, VC6 release gate, compiler/config, automation status, evidence run/artifact, and last certified commit/date.

## Strict RED map

| Test/workflow area | RED behavior required before implementation |
|---|---|
| `tests/test_vc6_fixture_execution_e2e.py` | Public CLI positive Debug/Release full chain; exact envelope/exit/artifacts; zero unresolved/placeholders; product/output integrity. |
| negative oracle tests | Contract-current wrong oracle exits 32 and retains immutable reviewable evidence. |
| crash/timeout tests | Crash attribution and later-case execution; timeout outcome and no descendants. |
| CI contract tests | Host compiler lane cannot skip; exact required commands/artifacts/source-integrity checks are present. |
| protected workflow tests/review | Trigger, permissions, labels, exact SHA, external root, tool version, timeouts, concurrency, no fork credentials, always-upload behavior. |
| acceptance matrix validation | Every required row and evidence field exists; host and VC6 gates are distinct. |

## Phase 2 verification and stop point

- Run host E2E and all negative variants, semantic/harness/build/execution/evidence regressions, and fixture integrity checks.
- Run every Python module separately/serially, compileall, CLI/package/schema gates, extension tests where adapter behavior is exercised, and `git diff --check`.
- Confirm the full G2 checklist: per-source settings; inactive-code exclusion; one type resolver; same-TU static bridge; faithful approved values/oracles; blockers before compile; forbidden patterns absent; host positive/negative E2E; validated warm cache/progress; protected VC6 release gate semantics.
- Obtain fresh formal approval and merge. Then pause and report Phase 2 completion evidence; do not start Phase 3 without a new user instruction.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git switch -c codex/p2t8-vc6-certification
py -m unittest tests.test_execution_crash_reconciliation -v
```
