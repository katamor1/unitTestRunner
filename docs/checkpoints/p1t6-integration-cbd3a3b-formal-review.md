# Phase 1 Task 6 base-to-head review

- Base: `b66790165a2d4f82943cd199b3b499e1f1725fc3`
- Head: `9c1075375a902f5e1a3f443eff9b4d1cd456c2f8`
- Scope: review decisions, exact subject currency, semantic readiness, CLI discovery/write, Task 6 schema versions.

## Spec compliance

- Stable semantic IDs: implemented in `review_ids.py`; tests cover Unicode/separators, C identifier case, reorder/localization, collisions, and TestSpec/dossier parity.
- Closed decision models and 1.0→1.1 migrations: implemented; immutable 1.0 resources retained for `review_decisions`, `function_dossier`, and `dossier_manifest`.
- Atomic repository: same-directory exclusive temp write, fsync, replace, exact final-byte verification, revision/fingerprint guards, containment and symlink/reparse rejection.
- Exact subject currency: path/kind/hash/revision/schema/source/function/semantic subject checks; record path re-resolves current dossier under the ledger lock and rejects subject bytes changed after discovery.
- Readiness: `ready_for_review`, `review_complete`, `evidence_ready`, and `test_green` remain independent; only `RunOutcome.PASSED` is GREEN.
- CLI: `get-review-status` and `record-review-decision` use CLI v1 envelope and exact ProducedArtifact output.
- Scope boundary: no VS Code extension changes and no Phase 1 Task 8 policy/process changes.

## Verification evidence

- Authoritative isolated Python gate: 117/117 modules, 563 tests, 2 skips, 0 failures, 0 errors, 0 nonzero modules.
- Focused package/schema gate: 37 tests passed.
- `compileall`: passed.
- CLI help: passed.
- `git diff --check`: passed.
- Fresh wheel install: CLI starts from installed wheel; 40 artifact kinds and 44 registered contract versions load from package resources.
- Host VC6 fixture compile/link E2E: passed in isolated full gate.

## Review findings

- Critical: 0
- Important: 0
- Minor: 0 blocking findings

One Important issue was found during review and fixed before this verdict: a subject artifact could change after discovery while an old subject fingerprint was still accepted. Commit `9c10753` now re-resolves the current dossier and validates subject bytes under the ledger lock; a RED/GREEN CLI regression test covers the no-write behavior.

## Verdict

**Approved for integration**, based on the complete base-to-head review and fresh verification above.

Limitation: no separate subagent reviewer was available in this runtime; this is a structured independent review pass by the executing agent, supplemented by the full isolated test, package, fixture, and contract gates.
