# Phase 2 Task 6 Faithful Approved C90 Lowering Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and a fresh formal reviewer.

**Goal:** Lower only complete, current, approved typed cases into exact C90, with no partial placeholder or lossy fallback executable function.

**Architecture:** A whole-case generation gate validates TestSpec, target, type, macro, subject, and decision currency before pure value/oracle lowering. The P2 T4 renderer composes declarations, setup, bridges, dependency controls, invocation, and assertions exactly once.

**Tech Stack:** Python pure renderers, C90/CP932/CRLF, host compile/run fixtures, immutable harness reports.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Execute after approved/merged P2 T4 and T5.
- Branch: `codex/p2t6-c90-lowering`.
- Approval is supplied explicitly through the Task 6 ledger contract; never discover it from a conventional filesystem path.

## Generation gate and lowering rules

- `assess_case_generation_gate()` runs before any input, state, stub, dependency override, or oracle lowering.
- Verify canonical TestSpec revision/hash, P2 T7 target identity, all review IDs/resolutions, exact subject kind/path/hash/revision, P2 T2 macro fingerprints, and P2 T3 type completeness.
- Only current non-stale `APPROVED` authorizes executable assertions. Missing, stale, open, changes-requested, waived, or unresolved blocks the entire case and records every semantic ID/reason.
- `lower_value()` is pure and returns declarations, setup statements, expression, or blockers. Gather C90 declarations at function start.
- `render_oracle()` is pure and emits exact typed assertions or blockers. Exact/never call counts use equality, including zero; range uses both limits; no tautology.
- Remove state-reflector inference, dispatcher `int`/`void *` fallbacks, unsafe completion int-stub fallbacks, regex post-editing, and raw-statement injection from executable paths.
- File-static state uses P2 T4 accessors. Generated C is strict CP932/CRLF and product hashes remain unchanged.

## Reporting and contract decisions

- Harness reports mark each case generated or blocked and record semantic IDs, exact TestSpec/decision/type/macro hashes, and all blockers.
- A fully resolved case reports placeholder count 0; never use a default minimum placeholder count.
- Add explicit decision-ledger CLI/dossier input and validate it through the normal contract loader.
- If the generation-gate/report shape changes, advance only the affected harness report kind one minor from actual current, retaining prior schemas and display-only migration where exact facts are unavailable.

## Strict RED map

| Test module/fixture | RED behavior required before implementation |
|---|---|
| `tests/test_typed_harness_generation.py` | NULL, integer suffix, enum, approved macro, binary AST, exact pointer fixture/length, aggregate members, and C90 declaration order retain meaning. |
| `tests/test_reviewed_oracle_generation.py` | Exact return/global/buffer/stub count/argument assertions; exact zero and never use `== 0`; ranges use both bounds; stale/missing/waived/open/changes block. |
| harness contract/report tests | Blocked cases emit no executable function and list all semantic IDs; resolved placeholder count is zero; report hashes match exact inputs. |
| forbidden-pattern audit | Generated C contains none of `0 /* candidate:`, `TBD_EXPECTED_RETURN_INT`, `GetCallCount() >= 0`, or opaque `double[512]` pointer fixtures. |
| host fixture | Strict CP932/CRLF C90 compiles/runs, assertions execute, and product bytes/hash are unchanged. |

## Verification and handoff

- Run typed harness/oracle/dependency/state/build/TestSpec/CLI regressions and fixture compile/run.
- Run every Python module separately/serially, compileall, applicable schema/package gates, CLI smoke, forbidden-pattern search, and `git diff --check`.
- Review generated C and exact report inputs for at least one scalar, one pointer/aggregate, and one blocked case.
- Record generated/blocked counts, blocker IDs, fixture results, and product hash comparison.
- Leave clean and unmerged until fresh formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git switch -c codex/p2t6-c90-lowering
py -m unittest tests.test_harness_skeleton_generation -v
```
