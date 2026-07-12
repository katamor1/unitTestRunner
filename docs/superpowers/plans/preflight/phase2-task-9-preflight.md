# Phase 2 Task 9 Workspace Cache and Progress Protocol Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, `superpowers:systematic-debugging` for concurrency failures, and a fresh formal reviewer.

**Goal:** Reuse a validated content-keyed VC6 workspace index and emit a bounded, validated progress stream without changing semantic results or stdout CLI envelopes.

**Architecture:** Immutable sharded indexes are injected by callers through discovery and analysis; atomic cache storage is outside product source and rebuilds safely on any invalid entry. An invocation-scoped reporter emits schema-validated stderr events, while the TypeScript runner parses arbitrary chunking and preserves non-events as diagnostics.

**Tech Stack:** Python JSON/cache locks, SHA-256 content keys, stderr protocol, TypeScript `StringDecoder`, concurrency/performance fixtures.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Execute after approved/merged P2 T1, T7, T2, T3, T4, T5, and T6, and before final certification T8.
- Branch: `codex/p2t9-workspace-cache-progress`.
- Provide protocol and callback only. Phase 3 owns progress UI, coordinator state, cancellation UX, queues, and persistence.

## Workspace-index contract

- Add immutable `WorkspaceIndex`/`WorkspaceIndexKey` and sharded atomic `index_store`.
- Parse DSW/DSP topology, exact membership, P2 T1 contexts, dependency closure, and header/type lookup metadata once; inject the caller-owned index through discovery, selection, source membership, link resolution, dossier, reanalysis, and CLI rendering.
- Keys include internal parser/format versions, normalized workspace/DSW identity, DSW content hash, relative DSP paths/hashes, exact configuration, and downstream compile/type input hashes. Stat data is a read hint only.
- Shard topology, project/DSP, and source/header/type data so one change invalidates only affected/dependent shards.
- Store outside product source under output-owned cache by default. Reject product-tree roots and symlink/junction/reparse components.
- JSON has strict schema/version/size/depth limits, digest filenames, contained unique temp, fsync, atomic replace, bounded per-key cross-process locks, and safe stale-owner handling.
- Corrupt, truncated, unsupported, oversized, or hash-mismatched data emits a diagnostic and rebuilds semantically identically.
- Never cache source bodies, secrets/environment, review decisions, TestSpec, evidence, or outcomes.

## Progress protocol contract

- Inject `ProgressReporter`; use no globals. Create one invocation ID before dispatch and reuse it in final CLI result.
- Emit one flushed UTF-8 stderr line per event: `UTR_EVENT {validated JSON}`. Stdout remains exactly one final envelope.
- Protocol 1.0.0 is standalone, not an ArtifactKind and not a CLI-result version bump.
- Closed event fields include invocation ID, monotonic sequence, command, phase, state, completed/total/unit, bounded message, and diagnostic code.
- `cliRunner.ts` takes an optional callback; `progressEvent.ts` validates runtime data. Use `StringDecoder` plus carry buffer for split prefix/JSON/multibyte/lines.
- Strip valid events from returned diagnostics; preserve malformed-prefixed and normal stderr. Bound line/buffer, flush residual, preserve order, reject duplicates/out-of-order/wrong invocation, and isolate callback exceptions.

## Strict RED map

| Test module/area | RED behavior required before implementation |
|---|---|
| `tests/test_vc6_workspace_index.py` | One cold Quick Check parses each DSW/DSP once; unchanged warm run parses zero; deleting cache preserves byte/semantic output. |
| `tests/test_vc6_workspace_index_invalidation.py` | DSP/dependent/unrelated project, DSW, source/header, and same-size/same-mtime mutations invalidate exact shards; corrupt/version/oversize/delete/UNC/case/long/traversal/reparse/read-only/interrupted/two-process cases rebuild safely. |
| `tests/test_large_workspace_performance.py` | Generated hundreds-project fixture proves warm parser-call reduction and conservative elapsed ratio without absolute workstation timing. |
| Python CLI progress tests | Invocation/sequence/schema/stderr/stdout integrity, cache diagnostics, flush, bounded messages, and final-envelope identity. |
| TypeScript parser/runner tests | Split prefix/JSON/multibyte, multiple lines, malformed/oversized, callback throw, timeout residual, duplicate/order/invocation rejection, ordinary stderr preservation. |

## Verification and handoff

- Run cache/index/invalidation/performance/CLI tests, affected VC6/dossier/reanalysis/link tests, TypeScript runner/parser tests and build.
- Run every Python module separately/serially, compileall, package/schema gates, `npm.cmd test`/compile/build, and `git diff --check`.
- Compare cold/warm semantic outputs byte-for-byte where deterministic and record parser-call counts plus conservative ratio.
- Audit for repeated authoritative parser paths and import-time patches.
- Leave clean and unmerged until fresh formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git switch -c codex/p2t9-workspace-cache-progress
py -m unittest tests.test_vc6_project_context_selection -v
```
