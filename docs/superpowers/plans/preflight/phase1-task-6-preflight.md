# Phase 1 Task 6 Review Decisions and Semantic Readiness Preflight

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and a fresh formal reviewer.

**Goal:** Persist exact, stale-aware review decisions and calculate review, evidence, and GREEN readiness without file-existence or embedded-approval authority.

**Architecture:** One stable review-ID builder feeds dossier and TestSpec references. A lock-protected exact-bytes ledger repository resolves subject artifacts itself, while a shared assessment service computes decision currency and four independent readiness axes.

**Tech Stack:** Python dataclasses/enums, JSON Schema, atomic same-directory writes, SHA-256, CLI v1 envelope, `unittest`.

## Status, prerequisite, and branch

- Product implementation status: **not started**.
- Recorded Task 5 foundation: head `b5baacd`, formally Approved with Critical/Important/Minor all 0, integrated as `36622ed`; retain `36622ed` as an ancestor. See the [completion baseline](README.md#task-5-completion-baseline) for verification evidence.
- Start only after Phase 1 Task 5 is formally approved and merged into `codex/unit-test-runner-hardening-sdd`.
- Branch: `codex/p1t6-review-decisions-readiness`.
- Preserve Task 5 canonical TestSpec 1.1.0, immutable-run/evidence, truthful outcomes, and exact-saved-bytes behavior.
- Do not implement VS Code adoption or Task 8 policy/traceability changes.

## Deliverable map

- Create `src/unit_test_runner/dossier/review_decision_models.py` for resolutions, exact subject references, decision sets, and assessment collections.
- Create `src/unit_test_runner/dossier/review_decision_repository.py` for contained lock/temp paths, expected revision, exact-byte atomic persistence, and conflict results.
- Create `src/unit_test_runner/dossier/review_assessment.py` for stable IDs, subject currency, orphan detection, and the four readiness axes.
- Modify dossier review generation/finalization/readiness so `done` and embedded status never confer authority.
- Add CLI discovery and `record-review-decision`; both use the same validated semantic snapshot.
- Add/modify schemas for only the kinds listed below.

## Contract and version decisions

- `reports/review_decisions.json` is the sole approval authority.
- Advance `REVIEW_DECISIONS`, `FUNCTION_DOSSIER`, and `DOSSIER_MANIFEST` to 1.1.0. Keep immutable 1.0 schemas and definitions.
- A 1.0 decision without provable subject revision migrates with `revision: null`; it is stale/blocking against a revisioned current subject.
- Old `done=true` survives only as non-authoritative migration metadata.
- Reuse the Task 5 current-version builder and exact final-byte `ProducedArtifact` pattern.
- The CLI envelope remains 1.0.0.

## Semantic rules fixed before coding

- Stable ID tuple is `(category, function_id, optional_case_id, semantic_subject_key)` after Unicode NFKC, outer-whitespace trimming, and separator normalization. Do not case-fold C identifiers or include order, title, localization, paths, artifact revisions, or hashes.
- Different semantic tuples producing one ID are a typed collision. Reordered or localized items keep IDs; changed semantic subjects create new IDs and leave prior decisions orphaned.
- The repository resolves the current review item and its exact subjects. Callers provide only review ID, resolution metadata, expected ledger revision, and aggregate subject fingerprint.
- Aggregate fingerprints use sorted canonical subject references: kind, normalized relative path, exact SHA-256, and revision where defined.
- Terminal `approved`, `changes_requested`, and `waived` require nonblank reviewer/rationale and a timezone-aware canonical timestamp. Waiver never authorizes Phase 2 executable generation.
- Subject currency requires exact path, kind, hash, revision, strict-current contract validity, source/function identity, and semantic subject identity.
- Avoid a finalization cycle: dossier decisions bind stable input artifacts, not a `function_dossier.json` whose hash changes when decisions are summarized.
- Readiness axes are independent: `ready_for_review`, `review_complete`, `evidence_ready`, `test_green`. Only terminal `RunOutcome.PASSED` is GREEN; failed/blocked/inconclusive/cancelled/timed-out/error evidence may still be reviewable.

## Strict RED map

| Test module | RED behavior required before implementation |
|---|---|
| `tests/test_review_decisions.py` | Stable IDs survive reorder/localization; dossier and TestSpec share IDs; collisions fail; terminal metadata validates; unknown IDs/subject guards write nothing; sequential/concurrent stale writers yield one success; containment/reparse checks reject; 1.0 migration is lossless and leaves input bytes unchanged. |
| `tests/test_review_decision_staleness.py` | Byte/hash, revision, path, kind, missing/moved, invalid JSON, schema-invalid, and semantic-key changes produce stale/orphan states; only exact current approved/waived decisions complete review. |
| `tests/test_dossier_readiness.py` | Table every `RunOutcome`; mtime/existence cannot advance readiness; optional absence affects only declared dependencies; compatible-migrated artifacts are display-only. |
| CLI contract tests | Success returns one exact ProducedArtifact; unknown ID, stale revision, fingerprint mismatch, invalid waiver, and I/O failure are nonzero/no-write/no-artifact; discovery exposes validated guards and four axes. |

Establish failures for the repository, assessment, and CLI seams before product implementation. Do not make a RED test pass by weakening Task 1-5 contract validation.

## Implementation slices and review checkpoints

1. Stable-ID builder plus dossier/TestSpec parity and collision tests.
2. Closed decision models and kind-specific 1.0-to-1.1 migration.
3. Atomic repository with containment, lock, exact bytes, revision and subject guards.
4. Shared subject resolver and stale/orphan assessment.
5. Independent semantic readiness using immutable execution/evidence loaders.
6. Validated discovery plus write CLI envelopes from one snapshot.
7. Focused, related, isolated full, package/schema, CLI, and diff gates.

Each slice may be a commit, but the fresh reviewer judges the complete base-to-head task diff. Resolve all Critical/Important findings before merge.

## Verification and handoff

- Focused: the three named modules and Task 6 CLI cases.
- Related: Task 1-5 contracts, dossier, TestSpec, execution, evidence, and CLI modules.
- Full: enumerate every `tests/test_*.py` module and run each separately and serially in a fresh Python process as defined in [the handoff policy](README.md#authoritative-isolated-verification-policy).
- Run `py -m compileall -q src tests`, CLI discovery/write smoke, wheel/fresh-install schema registry checks, and `git diff --check`.
- Run VS Code tests only if extension files are touched unexpectedly; such changes require scope review first.
- Record RED evidence, commit IDs, exact schema versions, module/test/skip/failure/error/nonzero totals, limitations, and reviewer verdict.
- Leave the task branch clean and unmerged; merge only after fresh formal approval.

## Restart commands

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git switch codex/unit-test-runner-hardening-sdd
git status --porcelain
git log -1 --oneline
git switch -c codex/p1t6-review-decisions-readiness
py -m unittest tests.test_test_spec_contract -v
```

If the base is dirty, Task 5 is not merged, or the Task 5 focused module fails, stop before creating product changes.
