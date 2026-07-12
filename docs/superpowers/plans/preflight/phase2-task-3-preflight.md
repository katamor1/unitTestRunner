# Phase 2 Task 3 Shared C Type Resolver Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and a fresh formal reviewer.

**Goal:** Replace target, dependency, bridge, and parameter type heuristics with one active-context-aware type graph carrying exact ABI facts and provenance.

**Architecture:** A shared `CTypeResolver` consumes raw declarators and P2 T2 active headers under each source's P2 T1 context. Resolved type IDs and complete graphs become the only ABI comparison authority; ambiguity and incomplete by-value types are explicit blockers.

**Tech Stack:** Python C declarator parsing, immutable type graph, JSON contracts, practical C fixtures.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Execute after approved/merged P2 T2.
- Branch: `codex/p2t3-type-resolver`.
- This task resolves types only; T4 generates bridges, T5 defines typed values, and T6 lowers C.

## Resolver contract

- Add `CTypeResolver`, `HeaderSource`, `CTypeKind`, `ResolvedCType`, and `TypeResolutionSet` in `c_analyzer/type_resolver.py`.
- Resolve raw declarations, not only stripped type strings.
- Each type records stable `type_id`, canonical spelling, qualifiers/calling convention, provenance path/hash, compile-context fingerprint, diagnostics, pointee/element/extent, function signature type IDs, aggregate/enum members, and completeness.
- The same implementation serves target and dependency sources, but each dependency resolves under its own effective context and active headers.
- Permit pointer-to-incomplete; block incomplete aggregate by value. Variadic, cyclic, conditional, or conflicting cases produce typed blockers rather than a fallback.

## Integration boundary

- Signature extraction passes raw declarators and stores resolved refs/type graph. Legacy `classify_type()` becomes display compatibility only.
- Dependency signature discovery retains location evidence but deletes independent typedef/category/canonicalization logic.
- ABI comparison uses stable type IDs plus complete graphs; dict last-wins and lossy declarator stripping are forbidden.
- Dossier/reanalysis create the resolver from exact selected target context and active headers.
- Do not add heuristics to `harness/type_bridge.py`; T4 consumes the graph explicitly.

## Contract and version decisions

- Advance `FUNCTION_SIGNATURE` and `DEPENDENCY_POLICY` one minor from their actual P2 T2 current versions.
- Retain every prior schema. Old category strings cannot prove completeness, provenance, or type ID and migrate only to unknown/review-required display state.
- Embed/reference the resolution set through signature hash/type IDs; do not create a redundant standalone ArtifactKind unless implementation proves a contract boundary that cannot be represented.

## Strict RED map

| Test module/fixture | RED behavior required before implementation |
|---|---|
| `tests/test_type_resolver.py` | Builtin/scalar chains, pointer typedef, incomplete pointer/value rules, tagged/anonymous struct/union, nested members/arrays, enum values, function pointers, calling convention, arrays, variadic/cycles. |
| active-context conflict tests | Active conflicting typedef is ambiguity; inactive conflict disappears; UNKNOWN conflict blocks; same typedef under differing source contexts blocks when ABI differs. |
| `tests/test_dependency_signature_resolver.py` | Target and dependency spelling resolve to same type ID/canonical ABI; no independent category logic remains. |
| practical fixture | Aggregates, callback, macro array extents, direct/typedef function pointers, and provenance hashes resolve consistently. |
| contract/reanalysis tests | Old schema is display-only; exact type IDs survive dossier, TestSpec freshness, and reanalysis references. |

## Verification and handoff

- Run resolver/signature/dependency focused tests, practical fixture, bridge/dispatcher compatibility regressions, TestSpec/provenance/reanalysis, and schema/wheel gates.
- Run every Python module separately/serially, compileall, CLI smoke, fresh-install registry load, and `git diff --check`.
- Product audit must find one semantic type authority; legacy classifiers cannot drive executable decisions.
- Record type IDs/provenance for representative aggregate, callback, and target/dependency equivalence cases.
- Leave clean and unmerged until fresh formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git switch -c codex/p2t3-type-resolver
py -m unittest tests.test_dependency_signature_resolver -v
```
