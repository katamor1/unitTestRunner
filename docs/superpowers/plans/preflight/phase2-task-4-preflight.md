# Phase 2 Task 4 Explicit Typed and Same-TU Bridge Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and a fresh formal reviewer.

**Goal:** Remove harness import-time compatibility monkeypatches and generate exact typed public/static bridges from the shared type graph without modifying product source.

**Architecture:** Pure bridge planning consumes P2 T3 resolved types; extracted source copies receive explicit same-translation-unit wrappers and permitted state accessors. A canonical renderer receives dependencies explicitly and strict encoding blocks before compilation.

**Tech Stack:** Python renderers, generated C90/CP932/CRLF, host compile/link, hash-chain contracts.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Execute after approved/merged P2 T3.
- Branch: `codex/p2t4-explicit-bridges`.
- P2 T3 `ResolvedCType` is the sole authority; never add regex, `int`, or `void *` fallback.

## Deliverable map

- Refactor `harness/type_bridge.py` so `plan_target_bridge()` is pure and returns exact prototype, verified headers, same-TU requirement, generated symbol, accessors, blockers, and input fingerprints.
- Add `build/translation_unit_bridge.py` for contained extracted-copy bridge append and truthful pre/post hashes.
- Add canonical `harness/test_function_renderer.py`; pass all renderer/lowering dependencies explicitly.
- Delete `harness/target_invocation_compat.py` and `parameter_init_compat.py`; package/direct imports must not mutate private function identities.
- Audit the build package so no import-time patch restores global compile flags or bypasses the explicit plan.

## Bridge and encoding rules

- For static targets, copy/isolate product source, append a non-static wrapper in that extracted translation unit, then apply dependency rewrite.
- Record product, pre-bridge extracted, post-bridge, and final build hashes separately; original product bytes/hash never change.
- Generate file-static accessors only for completely resolved scalar, enum, or pointer types. Aggregates, callbacks, incomplete by-value, and ambiguous types block. Pointer accessors retain exact pointee types.
- Generated/extracted C never uses `errors="replace"`. Unrepresentable CP932 produces a structured blocker before compiler spawn.
- Package and direct-module entrypoints render byte-identical output and import order changes no function identity.

## Contract and version decisions

- If serialized bridge plan, hash chain, or encoding metadata changes harness/build report shape, advance only the affected kinds one minor from actual current and retain old schemas.
- If exact facts cannot be reconstructed, old data is display-only rather than fabricated.
- Do not bump TestSpec or unrelated kinds in this task.

## Strict RED map

| Test module/area | RED behavior required before implementation |
|---|---|
| `tests/test_static_target_bridge.py` | Static target links only through appended same-TU symbol; exact scalar/enum/pointer accessors; aggregate/state ambiguity blocks; product unchanged with truthful hash chain. |
| target invocation/type tests | Typedef, calling convention, array, pointer prototypes exactly match resolver; no fallback prototype. |
| module-boundary tests | Importing harness/build never changes generator/private identities; compat modules are absent; package/direct rendering matches. |
| `tests/test_build_output_encoding.py` | Unrepresentable CP932 writes no replacement bytes and blocks compile unit before spawn; CRLF/C90 retained. |
| workspace/host verification | Extracted append/rewrite order is correct and host compile/link exercises the explicit bridge. |

## Verification and handoff

- Run resolver/bridge/static/build-boundary/encoding/workspace/host-verification/harness regressions.
- Run every Python module separately/serially, compileall, fixture compile/link, applicable package/schema gates, and `git diff --check`.
- Audit for removed compat files, import-time patch calls, generated `errors="replace"`, and fallback types.
- Record original/pre/post/final hashes and exact prototype for at least one static fixture.
- Leave clean and unmerged until fresh formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git switch -c codex/p2t4-explicit-bridges
py -m unittest tests.test_build_and_execution_module_boundaries -v
```
