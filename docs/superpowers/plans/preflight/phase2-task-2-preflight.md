# Phase 2 Task 2 Configuration-Aware Active Source Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and a fresh formal reviewer.

**Goal:** Build one configuration-aware active-source model so inactive code disappears from authoritative facts and unknown conditions remain explicit blockers.

**Architecture:** A deterministic expression parser and provenance-ordered macro environment drive offset-preserving conditional masking. Every analyzer consumes the same `ActiveSource`; unknown regions retain stable condition IDs and can never be promoted to confirmed executable facts.

**Tech Stack:** Python tokenizer/precedence parser, CP932/CRLF source handling, JSON contracts, analyzer fixtures.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Execute after approved/merged P2 T1 and T7.
- Branch: `codex/p2t2-active-source`.
- Do not use Python `eval()` or a host preprocessor for static-analysis truth.

## Core service contract

- Add `preprocessor_expression.py`, `macro_environment.py`, and `active_source.py`.
- Support `defined`, integer/hex literals, unary/arithmetic/comparison/bitwise/shift/logical operators, precedence, parentheses, and short-circuit truth propagation.
- Macro provenance order is command line, forced include, PCH/header, then source-local `#define/#undef`; retain artifact/hash and P2 T1 context fingerprint.
- Conditional frames track parent state, prior selected branch, and current state across `#if/#ifdef/#ifndef/#elif/#else/#endif`.
- Mask inactive text with whitespace while preserving offsets, CRLF, and line count. UNKNOWN remains inspectable with stable condition IDs.
- Function-like macros, unsupported tokens, and unreadable includes become UNKNOWN rather than false or active.

## Consumer boundary

- Route source digest, function locator/signature, call/global/coverage/boundary analysis, dependency policy, dossier, and reanalysis through the same `ActiveSource`.
- Remove authoritative raw-source reopening/re-parsing paths.
- Propagate active state and condition IDs into facts.
- Block TestSpec/harness executable placement whenever target, input, oracle, call, dependency, or coverage facts depend on UNKNOWN conditions; list every stable condition ID.

## Contract and version decisions

- Advance `SOURCE_DIGEST` and all changed fact kinds—FunctionLocation/Signature, GlobalAccess, CallReport, CoverageDesign, BoundaryCandidates, DependencyPolicy—one minor from their actual P2 T7 current versions.
- Retain all old schemas. Old artifacts cannot reconstruct active/unknown provenance and are display-only/stale/blocking, never labelled active.
- Avoid a TestSpec bump if its shape is unchanged; blockers and freshness refs can carry the effect. TestSpec remains P2 T7's 1.2.0 until P2 T5.

## Strict RED map

| Test module/area | RED behavior required before implementation |
|---|---|
| `tests/test_preprocessor_expression.py` | Precedence, comparison, logical/bitwise/shift, short-circuit, `defined`, hex/integer, and unsupported-token UNKNOWN. |
| `tests/test_configuration_active_source.py` | First true branch wins; inactive parent dominates nested true child; Debug/Release source defines differ; forced include/PCH/source define-undef order; stable UNKNOWN IDs. |
| source reading/analyzer tests | CP932, CRLF, continuation offsets preserved; inactive duplicate target/call/global write/branch/boundary disappears. |
| TestSpec/harness/dependency tests | UNKNOWN facts block executable cases with condition IDs; no analyzer bypasses the shared model. |
| schema/migration tests | New fact currents validate; older semantics are display-only/stale and never fabricated active. |

## Verification and handoff

- Run focused expression, active-source, source-reading, and analyzer tests; then practical fixture, TestSpec/harness, dependency, reanalysis, contract/schema/wheel modules.
- Run every Python module separately/serially, compileall, CLI snapshots, fresh-install schema load, and `git diff --check`.
- Audit product source for authoritative direct raw-source reads in migrated analyzers.
- Record context fingerprints and stable condition IDs for Debug/Release evidence.
- Leave clean and unmerged until fresh formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git switch -c codex/p2t2-active-source
py -m unittest tests.test_c_source_reading -v
```
