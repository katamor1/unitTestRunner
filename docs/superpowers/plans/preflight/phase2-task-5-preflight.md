# Phase 2 Task 5 Typed TestSpec Values and Oracles Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and a fresh formal reviewer.

**Goal:** Replace raw C expression strings with a closed typed input/state/stub/oracle model bound to exact type, macro, target-context, and review identities.

**Architecture:** Tagged typed values and comparisons reference P2 T3 type IDs, P2 T2 macro fingerprints, P2 T7 target identity, and P1 T6 review IDs. Builders may create unresolved candidates, but executable placement requires complete typed structure without embedded authority.

**Tech Stack:** Python closed unions/dataclasses, JSON Schema, canonical TestSpec repository/migration, CP932 byte fixtures.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Execute after approved/merged P2 T4; P2 T3/T4 type and bridge contracts are mandatory inputs.
- Branch: `codex/p2t5-typed-test-spec`.
- `review_decisions.json` remains the only approval authority; typed values/oracles store references, never approval/status.

## Typed model contract

- Define closed tagged values for integer, float, enum, macro, NULL, address fixture, encoded string bytes, aggregate members, binary AST, and any additional explicitly justified kinds.
- Preserve integer spelling/base/width/signedness; macro definition artifact/hash/expansion fingerprint; string encoding/exact bytes; pointer fixture pointee type/element count.
- Binary expressions permit only reviewed enum operators and typed operands. Reject arbitrary statements, casts, calls, comma, assignment, and raw expression injection.
- Define exact/range/float tolerance/bytes/string+length/call-count/argument-sequence comparisons and return/global/output-buffer oracle targets.
- Parameters, globals, state, stub returns/arguments, dependencies, and oracles all reference the same P2 T3 type graph.
- Builders consume exact target/context, macro environment, type set, and stable ID builder. Ambiguous identifiers/macros become unresolved candidates and cannot be executable.

## Approval and executable-placement rules

- Generation may create non-executable candidates and review items without decisions.
- Executable placement requires complete typed values and review references. T6 performs current-decision authorization before lowering.
- Missing review IDs, unresolved values, or embedded approval/status fields cannot enter executable cases.
- Static analysis never fabricates oracle approval.

## Contract and version decisions

- Advance TestSpec from P2 T7's 1.2.0 to **1.3.0** and freeze `test_spec_v1_2.schema.json` before adding typed 1.3 shape.
- This intentionally reconciles two source briefs that independently proposed TestSpec 1.2.0: T7 already owns 1.2.0 because exact TargetIdentity is implemented earlier; T5 therefore owns 1.3.0 for typed values/oracles.
- Retain 1.2, 1.1, and 1.0 schemas plus explicit v0.1 migration behavior.
- Only obvious NULL, numeric, and encoded literal forms may migrate automatically. Preserve every other raw value as migration metadata plus stable unresolved review item, move its case to candidate/blocking, and never guess enum, macro, or approval.
- Migration is in memory and originals remain byte-unchanged.

## Strict RED map

| Test module/area | RED behavior required before implementation |
|---|---|
| `tests/test_typed_test_spec_values.py` | Round-trip NULL, `0x10U`, enum, macro/hash, typed `X-1`, CP932 bytes, aggregate, pointer/length, every oracle/comparison variant. |
| schema/model injection tests | Statement/cast/call/comma/assignment/raw C strings reject; embedded authority and missing review refs reject executable placement. |
| context/freshness tests | Debug/Release same-name macro selects exact context and stales on fingerprint change; ambiguous macro/identifier remains candidate. |
| migration tests | 1.2/1.1/1.0/v0.1 originals unchanged; obvious literals type safely; ambiguous strings preserve metadata and become unresolved review work. |
| review-decision tests | No decision still permits non-executable candidate; no typed field confers authority. |

## Verification and handoff

- Run typed model/schema/TestSpec generation/migration/contract/review/test-design focused modules.
- Run every Python module separately/serially, compileall, wheel/fresh-install/registry load, CLI smoke, and `git diff --check`.
- Inspect schema diffs to prove 1.2 was not modified and 1.3 is registered current.
- Record round-trip evidence for representative typed values and migration disposition counts.
- Leave clean and unmerged until fresh formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git switch -c codex/p2t5-typed-test-spec
py -m unittest tests.test_test_spec_contract -v
```
