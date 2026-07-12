# Phase 1 Task 7 VS Code Canonical-Contract Adoption Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and a fresh formal reviewer.

**Goal:** Make the VS Code extension advance workflow state only from validated CLI envelopes, exact produced artifacts, review decisions, immutable evidence, and semantic readiness.

**Architecture:** The extension always requests JSON, validates the v1 envelope before interpreting process exit, consumes Task 6 discovery guards, and derives UI state from independent readiness axes. Paths remain display/open candidates rather than completion authority.

**Tech Stack:** TypeScript 5.4, VS Code 1.85 Extension API, Node tests, Python CLI v1 envelope.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Start only after Phase 1 Tasks 5 and 6 are formally approved and merged.
- Branch: `codex/p1t7-vscode-contract-workflow`.
- Do not implement Task 8 option policy, completion-loop, traceability, process unification, or placeholder rules.

## Required backend seam

Task 6 discovery must provide one validated snapshot containing ledger revision, current review IDs, aggregate subject fingerprints, resolution currency, blocked reasons, and `ready_for_review`, `review_complete`, `evidence_ready`, `test_green`. The extension must not parse an unvalidated ledger, infer conventional paths, or ask users to type opaque IDs/hashes.

## Deliverable map

- Update `vscode/extension/src/cli/commandBuilder.ts`, `cliEnvelope.ts`, and `cliResultParser.ts` for always-JSON commands, Task 6 guards, and exit/envelope agreement.
- Update `reports/reportPathResolver.ts` to resolve by validated artifact kind/inventory.
- Replace save/file authority in `workflow/workflowState.ts` and `workflowPanelBase.ts` with semantic state and explicit decisions.
- Update `extension.ts`, `commands/commandRegistry.ts`, and `package.json`; command registration and contributions are part of the contract.
- Update user/developer documentation for canonical TestSpec, generated views, decision authority, immutable evidence, migration notices, and outcome semantics.

## Contract and version decisions

- CLI envelope remains 1.0.0.
- TestSpec current at this task is 1.1.0.
- Task 6 `FUNCTION_DOSSIER`, `DOSSIER_MANIFEST`, and `REVIEW_DECISIONS` current at 1.1.0.
- Other kinds use their registry current versions; never hardcode a global 1.0.0 artifact version.
- This task adds no production schema bump. Compatible older/v0.1 artifacts are display-only with explicit source/current versions, original path, no-auto-save status, and required action.

## Semantic and UI rules fixed before coding

- Every workflow invocation supplies `--json`, independent of display preferences.
- Harness uses `--test-spec reports/test_spec.json`; reanalysis uses the canonical previous-TestSpec option. Never regenerate legacy editable aliases.
- Validate the envelope first, then require process exit to equal envelope `exit_code`. Preserve valid nonzero terminal envelopes and their artifacts.
- Expected artifacts are never completion proof. Produced artifacts must match kind, normalized path, exact hash, revision, workspace, and function identity.
- Remove `AwaitingSave`, manual `confirmStep`, document-save completion, and existence backfill as authority. Legacy persisted flags migrate without current authority.
- Keep review completeness, evidence availability, and GREEN visibly separate. Only `passed` is GREEN; all other terminal evidence remains truthful and openable.
- Workspace/function changes clear prior semantic state.
- `test_spec.md`/CSV are generated review views; canonical changes use `update-test-spec`.

## Strict RED map

| Test area | RED behavior required before implementation |
|---|---|
| CLI parser tests | Only fully validated v1 envelopes advance state; process/envelope exit mismatch rejects; nonzero terminal artifacts survive; malformed discovery/readiness rejects; per-kind current versions and display-only older versions are distinguished. |
| Command/path adapter tests | Always `--json`; canonical TestSpec options; discovered decision ID/revision/fingerprint reproduced exactly; artifact-kind inventory resolves immutable run/evidence and ledger; conventional existence never completes. |
| Workflow state tests | Table four independent axes; planned is no evidence/GREEN; passed alone is GREEN; stale/missing/open/changes review is incomplete; one decision cannot complete multiple items; mtime/existence changes nothing. |
| Panel/registry tests | No save-confirm UI; explicit decision actions; separate review/evidence/GREEN rendering; migration notice is complete; failed evidence is not complete/GREEN; command is registered and contributed once. |

Include tests for workspace/function changes and legacy persisted state so prior completion/save flags cannot leak authority.

## Implementation slices and review checkpoints

1. Runtime types/validators for Task 6 discovery and all terminal envelope rows.
2. Command builder and path inventory using canonical TestSpec and exact decision guards.
3. Semantic workflow-state migration with no filename/save authority.
4. Panel actions and separate readiness/outcome rendering.
5. Activation, registry, package contributions, and documentation.
6. Focused extension tests/build, related Python adapter tests, and diff checks.

## Verification and handoff

- Run focused extension parser, adapter, workflow state, panel, registry, and package tests.
- Run `npm.cmd test`, TypeScript compile/build, and package checks.
- Run related Python CLI/contract modules separately. If any Python product file changes, run every Python module separately and serially through the authoritative isolated full gate.
- Run `git diff --check`; run package/help snapshots that prove Task 6 commands remain discoverable.
- Record RED evidence, Node/Python totals, exact migration display behavior, limitations, commits, and fresh reviewer verdict.
- Leave clean and unmerged until formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git log -1 --oneline
git switch -c codex/p1t7-vscode-contract-workflow
Set-Location .\vscode\extension
npm.cmd test
```

Do not start if Task 6 discovery cannot return validated opaque guards and all four readiness axes.
