# Phase 2 Task 7 Exact VC6 Target Identity Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and a fresh formal reviewer.

**Goal:** Require reviewable exact DSW/DSP/project/full-configuration/source selection and bind every function-scoped artifact to one stable target identity.

**Architecture:** Candidate discovery is deterministic but never first-match authority. Selection happens before any output write; a shared `TargetIdentity` separates stable project/function identity from content/build-context revision facts and is semantically validated across artifacts.

**Tech Stack:** Python VC6 discovery, CLI v1 envelopes, JSON Schema, practical multi-DSP fixtures.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Execute after approved/merged P2 T1 and before P2 T2.
- Branch: `codex/p2t7-project-config-identity`.
- Do not add active preprocessing, shared type resolution, typed bridges, or generated-C behavior.

## Candidate and selection contract

- Add `ProjectContextCandidate`, `SelectedProjectContext`, and typed ambiguous/not-found errors.
- Candidate evidence includes deterministic DSW/DSP relative paths, project, full configuration, source, DSP location, exclusion, and effective-context fingerprint.
- Discovery order is DSW order then DSP configuration order. Execution auto-selects only when exactly one valid non-excluded candidate exists.
- Multiple candidates require exact project plus exact full configuration. Reject `Debug`, `Win32 Debug`, case-insensitive aliases, and ambiguous defaults as execution authority.
- Remove implicit `Win32 Debug` from analyze, quick-check, and reanalysis.
- Selection and ambiguity validation occur before output directory, request, temp, or artifact creation.
- Analysis, reanalysis, and quick-check share the same selector and machine-readable nonzero ambiguity envelope.

## Target identity contract

- Stable logical target ID derives from DSW, DSP, project, full configuration, source, and function semantic ID.
- Revision facts include source hash/range plus signature and build-context fingerprints.
- Project/configuration changes create a distinct logical target. Source content changes stale the same logical target revision.
- Every function-scoped artifact carries and validates the same explicit identity; do not hide it in `extensions` or reuse `stable_function_id` alone.
- Cross-project, cross-configuration, source-context, or revision mixing is rejected semantically.

## Contract and version decisions

- Advance each affected function-scoped kind one minor from its actual current registry version and retain every earlier schema.
- TestSpec must gain explicit TargetIdentity. Because the approved execution order is T1, T7, T2, T3, T4, T5, advance TestSpec from 1.1.0 to 1.2.0 in this task.
- The P2 T5 source brief also proposed 1.2.0 independently for typed values. That is not a transcription error: T5 will instead advance TestSpec from this task's 1.2.0 to 1.3.0. Both schemas remain immutable and supported according to migration policy.
- Older artifacts lacking exact project/configuration are display-only/stale or fail typed migration; never fabricate identity.

## Strict RED map

| Test module/fixture | RED behavior required before implementation |
|---|---|
| `tests/test_vc6_project_context_selection.py` | Same source in two DSPs returns structured candidates and writes nothing; short names never select; exact project/full config selects one; excluded membership is invalid. |
| practical multi-DSP fixture | Multiple configs in one project remain ambiguous; analyze/reanalysis/quick-check produce identical candidate/error behavior. |
| identity/contract tests | Same source/function across contexts has distinct logical IDs; source hash changes revision not project target; mixed artifact identities reject. |
| CLI no-write tests | Ambiguity is a truthful nonzero input outcome and leaves no output/request/temp artifacts. |
| schema/package tests | New current schemas load from source and fresh wheel; every prior schema remains immutable; unprovable migration is display-only. |

## Verification and handoff

- Run selection, membership, CLI, identity, contract, and practical fixture tests.
- Run every Python module separately/serially, compileall, CLI help/error snapshots, wheel/fresh-install registry checks, and `git diff --check`.
- Review the complete list of function-scoped kinds changed; reject a partial identity rollout that permits artifact mixing.
- Record the actual pre-task registry versions and resulting versions in the report.
- Leave clean and unmerged until fresh formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git switch -c codex/p2t7-project-config-identity
py -m unittest tests.test_vc6_project_context_selection -v
```
