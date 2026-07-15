# Phase 1 Task 6 Review Decisions and Semantic Readiness Execution Plan

> **Execution rule:** Use task-scoped fresh implementers and fresh spec/code-quality reviewers. Only one agent writes the product worktree at a time. Every behavior change starts with an assertion-level RED, then the smallest GREEN, then focused regression and review.

> **Review acceptance rule:** Every future Task 6 slice, reconciliation checkpoint, and final candidate is accepted only when fresh spec and code-quality reviews both report **Critical 0 / Important 0 / Minor 0** (`C0/I0/M0`). Historical review evidence retains its exact recorded counts, but it never weakens this forward gate.

**Goal:** Move the hardening program from **13/38** to **14/38** by delivering one carrier-free Task 6 product pull request that persists exact stale-aware review decisions and reports review, evidence, and test readiness from semantic state rather than file existence or embedded approval flags.

**Architecture:** One public stable review-ID builder is shared by dossier and TestSpec. A lock-protected review-decision repository resolves current review items and their exact subject bytes itself while holding the ledger lock. A separate assessment service derives subject currency, orphan state, and four independent readiness axes. Contract 1.0 remains immutable; current 1.1.0 is explicit and migration is lossless.

**Tech stack:** Python 3.12 dataclasses/enums, JSON Schema 2020-12, `jsonschema`, direct `referencing` dependency, SHA-256, same-directory atomic replacement, bounded Windows sharing-denial retry, CLI envelope 1.0.0, `unittest`, setuptools wheel metadata.

---

## 1. Authority, starting point, and progress rule

### Authoritative inputs

- `docs/superpowers/specs/2026-07-14-phase1-task6-staged-recovery-design.md`
- `docs/superpowers/plans/preflight/phase1-task-6-preflight.md`
- Task 6 in `docs/superpowers/plans/2026-07-11-unit-test-runner-phase-1-contract-execution-evidence.md`
- `docs/superpowers/plans/2026-07-11-unit-test-runner-hardening-master.md`

If an implementation detail conflicts with those documents, stop that slice and resolve the mismatch before product code continues. The preflight semantic rules take priority over recovered implementation details.

### Clean starting point

- Product worktree: `C:\Users\stell\source\repos\unitTestRunner-postmerge-pr17`
- Branch: `codex/p1t6-review-decisions-readiness-clean`
- Base: `969ce9462a688e94c887d6e77359e40296d8927b`
- Base meaning: PR #17, PR #18, and Windows writer-lock hotfix PR #19 are merged into `main`.
- Main push CI run: `29352868580`, all 6 jobs GREEN.
- Main Python evidence: 112 independently executed modules, 543 tests, 0 failures/errors/nonzero modules; writer-snapshot regression GREEN; 7 Windows path aliases GREEN.
- Main VC6 evidence: real `C:\mingw64\bin\gcc.exe`, non-skipped build E2E GREEN.

The primary checkout at `C:\Users\stell\source\repos\unitTestRunner` contains user-owned staged/untracked work and must not be changed. All Task 6 writes occur only in the product worktree above.

### Progress accounting

- Keep progress at **13/38** throughout implementation, review, PR checks, and pre-merge verification.
- Advance to **14/38** only after the carrier-free Task 6 PR is merged, the exact merge SHA passes post-merge local checks and hosted `main` checks, and the tracked progress/handoff documents are updated in a separate post-merge documentation commit.
- Before starting Task 7 product code, write and commit the Task 7 execution plan from the then-current `main`.

---

## 2. PR #11-#16 recovery and cleanup boundary

Open draft PRs #11 through #16 are obsolete recovery work. None is a merge candidate or an implementation authority. PR #16 (`codex/bootstrap-p1t6-v3`) is additionally a transport carrier whose recovered bytes may be consulted only under the rules below.

Verified recovery identity:

- Source base: `b667901`
- Reconstructed tree on that base: `363ddb6f86a4508eb5f4dd2a26013b837a5e26d6`
- gzip bytes: 41,476
- gzip SHA-256: `121bfc6fdcbb6e8728402997f291a0ef3af000d775d3c8bca791e0de28d13123`
- patch bytes: 223,625
- patch SHA-256: `8aaa74a87b2e1ea64087726bbcbfd8c998d5940c458d04768b63f969fe461ef0`
- Reconstructed patch check against base `969ce946`: clean.

Rules:

1. Never merge any of PRs #11 through #16.
2. Never run a bulk `git apply` of the PR #16 carrier patch in the product worktree.
3. Use `git show 363ddb6f86a4508eb5f4dd2a26013b837a5e26d6:<path>` only to inspect individual intended behavior or test wording after the authoritative design has been read.
4. Recreate each behavior with a new assertion-level RED on the current tree.
5. Do not copy PR #16 carrier code that predates PR #19's Windows sharing-denial semantics.
6. Retain all six open draft PRs until the new carrier-free Task 6 product PR is merged and that exact merge SHA passes both post-merge local checks and the hosted `main` checks.
7. Only then close PRs #11, #12, #13, #14, #15, and #16 through GitHub and read each one back with `state=CLOSED`.
8. Do not delete any remote branch as part of this recovery or cleanup sequence.

---

## 3. Fixed semantic decisions

These decisions are not reopened during coding unless a direct contradiction is found in an authoritative input.

### Review IDs

- One public builder owns the ID algorithm for dossier and TestSpec.
- Semantic tuple: `(category, function_id, optional_case_id, semantic_subject_key)`.
- Normalize with Unicode NFKC, outer-whitespace trimming, and separator normalization.
- Do not case-fold C identifiers.
- Do not include ordinal position, title, localized text, file path, artifact revision, or hash.
- Reorder and localization preserve IDs.
- A changed semantic subject produces a new ID and leaves the previous decision orphaned.
- Two distinct normalized tuples producing one ID are a typed collision, never a silent merge.

### Contracts and migrations

- Current `REVIEW_DECISIONS`, `FUNCTION_DOSSIER`, and `DOSSIER_MANIFEST` are 1.1.0.
- Their 1.0 schemas and all definitions reachable from those schemas are immutable.
- Add `common_v1_0.schema.json`; every 1.0 schema, including the existing TestSpec 1.0 schema, must stop referencing mutable `common.schema.json`.
- Migration is lossless and does not mutate input bytes or input objects.
- Every newly recorded 1.1 decision is repository-owned `authority="current"` with `source_schema_version="1.1.0"`; callers cannot choose either field. Every migrated 1.0 decision is explicitly `authority="display_only"` with its source schema version, regardless of whether a revision can be reconstructed. An unprovable subject revision also migrates as `revision: null`. Assessment requires current authority as well as exact references, so a migrated decision can never become authoritative merely because its null revision happens to match a legitimate unrevisioned current subject.
- Legacy `done=true` is retained only as non-authoritative migration metadata.

### Decision authority and repository boundary

- Only `reports/review_decisions.json` can authorize approval/waiver/change requests.
- Embedded dossier/TestSpec status and `done` never confer authority.
- Every decisionable current review item has at least one exact selected subject reference; empty `subject_artifacts` is invalid in models, schemas, discovery, and repository writes. The generic final-review fallback binds exactly a present strict-current TestSpec. Only verified absence of the TestSpec path permits the analysis-only fallback to the three strict-current MVP1 core artifacts: source digest, function location, and function signature; a present legacy/invalid/mismatched TestSpec fails closed and cannot be bypassed by the core fallback. If neither choice is eligible, no decisionable fallback is emitted and both `ready_for_review=false` and `review_complete=false`; empty `all(items)` must never vacuously authorize Phase 2.
- Callers supply review ID, resolution metadata, expected ledger revision, and the aggregate subject fingerprint observed during discovery.
- The repository, while holding its ledger lock, resolves the exact current review item and subject artifacts again.
- DOSSIER_MANIFEST 1.1 contains a `review_subject_snapshot` generation fence: monotonic generation, publication state (`dirty`, `publishing`, or `complete`), transaction token, source/function identity, sorted exact subject references, decision `subject_fingerprint`, full-state `snapshot_id`, and `previous_complete` identity. The authoritative preflight fingerprint projection is exact and narrow: `subject_fingerprint` hashes only each selected decision reference's artifact kind, normalized workspace-relative POSIX path, exact lowercase SHA-256, and nullable revision. Role/source/function/semantic fields remain mandatory full currency identity and snapshot-descriptor inputs, but do not alter that four-field aggregate fingerprint. Neither ID includes physical snapshot storage paths. `snapshot_id` hashes the versioned canonical logical full-state descriptor fixed below: nullable external-source/function identity, the exact published external-source observation plus sorted `core_source_reasons`, the closed mutation-path presence/byte map, selector binding, selected decision/readiness references and required-evidence file facts, sorted full normalized review-item bindings, and fixed logical immutable slots.
- Each full review-item binding stores `(review_id, category, function_id, case_id, semantic_subject_key, exact subject references)`. The publisher verifies that the semantic fields are already canonical-normalized and that `build_review_id(category, function_id, case_id, semantic_subject_key) == review_id`; every nonempty item has at least one exact selected reference. The immutable index—not mutable dossier summary bytes—is the sole source from which the resolver reconstructs `ReviewItemSnapshot` values.
- The snapshot-ID descriptor excludes `snapshot_id` itself, generation/token/manifest bytes, physical `reports/review_subject_snapshots/<snapshot_id>` prefixes, and the stored index/hash. Physical snapshot paths are derived only after the ID is known. The stored index may then include its ID, full bindings, and physical paths and gets a separate fenced `index_sha256`; that index hash does not feed back into the snapshot-ID descriptor.
- The complete mutable publication-trigger set is ten canonical paths: `reports/source_digest.json`, `reports/function_location.json`, `reports/function_signature.json`, `reports/test_spec.json`, `reports/harness_skeleton_report.json`, `reports/build_completion_plan.json`, real-run/legacy-import `reports/latest_run.json`, dry-run/legacy-flat `reports/test_execution_report.json`, real evidence `reports/latest_evidence.json`, and legacy-flat `reports/evidence_manifest.json`. Every real mutation seam uses one revision-checked manifest publication repository/writer lock and atomic saved-byte replacement. Lock order is manifest-publication lock before any domain writer lock; no call path may acquire them in reverse.
- Real execution runs remain non-destructive: no flat alias is created. The mutable `latest_run.json` pointer and its contained immutable `runs/<run_id>/test_execution_report.json` target are both exact decision/readiness subjects when strict-valid. Pointer publication validates the immutable target before marking dirty/replacing the pointer. An invalid/present pointer fails the run-dependent axes closed and never falls back: `test_green=false`, evidence that requires a selected run is false with a typed reason, but independently valid review items remain discoverable/finalizable and decision recording/review axes continue. The flat report is a compatibility subject only when the pointer is absent and that legacy/dry-run path is strict-valid.
- Real evidence is likewise pointer-owned: `latest_evidence.json` and its contained immutable `evidence/<id>/evidence_manifest.json` target are validated together. Entries marked `required=true` across the strict manifest's `source_files`, `generated_files`, `build_reports`, `test_reports`, and `logs` arrays are normalized by unique `(collection, file_kind, normalized path)` into required-file facts containing declared path/hash/exists/integrity plus the exact publication-time presence/hash/containment observation; duplicate normalized paths with conflicting declarations are invalid. Optional entries remain covered by the immutable manifest bytes but are not promoted to external required-file facts. The resolver returns a separate fresh current observation for each indexed required fact. `evidence_ready=true` requires every required declaration to say `exists=true`, provide a hash, and say `integrity_status="valid"`; its stable current observation must equal its indexed publication observation exactly, and that shared state must be contained, regular, non-reparse, present, and equal to the declared hash. Declaration failure (`exists!=true`, missing declared hash, or integrity other than `valid`) keeps only the evidence axis false until a new strict evidence-manifest publication is selected (and, for pointer-owned evidence, a pointer selects that new immutable target) and finalization publishes its state. A valid declaration with a stable published/current observation difference also keeps only that axis false, but repairing the component to its declared exact bytes may be re-finalized against the **same** immutable evidence manifest/pointer; the immutable evidence target is never rewritten, and finalization publishes a distinct snapshot/generation only when the logical descriptor differs. An in-attempt observation change retries/conflicts. Present required bytes and negative/invalid facts are included in the same immutable full-state snapshot, so neither later tampering nor later repair can silently reuse a mismatched readiness result. Explicit historical evidence publication remains valid even when pointer `source_run_id` differs from the selected latest run, but Task 6 reports `evidence_ready=false` with `evidence_for_noncurrent_run`; it never combines old evidence with the current run. A present path/hash/schema-invalid evidence pointer fails closed and never falls back. Legacy flat evidence is eligible only when both evidence/run pointers are absent, flat execution is current, and the flat manifest binds that exact execution path/hash; its required-file facts follow the same rule.
- If no manifest exists, those writers still take the publication writer lock so first finalization cannot cross with a write. If a complete or dirty fence exists, a subject writer atomically publishes a fresh `dirty` fence at `generation = current + 1`, preserving the last `previous_complete`, **before** replacing its one canonical JSON subject. It leaves the fence dirty; no raw subject writer can make review current. A writer encountering `publishing` refuses and exposes recovery state.
- The finalizer alone turns a coherent current subject set into a decision snapshot. While holding the same writer lock, it captures a sorted closed presence map for all ten mutation paths (`exists` plus exact SHA-256 when present), resolves execution/evidence selectors and required evidence-component facts, and reads/stages all current decision/readiness subjects. It writes exact immutable copies for every present mutation path, selected dynamic run/evidence target, and present required evidence component under `reports/review_subject_snapshots/<snapshot_id>/...` with exclusive-create/verify-existing semantics; absent/invalid component facts remain explicit index states rather than fabricated files. It then validates the immutable recovery/subject index. A snapshot path is never overwritten or deleted by Task 6. Generation selection is exhaustive: absent/immutable-1.0 authority starts at generation 1; a dirty fence finalizes at `dirty.generation + 1`; a complete fence whose logical full-state descriptor differs finalizes at `complete.generation + 1`; and a complete fence with the same descriptor is a fence no-op—only `update_summary` may rewrite noncanonical summary fields while preserving generation/token/snapshot/fingerprint/canonical fence bytes. It then atomically publishes any changed target fence as `publishing`, revalidates the unchanged positive **and negative** path states/current/immutable bytes and every required evidence-component fact, and atomically publishes the same generation/token/snapshot ID/subject fingerprint as `complete`; it does not rewrite the mutable subjects it captured. Each of those two manifest replaces increments `manifest_revision`: from absent or immutable 1.0, the first 1.1 `publishing` write is revision 1 and the first complete fence is revision 2. Normal finalization refuses an already `publishing` fence and requires explicit recovery.
- The sole authoritative fence path is always `<workspace>/reports/dossier_manifest.json`, and every immutable snapshot path is relative to that same workspace. `finalize-dossier --workspace X --out Y` with detached Y still publishes canonical dossier/manifest authority under X; Y may receive presentation-only exports but never an authoritative manifest, ledger, or duplicate editable JSON. CLI results point to the workspace authority. Resolved-identical X/reports and Y is the only same-path exception.
- A summary-only writer reloads the current manifest while holding the writer lock, refuses a `dirty` or `publishing` generation, and preserves the latest complete fence byte-for-byte. Stale expected revision/fence conflicts rather than rolling generation backward. Parallel subject writers/finalizers serialize, and an old summary writer cannot republish an older fence.
- Decision/readiness summaries are outside the fenced canonical subsection, and neither the manifest nor its summary is a decision subject, so no hash cycle is introduced.
- One read-only stable resolver is used by both record and assessment. It requires no active/recovery publication marker and accepts only a `complete` manifest fence, validates the closed ten-path presence map (including required absence), reads every selected immutable snapshot byte and verifies the fenced kind/role/path/hash/revision/semantic identity, verifies every present mutable path still has its indexed exact bytes and every absent path remains absent, then re-reads the marker and strict-validates the manifest and requires the entire canonical complete fence bytes/generation/token to be unchanged. Because every compliant writer takes the common lock and publishes `dirty` before mutation, and every completed A→B→A cycle consumes newer generation(s), a writer that overlaps or completes during the read is detected. An active/recovery marker or a `dirty`/`publishing` fence is retryable. A registered path whose presence changes between the attempt's initial and final observations, a fence change, or any other bytes/state change within the attempt is a typed conflict/retry, never a hybrid snapshot. With the marker and complete fence unchanged, a registered path whose presence or bytes are stably different from the indexed closed map is the nonretryable `invalid_review_snapshot` state defined below. Stable external-source/evidence-component mismatch is instead a semantic stale/readiness fact so independent axes remain evaluable.
- The C source file is the sole external-path exception and is a read-only currency guard, not a publication-trigger path or an output root. Existing 1.0 artifact contracts remain unchanged: every core envelope and every `ReviewSubjectReference.source_path` keeps the normalized analysis-source-root-relative logical identity required by the 1.0 contract/path policy; it is not relative to the dossier authority output. The analysis workflow builds one `ReviewCoreSourceBinding` from its already validated canonical source root, normalized relative source, function name/ID, and exact digest hash and passes it through a new optional keyword on all three existing writer APIs; existing positional call shapes remain valid. Each core writer validates every corresponding field its in-memory model actually carries before persisting the same `ReviewExternalSourceFact(logical_source_path, canonical_absolute_locator, sha256)` only in the producer-owned `extensions.review_external_source` field and serializing a strict-current 1.0 envelope. Source digest checks logical path/hash; location and signature also check function name/identity, while the full workflow's binding constructor has already cross-validated the analyzed function. A direct writer call without that keyword may derive the binding only from a strict shape/path/function/hash check of an existing `<out>/input/request.json`. An explicitly supplied or present-request binding that is inconsistent with any available model/request field fails before any product write. If both binding and request are absent, the legacy direct-call compatibility path keeps its existing raw 0.1 canonical/sidecar bytes inside the same journal/publication transaction; it is compatible/display-only and can never satisfy the strict-current triple or readiness. Finalization derives authority only by strict cross-validation of three current envelopes: logical subject path/hash/function identity and the separately typed external fact must all agree. It never treats the contract-relative `source_path` as an absolute locator and never accepts a caller- or recovery-supplied locator. The external spelling must be absolute and already equal canonical resolution; the leaf and traversed components must be regular/non-symlink/non-reparse as applicable, so relative locators, alternate aliases, mismatches, and symlink/junction/reparse traversal fail closed even when target bytes happen to match. A legitimate canonical source outside the authority workspace remains a valid declared fact; no operation joins its locator to the workspace, treats it as a rooted committed output, or writes/renames/deletes it. Finalization makes two stable live observations and stores the exact `published_source_observation` with the declared fact and sorted core reasons in the logical descriptor/index. A valid observation includes the exact hash; a stable missing/nonregular/symlink/reparse/unreadable/hash-mismatch state remains an indexed invalid observation rather than fabricated bytes. Decision references retain only contract-valid relative source identity plus exact artifact hashes that already cover the extension. Each resolver attempt makes a fresh two-read `observed_source_observation` before subject collection and immediately before the final manifest/marker reread. If those two observations differ, the attempt conflicts/retries. `source_current=true` requires a non-null fenced fact, exact equality between the stable observed and indexed published observations, `state="valid"`, and an observed hash equal to the declared fact hash. Any stable observation difference—including invalid→valid source recovery—returns both observations with `source_current=false`; `ready_for_review=false`, all affected decisions are stale, `review_complete=false`, and record rejects without writing until finalization publishes a new snapshot ID/generation. Evidence/test axes remain independently evaluable. An edit after a returned current snapshot is therefore observed as stable stale state by the next assessment rather than authorizing the new bytes.
- A missing, legacy-only, or contract/cross-binding-invalid core triple is itself a coherent fail-closed snapshot state, not a finalization crash. The immutable index stores `external_source=null`, `published_source_observation=null`, `function_id=null` when no independent strict identity exists, typed `core_source_reasons`, and exact present/absent mutation facts; no live external-source read is attempted. A valid cross-bound triple yields a non-null fact even when its live observation is stably invalid, so that reason/state is independently fenced. Either fail-closed state may support valid run/evidence/test facts, but emits no generic core fallback or has `source_current=false`, `ready_for_review=false`, `review_complete=false`, and rejects decision recording. Only a non-null fact whose stable current observation exactly equals its indexed valid published observation enables source-current review authority.
- Every public discovery, assessment, or record operation creates exactly one private retry budget with `max_attempts=3` and one strict monotonic `deadline=start+2.0`; neither value is reset or nested. The public discovery wrapper retries a private single-attempt resolver. Assessment owns the outer L1→S→L2 loop and calls that single-attempt resolver directly, never the public retrying wrapper; one failed or successful complete L1→S→L2 sequence consumes one aggregate attempt. Record creates the same one budget after taking the ledger lock and calls the single-attempt resolver directly. Persistent ledger/publication churn, a persistent `publishing` fence, or deadline exhaustion terminates as typed `current_snapshot_conflict` with aggregate attempts/elapsed time; a writer holding the ledger lock never retries forever.
- A stable unavailable or corrupt review publication is never churn. Verified manifest absence and strict 1.0-before-finalization raise nonretryable `ReviewSnapshotStateError(code="review_snapshot_unavailable")`; stable malformed 1.1 manifest/fence/presence map, snapshot-ID/index/path/identity failure, missing/mismatched immutable bytes, or unfenced mutable-byte mismatch raises nonretryable `ReviewSnapshotStateError(code="invalid_review_snapshot")` with the closed reason, normalized subject path when applicable, generation/snapshot identity, and publication recovery state. Stable external-source or required-evidence observation mismatch remains the semantic stale/readiness state defined above, not this structural error. Public discovery/assessment propagate the typed state error on the first attempt. Record converts it losslessly to the matching write status with the known ledger revision and no temp/write/artifact. Only state that changes during an attempt, an active marker, dirty/publishing, or fence churn is retryable `current_snapshot_conflict`.
- The successfully revalidated immutable published snapshot is the decision-validation linearization point. `current` means the latest revision-checked published fence, not an arbitrary in-progress raw file write. A compliant subject writer first exposes an active marker or a newer `dirty` fence, so overlap is retryable and its completed publication requires a newer generation. With no marker or fence movement, a stable mutable presence/byte mismatch is structural `invalid_review_snapshot`, not semantic staleness and not retry churn; finalization must publish a new complete generation before current authority can resume.
- Subject writers share the manifest publication protocol but do not share the ledger lock. If a subject publication starts after the stable fenced snapshot, the decision remains bound to the captured old exact bytes and must assess dirty/publishing/stale against the changed subject; it must never authorize the new bytes. The repository does not claim ledger-lock exclusion over subject writers.
- `os.replace(temporary, review_decisions.json)` is the persistence commit point. Every failure before it is a pre-commit failure and returns nonzero/no-ledger-write/no-artifact. If cleanup itself also fails, the error truthfully reports `recovery_required` and every contained residue path rather than claiming cleanup succeeded.
- A lock-cleanup failure after the commit point raises the distinct typed `ReviewDecisionPersistenceError(code="committed_cleanup_failed")`: nonzero `RunOutcome.ERROR`, `committed=true`, `recovery_required=true`, the new revision, and the one exact `ProducedArtifact` that was actually committed. It must never be reported as no-write.
- Exact contained marker paths are fixed: the ledger uses `<workspace>/reports/.review_decisions.json.lock`, the common subject publisher uses `<workspace>/reports/.dossier_manifest.json.lock`, and TestSpec retains its existing `<workspace>/reports/.test_spec.json.lock` domain marker acquired second. Marker files are recovery metadata, not product artifacts, mutation subjects, or immutable snapshot entries; any undeleted marker is exposed only through the corresponding recovery state/residue model.
- The lock records an owner token. On exit it attempts to record a released state before its descriptor is closed. **Task 6 never automatically deletes or reclaims a lock left by a timed-out cleanup**, even when marked released; path/token rereads are insufficient to prevent a reclaimer from deleting a newly active lock. Read-only discovery reports the contained marker, owner/state, committed revision/hash when present, and `manual_recovery_required=true`. Recovery requires all writers to be stopped and explicit operator verification/removal. Held, malformed, symlink, or reparse-point locks remain blocking. Designing an atomic claim/OS-lock recovery protocol is out of Task 6 scope.
- The manifest-publication lock follows the same conservative marker rule and records marker kind, owner token, publication generation/token, and state. A `dirty` or `publishing` fence retains immutable `previous_complete={generation, transaction_token, snapshot_id, subject_fingerprint, canonical_fence_sha256}` (or `null` for first publication), target snapshot ID/subject fingerprint/index hash when known, nullable external-source fact, published source observation/core reasons, and function identity. A subject writer's pre-finalization `dirty` fence has no target index yet, so all target identity/source/observation/function fields are null and target core reasons are empty; that unknown target state is distinct from an indexed null-source snapshot and cannot use recovery `complete`. Read-only discovery serializes this as `publication_recovery_state`; it never removes the marker or edits the fence.
- Task 6 has no automatic subject-publication recovery. Normal readers/writers always treat both held and released recovery markers as blocking. The explicit offline operator command is the sole exception: it requires `--confirm-all-writers-stopped`, exact marker owner/transaction tokens, the expected generation for a 1.1 manifest, and `complete`, `restore-previous`, `abandon-to-dirty`, `clear-complete-marker`, or `clear-uninitialized-marker`. It re-reads a contained regular non-reparse marker/fence, requires every supplied identity to match, removes only that exact stale marker (held or released), immediately acquires a fresh normal writer lock, and CAS-rechecks the same fence/uninitialized state. Malformed, missing-identity, symlink/reparse, token-mismatched, or concurrently changed state remains blocked.
- COMPLETE/RESTORE authority-changing recovery treats a non-null fenced C-source fact, selected dynamic run/evidence targets, and every declared required-evidence component presence/hash/validity fact as **external fence facts**. It never writes, renames, or deletes them. When the target index has `external_source=null`, those actions instead require that exact null plus its `core_source_reasons` and immutable/current path facts and perform no source-locator read or source-argument check. `complete` is allowed only when the target immutable index/bytes, all ten positive/negative mutation-path states, the conditional source rule, and two stable observations of every other target external fence fact equal the same publishing target; it atomically changes only that same generation/token/fingerprint to `complete`. Marker-only CLEAR-COMPLETE and fail-closed ABANDON deliberately confer no target authority and therefore do not require external facts to remain current.
- `restore-previous` is admitted only from strict 1.1 `dirty` or `publishing` and requires a strict-valid previous immutable snapshot. **Before any product-byte mutation**, it conditionally makes two stable observations of a non-null previous `ReviewExternalSourceFact` and requires the result to equal its indexed `published_source_observation`; a prior valid observation therefore requires the same regular/non-symlink/non-reparse exact hash, while a prior invalid observation requires the same typed invalid state/hash/reason rather than pretending it is valid. A previous null fact instead requires exact null/reasons and no source read. It also verifies every selected dynamic target as contained/regular/non-reparse with exact bytes/internal identity and requires each current required-evidence observation to equal the declared/publication-time state recorded by the previous index. A source fact, when present, comes only from that immutable snapshot and is never accepted as a recovery argument. Any changed external observation/fact rejects recovery without publishing dirty or touching canonical bytes. After that preflight it publishes `dirty` with a fresh token at `generation = abandoned + 1`, atomically restores every previously present canonical path, and guarded-renames every previously absent but currently present canonical path out of its location before contained cleanup. It re-verifies the full presence map, selected subjects, conditional source state, dynamic targets, and required-component facts before `publishing` and again before `complete`. It never rolls generation back or reuses an abandoned generation. A crash during recovery remains dirty/publishing and requires the same explicit procedure again; first publication with no valid previous snapshot stays fail-closed if it cannot complete.
- `abandon-to-dirty` is the explicit fail-closed restart when a strict-valid `dirty` or `publishing` fence can no longer complete/restore because current bytes or external source/evidence facts drifted. After the exact marker/fence CAS under the fresh lock, it does **not** validate or authorize the abandoned target, restore/delete any canonical subject, or modify/delete an immutable target. It atomically writes a new `dirty` fence at `generation = abandoned + 1` with a fresh token and next manifest revision, preserves the optional `previous_complete` identity as historical metadata, and clears all target snapshot/index/fingerprint/source/observation/function fields with empty target core reasons. After marker cleanup, normal finalization may capture the then-current workspace into a still newer complete generation. A second crash remains a normal dirty recovery state. REDs cover first publication, dirty, and publishing crashes followed by source/evidence/current-byte drift and prove this action restores a finalization path without conferring readiness.
- `clear-complete-marker` is allowed when the manifest/fence is strict-valid `complete` and the exact stale marker records that same generation/token/canonical-fence identity. It intentionally does **not** require mutable subjects, immutable subjects, external C source, dynamic targets, or required evidence components still to match: removing a stale cleanup marker asserts only lock ownership/CAS, never currency or readiness. It changes no product artifact/fence byte, acquires/rechecks through a fresh lock, and reports zero produced artifacts. The next ordinary resolver/finalizer performs full byte/external revalidation and reports stale/invalid state or publishes a newer generation. REDs change source, evidence, mutable subjects, and immutable bytes after complete commit but before operator cleanup and prove marker clearing cannot make them current. A failure cleaning the recovery command's own new marker remains truthful recovery-required state.
- `clear-uninitialized-marker` is allowed only when the authoritative manifest is either verified absent or strict-valid immutable 1.0 with the operator-supplied exact SHA-256, and the stale marker's kind/owner/transaction token matches. It leaves an existing 1.0 manifest byte-identical, changes no product artifact, and reports zero produced artifacts; normal first finalization then captures whichever atomic subject commit actually exists and establishes 1.1 generation 1. A 1.1/invalid/changed 1.0 manifest or any generation-bearing mismatch rejects this action.
- Every successful recovery result contains a repository-built `ReviewSubjectRecoveryTransition`: the accepted action and marker identities plus closed `before` and `after` fence identities captured under the same CAS/lock. The CLI never pre-reads or reconstructs these values. Clear actions have byte-identical before/after identities; COMPLETE, RESTORE, and ABANDON report their exact committed transition.

The recovery action/state matrix is closed; action names are accepted by the parser but the repository admits only these authority states:

| Action | Only admitted pre-state | Authority/product effect |
|---|---|---|
| `complete` | strict 1.1 `publishing` with a fully identified target | Same generation/token target becomes `complete` after full internal/external validation |
| `restore-previous` | strict 1.1 `dirty` or `publishing` with a strict-valid `previous_complete` | Newer dirty→publishing→complete generation restores that previous logical snapshot |
| `abandon-to-dirty` | strict 1.1 `dirty` or `publishing` | Newer target-empty `dirty`; no subject/immutable target is restored or authorized |
| `clear-complete-marker` | strict 1.1 `complete` matching the marker identity | Marker-only cleanup; fence/product bytes unchanged |
| `clear-uninitialized-marker` | verified manifest absence or strict-valid immutable 1.0 matching the supplied identity | Marker-only cleanup; absent/1.0 authority unchanged |

Every other action × absent/1.0/dirty/publishing/complete combination, including RESTORE from complete, is rejected before stale-marker removal, fresh-lock creation, product mutation, or artifact projection. Repository table-driven REDs exercise all allowed and forbidden cells; cleanup failure tests begin only after an allowed cell reaches its documented linearization/commit point.

`ReviewSubjectPublicationError.recovery_transition` is null before an action is admitted/linearized. Once an allowed recovery crosses its first action-specific linearization point—accepted marker-only CAS for a clear action, or the first recovery manifest/subject commit for COMPLETE/RESTORE/ABANDON—the repository attaches the same accepted `before` identity and updates `after` to the exact latest committed fence identity on every later failure. Post-commit/cleanup CLI errors serialize that transition directly and never pre-read/reconstruct it.
- Terminal `approved`, `changes_requested`, and `waived` require a nonblank reviewer, nonblank rationale, and timezone-aware canonical timestamp.
- Waiver never authorizes Phase 2 executable generation.

### Subject currency and readiness

- Exact subject identity includes kind, `artifact|current_selector` role, normalized contained relative path, exact saved-byte SHA-256, contract revision where defined, source/function identity, and semantic subject identity.
- Aggregate fingerprints sort only the canonical four-field `(kind, path, SHA-256, nullable revision)` projections before hashing; full identity fields above are validated separately.
- Dossier decisions bind stable input artifacts; they do not bind a finalized `function_dossier.json` whose own decision summary would create a hash cycle.
- Readiness axes are independent:
  - `ready_for_review`
  - `review_complete`
  - `evidence_ready`
  - `test_green`
- Only terminal `RunOutcome.PASSED` is GREEN. Failed, blocked, inconclusive, cancelled, timed-out, and error outcomes may still be reviewable evidence but are never GREEN.
- `ready_for_review=true` requires the same complete snapshot to contain strict-current authoritative `source_digest`, `function_location`, and `function_signature`, one cross-validated non-null external source fact whose stable observed source state exactly equals its indexed published observation and is `valid` with the declared hash, no core blocking reason, and a nonempty valid decisionable-item set. TestSpec may be the generic item's binding but cannot substitute for a missing core artifact. Compatible-migrated/display-only core artifacts do not satisfy this predicate.
- Existence, mtime, or embedded `done` cannot advance any semantic axis.

Required readiness truth table:

| Input state | `ready_for_review` | `review_complete` | `evidence_ready` | `test_green` | Phase 2 generation authority |
|---|---:|---:|---:|---:|---:|
| Valid complete snapshot with the strict-current core triple, exact-equal indexed/current valid external-source observation, and a nonempty exact decisionable-item set; no ledger yet | true | false | derived only from evidence | derived only from valid current run | false |
| Any required review subject missing/invalid/stale | false | false | independent | independent | false |
| Current item missing a decision or resolution `open` | unchanged from subjects | false | independent | independent | false |
| Current exact decision is `changes_requested` | unchanged from subjects | false | independent | independent | false |
| Decision is stale, display-only migrated, or applies only to an orphan | unchanged from current subjects | false for the affected current item | independent | independent | false |
| With the strict-current/core/source/nonempty predicate satisfied, every required current item has an exact current `approved` decision | true | true | independent | independent | allowed only when every separate Phase 2 prerequisite is also true |
| With the strict-current/core/source/nonempty predicate satisfied, every required current item has exact current `approved` or `waived` | true | true | independent | independent | **false when any required item is waived** |
| Valid current evidence package for a failed/blocked/inconclusive/cancelled/timed-out/error run | independent | independent | true | false | false |
| Valid current terminal run is `PASSED`, but required evidence package is absent | independent | independent | false | true | false until the separate evidence prerequisite is met |

An orphan that does not correspond to any current item is reported for audit but does not substitute for, or by itself invalidate, decisions on all current items. Every current item is evaluated independently before the aggregate `review_complete` value is computed.

---

## 4. Mandatory corrections to the recovered carrier

| Gap in recovered carrier | Required current-tree behavior | Regression evidence |
|---|---|---|
| `validator.py` imports `referencing` but `pyproject.toml` does not declare it | Add direct `referencing>=0.28.4,<1`; wheel metadata must declare it; a normal fresh install must resolve dependencies without `--no-deps` | `tests/test_wheel_contract.py` inspects `Requires-Dist` and installs the wheel into a fresh venv normally |
| New ledger uses raw `os.open`, `os.replace`, and unlink paths | Use bounded strict-deadline retry for transient Windows `PermissionError`, preserving non-Windows and non-transient behavior and original traceback | Deterministic lock-create, lock-delete, replace, temp-cleanup, timeout, and concurrent-writer regressions |
| Repository receives pre-resolved `current_items` | Repository re-resolves the immutable published snapshot/items/subjects under the ledger lock | Discovery, subject mutation, then write produces a typed conflict, no ledger/temp residue, and no revision change |
| 1.0 schemas reference mutable `common.schema.json` | Snapshot the definitions required by published 1.0 contracts into immutable `common_v1_0.schema.json`; point the existing TestSpec 1.0 schema and all Task 6 1.0 schemas at it | Mutation/addition in current common definitions cannot change TestSpec or Task 6 1.0 validation/migration results |

### Shared Windows retry design

Create a domain-neutral retry primitive (planned location: `src/unit_test_runner/atomic_io.py`) that accepts the filesystem operation and an injected Windows predicate/clock/sleep policy. Keep the existing TestSpec repository's module-level wrapper seam so its established monkeypatch-based regressions remain valid; delegate through that seam rather than making dossier import TestSpec-private code. The review ledger and review-subject publisher use the same common primitive through their own module-level wrappers. Any refactor must keep every PR #19 focused regression GREEN before ledger or publication work continues.

Each wrapper creates one strict monotonic deadline once per filesystem operation and never resets it between attempts. Only transient Windows `PermissionError` is retried; non-Windows, non-transient, and expired-deadline failures are raised immediately with the original exception and traceback. The publisher wrappers cover publication-marker create/delete, manifest replace, lock-free subject replace, temp cleanup/unlink, and guarded recovery rename/delete. TestSpec subject replacement remains on its existing wrapper inside the outer publication transaction. Deterministic tests inject predicate/clock/sleep and failures at every covered operation, including a permanent cleanup failure after commit, so retry policy cannot silently diverge between the ledger, TestSpec, and the publisher.

Writer-lock acquisition has a separate shared bounded policy aligned with the existing TestSpec contract: one strict 10.0-second monotonic deadline and 0.01-second capped poll interval for `FileExistsError`, with the same deadline also bounding nested transient-Windows-`PermissionError` retries. Publication and ledger lock loops never reset the deadline and never delete/reclaim the observed marker. If the owner removes it in time, the waiter acquires normally; otherwise the code re-reads the contained marker and returns typed no-write `publication_recovery_blocked` or ledger `recovery_blocked` with manual-recovery metadata. Those empty-projection outcomes map to exit 1; malformed/reparse markers remain blocked. Injected clock/sleep tests cover wait→acquire, exact deadline timeout, two waiters, and a released-but-not-deleted marker. TestSpec keeps its public/module-level 10.0-second behavior while delegating the common mechanics.

---

## 5. TDD and review protocol

### What counts as RED

- The test imports only APIs already introduced by the immediately preceding structural step.
- RED must be an assertion failure proving absent/incorrect behavior.
- `ImportError`, collection/setup failure, syntax error, fixture construction failure, or unrelated baseline failure does not count as behavioral RED.
- Capture the exact failing test and the assertion reason in the slice handoff/commit notes.

### Structural new-module sequence

For every new module:

1. Add a structural test using `importlib.util.find_spec(...)` and assert that the public seam exists. This assertion is the structural RED.
2. Add the smallest importable module/API stub; run the structural test GREEN.
3. Add behavior tests against that public API and obtain assertion-level RED.
4. Implement only enough behavior for GREEN.
5. Run focused plus directly related regressions.

Do not write a behavior test that fails only because the future module cannot be imported.

### Per-slice agent sequence

1. Fresh implementer receives only the authoritative slice requirements, file scope, and exact RED/GREEN commands.
2. Implementer writes tests first, records RED, implements minimal GREEN, and reports changed files/tests.
3. Fresh spec reviewer compares the diff to the fixed semantic rules and carrier corrections.
4. Fresh code-quality reviewer checks atomicity, boundary handling, error typing, regression risk, and test strength.
5. The implementer or a dedicated fixer resolves findings; reviewers recheck.
6. Commit only when focused and related tests are GREEN and both fresh reviews report Critical 0 / Important 0 / Minor 0 (`C0/I0/M0`).

Only one writer may modify the worktree at a time. Read-only reconnaissance/review can run in parallel.

Historical review records keep the counts they actually received. They remain evidence for their historical heads only and cannot authorize a future slice or final candidate below `C0/I0/M0`.

---

## 6. Planned file map

### New product files

- `src/unit_test_runner/review_ids.py`
- `src/unit_test_runner/atomic_io.py`
- `src/unit_test_runner/contracts/consumer.py`
- `src/unit_test_runner/dossier/review_decision_models.py`
- `src/unit_test_runner/dossier/review_decision_repository.py`
- `src/unit_test_runner/dossier/review_assessment.py`
- `src/unit_test_runner/review_subject_publisher.py`
- `src/unit_test_runner/schemas/common_v1_0.schema.json`
- `src/unit_test_runner/schemas/review_decisions_v1_0.schema.json`
- `src/unit_test_runner/schemas/function_dossier_v1_0.schema.json`
- `src/unit_test_runner/schemas/dossier_manifest_v1_0.schema.json`

### Existing product files expected to change

- `pyproject.toml`
- `src/unit_test_runner/build_probe.py`
- `src/unit_test_runner/c_analyzer/source_digest.py` to validate the existing input-request source-root binding, emit a strict-current 1.0 envelope plus typed external-source extension, and wrap masked-source/JSON/Markdown output in one outer subject mutation
- `src/unit_test_runner/c_analyzer/function_location_writer.py` to emit the same strict-current logical/external source binding and atomically journal JSON/Markdown/function-slice outputs in one outer subject mutation
- `src/unit_test_runner/c_analyzer/signature_writer.py` to emit the same strict-current logical/external source binding and wrap JSON/Markdown output in one outer subject mutation
- `src/unit_test_runner/cli/parser.py`
- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/cli/main.py` to serialize subject-publication conflicts and pre/post-commit failures before the generic internal-error boundary
- `src/unit_test_runner/contracts/registry.py`
- `src/unit_test_runner/contracts/migrations.py`
- `src/unit_test_runner/contracts/__init__.py` to export one strict-current/explicit-legacy consumer-data normalization seam
- `src/unit_test_runner/contracts/validator.py` only if strict-current/reference handling requires it
- `src/unit_test_runner/dossier/__init__.py`
- `src/unit_test_runner/dossier/artifact_collector.py`
- `src/unit_test_runner/dossier/dossier_models.py`
- `src/unit_test_runner/dossier/dossier_writer.py`
- `src/unit_test_runner/dossier/finalizer.py`
- `src/unit_test_runner/dossier/readiness.py`
- `src/unit_test_runner/dossier/review_workflow.py`
- `src/unit_test_runner/dossier/workflow.py` to construct one stable logical/function/external source binding and pass it to all three core writers through a backward-compatible keyword seam
- `src/unit_test_runner/build/build_workspace_generator.py` to accept strict-current envelope or explicit legacy consumer data at its direct public entry without duplicating unwrapping rules
- `src/unit_test_runner/reanalysis/workflow.py` and `src/unit_test_runner/reanalysis/snapshot_builder.py` to normalize current core envelopes to consumer data while preserving explicit legacy snapshots
- `src/unit_test_runner/harness/__init__.py`, `src/unit_test_runner/harness/harness_skeleton_generator.py`, `src/unit_test_runner/harness/c90_writer.py`, `src/unit_test_runner/harness/dependency_dispatcher.py`, `src/unit_test_runner/harness/runner_output_enhancer.py`, `src/unit_test_runner/harness/state_setup_reflector.py`, `src/unit_test_runner/harness/target_invocation_compat.py`, `src/unit_test_runner/harness/parameter_init_compat.py`, and `src/unit_test_runner/harness/harness_report_writer.py` to accept/derive the shared review binding, open/thread one full harness operation before the first generated C/header write, and publish a strict-current report when bound while preserving raw-0.1 direct-call compatibility when no trusted binding exists
- `src/unit_test_runner/build_completion/completion_report_writer.py` to accept the shared operation/binding, atomically journal plan/iteration/history JSON/Markdown, and publish a strict-current canonical `build_completion_plan` when bound while preserving raw-0.1 direct-call compatibility otherwise
- `src/unit_test_runner/build_completion/build_completion_analyzer.py` to consume strict-current harness/core envelopes through the shared consumer-data seam while retaining explicit legacy input support and threading the caller's operation to its first report write
- `src/unit_test_runner/build_completion/completion_applier.py` to receive that same operation, atomically journal generated stub header/source and Makefile updates, and retain existing positional direct-call compatibility by opening one operation only when no parent is supplied
- `src/unit_test_runner/execution/test_result_writer.py` to accept/derive the shared review binding, open one outer mutation before the first dry-run/legacy-flat report/result/CSV/Markdown/log commit, and publish a strict-current `test_execution_report` when bound while preserving raw-0.1 direct-call compatibility and immutable real-run paths
- `src/unit_test_runner/execution/run_paths.py` and `src/unit_test_runner/execution/evidence_paths.py` to expose exclusive unpublished-root ownership and truthful cleanup/residue boundaries
- `src/unit_test_runner/execution/test_execution.py` to dirty/publish the real-run `latest_run.json` selector only after its immutable run report validates
- `src/unit_test_runner/execution/execution_runner.py` to write immutable stdout/stderr/combined logs through the owning run operation rather than unjournaled in-place writes
- `src/unit_test_runner/execution/report_loader.py` to dirty/publish the legacy-import `latest_run.json` selector only after its immutable imported run validates
- `src/unit_test_runner/execution/evidence_manifest.py` to accept/derive the shared review binding, open one outer mutation before the first legacy-flat manifest/package commit, publish a strict-current evidence manifest when bound, and preserve raw-0.1 direct-call compatibility plus immutable real-evidence targets
- `src/unit_test_runner/test_spec/generation.py`
- `src/unit_test_runner/test_spec/identity.py` to delegate its existing `stable_function_id(...)` API to the one public `build_function_id(...)` algorithm
- `src/unit_test_runner/test_spec/patch.py` and `src/unit_test_runner/test_spec/exporters.py` to reuse the explicit TestSpec operation journal while preserving PR #19 pair-rollback semantics
- `src/unit_test_runner/suite/manager.py` to re-raise subject-publication failures before its generic per-entry error capture
- `src/unit_test_runner/schemas/test_spec_v1_0.schema.json` to bind the published 1.0 contract to immutable common definitions
- `src/unit_test_runner/schemas/common.schema.json`
- `src/unit_test_runner/schemas/review_decisions.schema.json`
- `src/unit_test_runner/schemas/function_dossier.schema.json`
- `src/unit_test_runner/schemas/dossier_manifest.schema.json`
- `src/unit_test_runner/test_spec/repository.py` to delegate its existing retry seam to the common helper and dirty/publish the canonical `test_spec` subject, with PR #19 regressions unchanged

The global published-1.0 freeze also changes these exact existing schemas from mutable `common.schema.json` to immutable `common_v1_0.schema.json` (the three Task 6 current schemas above move to 1.1 and their new `_v1_0` snapshots carry the old reference):

- `src/unit_test_runner/schemas/boundary_candidates.schema.json`
- `src/unit_test_runner/schemas/build_completion_history.schema.json`
- `src/unit_test_runner/schemas/build_completion_iteration.schema.json`
- `src/unit_test_runner/schemas/build_completion_plan.schema.json`
- `src/unit_test_runner/schemas/build_context.schema.json`
- `src/unit_test_runner/schemas/build_probe_report.schema.json`
- `src/unit_test_runner/schemas/build_workspace_report.schema.json`
- `src/unit_test_runner/schemas/call_report.schema.json`
- `src/unit_test_runner/schemas/change_impact.schema.json`
- `src/unit_test_runner/schemas/cli_result.schema.json`
- `src/unit_test_runner/schemas/coverage_design.schema.json`
- `src/unit_test_runner/schemas/dependency_policy.schema.json`
- `src/unit_test_runner/schemas/dsw_discovery.schema.json`
- `src/unit_test_runner/schemas/evidence_manifest.schema.json`
- `src/unit_test_runner/schemas/evidence_source_run.schema.json`
- `src/unit_test_runner/schemas/function_location.schema.json`
- `src/unit_test_runner/schemas/function_signature.schema.json`
- `src/unit_test_runner/schemas/global_access.schema.json`
- `src/unit_test_runner/schemas/harness_skeleton_report.schema.json`
- `src/unit_test_runner/schemas/input_request.schema.json`
- `src/unit_test_runner/schemas/latest_evidence_pointer.schema.json`
- `src/unit_test_runner/schemas/latest_run_pointer.schema.json`
- `src/unit_test_runner/schemas/latest_suite_run_pointer.schema.json`
- `src/unit_test_runner/schemas/project_membership.schema.json`
- `src/unit_test_runner/schemas/prompt_pack.schema.json`
- `src/unit_test_runner/schemas/quick_summary.schema.json`
- `src/unit_test_runner/schemas/reanalysis_snapshot.schema.json`
- `src/unit_test_runner/schemas/regression_selection.schema.json`
- `src/unit_test_runner/schemas/source_digest.schema.json`
- `src/unit_test_runner/schemas/source_membership.schema.json`
- `src/unit_test_runner/schemas/state_setup_reflection.schema.json`
- `src/unit_test_runner/schemas/suite_manifest.schema.json`
- `src/unit_test_runner/schemas/suite_run_report.schema.json`
- `src/unit_test_runner/schemas/test_case_reconciliation.schema.json`
- `src/unit_test_runner/schemas/test_execution_report.schema.json`
- `src/unit_test_runner/schemas/test_result.schema.json`

### Test files expected to change or be added

- `tests/test_build_probe.py`
- `tests/test_contract_registry.py`
- `tests/test_contract_validation.py`
- `tests/test_contract_migrations.py`
- `tests/test_public_artifact_schemas.py`
- `tests/test_wheel_contract.py`
- `tests/test_dossier_review_workflow.py`
- `tests/test_review_decisions.py`
- `tests/test_review_decision_staleness.py`
- `tests/test_dossier_readiness.py`
- `tests/test_dossier_review_authority.py`
- `tests/test_review_decision_integration.py`
- `tests/test_review_decision_cli.py`
- `tests/test_review_subject_publication.py`
- `tests/test_execution_run_history.py`
- `tests/test_prepare_evidence_non_destructive.py`
- `tests/test_execution_evidence.py`
- `tests/test_build_and_execution_module_boundaries.py`
- `tests/test_c_source_reading.py`
- `tests/test_function_analysis_reports.py`
- `tests/test_build_workspace_generation.py`
- `tests/test_build_diagnostics_and_completion.py`
- `tests/test_dependency_policy_explicit_harness.py`
- `tests/test_evidence_integrity.py`
- `tests/test_harness_report_localization.py`
- `tests/test_harness_skeleton_generation.py`
- `tests/test_reanalysis_snapshot_builder.py`
- `tests/test_test_spec_formal_review_provenance.py`
- `tests/test_test_spec_reanalysis.py`
- `tests/test_suite_manager.py`
- `tests/test_suite_cli.py`
- `tests/test_test_spec_contract.py`
- `tests/test_test_spec_generation.py`
- `tests/test_test_spec_repository.py`
- `tests/test_test_spec_formal_review_export_atomicity.py`
- `tests/test_test_spec_formal_review_writer_snapshots.py`

### Durable Task 6 evidence file

- `docs/superpowers/plans/2026-07-15-phase1-task6-review-decisions-readiness.md`
- `docs/superpowers/plans/2026-07-15-phase1-task6-gate-evidence.md`

This evidence file records only facts known at each reviewed boundary. Post-merge progress changes belong to the later closeout documentation branch, not the product branch.

### Public domain seams fixed for fresh implementers

The recovered carrier is observational input only. The preflight narrows one older master-plan interface because caller-supplied subject lists would violate the binding authority rule:

| Older master interface | Task 6 resolution |
|---|---|
| `record_review_decision(path, decision, *, expected_revision)` where `decision` already contains subjects | **Signature superseded only:** do not export this unsafe shape. Export the safe keyword-only wrapper below; it accepts decision metadata and discovery guards but never subject references. |
| `assess_review_completion(review_items, decisions, current_artifacts)` | **Signature superseded only:** preserve `assess_review_completion` as the canonical public name, but replace all caller-supplied current subjects/artifacts with the workspace-owned resolver below. Export `assess_review_decisions` only as a documented compatibility alias to the same implementation. |

No other semantic requirement in the master plan is superseded. Public exports are the names and types explicitly listed in this section; carrier-only helpers are private.

The domain-neutral publication seam is importable without importing `unit_test_runner.dossier`. DOSSIER_MANIFEST 1.1 has a monotonic `manifest_revision` incremented on every atomic manifest mutation, independently of subject generation. The repository owns the exact ten-path mutation registry, writer marker, revision CAS, dirty/publication transitions, and truthful recovery errors:

```python
class ReviewSubjectMutation(StrEnum):
    SOURCE_DIGEST = "source_digest"
    FUNCTION_LOCATION = "function_location"
    FUNCTION_SIGNATURE = "function_signature"
    TEST_SPEC = "test_spec"
    HARNESS_SKELETON_REPORT = "harness_skeleton_report"
    BUILD_COMPLETION_PLAN = "build_completion_plan"
    EXECUTION_CURRENT_POINTER = "execution_current_pointer"
    LEGACY_EXECUTION_REPORT = "legacy_execution_report"
    EVIDENCE_CURRENT_POINTER = "evidence_current_pointer"
    LEGACY_EVIDENCE_MANIFEST = "legacy_evidence_manifest"

@dataclass(frozen=True)
class ReviewExternalSourceFact:
    logical_source_path: str  # normalized relative contract identity
    canonical_absolute_locator: str  # read-only external locator
    sha256: str

@dataclass(frozen=True)
class ReviewExternalSourceObservation:
    state: Literal[
        "valid", "missing", "not_regular", "symlink", "reparse",
        "unreadable", "hash_mismatch",
    ]
    observed_sha256: str | None
    reason: str | None

@dataclass(frozen=True)
class ReviewCoreSourceBinding:
    function_id: str
    function_name: str
    external_source: ReviewExternalSourceFact

@dataclass(frozen=True)
class ReviewMutationPathState:
    mutation: ReviewSubjectMutation
    path: str
    exists: bool
    sha256: str | None

@dataclass(frozen=True)
class ReviewRequiredFileFact:
    collection: Literal[
        "source_files", "generated_files", "build_reports", "test_reports", "logs",
    ]
    file_kind: str
    path: str
    required: Literal[True]
    declared_sha256: str | None
    declared_exists: bool
    declared_integrity_status: str | None
    published_state: Literal["valid", "missing", "invalid", "uncontained"]
    published_sha256: str | None
    published_reason: str | None
    immutable_slot: str

@dataclass(frozen=True)
class ReviewRequiredFileObservation:
    collection: Literal[
        "source_files", "generated_files", "build_reports", "test_reports", "logs",
    ]
    file_kind: str
    path: str
    observed_state: Literal["valid", "missing", "invalid", "uncontained"]
    observed_sha256: str | None
    reason: str | None

@dataclass(frozen=True)
class ReviewSubjectPublicationRecoveryState:
    required: bool
    marker_path: str | None
    marker_kind: str | None
    marker_owner_token: str | None
    marker_state: str | None
    marker_generation: int | None
    marker_transaction_token: str | None
    publication_state: Literal["dirty", "publishing", "complete"] | None
    manifest_revision: int | None
    legacy_manifest_sha256: str | None
    generation: int | None
    transaction_token: str | None
    canonical_fence_sha256: str | None
    target_fingerprint: str | None
    target_snapshot_id: str | None
    target_index_sha256: str | None
    external_source: ReviewExternalSourceFact | None
    published_source_observation: ReviewExternalSourceObservation | None
    core_source_reasons: tuple[str, ...]
    function_id: str | None
    previous_complete_generation: int | None
    previous_complete_transaction_token: str | None
    previous_complete_fingerprint: str | None
    previous_complete_snapshot_id: str | None
    previous_complete_canonical_fence_sha256: str | None
    current_path_states: tuple[ReviewMutationPathState, ...]
    previous_complete_path_states: tuple[ReviewMutationPathState, ...]
    residue_paths: tuple["ReviewSubjectResiduePath", ...]
    manual_recovery_required: bool

@dataclass(frozen=True)
class ReviewSubjectPublicationEntry:
    artifact_kind: str
    subject_role: Literal["artifact", "current_selector"]
    current_relative_path: str
    expected_sha256: str
    revision: int | None
    source_path: str | None  # normalized relative contract identity
    source_sha256: str | None
    function_id: str | None
    semantic_subject_key: str | None
    immutable_slot: str

@dataclass(frozen=True)
class ReviewSelectorBinding:
    execution_state: Literal["pointer", "legacy_flat", "absent", "invalid"]
    selected_run_id: str | None
    run_outcome: RunOutcome | None
    execution_references: tuple["ReviewSubjectReference", ...]
    execution_reasons: tuple[str, ...]
    evidence_state: Literal["pointer", "legacy_flat", "absent", "invalid"]
    selected_evidence_id: str | None
    evidence_source_run_id: str | None
    evidence_references: tuple["ReviewSubjectReference", ...]
    evidence_reasons: tuple[str, ...]

@dataclass(frozen=True)
class ReviewItemPublicationBinding:
    review_id: str
    category: str
    function_id: str
    case_id: str | None
    semantic_subject_key: str
    subject_references: tuple[ReviewSubjectReference, ...]

@dataclass(frozen=True)
class ReviewSubjectSnapshotCandidate:
    descriptor_version: Literal["1.0.0"]
    function_id: str | None
    external_source: ReviewExternalSourceFact | None
    published_source_observation: ReviewExternalSourceObservation | None
    core_source_reasons: tuple[str, ...]
    mutation_path_states: tuple[ReviewMutationPathState, ...]
    selector_binding: ReviewSelectorBinding
    publication_entries: tuple[ReviewSubjectPublicationEntry, ...]
    required_evidence_files: tuple[ReviewRequiredFileFact, ...]
    review_item_bindings: tuple[ReviewItemPublicationBinding, ...]

def build_review_snapshot_id(candidate: ReviewSubjectSnapshotCandidate) -> str: ...

@dataclass(frozen=True)
class ReviewSubjectOutputRoot:
    role: Literal["authority_workspace", "presentation_output"]
    path: str  # normalized absolute root

@dataclass(frozen=True)
class ReviewSubjectCommittedFile:
    root: ReviewSubjectOutputRoot
    artifact_kind: str
    path: str  # normalized path relative to root
    sha256: str
    schema_version: str | None

@dataclass(frozen=True)
class ReviewSubjectDeletedPath:
    root: ReviewSubjectOutputRoot
    path: str

@dataclass(frozen=True)
class ReviewSubjectSupersededPath:
    root: ReviewSubjectOutputRoot
    path: str
    last_committed_sha256: str | None
    observed_state: Literal[
        "missing", "file", "directory", "symlink", "reparse", "other", "unreadable"
    ]
    observed_sha256: str | None
    reason: str | None

@dataclass(frozen=True)
class ReviewSubjectResiduePath:
    root: ReviewSubjectOutputRoot
    path: str  # normalized path relative to root
    observed_state: Literal[
        "file", "directory", "symlink", "reparse", "other", "unreadable"
    ]
    observed_sha256: str | None
    reason: str

@dataclass(frozen=True)
class ReviewSubjectFenceIdentity:
    manifest_revision: int | None
    legacy_manifest_sha256: str | None
    publication_state: Literal["dirty", "publishing", "complete"] | None
    generation: int | None
    transaction_token: str | None
    subject_fingerprint: str | None
    snapshot_id: str | None
    canonical_fence_sha256: str | None

@dataclass(frozen=True)
class ReviewSubjectRecoveryTransition:
    action: Literal[
        "complete", "restore-previous", "abandon-to-dirty",
        "clear-complete-marker", "clear-uninitialized-marker",
    ]
    accepted_marker_owner_token: str
    accepted_marker_transaction_token: str
    before: ReviewSubjectFenceIdentity
    after: ReviewSubjectFenceIdentity

@dataclass(frozen=True)
class ReviewSubjectPublicationResult:
    authority_workspace_root: str
    manifest_revision: int | None
    legacy_manifest_sha256: str | None
    generation: int | None
    publication_state: Literal["dirty", "publishing", "complete"] | None
    transaction_token: str | None
    subject_fingerprint: str | None
    snapshot_id: str | None
    committed_files: tuple[ReviewSubjectCommittedFile, ...]
    deleted_paths: tuple[ReviewSubjectDeletedPath, ...]
    superseded_paths: tuple[ReviewSubjectSupersededPath, ...]
    residue_paths: tuple[ReviewSubjectResiduePath, ...]
    recovery_state: ReviewSubjectPublicationRecoveryState
    recovery_transition: ReviewSubjectRecoveryTransition | None

class ReviewSubjectPublicationError(RuntimeError):
    authority_workspace_root: str
    code: Literal[
        "publication_conflict",
        "publication_precommit_failed",
        "publication_committed_failed",
        "publication_recovery_blocked",
    ]
    committed_files: tuple[ReviewSubjectCommittedFile, ...]
    deleted_paths: tuple[ReviewSubjectDeletedPath, ...]
    superseded_paths: tuple[ReviewSubjectSupersededPath, ...]
    residue_paths: tuple[ReviewSubjectResiduePath, ...]
    recovery_state: ReviewSubjectPublicationRecoveryState
    recovery_transition: ReviewSubjectRecoveryTransition | None
    primary_error: BaseException
    cleanup_errors: tuple[BaseException, ...]

class ReviewSubjectMutationTransaction:
    def prepare_commit(self, final_bytes: bytes) -> None: ...
    def record_subject_commit(self, committed: ReviewSubjectCommittedFile) -> None: ...

class ReviewSubjectOperation:
    def replace_product_file(
        self, *, root: ReviewSubjectOutputRoot,
        artifact_kind: str, relative_path: str,
        final_bytes: bytes, schema_version: str | None,
    ) -> ReviewSubjectCommittedFile: ...
    def install_immutable_file(
        self, *, root: ReviewSubjectOutputRoot,
        artifact_kind: str, relative_path: str,
        final_bytes: bytes, schema_version: str | None,
    ) -> ReviewSubjectCommittedFile: ...
    def delete_product_path(
        self, *, root: ReviewSubjectOutputRoot,
        relative_path: str, expected_sha256: str | None,
    ) -> None: ...
    def record_external_commit(
        self, committed: ReviewSubjectCommittedFile,
    ) -> None: ...
    @property
    def committed_files(self) -> tuple[ReviewSubjectCommittedFile, ...]: ...
    @property
    def deleted_paths(self) -> tuple[ReviewSubjectDeletedPath, ...]: ...
    @property
    def superseded_paths(self) -> tuple[ReviewSubjectSupersededPath, ...]: ...
    @property
    def residue_paths(self) -> tuple[ReviewSubjectResiduePath, ...]: ...

class ReviewSubjectPublicationRepository:
    def operation(
        self, *, additional_output_roots: tuple[ReviewSubjectOutputRoot, ...] = (),
    ) -> ContextManager[ReviewSubjectOperation]: ...

    def subject_mutation(
        self, *, operation: ReviewSubjectOperation,
        mutation: ReviewSubjectMutation,
        relative_path: str,
        preflight: Callable[[], None] | None = None,
    ) -> ContextManager[ReviewSubjectMutationTransaction]: ...

    def replace_subject(
        self, *, operation: ReviewSubjectOperation,
        mutation: ReviewSubjectMutation,
        relative_path: str, final_bytes: bytes,
    ) -> ReviewSubjectPublicationResult: ...  # convenience for lock-free domain writers

    def finalize_snapshot(
        self, *, operation: ReviewSubjectOperation,
        candidate_factory: Callable[[], ReviewSubjectSnapshotCandidate],
    ) -> ReviewSubjectPublicationResult: ...

    def update_summary(
        self, *, operation: ReviewSubjectOperation,
        expected_manifest_revision: int,
        summary_payload: dict[str, object],
    ) -> ReviewSubjectPublicationResult: ...

    def recover(
        self, *, operation: ReviewSubjectOperation,
        expected_generation: int | None,
        expected_uninitialized_manifest_sha256: str | None,
        expected_marker_owner_token: str,
        expected_transaction_token: str,
        action: Literal[
            "complete", "restore-previous", "abandon-to-dirty",
            "clear-complete-marker", "clear-uninitialized-marker",
        ],
        confirm_all_writers_stopped: bool,
    ) -> ReviewSubjectPublicationResult: ...
```

Each committed/deleted fact carries an explicit normalized root identity/role plus a contained relative path. The repository fixes `authority_workspace_root`; detached dossier exports register their resolved `presentation_output` root before the operation begins. This also lets a suite-entry error name the entry workspace rather than the suite manifest's directory. Every registered producer, finalizer, and recovery invocation opens one explicit operation context before its first product write. The journal snapshots the exact baseline state on first touch and appends ordered commit/delete events; repeated commits to the same rooted path are expected for dirty→publishing→complete and restore flows. At projection time, a path still equal to the operation's last event is compared with baseline and emitted only as its last net-changed file or final deletion. If a later concurrent writer has replaced that state, it is emitted only as `superseded_paths` with last-owned and observed identities—never as this operation's artifact. Restoring the original hash/presence is net-zero, not an artifact; a rooted path may never appear in both final `committed_files` and `deleted_paths`.

All journal-managed overwrites serialize final bytes first, write/close a same-directory temporary, and use the shared retry wrapper around atomic replace as the sole product commit point. New immutable run/evidence roots are exclusively owned while unpublished; files are recorded only after close/hash verification, and pointer-conflict cleanup that restores verified absence projects to net-zero. Immutable snapshot installs use exclusive-create/verify-existing publication and never overwrite. Mid-temp-write failures report contained temp residue/cleanup without pretending the destination committed. Direct in-place truncate/write of a journal-managed existing product file is forbidden.

The operation context itself is journal-only. Every registered producer with more than one related output uses an explicit outer `subject_mutation(...)`: source digest (masked source/JSON/Markdown), function location (JSON/Markdown/slice), function signature (JSON/Markdown), TestSpec (canonical/views), full harness generation, build completion (plan/iteration/history JSON/Markdown), dry-run/legacy-flat execution (canonical/result JSON/CSV/Markdown/review/log outputs), and legacy-flat evidence (canonical/package). Each enters before its first related mutable sidecar commit. The repository acquires the publication lock, runs the optional no-write `preflight` under that lock, and only then publishes the newer dirty fence when 1.1 authority exists; a failed source-binding/pointer/CAS preflight therefore leaves product bytes and the complete fence unchanged. The transaction keeps the lock through every sidecar and canonical subject commit. Rendering that depends on the accepted preflight result occurs under the lock; other no-write validation may occur earlier. Immutable real-run/import/evidence target preparation may precede its single pointer mutation only because the target is still unreferenced; conflict cleanup must return it to the baseline or report a committed/residue outcome. `replace_subject(...)` is limited to a genuinely single-output registered mutation (including a validated pointer after target preparation) and is forbidden for every listed multi-output producer.

Every mutating repository API receives the operation explicitly; there is no ambient/context-variable journal. A caller spanning `finalize_snapshot`→assessment/sidecars→`update_summary` reuses the same explicit object, while a separate recovery invocation creates a fresh one. Nested producer helpers receive that object rather than silently opening a second journal.

Build completion fixes its real write boundary explicitly. `handle_complete_build` and the full dossier workflow each open one operation before `analyze_build_errors_from_workspace(...)` performs its first report commit, then pass that same keyword-only parent through analyzer → `apply_safe_completions(...)` → every `write_completion_reports(...)` call. A legacy direct analyzer/applier/reporter call opens exactly one operation only when no parent was supplied, preserving existing positional parameters. Stub header, stub source, and an existing Makefile are serialized before commit and written only through the operation's same-directory temp plus atomic replace; no shared-operation path may call unjournaled `write_c_file` or `Path.write_text`. Thus the initial reports, optional generated bytes/Makefile, and rewritten final reports form one truthful invocation projection.

Every operation write/delete/install call also names one root object that was registered when the operation opened. The operation rejects an unknown, role-mismatched, symlink/reparse, overlapping, or containment-ambiguous root before touching bytes. Detached presentation writes therefore cannot accidentally resolve against the authority workspace, and recovery cannot target a presentation root.

On failure, the operation recomputes its final projection. A nested `publication_committed_failed` is enriched with that projection. A conflict/precommit error keeps its original exit-1/exit-3 mapping only when committed files, deletions, superseded paths, and residue are all empty. Any attributable projection fact promotes it to `publication_committed_failed`/exit 3 with the original error as `primary_error`, every final exact artifact/deletion/superseded identity, cleanup/residue facts, and current recovery state. A later domain/sidecar/cleanup failure follows the same empty-vs-committed rule. This journal scope is one producer/finalizer/recovery invocation, not all earlier successful suboperations in a composite workflow; prior completed suite/workflow entries retain their own durable results. No operation may rely on reaching its normal success return to construct artifact truth.

Verified absence has manifest revision 0; a subject mutation before first finalization returns revision 0 with generation/state/token/snapshot fields `None`. A strict-valid immutable 1.0 manifest has no 1.1 revision and returns `manifest_revision=None` plus its exact legacy hash, without mutating the manifest. The first atomic 1.1 manifest write commits revision 1; every later atomic manifest replace increments it by exactly one, so first finalization's required publishing→complete pair ends at revision 2. Every valid current 1.1 manifest has revision `>=1`; invalid/unreadable state errors and never fabricates 0. Constructors and injected filesystem/clock/retry operations remain private test seams. `subject_mutation(...)` rejects a mutation/path pair outside the exact registry, acquires the publication lock, executes its no-write preflight, and publishes dirty only after that succeeds. Every outer writer records each sidecar commit in the parent operation and calls `prepare_commit(final_bytes)` immediately before the canonical replace plus `record_subject_commit(exact_file)` at that replace's commit point. A writer with an independent domain lock acquires it only after the publication lock, performs revision/current-byte validation and final serialization, and records the canonical commit before domain-lock cleanup. TestSpec must retain exactly this domain-lock path and its existing replace wrapper. Failure before dirty (including preflight) is no-write; failure after dirty reports that manifest even if `prepare_commit` was never reached. `replace_subject(...)` is only the single-output convenience adapter defined above and may never be used merely because a multi-output writer delegates its sidecars to helpers.

The transaction preserves the primary traceback and composes both domain and publication cleanup errors. Only failure before `subject_mutation(...)` entry/dirty commit is no-write. Failure after entry but before `prepare_commit` truthfully projects the dirty manifest plus any committed sidecars; failure after subject replace includes the final dirty manifest and exact subject/sidecar facts even if domain/publication lock cleanup then fails. It never reports a committed file as uncommitted. TestSpec's existing module-level Windows predicate/clock/sleep/replace wrappers remain the actual canonical commit operations so PR #19 monkeypatch and strict-deadline tests continue to observe them.

The execution/evidence pointer mutations validate each pointer's own contained immutable target and internal identity/hash binding before any dirty commit and never create flat aliases. They do **not** require `latest_evidence.source_run_id` to equal the separately selected latest-run ID: historical evidence publication is valid, and only assessment reports `evidence_ready=false` with `evidence_for_noncurrent_run` while leaving the other semantic axes independently evaluable. `finalize_snapshot(...)` is called only by dossier finalization: it acquires the publication lock first, then invokes `candidate_factory` so all ten path states, live source, stable IDs, and item bindings are built under that lock; it independently rereads/verifies every returned entry. For each binding it requires a fully normalized semantic tuple, recomputes and matches `review_id`, and rejects an empty subject tuple or a reference outside the selected exact entry set. Sorted full bindings are inputs to the logical snapshot ID and are serialized into the immutable index. A zero-item binding collection is valid for a coherent no-eligible-subject snapshot, but assessment must return both `ready_for_review=false` and `review_complete=false` rather than applying vacuous `all(...)`. Passing a candidate built before lock acquisition is forbidden. `update_summary(...)` may not alter canonical fence bytes. All domain locks, when needed, are acquired after the publication lock; no adapter may enter publication from inside a held domain lock. `ReviewSubjectPublicationError` intentionally is not an `OSError` or `CLIError`: it wraps the primary filesystem/domain error while avoiding legacy OSError-to-CLIError adapters. The module's only cross-domain model import is the leaf `review_ids`; it has no import of `dossier`, TestSpec, harness, build-completion, execution, or CLI packages.

`ReviewSubjectPublicationRecoveryState` serializes the target fence's `external_source`, `published_source_observation`, and `core_source_reasons` exactly as typed above. When `target_snapshot_id`/`target_index_sha256` identify a strict target index, semantic validation requires a non-null source to have a non-null complete observation, or a null source to have a null observation and nonempty reasons. An unfinalized `dirty` fence instead requires all target identity/source/observation/function fields null and target reasons empty; it cannot use `complete`, and may use `restore-previous` only when its separately verified previous snapshot exists, otherwise it stays fail-closed. Previous-complete source state is not ambiguously duplicated in the public recovery object: recovery follows `previous_complete_snapshot_id`, strict-loads its immutable index, and obtains the previous nullable fact/observation/reasons from that index. CLI/schema round-trip REDs cover a non-null stable-invalid target, an indexed null-source target, and an unfinalized dirty target without dropping or conflating these fields.

Every source/evidence observation `reason` stored in a descriptor, index, or public model is a deterministic machine code derived from the closed state/path-policy result; locale-dependent exception text is diagnostic-only and never participates in equality or snapshot hashing. Observation tuples are sorted by their canonical identity keys before comparison and serialization.

Stable-ID exports:

```python
@dataclass(frozen=True)
class ReviewSemanticKey:
    category: str
    function_id: str
    case_id: str | None
    semantic_subject_key: str

@dataclass(frozen=True)
class ReviewSubjectReference:
    artifact_kind: str
    subject_role: Literal["artifact", "current_selector"]
    path: str
    sha256: str
    revision: int | None
    source_path: str | None  # normalized relative contract identity
    source_sha256: str | None
    function_id: str | None
    semantic_subject_key: str | None

def build_review_id(
    category: str,
    function_id: str,
    case_id: str | None,
    semantic_subject_key: str,
) -> str: ...

def build_function_id(
    logical_source_path: str,
    function_name: str,
) -> str: ...

def subject_fingerprint(
    references: Iterable[ReviewSubjectReference],
) -> str: ...

class StableReviewIdRegistry:
    def register(
        self, *, category: str, function_id: str,
        case_id: str | None, semantic_subject_key: str,
    ) -> str: ...
```

`review_ids.py` owns `ReviewExternalSourceFact`, `ReviewExternalSourceObservation`, `ReviewCoreSourceBinding`, `ReviewSemanticKey`, `ReviewSubjectReference`, and the one deterministic `build_function_id(...)` seam so all three core producers, the top-level publisher, TestSpec, and dossier code share identity without entering the eager `dossier` package. Binding construction/validation requires `function_id == build_function_id(external_source.logical_source_path, function_name)`, a normalized nonempty relative logical path, canonical absolute locator, and lowercase exact SHA-256 before any producer can serialize it. `dossier/workflow.py` constructs the explicit binding once and passes it through the optional keyword seam; direct writers use the same builder only after validating `input/request.json`. The latest-run pointer is a `test_execution_report` reference with `subject_role="current_selector"`; its immutable target uses `subject_role="artifact"`. Both participate in the aggregate fingerprint without inventing a new public artifact kind. `ReviewIdCollisionError` carries the collided ID plus existing/candidate normalized semantic keys. `ReviewResolution` is closed to `open`, `approved`, `changes_requested`, and `waived`.

### Canonical identity byte contracts

These algorithms are persisted public identity, not implementation suggestions. All JSON hashing uses `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")`: strict UTF-8, no BOM, no trailing newline. Hash text is full lowercase SHA-256 hex unless a shorter length is explicitly fixed below. Values must be exact JSON/Python scalar types; booleans are never accepted as integers, floats/NaN/Infinity are forbidden, optional object keys are present with JSON `null`, and extra keys are rejected.

`build_function_id(...)` preserves the existing Task 5 `test_spec.identity.stable_function_id(...)` bytes for every valid input, and that existing API delegates to the public builder. It performs no NFKC or case folding on the path or C function identity. The logical path replaces `\\` with `/`, applies `PurePosixPath(...).as_posix()` so redundant separators and `.` are collapsed, and rejects empty, absolute, drive-prefixed, `..`-containing, NUL-containing, or non-string input. The function name is exact string input with outer whitespace stripped; empty, NUL-containing, or non-UTF-8-encodable input is rejected. Digest input is `normalized_path.encode("utf-8") + b"\x00" + stripped_name.encode("utf-8")`; the suffix is the first 12 characters of its lowercase SHA-256 hex. The slug is `re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "function"`, and the result is `fn_{slug}_{suffix}`. Literal vectors are:

```text
build_function_id("src\\制御.c", "Control_Update") == "fn_control_update_84fcdd81a442"
build_function_id("src/./制御.c", "Control_Update") == "fn_control_update_84fcdd81a442"
build_function_id("src/control.c", "Control_Update") == "fn_control_update_cdd351ecf31d"
build_function_id("src/control.c", "control_update") == "fn_control_update_b0fd58394269"
build_function_id("src/control.c", "制御") == "fn_function_bbf8b675d675"
```

`build_review_id(...)` accepts exact string `category`, `function_id`, and `semantic_subject_key`, plus exact string-or-`None` `case_id`; it never applies implicit `str(...)`. Each present component is `unicodedata.normalize("NFKC", value).strip()`, then every maximal Unicode-regex match of `r"[\s_:/\\|.\-]+"` is replaced by `/`, and outer `/` is stripped. An empty required component, an empty supplied case component, NUL, or strict-UTF-8 failure is rejected. Only `case_id is None` becomes the empty third digest component. The four normalized components `(category, function_id, case-or-empty, semantic_subject_key)` are joined by one NUL and UTF-8 encoded; the digest is the first 16 characters of lowercase SHA-256 hex. The category slug is `re.sub(r"[^A-Za-z0-9]+", "-", normalized_category).strip("-").lower() or "review"`; the output is `review-{slug}-{digest}`. Case remains significant in digest input. Literal vectors are:

```text
build_review_id(" expected＿result ", "Control_Update", "TC-01", " return／value ")
  == "review-expected-result-93cdf75d71c9e7d5"
build_review_id("expected-result", "control_update", "TC-01", "return/value")
  == "review-expected-result-08d00d45f722bfbe"
build_review_id(" 検査 ", "fn_制御_abcdef", " TC－01 ", " 境界 値 ")
  == "review-review-cce6c22d9cd872b6"
```

`subject_fingerprint(...)` accepts only the deduplicated selected decision-subject projection. Each exact object has only `artifact_kind`, normalized contained workspace-relative POSIX `path`, exact lowercase 64-hex `sha256`, and `revision` (`null` or a nonnegative non-bool integer). It excludes role, source/function/semantic fields, immutable slot/path, and every physical snapshot prefix; those fields are validated separately as full currency identity. Duplicate four-field objects and conflicting objects sharing `(artifact_kind, path)` are errors rather than implicit deduplication. The aggregate owner passes a shared reference only once even if several items use it. Objects sort by `(artifact_kind, path, sha256, revision)` with null revision before every integer, then use the common canonical JSON bytes and full SHA-256. Empty aggregate has the literal hash `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`, although a decisionable item itself may not be empty. This reversed-or-forward input vector always hashes to `9b84f9221eede6bcb697d2de5ef39bbfad9c2ded8fcf71d5433c199690832828`:

```json
[
  {"artifact_kind":"function_signature","path":"reports/関数.json","revision":null,"sha256":"0000000000000000000000000000000000000000000000000000000000000000"},
  {"artifact_kind":"test_spec","path":"reports/test_spec.json","revision":2,"sha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}
]
```

Changing the first revision from `null` to `0` produces `e2e93761ac4e12962d346f82e2e9271d1ddaa20980fa8b95517beb1719ded071`; changing only excluded role/source/function/semantic fields does not change the fingerprint.

`snapshot_id` is the full lowercase SHA-256 of one closed descriptor with exactly these ten top-level keys: `descriptor_version`, `function_id`, `external_source`, `published_source_observation`, `core_source_reasons`, `mutation_path_states`, `selector_binding`, `publication_entries`, `required_evidence_files`, and `review_item_bindings`. `descriptor_version` is literal `1.0.0`. Nested objects use the exact dataclass field names shown in this plan: external source has three fields, source observation three, mutation state four, selector binding ten, publication entry all ten including `immutable_slot`, required-file fact all eleven including `immutable_slot`, item binding all six, and each nested full subject reference all nine. Enum values serialize as their exact string `.value` (including nullable `run_outcome`), and null keys remain present.

The ten mutation entries are exactly these registry pairs, each present once, sorted by `(mutation, path)`: `source_digest→reports/source_digest.json`, `function_location→reports/function_location.json`, `function_signature→reports/function_signature.json`, `test_spec→reports/test_spec.json`, `harness_skeleton_report→reports/harness_skeleton_report.json`, `build_completion_plan→reports/build_completion_plan.json`, `execution_current_pointer→reports/latest_run.json`, `legacy_execution_report→reports/test_execution_report.json`, `evidence_current_pointer→reports/latest_evidence.json`, and `legacy_evidence_manifest→reports/evidence_manifest.json`. `exists=false` requires `sha256=null`; `exists=true` requires exact lowercase 64 hex. Publication-entry slots are exactly `subjects/{current_relative_path}`. Required-file slots are exactly `required_evidence/{collection}/{path}`. Every slot is a normalized snapshot-root-relative POSIX path, unique, and excludes `reports/review_subject_snapshots/<snapshot_id>/`.

Machine reason arrays are unique Unicode-code-point sorted codes and never contain localized prose, OS error text, or absolute paths. Selector and nested subject-reference arrays use the same full-reference ordering: `(artifact_kind, path, sha256, null-first revision, subject_role, null-first source_path, null-first source_sha256, null-first function_id, null-first semantic_subject_key)`. Publication entries sort by `(immutable_slot, artifact_kind, subject_role, current_relative_path, expected_sha256, null-first revision, null-first source_path, null-first source_sha256, null-first function_id, null-first semantic_subject_key)`; required facts by `(collection, file_kind, path)`; item bindings by `(review_id, category, function_id, null-first case_id, semantic_subject_key)` and their references by the full-reference order. Duplicate identity/slot, conflicting duplicate, missing registry entry, a selector/binding reference without its corresponding publication entry, or an implicit deduplication opportunity is rejected before hashing.

The descriptor excludes `snapshot_id`, the separately recomputed `subject_fingerprint`, generation, transaction token, manifest bytes/revision, physical snapshot prefix, stored index, and index hash. The following fail-closed minimal vector fixes the literal empty-state bytes: null function/source/observation; `core_source_reasons=["core_artifacts_absent"]`; all ten path pairs absent/null; empty publication/required/binding arrays; and this selector object:

```json
{"execution_state":"absent","selected_run_id":null,"run_outcome":null,"execution_references":[],"execution_reasons":["execution_absent"],"evidence_state":"absent","selected_evidence_id":null,"evidence_source_run_id":null,"evidence_references":[],"evidence_reasons":["evidence_absent"]}
```

Its canonical UTF-8 length is exactly 1607 bytes and `snapshot_id == 79939f7c49753ba0a1bd0585f2251d977f4e1a8506f4c47662bf43cf58dd6b8e`.

The Unicode/full golden uses `function_id="fn_control_update_84fcdd81a442"`; external source `(logical_source_path="src/制御.c", canonical_absolute_locator="C:\\work\\src\\制御.c", sha256="11"*32)`; a valid equal observation; only source-digest mutation present at hash `"22"*32`; one publication entry at `subjects/reports/source_digest.json`; and one full source-digest reference bound by `(review_id="review-core-7f407640673332b1", category="core", case_id=null, semantic_subject_key="source/digest")`; selector is the same absent object and required evidence is empty. Its canonical UTF-8 length is 2988 and `snapshot_id == 4bc2e6cb8bd4872d343a8c1bffffb94eda6f892c3ce8c089f226a59aa5bc1255`. Golden tests also permute every array, change null to zero, change descriptor version and each top-level field independently, reject duplicate identity/slot, and prove physical prefix/index-hash changes do not affect the ID.

Required immutable models:

```python
class ReviewResolution(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    WAIVED = "waived"

class ReviewDecisionAuthority(StrEnum):
    CURRENT = "current"
    DISPLAY_ONLY = "display_only"

@dataclass(frozen=True)
class ReviewItemSnapshot:
    review_id: str
    category: str
    function_id: str
    case_id: str | None
    semantic_subject_key: str
    subject_artifacts: tuple[ReviewSubjectReference, ...]

@dataclass(frozen=True)
class ReviewItemCollection:
    items: tuple[ReviewItemSnapshot, ...]
    def resolve(self, review_id: str) -> ReviewItemSnapshot | None: ...

@dataclass(frozen=True)
class ReviewReadinessSnapshot:
    selected_run_id: str | None
    run_outcome: RunOutcome | None
    execution_references: tuple[ReviewSubjectReference, ...]
    selected_evidence_id: str | None
    evidence_source_run_id: str | None
    evidence_references: tuple[ReviewSubjectReference, ...]
    required_evidence_files: tuple[ReviewRequiredFileFact, ...]
    observed_evidence_files: tuple[ReviewRequiredFileObservation, ...]
    ready_for_review: bool
    ready_for_review_reasons: tuple[str, ...]
    evidence_ready: bool
    evidence_ready_reasons: tuple[str, ...]
    test_green: bool
    test_green_reasons: tuple[str, ...]

@dataclass(frozen=True)
class ReviewSnapshot:
    items: ReviewItemCollection
    function_id: str | None
    external_source: ReviewExternalSourceFact | None
    published_source_observation: ReviewExternalSourceObservation | None
    observed_source_observation: ReviewExternalSourceObservation | None
    core_source_reasons: tuple[str, ...]
    source_current: bool
    source_reasons: tuple[str, ...]
    generation: int
    subject_fingerprint: str
    snapshot_id: str
    readiness: ReviewReadinessSnapshot
    publication_recovery_state: ReviewSubjectPublicationRecoveryState

class ReviewSnapshotConflictError(RuntimeError):
    code: Literal["current_snapshot_conflict"]
    attempts: int
    elapsed_seconds: float
    last_generation: int | None
    last_publication_state: str | None
    publication_recovery_state: ReviewSubjectPublicationRecoveryState

@dataclass(frozen=True)
class ReviewSnapshotStateDetails:
    reason_code: Literal[
        "manifest_absent", "legacy_manifest_requires_finalization",
        "manifest_invalid", "complete_fence_invalid", "presence_map_invalid",
        "snapshot_id_mismatch", "snapshot_index_missing", "snapshot_index_invalid",
        "immutable_subject_missing", "immutable_subject_mismatch",
        "mutable_subject_mismatch", "subject_identity_invalid", "path_policy_invalid",
    ]
    generation: int | None
    snapshot_id: str | None
    subject_path: str | None
    publication_recovery_state: ReviewSubjectPublicationRecoveryState

class ReviewSnapshotStateError(RuntimeError):
    code: Literal["review_snapshot_unavailable", "invalid_review_snapshot"]
    details: ReviewSnapshotStateDetails

@dataclass
class _ReviewSnapshotRetryBudget:
    started_at: float
    deadline: float
    attempts_started: int = 0
    max_attempts: Literal[3] = 3

def _resolve_review_snapshot_once(
    workspace: Path, *, budget: _ReviewSnapshotRetryBudget,
) -> ReviewSnapshot: ...

@dataclass(frozen=True)
class ReviewDecision:
    review_id: str
    resolution: ReviewResolution
    reviewer: str
    rationale: str
    decided_at: str | None
    subject_artifacts: tuple[ReviewSubjectReference, ...]
    authority: ReviewDecisionAuthority
    source_schema_version: str

@dataclass(frozen=True)
class ReviewDecisionSet:
    revision: int
    decisions: tuple[ReviewDecision, ...]
```

The repository interface deliberately differs from the carrier: it accepts no `current_items` or other pre-resolved subject collection. It also owns decision authority/provenance: public write inputs contain neither `authority` nor `source_schema_version`; successful persistence always stamps the current values, while migration alone creates display-only provenance.

```python
class ReviewDecisionWriteStatus(StrEnum):
    WRITTEN = "written"
    UNKNOWN_REVIEW_ID = "unknown_review_id"
    SUBJECT_FINGERPRINT_MISMATCH = "subject_fingerprint_mismatch"
    SOURCE_NOT_CURRENT = "source_not_current"
    REVISION_CONFLICT = "revision_conflict"
    CURRENT_SNAPSHOT_CONFLICT = "current_snapshot_conflict"
    REVIEW_SNAPSHOT_UNAVAILABLE = "review_snapshot_unavailable"
    INVALID_REVIEW_SNAPSHOT = "invalid_review_snapshot"
    INVALID_DECISION_METADATA = "invalid_decision_metadata"

@dataclass(frozen=True)
class ReviewDecisionLedgerSnapshot:
    payload: Mapping[str, object]  # recursively frozen mapping/tuple JSON view
    decision_set: ReviewDecisionSet
    raw_bytes: bytes
    sha256: str

@dataclass(frozen=True)
class ReviewRecoveryState:
    required: bool
    lock_path: str | None
    owner_token: str | None
    marker_state: str | None
    committed_revision: int | None
    committed_sha256: str | None
    residue_paths: tuple[str, ...]
    manual_recovery_required: bool

@dataclass(frozen=True)
class ReviewDecisionConflictDetails:
    expected_subject_fingerprint: str | None
    current_subject_fingerprint: str | None
    generation: int | None
    snapshot_id: str | None
    external_source: ReviewExternalSourceFact | None
    published_source_observation: ReviewExternalSourceObservation | None
    observed_source_observation: ReviewExternalSourceObservation | None
    source_reasons: tuple[str, ...]

@dataclass(frozen=True)
class ReviewSnapshotConflictDetails:
    attempts: int
    elapsed_seconds: float
    last_generation: int | None
    last_publication_state: str | None
    publication_recovery_state: ReviewSubjectPublicationRecoveryState

@dataclass(frozen=True)
class ReviewDecisionWriteResult:
    status: ReviewDecisionWriteStatus
    current_revision: int | None
    snapshot: ReviewDecisionLedgerSnapshot | None = None
    artifact: ProducedArtifact | None = None
    conflict_details: ReviewDecisionConflictDetails | None = None
    snapshot_conflict_details: ReviewSnapshotConflictDetails | None = None
    snapshot_state_details: ReviewSnapshotStateDetails | None = None
    message: str = ""

class ReviewDecisionLedgerError(RuntimeError):
    code: Literal["invalid_ledger", "ledger_unreadable"]
    current_revision: None
    ledger_path: str
    recovery_state: ReviewRecoveryState
    primary_error: BaseException | None

class ReviewDecisionPersistenceError(OSError):
    code: Literal[
        "precommit_io_failed",
        "precommit_cleanup_failed",
        "committed_cleanup_failed",
        "recovery_blocked",
    ]
    phase: str
    committed: bool
    current_revision: int | None
    artifact: ProducedArtifact | None
    recovery_state: ReviewRecoveryState
    primary_error: BaseException
    cleanup_errors: tuple[BaseException, ...]

class ReviewDecisionRepository:
    def __init__(
        self, workspace_root: Path, *,
        producer_version: str, producer_commit: str,
    ) -> None: ...

    def load(self) -> ReviewDecisionLedgerSnapshot | None: ...

    def record(
        self, *, review_id: str, resolution: ReviewResolution,
        reviewer: str, rationale: str, decided_at: str | None,
        expected_revision: int,
        expected_subject_fingerprint: str,
    ) -> ReviewDecisionWriteResult: ...

def record_review_decision(
    workspace_root: Path | str, *,
    review_id: str, resolution: ReviewResolution,
    reviewer: str, rationale: str, decided_at: str | None,
    expected_revision: int,
    expected_subject_fingerprint: str,
) -> ReviewDecisionWriteResult: ...
```

`ReviewItemSnapshot` construction/validation requires `len(subject_artifacts) >= 1`; a tuple type annotation alone is not treated as enforcement. `record(...)` invokes the canonical workspace snapshot resolver itself after acquiring the ledger lock. A private injectable clock/filesystem/snapshot test seam is allowed; callers of the public repository cannot substitute current items.

Ledger revision semantics are exact: `expected_revision` is a nonnegative integer; a strict containment check followed by verified absence of `reports/review_decisions.json` means current revision `0`; the first write requires expected revision `0` and commits revision `1`; every valid existing ledger has revision `>= 1`. `load()` returns `None` only for that verified absent state and never fabricates payload/raw bytes/hash for it. Existing JSON/UTF-8/schema/semantic/path-policy invalidity, directory, symlink, or reparse state raises `ReviewDecisionLedgerError(code="invalid_ledger", current_revision=None)`; a contained regular ledger that cannot be read raises `ReviewDecisionLedgerError(code="ledger_unreadable", current_revision=None)`. Both carry the deterministic ledger path and read-only recovery state, never fabricate revision `0`, propagate unchanged through assessment and record without snapshot retry, and are distinct from `ReviewDecisionPersistenceError`, which begins only after a strict ledger state has loaded and a mutating persistence operation fails. CLI discovery and write serialize `ledger_revision=0` only after verified absence.

`ReviewDecisionLedgerSnapshot` never exposes the mutable object returned by `json.loads`. Construction recursively freezes objects as read-only mappings and arrays as tuples after validation; nested aliases are not retained. Any API that needs a mutable projection receives a fresh defensive deep copy, while identity and persistence remain bound to `raw_bytes`/`sha256` plus the typed immutable decision set.

Expected conflicts use `ReviewDecisionWriteResult`. When the shared resolver exhausts, record converts `ReviewSnapshotConflictError` only to `CURRENT_SNAPSHOT_CONFLICT` plus a lossless `ReviewSnapshotConflictDetails` copy of aggregate attempts, elapsed seconds, last generation/state, and publication recovery state; the known lock-time ledger revision remains in `current_revision`, and no temp is created. A nonretryable `ReviewSnapshotStateError` instead maps only to `REVIEW_SNAPSHOT_UNAVAILABLE` or `INVALID_REVIEW_SNAPSHOT` with the lossless `snapshot_state_details`, same known revision, and no temp/write/artifact. These state statuses never consume a second attempt. Unrelated write statuses leave both snapshot detail fields null. Every filesystem/cleanup/recovery failure raises `ReviewDecisionPersistenceError`; `COMMITTED_CLEANUP_FAILED` is therefore not also a write-result status. The exception preserves its primary traceback, attaches cleanup errors without replacing it, and carries the exact artifact/revision only when committed. The module-level `record_review_decision(...)` is a thin safe wrapper over the repository and is the master-name-compatible public entry point.

Assessment seams:

```python
def discover_review_snapshot(workspace: Path | str) -> ReviewSnapshot: ...

@dataclass(frozen=True)
class ReviewItemAssessment:
    review_id: str
    status: ReviewAssessmentStatus
    resolution: ReviewResolution | None
    reasons: tuple[str, ...]
    subject_fingerprint: str
    complete: bool

@dataclass(frozen=True)
class ReviewAssessment:
    ledger_revision: int
    snapshot: ReviewSnapshot
    items: tuple[ReviewItemAssessment, ...]
    orphan_review_ids: tuple[str, ...]
    ready_for_review: bool
    review_complete: bool
    evidence_ready: bool
    test_green: bool
    ready_for_review_reasons: tuple[str, ...]
    review_complete_reasons: tuple[str, ...]
    evidence_ready_reasons: tuple[str, ...]
    test_green_reasons: tuple[str, ...]
    recovery_state: ReviewRecoveryState
    publication_recovery_state: ReviewSubjectPublicationRecoveryState

def assess_review_completion(
    workspace: Path | str,
) -> ReviewAssessment: ...

assess_review_decisions = assess_review_completion
```

`discover_review_snapshot(...)` computes `ReviewReadinessSnapshot` only from the same immutable index and current-byte revalidation used for review items; it never performs a second mutable workspace scan. `required_evidence_files` preserves the indexed publication facts and `observed_evidence_files` carries the separately keyed stable current observations. A required component is ready only when its current observation exactly equals the indexed fact and both are valid for the declaration. A stable missing/invalid/hash-mismatched state or any stable published/current difference returns `evidence_ready=false` with typed reason while the other axes remain evaluable; only a component whose two current observations differ within the attempt causes retry/conflict. Pointer or manifest schema/path/hash invalidity fails the evidence axis closed with no flat fallback, but does not erase independently valid review/run facts.

`assess_review_completion(...)` always loads the authoritative workspace ledger and resolves the workspace-owned snapshot; it cannot receive caller-supplied decisions, current items, artifacts, run facts, or evidence facts. It creates `_ReviewSnapshotRetryBudget` once, with `deadline = started_at + 2.0` from the one injected monotonic clock. Its outer coherence attempt reads ledger state L1, calls `_resolve_review_snapshot_once(...)` exactly once for stable complete subject generation S with all three subject-derived axes, then reads ledger state L2 and accepts only when both reads verified absence or both are strict existing snapshots with identical raw hash/revision. The private resolver performs no retry loop, sleep, deadline creation, or attempt-counter reset. Any transient S conflict or L1/L2 mismatch consumes that same aggregate attempt. Assessment and record never call public `discover_review_snapshot(...)`, whose wrapper owns retries only for direct discovery. `_assess_review_snapshot(snapshot, decisions)` combines the accepted ledger-derived `review_complete` axis with the other three axes already derived from S and returns all four plus per-axis reasons while retaining that exact S as `ReviewAssessment.snapshot`; the successful assessment revision is exactly `0` for accepted absence or the existing revision `>=1`. The CLI serializes function/source identity, generation, aggregate fingerprint, current items, exact references, and selector/readiness facts only from this retained snapshot; it never performs a second discovery. Changed ledger/subject state exhausts at the shared third started attempt or the same deadline and raises `ReviewSnapshotConflictError` whose attempts/elapsed fields describe the aggregate budget. Invalid/unreadable ledger raises its typed nonretryable error immediately. The private pure helper is the only decision-set injection seam for tests and is not exported. `ReviewAssessmentStatus` is closed to `missing`, `open`, `approved`, `changes_requested`, `waived`, and `stale`; orphan IDs are a separate collection. `ReviewItemAssessment.complete` is true only for exact current `authority="current"` approved/waived decisions. Display-only provenance is always stale even when every reference field, including a legitimate null revision, otherwise matches.

The repository may receive a stable snapshot whose external source is stale for read-only assessment, but `record(...)` refuses it before ledger temp creation and returns `SOURCE_NOT_CURRENT` with `ReviewDecisionConflictDetails` containing equal expected/current fingerprints, generation/snapshot, declared fact, indexed observation, fresh stable observation, and typed source reasons; it writes no temp/ledger byte or artifact. `SUBJECT_FINGERPRINT_MISMATCH` is reserved for an expected fingerprint that is unequal to the resolved four-field aggregate fingerprint. Finalization must publish a new source-bound generation before a decision can be recorded for newly observed bytes.

The pre-Task-6 `dossier.readiness.assess_readiness(artifacts, blocked_reasons, unresolved_items)` remains only a compatibility/presentation helper and cannot authorize review state, populate `get-review-status`, or gate Phase 2. Dossier finalization opens one operation journal before its first immutable snapshot/product write and keeps that journal across publication-lock release/reacquisition. After publishing a complete fence it releases the marker, calls the workspace-only `assess_review_completion(...)`, atomically writes presentation dossier sidecars through the journal, and uses manifest-revision/fence-guarded `update_summary(...)` only to cache those four values plus the assessed ledger revision for display. A concurrent subject change conflicts. A later ledger change may make that explicitly provenance-stamped cache stale, so consumers always call the workspace-only assessment rather than trusting cached summary fields. Any post-complete assessment/sidecar/summary failure with net changes is `publication_committed_failed` and reports the final manifest/snapshot/dossier facts rather than claiming no write.

### CLI contract fixed for Task 6

Read-only discovery:

```text
get-review-status --workspace PATH
```

Guarded write:

```text
record-review-decision
  --workspace PATH
  --review-id ID
  --resolution open|approved|changes_requested|waived
  [--reviewer TEXT]
  [--rationale TEXT]
  [--decided-at RFC3339_TIMESTAMP]
  --expected-revision INT
  --expected-subject-fingerprint SHA256
```

`--expected-subject-sha256` remains only as a compatibility alias for the aggregate `--expected-subject-fingerprint`; callers never provide a subject list. If both flags are supplied, the parser accepts them only when their normalized lowercase 64-hex values are identical and otherwise returns an exit-1 input error before discovery or write.

Explicit offline subject-publication recovery:

```text
recover-review-subject-publication
  --workspace PATH
  [--expected-generation INT]
  [--expected-uninitialized-manifest-sha256 SHA256|absent]
  --expected-marker-owner-token OWNER_TOKEN
  --expected-transaction-token TOKEN
  --action complete|restore-previous|abandon-to-dirty|clear-complete-marker|clear-uninitialized-marker
  --confirm-all-writers-stopped
```

All three commands use the existing `cli_result` 1.0.0 envelope. Internal `CLIResult.status` is not serialized and is never the public discriminator. `get-review-status` is read-only, performs no recovery mutation, and returns no produced artifacts. Its `data.details` is projected only from the returned `ReviewAssessment` plus the already normalized request workspace and deterministic ledger path; it contains ledger revision, function/source identity from `assessment.snapshot`, current items and exact references/fingerprints from that same snapshot, decision status/currentness/blocking reasons, orphan IDs, all four readiness axes, a serialized ledger `recovery_state` matching `ReviewRecoveryState`, and `publication_recovery_state` matching `ReviewSubjectPublicationRecoveryState`. The item collection key is exactly `items`; each entry contains `review_id`, `status`, nullable `resolution`, `reasons`, `subject_fingerprint`, `complete`, and the matching immutable-snapshot `subject_artifacts` without another workspace read. This projection may flatten those contract fields but never reopens the ledger, manifest, subjects, source, run, or evidence. Successful `record-review-decision` returns exactly one current 1.1.0 `review_decisions` `ProducedArtifact` plus `data.details.write_status="written"`, ledger revision/review ID/fingerprint, and `recovery_state.required=false`. `SOURCE_NOT_CURRENT` is an exit-1 guard conflict with the known lock-time revision, null artifact, and the structured source conflict details above. The explicit recovery command is unavailable through any automatic workflow: it requires every guard above and projects `recovery_action`, accepted marker identities, and exact before/after revision/state/generation/token/fingerprint/snapshot/canonical-fence identities solely from `ReviewSubjectPublicationResult.recovery_transition`; the CLI never reconstructs them with a pre-read. It also reports `deleted_paths` and returns `ProducedArtifact` entries only for exact present files it actually changed.

Expected user/guard conflicts and an uncommitted ledger `recovery_blocked` lock-acquisition timeout use `EXIT_INPUT_ERROR` (1), outcome `error`, empty artifacts/expected-artifacts, unchanged bytes, and `data.details.write_status` set to the typed conflict/recovery value. `ReviewDecisionLedgerError` is caught before persistence, `CLIError`, and generic handlers; both `invalid_ledger` and `ledger_unreadable` map exactly to exit 1/outcome error, empty artifacts/expected-artifacts, `errors[0].code == data.details.write_status == error.code`, `ledger_revision=null`, `current_revision=null`, and the serialized read-only `recovery_state`. Other pre-commit filesystem persistence/cleanup failures use `EXIT_OUTPUT_ERROR` (3), no ledger artifact, `errors[0].code` and `data.details.write_status` equal to the persistence error code, and truthful serialized `recovery_state`. `committed_cleanup_failed` is the sole post-commit ledger exception: `EXIT_OUTPUT_ERROR` (3), outcome `error`, `errors[0].code="committed_cleanup_failed"`, `data.details.write_status="committed_cleanup_failed"`, exactly one real artifact, and details containing `committed=true`, committed revision/hash, and `recovery_state.manual_recovery_required=true`. The CLI catches `ReviewDecisionPersistenceError` before generic `CLIError` so these fields/artifacts cannot be discarded. Internal invariant failures keep the existing exit 10 boundary; expected conflicts or filesystem denials do not become internal errors.

`get-review-status` catches `ReviewSnapshotStateError` before `CLIError`/generic handling and maps both state codes to exit 1/outcome error, empty artifacts/expected-artifacts, `errors[0].code == data.details.snapshot_state`, and exact reason/path/generation/snapshot/publication-recovery details. `record-review-decision` projects the corresponding write-result status into both `errors[0].code` and `data.details.write_status`, includes the known ledger revision plus the same state details, and returns no artifact/temp/write. Neither command retries a stable state error or maps it to exit 10; `current_snapshot_conflict` remains reserved for the changing/marker/dirty/publishing cases above.

The common `cli/main.py` dispatch boundary also catches `ReviewSubjectPublicationError` before `CLIError` and the generic internal-error handler for every subject-mutating command. A `publication_conflict` or uncommitted `publication_recovery_blocked` maps to exit 1 only when the operation's verified projection has no committed file, deletion, superseded path, or residue; any attributable fact promotes it to `publication_committed_failed`, exit 3, and `RunOutcome.ERROR`. Other precommit/committed filesystem failures map to exit 3. `errors[0].code` and `data.details.write_status` preserve the final publication code, and `publication_recovery_state` is always serialized. For every committed/deleted/superseded/residue fact, the CLI independently resolves its declared root and rechecks root-role/path containment; committed/current-file identities also require the exact current hash before a schema-compatible relative-path `ProducedArtifact` is built against that root. `data.details.artifact_roots` correlates each committed `(kind,path,sha256)` with its explicit absolute root/role, so suite-entry and detached-output facts are unambiguous. Structured deleted, superseded, and residue records serialize their own root role/path plus last-owned hash and observed state/current hash/reason as applicable and never become file artifacts. The original error remains the primary diagnostic and cleanup errors are additive. No publication failure becomes exit 10 or loses an attributable final file/deletion/residue fact. The top-level publisher never imports `cli.artifacts`; conversion occurs only in the CLI boundary.

Do not touch `vscode/extension` in Task 6. An unexpected need to do so is a scope-review stop.

---

## 7. Sequential implementation slices

### Slice 0 — Freeze the execution boundary

**Purpose:** Preserve a restartable plan before product edits.

Steps:

1. Verify branch/base/status and the primary checkout non-interference condition.
2. Commit this plan alone.
3. Push the branch as a checkpoint without opening a product PR yet.

Checks:

```powershell
git status --short --branch
$startAnchor = '969ce9462a688e94c887d6e77359e40296d8927b'
$planPath = 'docs/superpowers/plans/2026-07-15-phase1-task6-review-decisions-readiness.md'

# After staging only the plan, validate the actual index bytes before commit.
git diff --cached --check -- $planPath
if ($LASTEXITCODE -ne 0) { throw 'staged Task 6 plan diff check failed' }

# After the plan commit, validate the committed start-anchor-to-HEAD candidate.
git diff --check "$startAnchor...HEAD"
if ($LASTEXITCODE -ne 0) { throw 'committed Task 6 plan diff check failed' }
git diff --name-only "$startAnchor...HEAD"
if ($LASTEXITCODE -ne 0) { throw 'cannot enumerate committed Task 6 plan diff' }
```

Expected commit: `docs: plan Phase 1 Task 6 recovery`

### Slice 1 — Current-contract compatibility and direct wheel dependency

**Purpose:** Close the three compatibility gates before introducing new decision behavior.

RED A — current-envelope build-probe consumer:

- Extend the public build-probe test so a syntactically current 1.1.0 dossier envelope is read from its nested `data` object without assuming the legacy flat 1.0 shape.
- This slice does **not** register FUNCTION_DOSSIER 1.1.0 or change migrations; those contract changes belong to Slice 3. The compatibility RED exercises `build_probe(...)` directly and keeps the existing legacy-envelope test GREEN.
- The test must import existing public APIs successfully and fail on an expected value/validation assertion.

RED B — current-envelope reanalysis normalization:

- Establish the smallest exported `contracts.consumer` in-memory/file-loading seam for the already registered current 1.0 core contracts before any dossier schema bump. A strict-current envelope is validated for its expected artifact kind and yields only its nested `data`; an explicitly allowed raw 0.1 object retains its legacy consumer shape. A mismatched kind, unsupported version, or current-shaped invalid envelope fails closed and never falls back to legacy.
- Add `tests/test_reanalysis_snapshot_builder.py` REDs that feed strict-current source-digest/function-location/function-signature envelopes through the real snapshot-builder/workflow path. The returned payloads are their normalized `data`, snapshot source path/hash come from `data.source`, and `SnapshotArtifact.schema_version` retains the envelope's `1.0.0`. Existing explicit raw-0.1 fixtures remain byte/shape compatible.
- FUNCTION_DOSSIER 1.1 remains unregistered until Slice 3, so RED A's dossier-specific build-probe handling stays a direct compatibility branch in this slice rather than weakening the shared strict-current consumer.

RED C — direct dependency and normal install:

- Build a wheel, inspect `METADATA`, and assert a direct `Requires-Dist: referencing` with the supported bound.
- Replace the target-wheel `--no-deps` installation path with a normal fresh-venv installation that resolves declared dependencies, then import and exercise contract validation from the installed wheel.
- A missing module during an intentionally dependency-free install is not accepted as RED; the metadata assertion is the RED.

Focused command:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_contract_validation tests.test_build_probe tests.test_reanalysis_snapshot_builder tests.test_wheel_contract -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 1 focused tests failed' }
```

GREEN target:

- `build_probe(...)` accepts the nested current-envelope data shape while preserving legacy-envelope behavior.
- Reanalysis consumes strict-current core envelopes through the shared consumer-data seam and preserves only explicitly allowed raw-0.1 inputs.
- `pyproject.toml` declares `referencing>=0.28.4,<1` directly.
- Fresh normal wheel install validates all packaged schemas.

Review checkpoint: compatibility only; no review-decision persistence yet.

Expected commit: `fix: preserve current consumer and wheel compatibility`

Hosted checkpoint facts for the exact Slice 1 head `9cd9767f2add9406cd48ccf74e72e65ac4bb7bb1`:

- GitHub Actions run `29423972017` completed with 5 of 6 jobs GREEN and `Python tests` RED.
- The Python job executed 112 isolated modules. The failing modules were `tests.test_build_probe` and `tests.test_reanalysis_snapshot_builder`.
- The three assertion failures were raw-string or dictionary-key comparisons between a distinct Windows 8.3 short alias and the long spelling of the same physical path.
- This is historical evidence for that exact head, not an accepted Slice 2 entry gate.

### Slice 1 CI reconciliation — Equivalent Windows temporary-path aliases

**Purpose:** Reconcile the hosted-only alias-sensitive assertions without weakening containment or changing correct product behavior, and restore the exact-head hosted gate before Slice 2.

Execute this slice sequentially before Slice 2:

1. Before changing an assertion, reproduce the three hosted failures in a child Python process. The parent must obtain a real distinct long/8.3-short directory pair through the existing `tests.windows_path_alias_support` helper, prove the pair is textually distinct and `os.path.samefile(...)`-equal, and set that child's `TEMP`, `TMP`, and `TMPDIR` to the short alias plus `UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS=1`. The child runs only `tests.test_build_probe` and `tests.test_reanalysis_snapshot_builder`; the accepted RED is exactly the three hosted raw-string/dictionary-key assertion failures, not an import, setup, alias-unavailable, or unrelated failure.
2. For every failed operand pair, capture the concrete long and short file spellings while both exist and prove with `os.path.samefile(...)` that they name the same physical file before editing the assertion. Normalization or case-folded string equality alone is not physical-identity evidence.
3. If the product result names the correct contained physical file, change only `tests/test_build_probe.py` and `tests/test_reanalysis_snapshot_builder.py`. Replace only the alias-sensitive raw-string/dictionary-key expectations with physical-identity comparison and add both long-expected/short-actual and short-expected/long-actual coverage for each affected comparison family. Reuse the existing alias helper without modifying it; do not change product code, workflow files, or any other test module in this reconciliation.
4. If any product result names a different physical file or escapes containment, stop without a product change and amend and re-review this plan before continuing.

Forced-short-TEMP child command, run first on the pre-fix tree for the exact RED and again after the test-only change for GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
@'
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.windows_path_alias_support import (
    WINDOWS_8DOT3_PREFIX,
    windows_path_alias_pair,
)

repo = Path.cwd().resolve()
with tempfile.TemporaryDirectory(prefix=WINDOWS_8DOT3_PREFIX) as temp_dir:
    pair = windows_path_alias_pair(Path(temp_dir))
    assert os.path.samefile(pair.long, pair.short), pair
    assert os.path.normcase(os.path.normpath(os.fspath(pair.long))) != os.path.normcase(
        os.path.normpath(os.fspath(pair.short))
    ), pair
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = os.fspath(repo / "src")
    child_env["UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS"] = "1"
    for name in ("TEMP", "TMP", "TMPDIR"):
        child_env[name] = os.fspath(pair.short)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_build_probe",
            "tests.test_reanalysis_snapshot_builder",
            "-v",
        ],
        cwd=repo,
        env=child_env,
        check=False,
    )
    raise SystemExit(completed.returncode)
'@ | py -
```

After the test-only change, run the focused modules once in the normal environment and once with the forced-short-TEMP child command above:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
py -m unittest tests.test_build_probe tests.test_reanalysis_snapshot_builder -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 1 CI reconciliation normal focused tests failed' }
```

Then run the authoritative CI-equivalent dynamic inventory with one fresh forced-short-TEMP child process per module and required alias mode:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
@'
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.windows_path_alias_support import (
    WINDOWS_8DOT3_PREFIX,
    windows_path_alias_pair,
)

repo = Path.cwd().resolve()
modules = sorted(f"tests.{path.stem}" for path in (repo / "tests").glob("test_*.py"))
if not modules:
    raise SystemExit("isolated Python test discovery returned no modules")
failed = []
with tempfile.TemporaryDirectory(prefix=WINDOWS_8DOT3_PREFIX) as temp_dir:
    pair = windows_path_alias_pair(Path(temp_dir))
    assert os.path.samefile(pair.long, pair.short), pair
    assert os.path.normcase(os.path.normpath(os.fspath(pair.long))) != os.path.normcase(
        os.path.normpath(os.fspath(pair.short))
    ), pair
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = os.fspath(repo / "src")
    child_env["UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS"] = "1"
    for name in ("TEMP", "TMP", "TMPDIR"):
        child_env[name] = os.fspath(pair.short)
    for module in modules:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", module, "-v"],
            cwd=repo,
            env=child_env,
            check=False,
        )
        if completed.returncode != 0:
            failed.append(module)
print(f"isolated_modules={len(modules)} failures={len(failed)}")
if failed:
    raise SystemExit("isolated Python failures: " + ", ".join(failed))
'@ | py -
if ($LASTEXITCODE -ne 0) { throw 'Slice 1 CI reconciliation isolated required-alias gate failed' }
```

Obtain fresh spec and code-quality review for the exact reconciliation diff and accept it only at `C0/I0/M0`. Commit exactly as `test: handle equivalent Windows path aliases`, push that coherent checkpoint, and require all six hosted jobs GREEN for its exact pushed head before Slice 2 begins. Record the normal/forced focused exits, dynamic module count, review verdicts, commit/pushed SHA, hosted run ID/head SHA, and 6/6 job readback in the slice handoff.

### Slice 2 — Stable public review IDs shared by dossier and TestSpec

**Purpose:** Remove ordinal identity and establish one collision-checked semantic identity seam.

Structural RED/GREEN:

- `find_spec("unit_test_runner.review_ids")` assertion RED.
- Add the smallest public module and exported types/functions, then structural GREEN.

Behavior RED:

- Reordering review items preserves IDs.
- Localizing titles/display text preserves IDs.
- Separator/NFKC/outer-space equivalents preserve IDs.
- C identifier case remains significant.
- Semantic-subject changes produce different IDs.
- Distinct semantic tuples that collide raise a typed collision.
- Public dossier `build_review_items(...)` and TestSpec generation produce the same ID for the same semantic subject.
- Tests call public builders, not a test-only helper.
- Literal REDs assert every `build_function_id` and `build_review_id` vector in the canonical byte contract above, including Unicode/NFKC/separator handling, case-sensitive digest differences, `case_id=None` versus supplied blank, embedded-NUL rejection, path normalization/rejection, and TestSpec delegation preserving every pre-Task-6 function ID.
- Generic final-review ID remains semantic/stable while its exact subject tuple follows the fixed present-strict-TestSpec, else verified-TestSpec-absence plus source-digest/function-location/function-signature choice; a present invalid TestSpec or a phase with neither eligible choice emits no decisionable item.

Focused command:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_dossier_review_workflow tests.test_review_decisions tests.test_test_spec_contract -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 2 focused tests failed' }
```

GREEN target: no ordinal ID generation remains on either path; display fields are never identity inputs.

Expected commit: `feat: share stable semantic review ids`

### Slice 3 — Closed decision models, immutable 1.0, current 1.1.0, migration

**Purpose:** Define the versioned ledger/dossier contracts before persistence.

Structural RED/GREEN:

- Establish importable decision-model and schema-registry seams first.

Behavior RED:

- Closed resolution values and terminal metadata rules.
- Exact canonical subject-reference fields (including selector-vs-artifact role) and the separate authoritative four-field aggregate-fingerprint projection. Literal REDs fix the empty, Unicode/null/order, and null→zero hashes above; reversed input and excluded-field-only changes preserve the hash, while any projected field change differs and duplicate/conflicting identity is rejected.
- Current 1.1 common definitions add the separately typed `ReviewExternalSourceFact` shape (normalized relative logical identity, canonical absolute read-only locator, exact SHA-256) for manifest/index/dossier use; current 1.0 core envelopes keep their existing relative `subject.source_path` contract and carry the same fact only inside the already-open producer extension. Semantic validation rejects any attempt to put an absolute locator into a 1.0 subject/reference path.
- Current schemas/models reject an empty review-item `subject_artifacts` tuple; migration of an unbound legacy item preserves it only as non-authoritative/display-only metadata, never as a current decisionable item.
- Closed `dirty|publishing|complete` publication-state shape, transaction token/index hash, and conditional `previous_complete` recovery identity in DOSSIER_MANIFEST 1.1. A complete snapshot permits zero review-item bindings and nullable external source: a non-null fact requires a complete published observation, while a null fact requires nonempty typed `core_source_reasons` and a null observation. Every emitted decisionable binding still requires a nonempty fully populated exact immutable/current reference tuple.
- `get_contract(...)` distinguishes immutable 1.0 and current 1.1.0 for all three kinds.
- Every published 1.0 schema in the exact 40-contract inventory resolves only immutable `common_v1_0.schema.json` definitions: 36 existing non-Task-6 current-1.0 files, existing TestSpec 1.0, and the three new Task 6 `_v1_0` snapshots. The three Task 6 current schemas move to 1.1 and may reference current `common.schema.json`.
- An inventory RED enumerates schema files, asserts no schema whose effective version is 1.0 references mutable `common.schema.json`, and asserts the exact reviewed 40-path immutable set so a newly added 1.0 contract cannot silently escape the freeze.
- `common_v1_0.schema.json` is the exact published-1.0 definition snapshot needed by known 1.0 fixtures, not a copy made after Task 6-only definitions are added to current common.
- Adding/changing a current 1.1 definition cannot alter 1.0 validation results.
- 1.0-to-1.1 migration is lossless, leaves source bytes/objects unchanged, preserves legacy `done` as metadata only, stamps every migrated decision `authority="display_only"` plus its source schema version, and assigns `revision: null` when revision provenance is unprovable. Newly recorded decisions are the only path to `authority="current"`.
- The migration RED has two independently required layers. `tests.test_contract_migrations` exercises source-tree behavior, and `tests.test_wheel_contract` drives a normally installed wheel from a sanitized repository-external working directory under `python -I`. The installed-wheel matrix must be exact-set equal to `{REVIEW_DECISIONS, FUNCTION_DOSSIER, DOSSIER_MANIFEST}` and must migrate a strict-valid 1.0 fixture for every kind through the installed `contracts.migrations.migrate_payload(...)`; source-only migration tests are insufficient. For every vector, retain canonical input bytes and a deep copy, prove neither changes, validate the 1.1.0 output with the installed validator, and assert the kind-specific fail-closed semantics: legacy decisions are `display_only` with `source_schema_version="1.0.0"` and an unprovable `revision: null`; legacy dossier `done=true` survives only as non-authoritative migration metadata; and a 1.0 manifest cannot acquire a complete review fence. The isolated probe must prove `unit_test_runner`, `contracts.migrations`, `jsonschema`, and `referencing` all import from the fresh venv and no imported project module resolves under the repository.
- Legacy subject references without a role migrate as `artifact`; `current_selector` is never inferred from an unproven legacy path.
- Loaded ledger snapshots recursively freeze mapping/list payloads with no retained mutable alias; mutation attempts fail, defensive-copy mutation cannot change `decision_set`, `raw_bytes`, or `sha256`, and canonical persistence still uses the validated exact bytes.
- A valid DOSSIER_MANIFEST 1.0 migration does not invent a complete review fence; first locked finalization writes `publishing` at 1.1 `manifest_revision=1`, then establishes the complete generation-1 fence with exact current subjects at `manifest_revision=2`. Deterministic REDs inspect both commit points; neither increment may be skipped or reset. Subject writers encountering only 1.0 serialize with the publication lock but cannot confer current review state.
- Unknown versions and non-current strict validation fail closed.

Focused command:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_contract_registry tests.test_contract_validation tests.test_contract_migrations tests.test_wheel_contract tests.test_public_artifact_schemas tests.test_test_spec_contract tests.test_review_decisions -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 3 focused tests failed' }
```

Mandatory Slice 3 package/migration gate: immediately after the focused command is GREEN and before Slice 3 review, staging, or commit, execute the **entire** `Wheel/METADATA/normal fresh-install gate` block defined in Slice 9 against the same unchanged Slice 3 working-tree candidate. Do not extract only its source-tree tests or packaged-schema enumeration. The full execution must build the wheel, verify METADATA, perform the normal dependency-resolving fresh-venv install and `pip check`, sanitize Python/virtual-environment and `UNIT_TEST_RUNNER_*` variables, change to the repository-external probe directory, and run the installed wheel under `python -I` through the exact three-kind `{REVIEW_DECISIONS, FUNCTION_DOSSIER, DOSSIER_MANIFEST}` migration matrix with its input-immutability, strict-1.0 validation, 1.1.0 output-validation, kind-specific fail-closed, import-origin, and cleanup assertions.

The bytes that pass the focused command and the full wheel block are the bytes submitted for Slice 3 review and commit. Any tracked edit after either gate invalidates both results and requires both commands to be rerun before acceptance. The Slice 9 and Slice 10 executions are mandatory independent revalidations of later candidate heads; they cannot retroactively satisfy, replace, or defer this Slice 3 gate.

GREEN target: explicit immutable/current contracts and typed models with no persistence side effects, plus both the source-tree migration suite and the exact three-kind installed-wheel migration matrix GREEN.

Expected commit: `feat: version review decision contracts`

### Slice 4A — Behavior-preserving common Windows retry extraction

**Purpose:** Establish the shared Windows retry primitive before any new manifest writer or lock path uses it.

Structural RED/GREEN:

- Establish `atomic_io` with `find_spec(...)` RED, then the smallest importable retry seam.

Behavior sequence:

1. Run every PR #19 TestSpec lock/replace/export/writer-snapshot regression GREEN before refactoring.
2. Add characterization tests proving TestSpec module-level wrappers still observe their patched Windows predicate, strict deadline, clock/sleep, and original traceback.
3. Delegate those wrappers to the domain-neutral common retry primitive; do not add manifest or review-ledger behavior yet.
4. Re-run the full PR #19 focused set and deterministic two-writer stress. Any regression stops Slice 4A before a manifest publisher or ledger module exists.

Focused command:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_test_spec_repository tests.test_test_spec_formal_review_export_atomicity tests.test_test_spec_formal_review_writer_snapshots -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4A focused tests failed' }
```

Expected commit: `refactor: share Windows filesystem retry`

### Slice 4B — Exact non-cyclic dossier subject graph

**Purpose:** Make current review items resolvable from stable exact-saved-byte subjects.

#### Mandatory 4B TDD, review, commit, and push decomposition

Do **not** execute the acceptance catalog below as one RED/GREEN cycle or one commit. Execute 4B-A through 4B-E2 strictly in order, with only one product writer active. At the start of each sub-slice capture `$previousHead = git rev-parse HEAD`. Add only that sub-slice's assertion-level REDs and run its focused command to prove the intended missing behavior before changing product code. Implement the smallest coherent GREEN, rerun that focused command plus every already-completed 4B focused command, stage only the reviewed sub-slice paths, run `git diff --cached --check`, and commit with the exact message below. Fresh spec and code-quality reviewers then inspect exactly `$previousHead...HEAD`; resolve findings and repeat until both report Critical 0 / Important 0 / Minor 0 (`C0/I0/M0`). Finally run `git diff --check "$previousHead...HEAD"`, require a clean status, and `git push origin HEAD`. A later sub-slice never supplies an earlier sub-slice's GREEN.

##### Slice 4B-A — Domain-neutral publisher and journal core

- RED scope: standalone/import-cycle-safe `review_subject_publisher`, the closed ten-path registry, root containment, one operation journal, exact final-byte hashing, same-directory temp/replace, net committed/deleted/superseded/residue projection, one strict Windows retry deadline, conservative publication marker/lock behavior, pure canonical snapshot-ID goldens, and base raw-writer/publication-lock races. Establish no producer, finalizer, recovery action, or CLI adapter yet.
- Focused RED/GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_review_subject_publication tests.test_contract_validation tests.test_review_decisions -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4B-A focused tests failed' }
```
- GREEN target: the publisher primitives are independently usable; a timeout never reclaims a marker; domain errors retain original traceback plus exact final projection; pure descriptor hashing is physical-path independent.
- Expected commit: `feat: establish review subject publication core`.

##### Slice 4B-B1 — Bound core producers and consumer binding

- RED scope: one shared `ReviewCoreSourceBinding`, strict-current source-digest/location/signature envelopes, relative contract paths separated from the absolute external locator, stable review IDs and nonempty exact core candidate tuples, the shared current/explicit-legacy consumer seam, reanalysis consumption, raw-0.1 direct-call compatibility, and fail-before-write binding mismatch.
- Focused RED/GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_c_source_reading tests.test_function_analysis_reports tests.test_dossier_review_workflow tests.test_reanalysis_snapshot_builder tests.test_contract_migrations -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4B-B1 focused tests failed' }
```
- GREEN target: the three core writers persist one cross-validated binding through an outer publication operation; eligible core candidates are deterministic, but no complete immutable snapshot is published yet.
- Expected commit: `feat: publish bound core review subjects`.

##### Slice 4B-B2 — Atomic TestSpec publication

- RED scope: strict-current TestSpec preference, present-invalid TestSpec fail-closed behavior without core fallback, one outer canonical/view transaction, publication-to-TestSpec lock order, under-lock revision reread, deterministic two-writer behavior, final saved-byte hashes, and every pre-entry/dirty/commit/cleanup failure while preserving all PR #19 retry/monkeypatch semantics.
- Focused RED/GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_test_spec_repository tests.test_test_spec_formal_review_export_atomicity tests.test_test_spec_formal_review_writer_snapshots tests.test_test_spec_formal_review_provenance tests.test_test_spec_generation tests.test_test_spec_reanalysis tests.test_dossier_review_workflow -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4B-B2 focused tests failed' }
```
- GREEN target: TestSpec canonical and views share one truthful domain projection, existing positional and retry seams remain compatible, and cleanup failure cannot erase a committed fact.
- Expected commit: `feat: publish TestSpec review subjects atomically`.

##### Slice 4B-C1 — Harness publication

- RED scope: one operation opened before the first generated C/header write and threaded through generator, dispatcher, state reflector, runner enhancer, shared C writer, and both reports; binding/model preflight; strict-current bound output versus raw legacy direct calls; atomic sidecar failures and exact domain projection.
- Focused RED/GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_harness_skeleton_generation tests.test_harness_report_localization tests.test_dependency_policy_explicit_harness tests.test_build_and_execution_module_boundaries -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4B-C1 focused tests failed' }
```
- GREEN target: no harness sidecar precedes the dirty fence or escapes the shared journal, direct-call forms remain compatible, and the domain error reports only verified final facts.
- Expected commit: `feat: journal bound harness publication`.

##### Slice 4B-C2 — Build-completion publication

- RED scope: one parent operation spanning analyzer plan/iteration/history JSON/Markdown, safe-completion stub header/source and optional Makefile replacement, reporter rewrites, binding/model preflight, explicit keyword-only parent propagation, direct positional compatibility, and failures immediately before/after every representative commit.
- Focused RED/GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_build_diagnostics_and_completion tests.test_build_workspace_generation tests.test_build_and_execution_module_boundaries tests.test_dependency_policy_explicit_harness -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4B-C2 focused tests failed' }
```
- GREEN target: analyzer, `completion_applier`, and reporter have one exact final projection with no journal-external product write; binding mismatch stops before the first write.
- Expected commit: `feat: journal bound build completion publication`.

##### Slice 4B-D1 — Run and execution publication

- RED scope: real run, legacy import, dry-run/legacy-flat execution, both `latest_run.json` paths, immutable target validation before pointer commit, pointer-absent-only flat fallback, binding/consumer behavior, flat-to-pointer presence-map facts, and pointer-commit-aware cleanup.
- Focused RED/GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_execution_run_history tests.test_build_and_execution_module_boundaries tests.test_suite_manager tests.test_prepare_evidence_non_destructive -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4B-D1 focused tests failed' }
```
- GREEN target: real/imported immutable targets survive every post-pointer failure, real runs never create a flat alias, and committed run-domain facts are exact without any CLI conversion.
- Expected commit: `feat: publish immutable run selectors safely`.

##### Slice 4B-D2 — Evidence publication

- RED scope: current/legacy evidence publication, `latest_evidence.json`, immutable manifest validation, required-file normalization across all five collections, valid declaration versus invalid observation, pointer-aware cleanup, binding/consumer behavior, and publication facts needed for later stable observation/re-finalization.
- Focused RED/GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_prepare_evidence_non_destructive tests.test_execution_evidence tests.test_evidence_integrity tests.test_build_and_execution_module_boundaries tests.test_execution_run_history -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4B-D2 focused tests failed' }
```
- GREEN target: pointer and immutable manifest form one verified selection, optional entries are not promoted to required facts, invalid declarations remain distinct from observation failures, and no post-pointer failure deletes the target.
- Expected commit: `feat: publish immutable evidence selectors safely`.

##### Slice 4B-E1 — Immutable snapshot finalizer

- RED scope: integrate all A-D subject candidates into the exact immutable index and content-addressed snapshot, closed positive/negative presence map, detached authority/presentation roots, no self-reference, full descriptor/snapshot-ID/fingerprint validation, generation/revision table, `publishing` to `complete`, summary-only fence preservation, finalizer journal, races, superseded-manifest domain identity, and publishing/complete crash points.
- Focused RED/GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_review_subject_publication tests.test_dossier_review_workflow tests.test_dossier_contract_status tests.test_contract_validation tests.test_review_decisions tests.test_execution_run_history tests.test_execution_evidence tests.test_evidence_integrity -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4B-E1 focused tests failed' }
```
- GREEN target: a strict loader verifies the exact immutable index/snapshot and monotonic complete fence without using the later public resolver; no CLI exit or `ProducedArtifact` assertion belongs here.
- Expected commit: `feat: finalize exact review subject snapshots`.

##### Slice 4B-E2 — Explicit domain recovery

- RED scope: guarded recovery rename/delete, marker/fence CAS, the closed action/state matrix, COMPLETE/RESTORE external and indexed fact revalidation, RESTORE absence deletion, ABANDON restart, marker-only CLEAR actions, exact repository-owned before/after transition, crash-after-linearization projection, and permanent prohibition on automatic marker reclaim.
- Focused RED/GREEN:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_review_subject_publication tests.test_dossier_review_workflow tests.test_contract_validation -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 4B-E2 focused tests failed' }
```
- GREEN target: exactly the eight admitted action-state cells can mutate domain state, every other cell is no-write, all successful and post-linearization failures carry the exact transition, and no CLI serialization is implemented yet.
- Expected commit: `feat: recover review subject publication explicitly`.

The catalog below is an aggregate acceptance inventory, not an execution unit. In sentences that span later layers, 4B owns only publication-side facts: public stable resolution and in-attempt retry belong to Slice 5A; ledger persistence to Slice 5B; semantic source/evidence/test readiness to Slice 7; and exit codes, CLI artifacts, suite-entry conversion, and command dispatch to Slice 8. In particular, 4B domain errors expose `publication_conflict` or `publication_committed_failed` plus committed/deleted/superseded/residue facts; only Slice 8 maps an empty projection to exit 1 or an attributable projection to exit 3 and builds `ProducedArtifact` values.

Aggregate behavior catalog:

- Dossier and manifest expose stable IDs and canonical subject references.
- Every emitted decisionable item has a nonempty exact subject tuple. Its complete normalized semantic tuple is stored with the references in the immutable index, recomputes to the same review ID, and is included in the logical snapshot-ID descriptor. The generic final-review fallback binds exactly a present strict-current TestSpec; only verified TestSpec-path absence may select the strict-current source-digest/function-location/function-signature triple. Present legacy/invalid/mismatched TestSpec REDs emit no core fallback and remain not ready/review-incomplete, as do all other no-eligible-subject workspaces, instead of emitting an evergreen empty-bound decision.
- Exact SHA-256 is computed from final persisted bytes, not a pre-serialization object.
- Subject artifact paths and `ReviewSubjectReference.source_path` identities are normalized relative contract paths. The canonical absolute locator exists only inside the separately typed `ReviewExternalSourceFact`; it is never parsed as a subject/output path or written into an immutable 1.0 `source_path` field.
- Dossier decision subjects never include the mutable finalized dossier that summarizes those decisions.
- Top-level domain-neutral `review_subject_publisher.py` is established with structural RED before any producer delegates to it; placing it under `dossier` is forbidden because the package's eager exports would create writer import cycles. The exact ten mutable paths add source digest, function location, function signature, TestSpec, harness report, build-completion plan, execution/evidence current pointers, and their legacy-flat report/manifest paths; real pointers' immutable targets are additional read-only exact subjects.
- Publisher-local wrapper REDs prove the shared strict-deadline policy for marker create/delete, manifest replace, lock-free subject replace, temp cleanup/unlink, and guarded recovery rename/delete. One monotonic deadline is created per operation and is never reset; only transient Windows `PermissionError` retries. Non-Windows/non-transient failures and deadline expiry preserve the original exception/traceback. TestSpec replacement continues through its established wrapper rather than the publisher's lock-free replacement wrapper.
- Publication-lock REDs use injected clock/sleep to prove a competing active owner releases and the waiter acquires within the shared 10.0-second deadline, while exact timeout on held/released/malformed/reparse markers returns no-write `publication_recovery_blocked` with manual-recovery state and never reclaims the marker. Nested Windows sharing retries consume the same remaining deadline.
- Every concrete mutation seam preserves all existing positional call forms. Every producer API that accepts a propagated `ReviewCoreSourceBinding`—the three core writers plus the applicable harness, build-completion, execution, and evidence entry points—adds it only as an optional keyword-only parameter; independently invoked workspace entry points may derive it through the strict loader and still re-resolve it in the under-lock preflight. Each seam acquires the manifest-publication lock before any domain lock, publishes `dirty` before atomic subject replacement when a complete/dirty fence exists, and leaves review blocked until finalization. Source digest, function location, function signature, TestSpec, harness, build completion, legacy-flat execution, and legacy-flat evidence are all explicit outer-transaction cases; convenience replacement is limited to true single-output/pointer mutations. This covers eleven concrete producer call paths for the ten canonical mutations, including both independent `latest_run.json` updates. With no current manifest they still take the common lock, preventing a first-finalization race.
- All registered producer invocations create the common operation journal before any product write. REDs cover source digest, location, signature, TestSpec/exports, harness, build completion, both latest-run paths, legacy-flat execution, latest-evidence, and legacy-flat evidence with failures before/after every representative sidecar and canonical commit. Finalizer and recovery use the same journal in their own invocation scopes. A nested failure with net changes is promoted/enriched to a truthful committed publication error; an ordinary domain/cleanup failure follows the same rule. Exact final artifacts/deletions/rooted residue are identical whether the failure occurs before the handler's normal success return or during cleanup.
- Build-completion REDs exercise both `handle_complete_build` and the full dossier build phase with one parent operation spanning analyzer's initial plan/iteration/history JSON/Markdown, `apply_safe_completions` stub header, stub source, optional Makefile replace, and reporter's final rewrites. Fail immediately before and after each representative commit: only the dirty manifest and actually committed final files project as artifacts, uncommitted paths never do, the original exception remains primary, and even an authority-free direct call performs no journal-external write. Existing direct positional calls remain compatible while explicit parent operation parameters are keyword-only.
- The public harness wrapper opens one mutation/journal before `_generate_harness_skeleton` writes its first C/header and threads it through generator, dispatcher, state reflector, runner enhancer, shared C writer, and both report writes. A direct lower-level generator call opens its own operation only when no explicit parent was supplied. Failure at every generated-file/report boundary leaves a dirty fence when 1.1 authority existed and reports the rooted final projection; no generated sidecar can precede the fence under an old complete snapshot.
- Atomic-sidecar REDs inject failure while writing each same-directory temp, at replace, and during cleanup. Temp-write failure leaves the prior destination exact or reports only a `ReviewSubjectResiduePath` carrying its registered authority/presentation root, relative path, observed state/hash, and reason; replace is the sole overwrite commit point. Ordered journal events allow the same manifest/canonical path to change hashes repeatedly, while the public error/result projects only its verified final state. A create→cleanup or replace→exact-restore path is net-zero only when no rooted residue/superseded fact remains; an entirely empty projection retains domain code `publication_conflict`, while any attributable fact promotes the domain error to `publication_committed_failed` with exact committed/deleted/superseded/residue details. Slice 8 alone maps those domain facts to exit codes and CLI artifacts.
- The real analysis workflow constructs one explicit `ReviewCoreSourceBinding` and passes it to source-digest, function-location, and function-signature writers. They directly serialize strict-current 1.0 envelopes (not compatible-migrated 0.1 objects), retain relative subject/data paths, share `build_function_id(...)`, and carry the identical typed external fact in `extensions`; `test_spec.identity.stable_function_id(...)` delegates to that same algorithm. Present-but-invalid explicit/request binding fails before output. Existing direct calls with neither binding nor request keep byte-compatible raw 0.1 output inside the new transaction and remain display-only. REDs require the full analysis workflow and explicit-binding direct calls to strict-load all three current artifacts, while the pre-Task-6 direct-call/migration fixtures remain GREEN.
- That same optional binding is threaded through full-workflow harness, build-completion, dry-run/legacy-flat execution, and legacy-flat evidence producers. Before the first product write, every bound producer validates its own in-memory data/model `source_path`, `function_name`, and any present function/hash identity against `ReviewCoreSourceBinding`; a separately invoked workspace producer pre-resolves the strict core triple and repeats both the binding lookup and model-to-binding comparison in its under-lock no-write preflight before dirty. Any mismatch fails with no product write. An entirely absent/legacy binding selects the existing raw-0.1 compatibility output, while mixed/current-invalid binding fails without product writes. With a valid binding, each canonical JSON is a strict-current 1.0 envelope carrying relative subject identity and the same external extension. Harness/build/flat-execution/flat-evidence review or readiness subjects are decisionable only in that strict-current form; raw compatibility output remains display-only. Real immutable run/evidence paths keep their already-current contracts and use the same binding and model-to-binding validation for subject identity. REDs independently mismatch source path, function name/ID, and source hash for harness, build, flat execution/evidence, and real run/evidence publication and require the complete fence and every product byte to remain unchanged.
- Slice 1's `contracts.consumer` seam expands here to typed build/harness/execution/evidence consumer data plus `load_review_core_source_binding(workspace)`. A current envelope is strict-loaded for the expected kind and yields only its `data`; an explicitly allowed raw 0.1 input is compatible-validated and returned in its legacy consumer shape; a mismatched kind/version or a current-shaped invalid envelope fails closed and never silently falls back. `dossier/workflow.py`, direct `build_workspace_generator`, build-completion analyzer, execution/evidence loaders, `reanalysis/workflow.py`, and `reanalysis/snapshot_builder.py` use this one seam, so harness/build/test-design/reanalysis/execution accept both current workflow output and intentional legacy fixtures without ad-hoc `payload.get("data", payload)` logic.
- Analysis-only finalization binds the generic review fallback to all three exact strict-current core artifacts. Finalization accepts a legitimate canonical source outside the authority workspace only when all three artifacts cross-validate relative logical path/hash/function identity and the separate external fact. Relative/noncanonical external locators, logical/locator/hash disagreement, location/signature function mismatch, caller/recovery locator injection, and symlink/junction/reparse traversal fail closed. Any core changing marks dirty/stale; none may bypass the publication seam. With only legacy 0.1 cores, no eligible triple or later subject, no decisionable item is emitted and readiness/review completion are both false.
- TestSpec specifically uses the outer `subject_mutation` transaction, then its existing revision-checked lock and module-level replace wrapper. Deterministic two-writer tests prove publication→TestSpec lock order, current-revision reread, no deadlock/lost update, and unchanged PR #19 monkeypatch/deadline behavior.
- Failure injection separates pre-entry/no-write, dirty-entry-before-domain-replace, subject-committed-before-domain-cleanup, and publication-cleanup phases. Results/errors project the final dirty manifest and/or exact subject/sidecar artifacts only after real commit points, preserve the original TestSpec error/traceback, attach cleanup failures, and expose manual recovery without claiming no-write.
- Execution selection RED proves a valid contained `latest_run.json` plus immutable run report contributes both exact references; invalid/missing/mismatched pointer targets set run-dependent reasons/`test_green=false` (and dependent evidence false) without flat fallback or invalidating review discovery/finalization/decision write; pointer absence alone may select a strict-valid legacy/dry-run flat report; and a real run/import never creates or mutates the flat alias.
- Evidence selection RED proves a valid contained `latest_evidence.json` plus immutable evidence manifest contributes both exact readiness references, then normalizes every `required=true` entry across `source_files`, `generated_files`, `build_reports`, `test_reports`, and `logs` into unique declared/published-observation required-file facts. Every required exact-valid component is copied/indexed and revalidated; optional entries remain covered only by the immutable manifest subject. The resolver reports a separately keyed current observation. Stable missing/hash-mismatched/uncontained components or any stable published/current difference produce typed `evidence_ready=false` reasons without invalidating the other axes, while an in-attempt component mutation retries/conflicts. A present invalid pointer/target fails closed without flat fallback. A strict-valid historical pointer remains publishable/readable but yields `evidence_ready=false` plus `evidence_for_noncurrent_run` until its `source_run_id` equals the selected run. Legacy flat evidence is considered only with pointer-absent flat execution and must bind that exact report hash; its required components use the same checks. Matching failed and PASSED runs exercise evidence-ready independently from test-green.
- Real-run and legacy-import cleanup is pointer-commit-aware. Before pointer commit, an unpublished immutable run root may be removed and cleanup errors are attached/residue-reported. After `latest_run.json` commit is recorded, no exception or marker-cleanup failure may delete its referenced immutable run root; both execution call paths re-raise the publication error with target intact and exact committed-file/recovery facts.
- Evidence creation uses the same commit-aware cleanup: before latest-evidence pointer commit it may clean an unpublished evidence root; after pointer commit, every failure preserves the referenced immutable evidence target and re-raises exact publication state. Pointer/target races and post-commit cleanup failure are deterministic REDs.
- Pointer-specific operation-journal REDs inject cleanup failure after each pointer commit and require the domain error projection to contain at least the dirty DOSSIER_MANIFEST fact (when that commit occurred), the committed latest-run/latest-evidence pointer fact, and the exact immutable report/manifest target fact previously committed by the same command. Harness/build/legacy-flat REDs likewise retain every committed sidecar plus canonical subject/dirty manifest fact as applicable. Paths are deduplicated, and the original publication/domain traceback remains primary; Slice 8 owns CLI artifact conversion.
- Closed presence-map RED proves a complete design-only snapshot records absent optional paths; later unfenced harness creation or latest-run creation beside a legacy-flat snapshot invalidates the old complete fence. Restore removes every path that the previous complete map recorded absent, including flat→pointer→restore-flat, and reports those canonical removals only through `deleted_paths`.
- Detached-output RED finalizes with `--workspace X --out Y`, then resolves review state from X successfully, verifies the canonical manifest/fence/snapshots exist only under X, verifies Y contains presentation exports only, and confirms every fact carries the correct X-authority or Y-presentation root while every returned authority path names X. Unknown/overlapping/root-role-mismatched, containment, symlink/reparse, or ambiguous resolved roots fail before bytes change. A suite-entry failure likewise converts facts against the entry workspace root, not the suite root.
- Before complete manifest publication, finalization writes selected subjects, recovery-only trigger bytes, and every present required evidence component to the immutable content-addressed generation `reports/review_subject_snapshots/<snapshot_id>/...`; each path is exclusive-created or verified byte-identical if already present, invalid/absent component states remain explicit facts, and Task 6 never overwrites or deletes immutable snapshot bytes.
- Decision `subject_fingerprint` and full-state `snapshot_id` are tested independently: changing only a nonselected legacy flat file while a valid latest-run pointer/target stays fixed keeps the subject fingerprint/decision current but creates a distinct snapshot ID/directory and complete generation without an immutable-path collision.
- Snapshot-ID REDs assert the exact 1607-byte minimal and 2988-byte Unicode/full golden descriptors and literal hashes above. They permute every array, distinguish null from zero and each descriptor-version/top-level-field change, reject every duplicate identity/logical slot or missing cross-reference, and prove physical snapshot prefix/stored index/index hash never feeds the ID. The publisher recomputes the separate four-field subject fingerprint from selected binding references and rejects a fenced mismatch.
- With identical core artifact bytes, changing only the stable external-source observation (for example valid→missing, missing→hash-mismatch, or reparse→valid) changes the canonical descriptor, snapshot ID, directory, and generation while leaving the decision subject fingerprint unchanged. The immutable index preserves the exact published observation/core reasons, and the resolver returns fresh current observation reasons rather than reusing an older index reason.
- With identical pointer/manifest bytes and a **valid** declaration, changing only one stable required-evidence observation (including missing/hash-mismatch→declared-valid repair) leaves the old generation `evidence_ready=false`; re-finalization may reuse that exact immutable manifest/pointer without rewriting it, records the new published fact, and produces a distinct snapshot ID/directory/generation when the descriptor changes while leaving decision fingerprints unchanged. A declaration-invalid case stays false when only the component is repaired and becomes eligible only after a new valid manifest publication/selection and finalization.
- Deterministic no-self-reference RED recomputes the snapshot ID from the logical descriptor before any physical path exists, derives/stores the immutable index afterward, and proves changing only the stored ID/prefix/index hash is not an input cycle. Changing only a normalized semantic tuple/category while subject bytes stay equal changes review ID and snapshot ID without colliding with an existing snapshot directory. Decision references retain canonical current paths while the index alone maps them to exact immutable copies and reconstructs review items without reading mutable dossier summary bytes.
- DOSSIER_MANIFEST 1.1 publishes a monotonic `review_subject_snapshot` fence with `dirty|publishing|complete`, transaction/previous-complete identities, sorted exact immutable/current subject references, index hash, and aggregate fingerprint. Finalization publishes `publishing` only after the immutable index validates, then revalidates and publishes the same generation/token/fingerprint `complete`.
- Generation-table REDs fix every input branch: absence/strict 1.0→complete generation 1; dirty generation N→complete N+1; complete generation N with a changed full-state descriptor→complete N+1; and complete generation N with an identical descriptor→same generation/token/snapshot/fingerprint/canonical fence, with at most a summary-only manifest revision increment. The publishing and complete replaces each consume exactly one manifest revision.
- Deterministic races prove raw-writer vs finalizer and two concurrent finalizers serialize without lost generation; dirty/publishing discovery fails closed; and a stale summary writer conflicts instead of rolling a newer fence back or recreating A after A→B.
- A deterministic post-complete race lets another writer supersede the manifest before finalizer summary update. The failing finalizer returns domain code `publication_committed_failed` with its still-owned immutable/dossier facts and a structured superseded-manifest identity; it never claims the other writer's current manifest bytes as its own committed fact and never downgrades to an empty `publication_conflict`. Slice 8 proves the corresponding exit-3/artifact projection.
- Crash injection covers: lock acquired before dirty, dirty before subject replace, subject replace before finalization, publishing immediately after manifest replace, immutable/current revalidation, and complete before marker cleanup. Every point is either a prior complete snapshot with a blocking marker, or dirty/publishing with typed manual-recovery state—never falsely complete.
- Explicit recovery REDs cover exact marker owner/transaction/generation/manifest-SHA CAS, normal-path held/released blocking, offline recovery of an exact abandoned held marker after all-writers-stopped confirmation, malformed/symlink/reparse/token-mismatched refusal, complete-only when target bytes match, restore-only with a valid previous snapshot at a strictly newer generation, abandon-to-dirty only from strict dirty/publishing at a strictly newer generation, clear-complete-marker only for exact already-complete marker/fence identity, clear-uninitialized-marker only for verified absence or byte-identical strict-valid 1.0, zero product artifacts for both clear actions, first-publication restore refusal, and a second crash during restore/abandon followed by the same guarded procedure. COMPLETE/RESTORE preflight and final recheck cover the exact declared fact plus indexed published observation when the target/previous index has a non-null external C-source fact; a null-source snapshot succeeds without a locator argument/read only when its null plus typed core reasons and immutable/current facts match exactly. Those two actions also cover contained dynamic run/evidence targets and every required-evidence component state; changed/missing/path-policy-invalid facts reject before authority-changing mutation, and recovery never writes or deletes external facts. CLEAR-COMPLETE REDs instead drift each internal/external fact after commit and prove marker-only cleanup succeeds but the next ordinary resolution remains stale/invalid. ABANDON REDs drift the same facts after dirty/publishing and prove the new target-empty dirty fence allows later normal finalization without accepting the abandoned target. Every success returns repository-owned exact before/after transition identities. No timed-out marker is auto-reclaimed.
- Rewriting decision/readiness summaries without a subject-set change therefore preserves the fenced generation and canonical fence bytes, preventing both a decision-summary hash cycle and fence rollback.
- Missing, invalid, duplicated, cyclic, or identity-mismatched subjects fail closed.
- Finalization remains deterministic and prior Task 1–5 artifact contracts remain valid.

Focused command:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_review_subject_publication tests.test_dossier_review_workflow tests.test_dossier_contract_status tests.test_contract_validation tests.test_review_decisions -v
if ($LASTEXITCODE -ne 0) { throw '4B aggregate publisher/finalizer tests failed' }
py -m unittest tests.test_test_spec_repository tests.test_test_spec_formal_review_export_atomicity tests.test_test_spec_formal_review_writer_snapshots tests.test_harness_report_localization tests.test_build_diagnostics_and_completion tests.test_build_and_execution_module_boundaries tests.test_execution_run_history tests.test_prepare_evidence_non_destructive tests.test_execution_evidence tests.test_c_source_reading tests.test_function_analysis_reports tests.test_contract_migrations -v
if ($LASTEXITCODE -ne 0) { throw '4B aggregate producer regressions failed' }
py -m unittest tests.test_build_workspace_generation tests.test_dependency_policy_explicit_harness tests.test_reanalysis_snapshot_builder tests.test_test_spec_formal_review_provenance tests.test_test_spec_generation tests.test_test_spec_reanalysis -v
if ($LASTEXITCODE -ne 0) { throw '4B aggregate consumer/provenance regressions failed' }
```

Aggregate GREEN target: the nine reviewed and pushed sub-slices jointly provide one exact, non-cyclic current subject graph ready for Slice 5 resolution. This aggregate rerun creates no additional 4B commit.

### Slice 5 — Stable capture and atomic stale-aware repository

**Purpose:** Establish retry behavior and a real multi-file published snapshot before making `reports/review_decisions.json` the sole mutable authority.

#### Slice 5A — Fenced stable review-subject resolver

Structural RED/GREEN:

- Establish the snapshot-discovery portion of `review_assessment.py` without persistence or decision assessment.

Behavior RED groups:

1. Resolve a strict-valid DOSSIER_MANIFEST 1.1 `review_subject_snapshot` fence and every exact byte from its immutable content-addressed generation; verify the generation index, aggregate fingerprint, sorted full bindings, semantic normalization, and recomputed review IDs before returning. Reconstruct `ReviewItemSnapshot` only from that immutable index, never from a mutable function-dossier summary.
2. Verify each registered mutable subject path still equals its immutable exact copy. For a non-null external source, make two stable live observations and return the current typed observation against the fenced fact; for a null source, require nonempty typed core reasons and perform no locator read. Then re-read/strict-validate the manifest fence before returning.
3. Observe an active/recovery marker or `dirty`/`publishing` fence before, during, or after reads and require typed conflict/retry rather than a hybrid collection.
4. Mutate one or several mutable subjects through the real producer seams during sequential reads and require their pre-mutation generation bump to invalidate the attempt.
5. Publish fence B during the read and require the before/after canonical fence/generation/token check to retry or conflict.
6. Synchronize an update between any two immutable/current subject reads and prove no mixed A/B bundle is returned.
7. Reproduce ABA through two real writer publications: mutable subject bytes change A→B→A while reading, but monotonic generation prevents accepting that attempt; only a subsequent fully stable complete A generation may return.
8. Change a subject only after a returned stable snapshot; the captured old exact reference remains well formed but a later resolver call reports dirty/publishing or a new fingerprint rather than authorizing new bytes. Slice 6 proves the resulting assessment is stale.
9. Persistent marker/fence churn exhausts at exactly three started aggregate attempts or the one strict 2.0-second monotonic deadline and raises `ReviewSnapshotConflictError(code="current_snapshot_conflict")`; injected clock tests prove no unbounded retry. Direct discovery calls the private once resolver at most three times. A first-attempt deadline expiry ends on that same deadline, and the resolver itself never constructs a nested budget.
10. Reconstruct review items and all readiness facts solely from the immutable index/current-byte checks. Required evidence components are read before and after within the same attempt: a stable current observation different from its published fact—including a valid declaration's missing/hash-mismatched→declared-valid repair—returns `evidence_ready=false` and requires re-finalization, while a missing→present, valid→changed, or A→B transition between the two current reads retries/conflicts rather than returning a hybrid. REDs prove same-pointer/same-immutable-manifest re-finalization can publish the repaired observation without target rewrite, whereas an invalid declaration plus component-only repair remains false until a new valid manifest is published/selected.
11. Accept a legitimate canonical source outside the authority workspace only through the cross-validated three-core-artifact fact. Reject relative/noncanonical locators, path/hash/function disagreement, and caller/recovery locator injection. For a non-null fact, edit, remove, restore, or replace the bound C source before, between, and after the two live-source reads: in-attempt observation changes conflict/retry; every stable observation different from the indexed published observation—including missing/hash-mismatched→valid recovery—is stale and requires re-finalization; only an exact valid observation equality sets `source_current=true`. An edit after return cannot alter captured references and is stale on the next resolution/assessment. For a null fact, prove no source read occurs and the indexed core reasons drive fail-closed status.
12. Verified manifest absence and strict-valid 1.0 return first-attempt `review_snapshot_unavailable` with exact reason. Stable malformed/invalid fence, ten-path presence map, snapshot ID, immutable index, unfenced creation/deletion, overwritten/missing immutable bytes, wrong kind/role/path/hash/revision/source/function/semantic identity, symlink/reparse traversal, and duplicate subject identity return first-attempt `invalid_review_snapshot` with the exact closed reason/path/generation/snapshot/recovery details. None is retried or falls into a generic exception; table REDs distinguish every reason from transient A→B churn and from semantic external-source/evidence staleness.

Focused command:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_review_decisions tests.test_review_subject_publication tests.test_dossier_review_workflow -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 5A focused tests failed' }
```

GREEN target: a resolver returns only one stable published fenced subject bundle. No repository or ledger write exists yet.

Expected commit: `feat: resolve fenced review subject snapshots`

#### Slice 5B — Atomic revision-checked ledger and truthful cleanup failures

Structural RED/GREEN:

- Establish importable repository/result/error/recovery APIs before persistence behavior tests.

Behavior RED groups:

1. Verified absent ledger reports revision `0`; first write with expected revision `0` commits revision `1` and exact canonical bytes. A negative expected revision is invalid metadata and cannot enter persistence.
2. Expected ledger revision mismatch, including a nonzero expectation against verified absence: typed conflict with current revision `0`, no write.
3. Discovery fingerprint mismatch at the fenced snapshot: typed conflict, no write.
4. Unknown review ID: no write.
5. Sequential stale writers: first succeeds, second conflicts.
6. Concurrent writers from the same revision: exactly one succeeds; no lost update, truncated JSON, temp, or unexplained lock residue.
7. A subject writer marks dirty—or the external C source changes—after the stable fenced snapshot but before ledger replace: a committed decision remains bound only to captured old references/source hash. Dirty/fence movement conflicts; a source change during the resolver's two observations retries. Every stable observation change, including recovery from an indexed invalid observation to the declared valid bytes, makes assessment stale/not-ready and makes record return `SOURCE_NOT_CURRENT` with equal fingerprints plus both observations until re-finalization publishes a new snapshot ID/generation. Only a genuinely unequal expected/resolved four-field hash returns `SUBJECT_FINGERPRINT_MISMATCH`. Neither path authorizes or writes the new bytes.
8. Malformed JSON, schema/semantic/path-policy invalidity, directory/symlink/reparse ledger state, and permanent read denial raise exact `invalid_ledger` or `ledger_unreadable` `ReviewDecisionLedgerError` with `current_revision=None`; they propagate through load, assessment L1/L2, and record without retry, never masquerade as revision `0`, and never create a ledger temp.
9. Windows transient `PermissionError` during lock create/delete, replace, and temp cleanup retries within one strict monotonic deadline.
10. `FileExistsError` on an active ledger marker waits with injected clock/sleep under the one strict 10.0-second/0.01-second policy. Owner release permits acquisition; exact deadline on held/released/malformed/reparse state returns domain no-write `recovery_blocked` with manual-recovery metadata and never removes the marker. Nested Windows permission retries share the remaining deadline; Slice 8 alone maps that empty domain projection to CLI exit 1.
11. Pre-commit lock/create/read/temp/fsync/replace failures preserve the primary error/traceback and produce no ledger change or artifact. Transient cleanup succeeds without residue; a separately injected permanent cleanup failure reports its contained temp/lock residue without masking the primary error.
12. A lock-delete timeout after successful replace raises `ReviewDecisionPersistenceError(code="committed_cleanup_failed")` with `committed=true`, exact new revision/artifact/hash, and manual-recovery state; discovery observes both the committed decision and marker.
13. No Task 6 code path automatically reclaims or deletes a timed-out marker. Two waiting writers plus the original releaser never delete an active/new owner token and both writers remain blocked with recovery metadata.
14. A recovery test may simulate the documented operator procedure only after every writer/releaser thread has joined: verify contained regular path, marker token/state, exact committed revision/hash, remove the marker explicitly, then prove a new write can acquire normally. This is not an automatic product recovery API.
15. Held/malformed/symlink/reparse markers remain blocking. Non-Windows or non-transient errors are not retried or retyped.
16. Persistent subject publication churn while the ledger lock is held terminates within the one fixed resolver budget as `ReviewDecisionWriteStatus.CURRENT_SNAPSHOT_CONFLICT`, with the known ledger revision, lossless typed attempts/elapsed/last generation/state/publication-recovery details, and no ledger/temp write. Two S conflicts followed by a third conflict/mismatch start exactly three once-resolver calls, never nine; deadline and counter are not reset under the ledger lock.
17. Every stable unavailable/invalid snapshot reason from Slice 5A maps in record on the first resolver call to the matching `REVIEW_SNAPSHOT_UNAVAILABLE`/`INVALID_REVIEW_SNAPSHOT` result, known ledger revision, exact state details/recovery state, and zero temp/ledger/artifact mutation; no reason is retyped as churn, persistence failure, or internal error.

Focused commands:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_review_decisions tests.test_review_decision_integration -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 5B repository tests failed' }
py -m unittest tests.test_test_spec_repository tests.test_test_spec_formal_review_export_atomicity tests.test_test_spec_formal_review_writer_snapshots -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 5B TestSpec regressions failed' }
```

Additional deterministic stress uses the repository's test entry points and records iteration/residue counts; an ad-hoc script is not the only evidence.

GREEN target: the repository obtains the stable fenced snapshot itself, serializes ledger writers, never auto-reclaims a timed-out lock, and reports every pre/post-commit outcome according to the bytes that actually exist.

Expected commit: `feat: persist review decisions atomically`

### Slice 6 — Currency, stale/orphan assessment, and sole authority

**Purpose:** Separate persisted resolution from current semantic authority.

Behavior RED:

- Exact current approved/waived/changes-requested decisions are assessed distinctly.
- Byte/hash, revision, path, kind, missing/moved file, invalid JSON, schema-invalid content, source/function mismatch, and semantic-key changes are stale.
- Old decisions with no current ID are orphaned and retained for review/audit, not silently discarded.
- A changed semantic subject creates a new unreviewed item and leaves the prior decision orphaned.
- `done=true`, embedded status, or embedded approval never completes review.
- TestSpec, TypedCValue, and OracleSpec public schemas/models expose no approval/status/done/resolution authority field; injecting such a field is rejected by strict schema/model validation rather than merely ignored.
- Migrated `authority="display_only"` decisions are always stale, including when `revision: null` happens to equal a legitimate unrevisioned current subject; null revision alone is never the provenance discriminator.
- Assessment is deterministic and has no writes.
- Public assessment accepts only a workspace—never caller-supplied decisions, current items, or artifacts—and calls the identical fenced resolver used by writes. Only the private pure helper accepts an injected decision set for unit tests.
- Production assessment double-collects ledger L1 → stable subject snapshot S → ledger L2 and accepts only two verified-absent reads or two strict existing snapshots with byte/hash/revision identity. The returned `ReviewAssessment` retains that exact S; deterministic tests assert its function/source identity, generation, aggregate fingerprint, current items/exact references, and all three subject-derived axes share S while the fourth axis uses the accepted L1/L2 ledger. Absent→created, created→absent, ledger commit, fence-change, inter-file, dirty/publishing, and A→B→A races return bounded `current_snapshot_conflict` or one state that was simultaneously coherent at S, never an impossible hybrid completion or a second-discovery mix.
- Persistent ledger/subject churn exhausts at three aggregate L1→S-once→L2 attempts or the shared 2.0-second deadline with typed conflict and no write. REDs force two S conflicts then an L1/L2 mismatch, three L1/L2 mismatches, and deadline expiry inside attempt one; every case reports the aggregate started count, calls the once resolver at most three times rather than nine, and never resets the deadline. A trap/mock on the public discovery wrapper proves assessment and record do not call it. Invalid/unreadable ledger at either ledger read propagates its typed error with unknown revision immediately, not a retryable conflict or empty decision set.
- A stable `ReviewSnapshotStateError` from S also propagates from assessment on that first aggregate attempt with its exact state details and accepted L1 read discarded; it is never assessed against decisions, retried, or converted to an all-false apparently successful assessment.
- `open`, missing, `changes_requested`, stale, and display-only decisions keep the affected current item incomplete; only exact `authority="current"` `approved` or `waived` completes that item, and an aggregate is complete only when every required current item is complete.
- Zero decisionable current items yields `review_complete=false` and no Phase 2 authority; the aggregate requires at least one nonempty-bound item before applying the all-current-approved/waived rule.

Focused command:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_review_decision_staleness tests.test_dossier_review_authority tests.test_review_decisions -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 6 focused tests failed' }
```

GREEN target: only current decisions in the external ledger can authorize review state.

Expected commit: `feat: assess current and orphaned review decisions`

### Slice 7 — Four independent semantic readiness axes

**Purpose:** Replace existence-driven readiness with explicit semantic axes.

Behavior RED:

- Table every `RunOutcome` value; only `PASSED` sets `test_green=true`.
- Reviewable failed/blocked/inconclusive/cancelled/timed-out/error evidence can make evidence reviewable but never GREEN.
- `ready_for_review`, `review_complete`, `evidence_ready`, and `test_green` vary independently in table-driven cases.
- The public workspace-only `assess_review_completion(...)` returns all four booleans, per-axis reasons, and its exact retained `ReviewSnapshot` in one `ReviewAssessment`; `get-review-status` projects its contract fields only from that object plus normalized request path context. `ReviewSnapshot.readiness` already contains the three subject-derived axes, run/evidence selector facts, and indexed/current required-file observations from the same stable generation/attempt, so neither assessment nor CLI reopens mutable workspace artifacts through the legacy existence-driven helper.
- A present invalid latest-run pointer/target yields `test_green=false` and typed dependent-evidence reasons with no flat fallback, while table cases prove valid review subjects/decisions still determine `ready_for_review` and `review_complete` and record remains available.
- A strict-valid, contained `latest_evidence.json` and immutable target are bound as exact readiness references. Historical evidence whose internally bound `source_run_id` differs from the separately selected latest run remains valid/current evidence state but yields only `evidence_ready=false` with `evidence_for_noncurrent_run`; it does not block subject publication, finalization, decision recording, or evaluation of the other three axes.
- A present malformed, uncontained, hash/identity-mismatched, or missing-target evidence pointer fails the evidence axis closed and never falls back to a flat manifest. Legacy flat evidence is eligible only when both evidence and run pointers are absent and it binds the exact strict-valid flat execution report. Pointer/target races are detected against the same publication snapshot.
- For both pointer-owned and legacy-flat evidence, every manifest entry marked required across all five file arrays must have a valid declaration plus an exact-equal indexed/current observation that is contained, regular, non-reparse, present, and exact-hash-valid for `evidence_ready=true`. Stable invalid or changed observations return typed reasons and remain false until re-finalization. REDs separate invalid declaration (component-only repair and same manifest remain false; a new valid publication can become true) from valid declaration with an initially invalid observation (repair to declared bytes, same immutable pointer/manifest SHA, re-finalize, new descriptor/generation, true, with immutable target unchanged). Deterministic log/report tampering or repair before resolution, during the two reads, and after a returned snapshot proves false/retry-or-conflict/stale behavior respectively without changing independent axes.
- Existence/mtime-only changes do not advance axes.
- Missing optional artifacts affect only declared dependent axes.
- Missing required artifacts fail the relevant axes. Table-driven REDs independently remove/invalidate each of source digest, function location, and function signature and require `ready_for_review=false` from the immutable snapshot even when TestSpec exists; all three strict-current cores plus valid items are required for true.
- Compatible-migrated/display-only artifacts cannot complete review.
- Embedded `done` and status have no effect.
- Exercise every row of the fixed truth table above, including `changes_requested=false`, current `approved=true`, current `waived=true` for review completion, and waiver never granting Phase 2 generation authority.

Focused command:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_dossier_readiness tests.test_dossier_review_authority tests.test_execution_evidence tests.test_evidence_integrity tests.test_execution_run_history -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 7 focused tests failed' }
```

If new run/evidence modules are added before this slice, enumerate them with `Get-ChildItem tests -Filter 'test_*.py'` and append every directly related module; do not omit the coverage.

GREEN target: the four axes are independently derived from validated semantic inputs.

Expected commit: `feat: derive semantic dossier readiness`

### Slice 8 — Validated CLI discovery, guarded decision write, and explicit offline recovery

**Purpose:** Expose one validated snapshot for discovery and write through CLI envelope 1.0.0.

Behavior RED:

- Discovery returns validated current items, exact subject guards, ledger revision, aggregate fingerprints, orphan/stale assessment, and all four axes.
- Dirty/publishing/marker/churn discovery returns nonzero `current_snapshot_conflict`, no artifact, and truthful serialized `publication_recovery_state`; it never performs recovery mutation.
- Stable absent/legacy-unfinalized publication returns `review_snapshot_unavailable`, while each stable malformed fence/presence/snapshot/index/path/identity/immutable/mutable mismatch returns `invalid_review_snapshot` on the first attempt. `get-review-status` and `record-review-decision` both return exit 1, exact typed state details/recovery state, empty artifacts, and no write; record also preserves the known ledger revision. None becomes churn, persistence failure, an all-false success, or exit 10.
- `record-review-decision` accepts only review ID, resolution metadata, expected ledger revision, and discovered aggregate fingerprint.
- Success returns exactly one `ProducedArtifact` for final saved `reports/review_decisions.json` bytes.
- Unknown ID, stale revision, actual expected/resolved fingerprint mismatch, source-not-current, invalid waiver/terminal metadata, containment failure, typed ledger error, and every **pre-commit** I/O failure return nonzero, no write, and no artifact. Invalid decision metadata serializes `data.details.write_status="invalid_decision_metadata"`. A stable source mismatch with equal fingerprints serializes exit 1 and `write_status="source_not_current"` plus known revision and exact conflict details; only unequal four-field fingerprints serialize `subject_fingerprint_mismatch`.
- Discovery and write expose `ledger_revision=0` only for verified absence. Malformed JSON, schema/semantic invalidity, directory/symlink/reparse state, and permanent read denial produce exact `invalid_ledger`/`ledger_unreadable` exit-1 envelopes with `errors[0].code` and `write_status` equal, `ledger_revision=null`/`current_revision=null`, unchanged ledger/temp bytes, empty artifacts, and recovery state. L1 or L2 failure is never treated as an empty ledger, retryable snapshot churn, or exit 10.
- Resolver exhaustion in `record-review-decision` serializes `data.details.write_status="current_snapshot_conflict"`, the known ledger revision when available, exact typed aggregate attempts/elapsed/last generation/state plus `publication_recovery_state` from `snapshot_conflict_details`, no ledger/temp mutation, and no artifact. It never reduces those fields to `message` text or reconstructs them with another discovery.
- A post-commit lock-cleanup timeout returns nonzero `RunOutcome.ERROR` with `errors[0].code` and `data.details.write_status` equal to `committed_cleanup_failed`, `committed=true`, the committed revision, exactly one truthful `ProducedArtifact`, and serialized manual-recovery state; a subsequent discovery exposes the committed decision and recovery marker without mutating it.
- Parser/help RED proves `recover-review-subject-publication` requires workspace, nonblank marker-owner/transaction tokens, a closed five-action value, and `--confirm-all-writers-stopped`; nonnegative expected generation is required for the four 1.1 actions, while clear-uninitialized requires exactly `absent` or an exact 1.0 manifest SHA and no fabricated generation. No normal command or workflow dispatches it automatically.
- Guard RED proves held/malformed/missing/wrong-kind/symlink/reparse/token-or-generation-mismatched marker, changed fence CAS, invalid target/previous immutable snapshot, source/dynamic-target/required-component mismatch for COMPLETE/RESTORE, COMPLETE byte mismatch, and RESTORE with no previous snapshot all return nonzero before product-byte mutation, empty artifacts, and truthful `publication_recovery_state`. A closed table invokes every one of the five actions against absent, strict 1.0, dirty, publishing, and complete and proves that only the eight admitted action-state cells above can remove a stale marker or write; all other cells, especially RESTORE-from-complete, are no-write/no-marker-change errors.
- COMPLETE success changes only the final DOSSIER_MANIFEST bytes and returns exactly that real artifact. RESTORE success returns the final DOSSIER_MANIFEST and each present canonical file actually restored, plus exact `deleted_paths` for canonical paths restored to absence; unchanged paths are not invented as artifacts. ABANDON changes only DOSSIER_MANIFEST to the next target-empty dirty fence and returns that artifact without restoring/deleting subjects or immutable targets. CLEAR-COMPLETE-MARKER and CLEAR-UNINITIALIZED-MARKER change no product bytes and return zero produced artifacts. All five successes expose the exact repository-owned `recovery_transition`; before/after identities remain equal for clear actions and carry the exact committed difference for the other actions.
- Recovery failure injection at every post-commit point is truthful: after the dirty/publishing manifest or any subject replace, it returns `RunOutcome.ERROR`, `recovery_required=true`, every exact final-byte artifact actually committed so far, the new dirty/publishing recovery state, and repository-owned `recovery_transition` with accepted before and latest committed after identities. A clear-action cleanup failure carries equal before/after identities after its marker-only linearization. Pre-linearization failures carry null transition. The CLI never re-reads to synthesize one and never reports a partial restore/abandon as no-write or complete.
- Invoke representative TestSpec, harness/build, latest-run, legacy-flat, finalizer, and recovery commands through the real CLI dispatch boundary. Inject each `ReviewSubjectPublicationError` code and assert exit 1/3, outcome/error code/write status, exact committed artifacts, and publication recovery fields; none may fall through to exit 10/internal_error.
- Suite execution re-raises `ReviewSubjectPublicationError` before its generic per-entry exception capture, stops scheduling/processing later entries, and lets the same top-level CLI boundary serialize exact exit 1/3 state. A post-pointer-commit injected failure preserves the immutable target and is never reduced to a string-only suite-entry error.
- Reanalysis, update-TestSpec, suite-run, and prepare-evidence handlers also place an explicit `except ReviewSubjectPublicationError: raise` before any broad OSError/Exception-to-CLIError adapter. Real-path REDs prove the error reaches `cli/main.py` unchanged from each handler.
- Latest-run and latest-evidence post-pointer cleanup REDs assert the top-level error artifact set includes the dirty manifest when written, the committed pointer, and the same-command immutable target (plus any other journaled domain commits), even though the success return path was never reached. Pre-pointer cleanup that actually removed an unpublished target does not fabricate that artifact.
- Supersession REDs replace an operation's last committed path with missing, a different regular file, directory, symlink, reparse point, and unreadable state. Each exact `ReviewSubjectSupersededPath` preserves root/path/last-owned hash/observed state/current hash/reason, never becomes that operation's `ProducedArtifact`, and forces truthful committed exit 3 rather than an empty conflict.
- Parser/help and JSON/non-JSON error behavior remain compatible with CLI envelope 1.0.0.
- Fingerprint flag REDs accept either canonical flag or compatibility alias, accept both only when normalized values are identical, and reject differing dual values before discovery/write.
- Discovery and write use the same resolver/assessment seam; commands cannot bypass repository re-resolution.

Focused command:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_review_decision_cli tests.test_review_subject_publication tests.test_cli_result_contract tests.test_cli_entry_point_contract tests.test_review_decision_integration tests.test_suite_manager tests.test_suite_cli -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 8 focused tests failed' }
```

GREEN target: CLI is a thin adapter over the validated domain services and reports exact committed bytes.

Expected commit: `feat: expose guarded review decision cli`

### Slice 9 — Cross-slice integration and full gates

**Purpose:** Prove the current tree, package, and runtime rather than relying on recovered carrier totals.

Focused Task 6 set:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest `
  tests.test_build_probe `
  tests.test_contract_registry `
  tests.test_contract_validation `
  tests.test_contract_migrations `
  tests.test_wheel_contract `
  tests.test_dossier_review_workflow `
  tests.test_review_decisions `
  tests.test_review_decision_staleness `
  tests.test_dossier_readiness `
  tests.test_dossier_review_authority `
  tests.test_review_decision_integration `
  tests.test_review_decision_cli `
  tests.test_review_subject_publication -v
if ($LASTEXITCODE -ne 0) { throw 'Slice 9 focused Task 6 set failed' }
```

Related regressions:

- All Task 1–5 contract, dossier, TestSpec, execution, evidence, CLI result, atomicity, and writer-snapshot modules.
- Every existing PR #19 Windows retry regression.
- Source-digest, function-location, function-signature, harness, build-completion, TestSpec, run/evidence pointer writers, and legacy-flat execution/evidence regressions proving all ten mutation paths delegate to the publication seam without changing public signatures, immutable layouts, or non-review sidecars.
- Source integrity: tracked `src/unit_test_runner/build/dependency_rewriter.py`, not ignored, `py -m compileall -q src tests`, and `tests.test_repository_source_tracking`.
- Fixture: `tests.test_fixture_cli_smoke` and `tests.test_vc6_fixture_build_e2e`; record the selected local compiler or the exact documented local-only skip.
- VS Code: clean dependency install, compile, unit tests, and Extension Host activation smoke even though extension source is not expected to change.
- `py -m unit_test_runner --help` and command-specific help.
- A real CLI discovery/write smoke in a copied temporary fixture; never modify repository fixtures in place.
- Wheel build, metadata inspection, normal fresh-venv install, import, registry enumeration, and schema validation.
- Every schema or migration change requires both `tests.test_contract_migrations` from the source tree and the exact three-kind installed-wheel migration matrix from a sanitized repository-external working directory under `python -I`; neither source-tree tests nor packaged-schema enumeration alone can satisfy this gate.
- Candidate whitespace gate over committed Task 6 bytes, never an argument-free clean-worktree check:

```powershell
$slice9Base = (git merge-base origin/main HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $slice9Base -notmatch '^[0-9a-f]{40}$') {
  throw 'cannot determine Slice 9 reviewed base'
}
$slice9Head = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $slice9Head -notmatch '^[0-9a-f]{40}$') {
  throw 'cannot determine Slice 9 candidate head'
}
git diff --check "$slice9Base...$slice9Head"
if ($LASTEXITCODE -ne 0) { throw 'Slice 9 base-to-head diff check failed' }
```

Concrete non-Python aggregate gates:

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
git ls-files --error-unmatch src/unit_test_runner/build/dependency_rewriter.py
if ($LASTEXITCODE -ne 0) { throw 'dependency_rewriter.py is not tracked' }

git check-ignore --no-index -q src/unit_test_runner/build/dependency_rewriter.py
$checkIgnoreExit = $LASTEXITCODE
if ($checkIgnoreExit -eq 0) { throw 'Python build package source is ignored' }
if ($checkIgnoreExit -ne 1) { throw "git check-ignore failed: $checkIgnoreExit" }

py -m compileall -q src tests
if ($LASTEXITCODE -ne 0) { throw 'compileall failed' }
py -m unittest tests.test_repository_source_tracking -v
if ($LASTEXITCODE -ne 0) { throw 'source tracking test failed' }
py -m unittest tests.test_fixture_cli_smoke tests.test_vc6_fixture_build_e2e -v
if ($LASTEXITCODE -ne 0) { throw 'fixture smoke failed' }

try {
  Push-Location .\vscode\extension -ErrorAction Stop
  npm.cmd ci
  if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
  npm.cmd run compile
  if ($LASTEXITCODE -ne 0) { throw 'VS Code compile failed' }
  npm.cmd test
  if ($LASTEXITCODE -ne 0) { throw 'VS Code unit tests failed' }
  npm.cmd run test:extension-host
  if ($LASTEXITCODE -ne 0) { throw 'Extension Host smoke failed' }
}
finally {
  Pop-Location
}
```

Record every command's exit code in the durable gate evidence.

Real CLI discovery/write gate (run from a clean candidate HEAD; all source input is a copied temporary fixture):

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Task6Smoke {
  param($Condition, [string]$Message)
  if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Get-Task6TreeHashes {
  param([Parameter(Mandatory)][string]$Root)
  $rootPath = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\')
  @(
    Get-ChildItem -LiteralPath $rootPath -Recurse -File |
      Sort-Object FullName |
      ForEach-Object {
        $relative = $_.FullName.Substring($rootPath.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$relative=$hash"
      }
  )
}

function Invoke-Task6Help {
  param([string]$Command, [string[]]$Needles)
  $lines = @(& $script:Task6Python -m unit_test_runner $Command --help 2>&1)
  $exitCode = $LASTEXITCODE
  $text = $lines -join [Environment]::NewLine
  Assert-Task6Smoke ($exitCode -eq 0) "$Command --help exited $exitCode`n$text"
  $script:Task6ExitEvidence.Add([pscustomobject]@{
    label="$Command-help"; process_exit=$exitCode; envelope_exit=$null
  }) | Out-Null
  foreach ($needle in $Needles) {
    Assert-Task6Smoke ($text.Contains($needle)) "$Command --help omitted $needle"
  }
}

function Invoke-Task6Json {
  param([string]$Label, [string[]]$Arguments, [int]$ExpectedExit = 0)
  $script:Task6InvocationCounter++
  $stderrPath = Join-Path $script:Task6LogRoot ('{0:D2}-{1}.stderr.txt' -f $script:Task6InvocationCounter, $Label)
  $stdoutLines = @(& $script:Task6Python -m unit_test_runner --json @Arguments 2> $stderrPath)
  $processExit = $LASTEXITCODE
  $stdoutText = $stdoutLines -join [Environment]::NewLine
  $stderrText = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { '' }
  Assert-Task6Smoke ($processExit -eq $ExpectedExit) "$Label process exit=$processExit expected=$ExpectedExit`nSTDOUT:`n$stdoutText`nSTDERR:`n$stderrText"
  try { $payload = $stdoutText | ConvertFrom-Json }
  catch { throw "$Label did not emit one valid JSON document.`n$stdoutText" }
  Assert-Task6Smoke (([string]$payload.artifact_kind) -ceq 'cli_result') "$Label artifact_kind is not cli_result"
  Assert-Task6Smoke (([string]$payload.schema_version) -ceq '1.0.0') "$Label schema_version is not 1.0.0"
  $envelopeExit = [int]$payload.data.exit_code
  Assert-Task6Smoke ($envelopeExit -eq $processExit) "$Label process/envelope exit mismatch"
  $script:Task6ExitEvidence.Add([pscustomobject]@{
    label=$Label; process_exit=$processExit; envelope_exit=$envelopeExit
  }) | Out-Null
  Assert-Task6Smoke (([string]$payload.data.command) -ceq $Arguments[0]) "$Label command mismatch"
  Assert-Task6Smoke (([string]$payload.producer.commit) -ceq $script:Task6CandidateHead) "$Label producer commit differs from candidate HEAD"
  if ($ExpectedExit -eq 0) {
    Assert-Task6Smoke (([string]$payload.data.outcome) -ceq 'passed') "$Label successful process did not report passed"
  }
  [pscustomobject]@{ ExitCode=$processExit; Payload=$payload; Stdout=$stdoutText; Stderr=$stderrText }
}

$task6Repo = (Resolve-Path -LiteralPath .).Path
$task6FixtureTemplate = Join-Path $task6Repo 'tests\fixtures\vc6_project'
$task6TempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$task6TempRoot = Join-Path $task6TempBase ('unitTestRunner-task6-smoke-' + [guid]::NewGuid().ToString('N'))
$task6FunctionWorkspace = Join-Path $task6TempRoot 'Control_Update'
$task6LogRoot = Join-Path $task6TempRoot 'cli-logs'
$script:Task6Python = (Get-Command py -ErrorAction Stop).Source
$script:Task6LogRoot = $task6LogRoot
$script:Task6InvocationCounter = 0
$script:Task6ExitEvidence = [System.Collections.Generic.List[object]]::new()
$task6HadPythonPath = Test-Path Env:PYTHONPATH
$task6OldPythonPath = $env:PYTHONPATH
$task6HadProducerCommit = Test-Path Env:UNIT_TEST_RUNNER_PRODUCER_COMMIT
$task6OldProducerCommit = $env:UNIT_TEST_RUNNER_PRODUCER_COMMIT
$task6Summary = $null

try {
  $headLines = @(& git rev-parse HEAD)
  Assert-Task6Smoke ($LASTEXITCODE -eq 0) 'git rev-parse HEAD failed'
  $script:Task6CandidateHead = ($headLines -join '').Trim()
  Assert-Task6Smoke ($script:Task6CandidateHead -cmatch '^[0-9a-f]{40}$') 'candidate HEAD is not a full lowercase Git SHA'
  $beforeStatus = @(& git status --porcelain=v1 --untracked-files=all)
  Assert-Task6Smoke ($LASTEXITCODE -eq 0) 'initial git status failed'
  Assert-Task6Smoke ($beforeStatus.Count -eq 0) "Task 6 CLI smoke requires a clean candidate worktree:`n$($beforeStatus -join "`n")"

  $env:PYTHONPATH = Join-Path $task6Repo 'src'
  $task6CliSourcePrefix = $env:PYTHONPATH.TrimEnd('\') + '\'
  $task6CliImportedPath = ((& $script:Task6Python -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
  Assert-Task6Smoke ($LASTEXITCODE -eq 0 -and $task6CliImportedPath.StartsWith($task6CliSourcePrefix,[StringComparison]::OrdinalIgnoreCase)) "CLI smoke imported wrong tree: $task6CliImportedPath"
  $env:UNIT_TEST_RUNNER_PRODUCER_COMMIT = $script:Task6CandidateHead
  New-Item -ItemType Directory -Path $task6TempRoot | Out-Null
  New-Item -ItemType Directory -Path $task6LogRoot | Out-Null
  Copy-Item -LiteralPath $task6FixtureTemplate -Destination $task6TempRoot -Recurse
  $sourceFixture = Join-Path $task6TempRoot 'vc6_project'
  $sourceBefore = @(Get-Task6TreeHashes -Root $sourceFixture)

  Invoke-Task6Help 'get-review-status' @('get-review-status','--workspace')
  Invoke-Task6Help 'record-review-decision' @('record-review-decision','--workspace','--review-id','--resolution','--reviewer','--rationale','--decided-at','--expected-revision','--expected-subject-fingerprint','--expected-subject-sha256')
  Invoke-Task6Help 'recover-review-subject-publication' @('recover-review-subject-publication','--workspace','--expected-generation','--expected-uninitialized-manifest-sha256','--expected-marker-owner-token','--expected-transaction-token','--action','abandon-to-dirty','--confirm-all-writers-stopped')

  $null = Invoke-Task6Json 'analyze' @(
    'analyze-function','--workspace',$sourceFixture,'--dsw',(Join-Path $sourceFixture 'Product.dsw'),
    '--source','src/control.c','--function','Control_Update','--configuration','Win32 Debug',
    '--project','Control','--phase','design','--out',$task6FunctionWorkspace
  )
  $null = Invoke-Task6Json 'finalize' @('finalize-dossier','--workspace',$task6FunctionWorkspace,'--function','Control_Update')
  $manifest = Join-Path $task6FunctionWorkspace 'reports\dossier_manifest.json'
  Assert-Task6Smoke (Test-Path -LiteralPath $manifest -PathType Leaf) 'finalize-dossier did not publish dossier_manifest.json'

  $initialStatus = (Invoke-Task6Json 'status-before' @('get-review-status','--workspace',$task6FunctionWorkspace)).Payload
  Assert-Task6Smoke (@($initialStatus.data.artifacts).Count -eq 0) 'get-review-status must return no artifacts'
  $initialDetails = $initialStatus.data.details
  Assert-Task6Smoke (([int]$initialDetails.ledger_revision) -eq 0) 'fresh copied fixture did not expose verified-absent ledger revision 0'
  Assert-Task6Smoke ($initialDetails.ready_for_review -eq $true) 'fresh finalized design fixture is not ready_for_review'
  $items = @($initialDetails.items)
  Assert-Task6Smoke ($items.Count -gt 0) 'no decisionable current review item was discovered'
  $item = @($items | Sort-Object -Property review_id)[0]
  $reviewId = [string]$item.review_id
  $fingerprint = [string]$item.subject_fingerprint
  Assert-Task6Smoke (-not [string]::IsNullOrWhiteSpace($reviewId)) 'discovered review_id is blank'
  Assert-Task6Smoke ($fingerprint -cmatch '^[0-9a-f]{64}$') 'discovered subject_fingerprint is not lowercase SHA-256'
  Assert-Task6Smoke (@($item.subject_artifacts).Count -gt 0) 'decisionable item has no exact subject artifacts'

  $write = (Invoke-Task6Json 'record' @(
    'record-review-decision','--workspace',$task6FunctionWorkspace,'--review-id',$reviewId,
    '--resolution','approved','--reviewer','task6-final-gate',
    '--rationale','Exact subject artifacts reviewed by the Task 6 final CLI gate.',
    '--decided-at','2026-07-15T12:00:00+09:00','--expected-revision','0',
    '--expected-subject-fingerprint',$fingerprint
  )).Payload
  $writeDetails = $write.data.details
  Assert-Task6Smoke (([string]$writeDetails.write_status) -ceq 'written') 'decision write_status is not written'
  Assert-Task6Smoke (([int]$writeDetails.ledger_revision) -eq 1) 'first decision did not commit ledger revision 1'
  Assert-Task6Smoke (([string]$writeDetails.review_id) -ceq $reviewId) 'write result review_id differs from guard'
  Assert-Task6Smoke (([string]$writeDetails.subject_fingerprint) -ceq $fingerprint) 'write result fingerprint differs from guard'
  $artifacts = @($write.data.artifacts)
  Assert-Task6Smoke ($artifacts.Count -eq 1) 'successful decision write must return exactly one artifact'
  $artifact = $artifacts[0]
  Assert-Task6Smoke (([string]$artifact.artifact_kind) -ceq 'review_decisions') 'write artifact kind is not review_decisions'
  Assert-Task6Smoke (([string]$artifact.path) -ceq 'reports/review_decisions.json') 'write artifact path is not canonical'
  Assert-Task6Smoke ($artifact.exists -eq $true) 'write artifact does not report exists=true'
  Assert-Task6Smoke (([string]$artifact.schema_version) -ceq '1.1.0') 'write artifact schema version is not 1.1.0'
  Assert-Task6Smoke (([string]$artifact.sha256) -cmatch '^[0-9a-f]{64}$') 'write artifact hash is malformed'
  $ledger = Join-Path $task6FunctionWorkspace 'reports\review_decisions.json'
  Assert-Task6Smoke (Test-Path -LiteralPath $ledger -PathType Leaf) 'reported decision ledger is missing'
  $actualLedgerHash = (Get-FileHash -LiteralPath $ledger -Algorithm SHA256).Hash.ToLowerInvariant()
  Assert-Task6Smoke ($actualLedgerHash -ceq ([string]$artifact.sha256).ToLowerInvariant()) 'artifact hash differs from final ledger bytes'

  $latestStatus = (Invoke-Task6Json 'status-after' @('get-review-status','--workspace',$task6FunctionWorkspace)).Payload
  Assert-Task6Smoke (@($latestStatus.data.artifacts).Count -eq 0) 'second status unexpectedly returned artifacts'
  $latestDetails = $latestStatus.data.details
  Assert-Task6Smoke (([int]$latestDetails.ledger_revision) -eq 1) 'rediscovery did not observe ledger revision 1'
  $latestMatches = @($latestDetails.items | Where-Object { ([string]$_.review_id) -ceq $reviewId })
  Assert-Task6Smoke ($latestMatches.Count -eq 1) 'rediscovery did not return exactly one selected item'
  $latestItem = $latestMatches[0]
  Assert-Task6Smoke (([string]$latestItem.status) -ceq 'approved') 'rediscovery did not assess approved status'
  Assert-Task6Smoke (([string]$latestItem.resolution) -ceq 'approved') 'rediscovery lost approved resolution'
  Assert-Task6Smoke (([string]$latestItem.subject_fingerprint) -ceq $fingerprint) 'rediscovery changed the subject guard'
  Assert-Task6Smoke (@($latestItem.reasons).Count -eq 0) 'newly approved exact-current item remains blocked'
  Assert-Task6Smoke (((Get-FileHash -LiteralPath $ledger -Algorithm SHA256).Hash.ToLowerInvariant()) -ceq $actualLedgerHash) 'read-only rediscovery changed ledger bytes'
  Assert-Task6Smoke ((@(Get-Task6TreeHashes -Root $sourceFixture) -join "`n") -ceq ($sourceBefore -join "`n")) 'analysis/finalization mutated copied source input'
  Assert-Task6Smoke (((@(& git rev-parse HEAD)) -join '').Trim() -ceq $script:Task6CandidateHead) 'candidate HEAD changed during smoke'
  $afterStatus = @(& git status --porcelain=v1 --untracked-files=all)
  Assert-Task6Smoke ($LASTEXITCODE -eq 0) 'final git status failed'
  Assert-Task6Smoke (($afterStatus -join "`n") -ceq ($beforeStatus -join "`n")) 'CLI smoke changed the product worktree'
  $task6Summary = [ordered]@{
    candidate_head=$script:Task6CandidateHead; review_id=$reviewId; subject_fingerprint=$fingerprint
    ledger_revision_before=0; ledger_revision_after=1; decision_status_after=[string]$latestItem.status
    artifact_path=[string]$artifact.path; artifact_sha256=$actualLedgerHash
    source_fixture_files=$sourceBefore.Count; worktree_unchanged=$true
    command_exits=@($script:Task6ExitEvidence)
  }
}
finally {
  try {
    if (Test-Path -LiteralPath $task6TempRoot) {
      $resolvedTemp = (Resolve-Path -LiteralPath $task6TempRoot).Path
      $safePrefix = $task6TempBase + '\unitTestRunner-task6-smoke-'
      Assert-Task6Smoke ($resolvedTemp.StartsWith($safePrefix,[StringComparison]::OrdinalIgnoreCase)) "refusing unsafe cleanup path: $resolvedTemp"
      $cleanupItem = Get-Item -LiteralPath $resolvedTemp -Force
      Assert-Task6Smoke (($cleanupItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "refusing reparse cleanup path: $resolvedTemp"
      Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
  }
  finally {
    if ($task6HadPythonPath) { $env:PYTHONPATH = $task6OldPythonPath } else { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
    if ($task6HadProducerCommit) { $env:UNIT_TEST_RUNNER_PRODUCER_COMMIT = $task6OldProducerCommit } else { Remove-Item Env:UNIT_TEST_RUNNER_PRODUCER_COMMIT -ErrorAction SilentlyContinue }
  }
}
Assert-Task6Smoke (-not (Test-Path -LiteralPath $task6TempRoot)) 'temporary CLI fixture was not cleaned'
$task6Summary['temporary_fixture_cleaned'] = $true
$task6Summary | ConvertTo-Json -Depth 5
```

The authoritative CLI evidence records the candidate SHA, every process/envelope exit, selected review ID/fingerprint, revisions 0→1, exact final ledger hash, re-read assessment, copied-source hash set, unchanged Git status, and cleanup result.

Wheel/METADATA/normal fresh-install gate. First run `py -m unittest tests.test_wheel_contract tests.test_contract_registry tests.test_public_artifact_schemas tests.test_contract_validation tests.test_contract_migrations -v`; then run this independent installed-wheel schema **and exact three-kind migration** probe. `--no-deps` is allowed only while building this project's wheel and is forbidden on the fresh-venv install. The source-tree checks intentionally use `PYTHONPATH=src`; before creating the fresh venv, the gate removes Python/virtual-environment and `UNIT_TEST_RUNNER_*` process variables, changes to a repository-external directory, and restores the exact starting environment even if install, probing, or cleanup fails. A source-tree `tests.test_contract_migrations` pass is necessary but cannot substitute for executing all Task 6 migrations through the normally installed wheel:

```powershell
$ErrorActionPreference = 'Stop'
$wheelSanitizedEnvironmentNames = @(
  'PYTHONHOME',
  'PYTHONPATH',
  'VIRTUAL_ENV',
  '__PYVENV_LAUNCHER__'
)
$wheelSavedEnvironment = @{}
foreach ($wheelEnvironmentEntry in Get-ChildItem Env:) {
  if (($wheelSanitizedEnvironmentNames -contains $wheelEnvironmentEntry.Name) -or
      $wheelEnvironmentEntry.Name.StartsWith('UNIT_TEST_RUNNER_',[StringComparison]::OrdinalIgnoreCase)) {
    $wheelSavedEnvironment[$wheelEnvironmentEntry.Name] = $wheelEnvironmentEntry.Value
  }
}
$wheelLocationPushed = $false

try {
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
py -m unittest tests.test_wheel_contract tests.test_contract_registry tests.test_public_artifact_schemas tests.test_contract_validation tests.test_contract_migrations -v
if ($LASTEXITCODE -ne 0) { throw 'wheel/registry/schema/migration source-tree tests failed' }
$wheelRepoRoot = (Resolve-Path -LiteralPath .).Path
$wheelTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$wheelTempPrefix = $wheelTempRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
$wheelGateRoot = [IO.Path]::GetFullPath((Join-Path $wheelTempRoot ('unitTestRunner-task6-wheel-gate-' + [guid]::NewGuid().ToString('N'))))
if (-not $wheelGateRoot.StartsWith($wheelTempPrefix,[StringComparison]::OrdinalIgnoreCase)) {
  throw "wheel gate root escaped system temp: $wheelGateRoot"
}
$wheelRepoPrefix = $wheelRepoRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if ($wheelGateRoot.Equals($wheelRepoRoot,[StringComparison]::OrdinalIgnoreCase) -or
    $wheelGateRoot.StartsWith($wheelRepoPrefix,[StringComparison]::OrdinalIgnoreCase)) {
  throw "wheel gate root must be outside the repository: $wheelGateRoot"
}
$wheelDistRoot = Join-Path $wheelGateRoot 'dist'
$wheelVenvRoot = Join-Path $wheelGateRoot 'venv'

try {
  New-Item -ItemType Directory -Path $wheelDistRoot -Force | Out-Null
  py -m pip wheel --disable-pip-version-check --no-deps --no-build-isolation --wheel-dir $wheelDistRoot $wheelRepoRoot
  if ($LASTEXITCODE -ne 0) { throw "wheel build failed: $LASTEXITCODE" }
  $projectWheels = @(Get-ChildItem -LiteralPath $wheelDistRoot -Filter 'unit_test_runner-*.whl' -File)
  if ($projectWheels.Count -ne 1) { throw "expected one project wheel; found $($projectWheels.Count)" }
  $projectWheel = $projectWheels[0]

  $metadataProbe = @'
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path
import re
import sys
import zipfile

wheel = Path(sys.argv[1]).resolve()
with zipfile.ZipFile(wheel) as archive:
    names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
    assert len(names) == 1, names
    metadata = BytesParser(policy=compat32).parsebytes(archive.read(names[0]))
requirements = metadata.get_all("Requires-Dist", [])

def normalized_name(value: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", value)
    assert match is not None, value
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()

direct = [value for value in requirements if normalized_name(value) == "referencing"]
assert len(direct) == 1, requirements
name_match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", direct[0])
assert name_match is not None
specifier = direct[0][name_match.end():].strip()
assert ";" not in specifier, direct[0]
if specifier.startswith("(") and specifier.endswith(")"):
    specifier = specifier[1:-1].strip()
assert {item.strip() for item in specifier.split(",") if item.strip()} == {">=0.28.4", "<1"}, direct[0]
assert not [value for value in requirements if normalized_name(value) == "typing-extensions"], requirements
print("METADATA Requires-Dist:", requirements)
'@
  $metadataProbe | py - $projectWheel.FullName
  if ($LASTEXITCODE -ne 0) { throw "wheel METADATA validation failed: $LASTEXITCODE" }

  foreach ($wheelEnvironmentName in $wheelSanitizedEnvironmentNames) {
    Remove-Item -LiteralPath "Env:$wheelEnvironmentName" -ErrorAction SilentlyContinue
  }
  foreach ($wheelEnvironmentEntry in @(Get-ChildItem Env: | Where-Object { $_.Name.StartsWith('UNIT_TEST_RUNNER_',[StringComparison]::OrdinalIgnoreCase) })) {
    Remove-Item -LiteralPath "Env:$($wheelEnvironmentEntry.Name)" -ErrorAction SilentlyContinue
  }

  Push-Location -LiteralPath $wheelGateRoot
  $wheelLocationPushed = $true
  try {
    py -m venv $wheelVenvRoot
    if ($LASTEXITCODE -ne 0) { throw "fresh venv creation failed: $LASTEXITCODE" }
    $wheelVenvPython = Join-Path $wheelVenvRoot 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $wheelVenvPython -PathType Leaf)) { throw "fresh venv Python missing: $wheelVenvPython" }

    # This is deliberately a normal dependency-resolving install.
    & $wheelVenvPython -m pip install --disable-pip-version-check --no-input $projectWheel.FullName
    if ($LASTEXITCODE -ne 0) { throw "normal fresh wheel install failed: $LASTEXITCODE" }
    & $wheelVenvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "fresh environment dependency check failed: $LASTEXITCODE" }

  $installedWheelProbe = @'
from importlib import resources
from pathlib import Path
import copy
import json
import sys

import jsonschema
import referencing
import unit_test_runner
import unit_test_runner.contracts.migrations as installed_migrations
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.contracts.migrations import migrate_payload
from unit_test_runner.contracts.registry import get_contract, iter_contracts, iter_contract_versions
from unit_test_runner.contracts.validator import validate_payload, validate_payload_schema

repo_root = Path(sys.argv[1]).resolve()
probe_cwd = Path.cwd().resolve()
venv_prefix = Path(sys.prefix).resolve()
assert probe_cwd != repo_root and not probe_cwd.is_relative_to(repo_root), (probe_cwd, repo_root)
assert venv_prefix.is_relative_to(probe_cwd), (venv_prefix, probe_cwd)
installed_modules = (unit_test_runner, installed_migrations, jsonschema, referencing)
installed_module_paths = {
    module.__name__: Path(module.__file__).resolve()
    for module in installed_modules
}
for module_name, installed_module_path in installed_module_paths.items():
    assert installed_module_path.is_relative_to(venv_prefix), (
        module_name,
        installed_module_path,
        venv_prefix,
    )
    assert not installed_module_path.is_relative_to(repo_root), (
        module_name,
        installed_module_path,
        repo_root,
    )
module_path = installed_module_paths['unit_test_runner']
migrations_module_path = installed_module_paths['unit_test_runner.contracts.migrations']
kinds = tuple(ArtifactKind)
current_contracts = tuple(iter_contracts())
versioned_contracts = tuple(iter_contract_versions())
assert kinds and len(current_contracts) == len(kinds)
assert {contract.kind for contract in current_contracts} == set(kinds)

schema_root = resources.files("unit_test_runner.schemas")
documents = {
    item.name: json.loads(item.read_text(encoding="utf-8"))
    for item in schema_root.iterdir()
    if item.name.endswith(".json")
}
expected_resources = {
    "common.schema.json",
    "common_v1_0.schema.json",
    *(contract.schema_resource for contract in versioned_contracts),
}
assert set(documents) == expected_resources, {
    "missing": sorted(expected_resources - set(documents)),
    "unexpected": sorted(set(documents) - expected_resources),
}
schema_ids = []
for resource_name, document in documents.items():
    Draft202012Validator.check_schema(document)
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema", resource_name
    schema_ids.append(document["$id"])
assert len(schema_ids) == len(set(schema_ids)), schema_ids
documents_by_id = {document["$id"]: document for document in documents.values()}
schema_registry = Registry()
for document in documents.values():
    schema_registry = schema_registry.with_resource(
        document["$id"],
        Resource.from_contents(document),
    )

def references(value):
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str):
            yield reference
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)

def resolve_pointer(document, pointer):
    current = document
    for token in pointer.lstrip("/").split("/"):
        current = current[token.replace("~1", "/").replace("~0", "~")]
    return current

for resource_name, document in documents.items():
    for reference in references(document):
        target_name, separator, fragment = reference.partition("#")
        if not target_name:
            target = document
        elif target_name in documents:
            target = documents[target_name]
        else:
            assert target_name in documents_by_id, (resource_name, reference)
            target = documents_by_id[target_name]
        if separator and fragment:
            assert fragment.startswith("/"), (resource_name, reference)
            resolve_pointer(target, fragment)

for kind in kinds:
    contract = get_contract(kind)
    assert contract.schema_resource in documents
    violations = validate_payload_schema(kind, {
        "artifact_kind": kind.value,
        "schema_version": contract.current_version,
    })
    assert isinstance(violations, tuple) and violations, kind.value

task6_migration_kinds = (
    ArtifactKind.REVIEW_DECISIONS,
    ArtifactKind.FUNCTION_DOSSIER,
    ArtifactKind.DOSSIER_MANIFEST,
)
assert {kind.value for kind in task6_migration_kinds} == {
    "review_decisions",
    "function_dossier",
    "dossier_manifest",
}
assert {get_contract(kind).current_version for kind in task6_migration_kinds} == {"1.1.0"}

sha256 = "7b18e68b2afcf1b0f0a1b857c5d1fcb2cf9db4d1540d778a266dbeaa3aa176a8"
producer = {
    "name": "unit-test-runner",
    "version": "0.1.0",
    "commit": "installed-wheel-probe",
}
subject = {
    "function_id": "fn_control_update_cdd351ecf31d",
    "source_path": "src/control.c",
    "source_sha256": sha256,
}
readiness = {
    "mvp_level": "analysis",
    "ready_for_review": True,
    "ready_for_harness_generation": False,
    "ready_for_build_probe": False,
    "ready_for_execution": False,
    "evidence_ready": False,
    "blocked": False,
    "blocked_reasons": [],
    "quality_score": None,
}
migration_vectors = {
    ArtifactKind.REVIEW_DECISIONS: {
        "artifact_kind": "review_decisions",
        "schema_version": "1.0.0",
        "producer": producer,
        "subject": subject,
        "data": {
            "revision": 1,
            "decisions": [{
                "review_id": "review-legacy-1",
                "resolution": "approved",
                "reviewer": "reviewer01",
                "rationale": "Reviewed evidence.",
                "decided_at": "2026-07-12T00:00:00+00:00",
                "subject_artifacts": [{
                    "artifact_kind": "test_spec",
                    "path": "reports/test_spec.json",
                    "sha256": "a" * 64,
                }],
            }],
        },
        "extensions": {},
    },
    ArtifactKind.FUNCTION_DOSSIER: {
        "artifact_kind": "function_dossier",
        "schema_version": "1.0.0",
        "producer": producer,
        "subject": subject,
        "data": {
            "target": {
                "source": "src/control.c",
                "function": "Control_Update",
                "configuration": "Debug",
                "project": "Control",
            },
            "project_membership": [],
            "build_context": {},
            "function": {"name": "Control_Update", "status": "ready"},
            "test_design": {},
            "diagnostics": [],
            "artifact_index": [],
            "review_items": [{
                "review_id": "review-legacy-1",
                "category": "analysis",
                "title": "Review source digest",
                "description": "Confirm analysis evidence.",
                "related_artifacts": [],
                "related_test_cases": [],
                "severity": "warning",
                "suggested_reviewer_role": "unit_test_reviewer",
                "done": True,
            }],
            "readiness": readiness,
        },
        "extensions": {},
    },
    ArtifactKind.DOSSIER_MANIFEST: {
        "artifact_kind": "dossier_manifest",
        "schema_version": "1.0.0",
        "producer": producer,
        "subject": subject,
        "data": {
            "artifact_index": [],
            "readiness": readiness,
        },
        "extensions": {},
    },
}
assert set(migration_vectors) == set(task6_migration_kinds)

def canonical_bytes(value):
    return (json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n").encode("utf-8")

def key_occurrences(value, key, path="$"):
    if isinstance(value, dict):
        for child_key, child in value.items():
            child_path = f"{path}.{child_key}"
            if child_key == key:
                yield child_path, child
            yield from key_occurrences(child, key, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from key_occurrences(child, key, f"{path}[{index}]")

migrated_by_kind = {}
for kind in task6_migration_kinds:
    input_bytes = canonical_bytes(migration_vectors[kind])
    source_payload = json.loads(input_bytes)
    source_copy = copy.deepcopy(source_payload)
    source_contract = get_contract(kind, "1.0.0")
    source_validator = Draft202012Validator(
        documents[source_contract.schema_resource],
        registry=schema_registry,
    )
    source_schema_errors = tuple(source_validator.iter_errors(source_payload))
    assert source_schema_errors == (), (kind.value, source_schema_errors)
    migrated = migrate_payload(kind, source_payload, target_version="1.1.0")
    assert source_payload == source_copy, kind.value
    assert canonical_bytes(source_payload) == input_bytes, kind.value
    assert migrated["artifact_kind"] == kind.value, kind.value
    assert migrated["schema_version"] == "1.1.0", kind.value
    violations = validate_payload(kind, migrated)
    assert violations == (), (kind.value, violations)
    migrated_by_kind[kind] = migrated

migrated_decision = migrated_by_kind[ArtifactKind.REVIEW_DECISIONS]["data"]["decisions"][0]
assert migrated_decision["authority"] == "display_only", migrated_decision
assert migrated_decision["source_schema_version"] == "1.0.0", migrated_decision
assert migrated_decision["subject_artifacts"][0]["revision"] is None, migrated_decision

migrated_dossier = migrated_by_kind[ArtifactKind.FUNCTION_DOSSIER]
done_occurrences = tuple(key_occurrences(migrated_dossier, "done"))
assert len(done_occurrences) == 1, done_occurrences
done_path, done_value = done_occurrences[0]
assert done_value is True and done_path.startswith("$.extensions.migration"), done_occurrences

migrated_manifest = migrated_by_kind[ArtifactKind.DOSSIER_MANIFEST]
assert migrated_manifest["data"].get("review_subject_snapshot") is None, migrated_manifest

print(json.dumps({
    "installed_module": str(module_path),
    "installed_migrations_module": str(migrations_module_path),
    "probe_cwd": str(probe_cwd),
    "artifact_kind_count": len(kinds),
    "current_contract_count": len(current_contracts),
    "versioned_contract_count": len(versioned_contracts),
    "packaged_schema_count": len(documents),
    "task6_migrations_verified": sorted(kind.value for kind in migrated_by_kind),
}, sort_keys=True))
'@
    & $wheelVenvPython -I -c $installedWheelProbe $wheelRepoRoot
    if ($LASTEXITCODE -ne 0) { throw "installed wheel runtime/schema/migration probe failed: $LASTEXITCODE" }
  }
  finally {
    if ($wheelLocationPushed) {
      Pop-Location
      $wheelLocationPushed = $false
    }
  }
}
finally {
  if (Test-Path -LiteralPath $wheelGateRoot) {
    $wheelCleanupTarget = [IO.Path]::GetFullPath($wheelGateRoot)
    $wheelCleanupName = [IO.Path]::GetFileName($wheelCleanupTarget)
    if (-not $wheelCleanupTarget.StartsWith($wheelTempPrefix,[StringComparison]::OrdinalIgnoreCase) -or
        -not $wheelCleanupName.StartsWith('unitTestRunner-task6-wheel-gate-',[StringComparison]::Ordinal)) {
      throw "refusing unsafe wheel cleanup: $wheelCleanupTarget"
    }
    $wheelCleanupItem = Get-Item -LiteralPath $wheelCleanupTarget -Force
    if (($wheelCleanupItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "refusing reparse wheel cleanup: $wheelCleanupTarget"
    }
    Remove-Item -LiteralPath $wheelCleanupTarget -Recurse -Force
  }
}
}
finally {
  if ($wheelLocationPushed) {
    Pop-Location
    $wheelLocationPushed = $false
  }
  foreach ($wheelEnvironmentName in $wheelSanitizedEnvironmentNames) {
    Remove-Item -LiteralPath "Env:$wheelEnvironmentName" -ErrorAction SilentlyContinue
  }
  foreach ($wheelEnvironmentEntry in @(Get-ChildItem Env: | Where-Object { $_.Name.StartsWith('UNIT_TEST_RUNNER_',[StringComparison]::OrdinalIgnoreCase) })) {
    Remove-Item -LiteralPath "Env:$($wheelEnvironmentEntry.Name)" -ErrorAction SilentlyContinue
  }
  foreach ($wheelSavedEnvironmentEntry in $wheelSavedEnvironment.GetEnumerator()) {
    Set-Item -LiteralPath "Env:$($wheelSavedEnvironmentEntry.Key)" -Value $wheelSavedEnvironmentEntry.Value
  }
}
```

Record the wheel path/hash, full `Requires-Dist` list, normal install and `pip check` exits, repository-external probe working directory, installed package and migration-module paths, artifact-kind/current/versioned-contract counts, packaged-schema count, the exact three migrated kinds, every input-immutability/output-validation/kind-specific semantic assertion, and cleanup result. The evidence must prove no project import came from the repository. The direct dependency is `referencing>=0.28.4,<1`; `typing-extensions` is not a Task 6 direct dependency.

Authoritative isolated full gate (dynamic inventory, one fresh process per module):

```powershell
$task6SourceRoot = (Resolve-Path -LiteralPath .\src).Path
$env:PYTHONPATH = $task6SourceRoot
$task6SourcePrefix = $task6SourceRoot.TrimEnd('\') + '\'
$task6ImportedPath = ((& py -c "from pathlib import Path; import unit_test_runner; print(Path(unit_test_runner.__file__).resolve())") -join '').Trim()
if ($LASTEXITCODE -ne 0 -or -not $task6ImportedPath.StartsWith($task6SourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "wrong Task 6 import root: $task6ImportedPath" }
$modules = Get-ChildItem -LiteralPath .\tests -Filter 'test_*.py' -File |
  Sort-Object Name |
  ForEach-Object { 'tests.' + $_.BaseName }
if (-not $modules) { throw 'isolated Python test discovery returned no modules' }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $env:TEMP "unit-test-runner-task6-$stamp.log"
$csv = Join-Path $env:TEMP "unit-test-runner-task6-$stamp.csv"
$rows = @()
$actualSkips = @()
foreach ($module in $modules) {
  $output = @(& py -m unittest $module -v 2>&1 | ForEach-Object { $_.ToString() })
  $exitCode = $LASTEXITCODE
  "`n=== $module ===" | Tee-Object -FilePath $log -Append | Out-Null
  $output | Tee-Object -FilePath $log -Append

  $trimmed = @($output | ForEach-Object { $_.Trim() })
  $ranLines = @($trimmed | Where-Object { $_ -match '^Ran (\d+) tests? in ' })
  $summaryLines = @($trimmed | Where-Object { $_ -match '^(OK(?: \(skipped=\d+\))?|FAILED \(.+\))$' })
  $parsed = $ranLines.Count -ge 1 -and $summaryLines.Count -ge 1
  $tests = 0
  $skips = 0
  $failures = 0
  $errors = 0
  if ($parsed) {
    $null = $ranLines[-1] -match '^Ran (\d+) tests? in '
    $tests = [int]$Matches[1]
    $summary = $summaryLines[-1]
    if ($summary -match 'skipped=(\d+)') { $skips = [int]$Matches[1] }
    if ($summary -match 'failures=(\d+)') { $failures = [int]$Matches[1] }
    if ($summary -match 'errors=(\d+)') { $errors = [int]$Matches[1] }
  }

  foreach ($line in $trimmed) {
    if ($line -match '^\S+ \((?<qualified>[^)]+)\) \.\.\. skipped [''\"](?<reason>.*)[''\"]$') {
      $actualSkips += "$($Matches.qualified)|$($Matches.reason)"
    }
  }
  if ($parsed -and $skips -ne @($actualSkips | Where-Object { $_ -like "$module.*" }).Count) {
    $parsed = $false
  }
  $rows += [pscustomobject]@{
    Module=$module; ExitCode=$exitCode; Parsed=$parsed; Tests=$tests;
    Skips=$skips; Failures=$failures; Errors=$errors
  }
}
$rows | Export-Csv -LiteralPath $csv -NoTypeInformation -Encoding utf8

$testsTotal = ($rows | Measure-Object Tests -Sum).Sum
$skipsTotal = ($rows | Measure-Object Skips -Sum).Sum
$failuresTotal = ($rows | Measure-Object Failures -Sum).Sum
$errorsTotal = ($rows | Measure-Object Errors -Sum).Sum
$nonzeroTotal = @($rows | Where-Object { $_.ExitCode -ne 0 }).Count
$parseFailureTotal = @($rows | Where-Object { -not $_.Parsed }).Count
"isolated_modules=$($modules.Count) tests=$testsTotal skips=$skipsTotal failures=$failuresTotal errors=$errorsTotal nonzero=$nonzeroTotal parse_failures=$parseFailureTotal log=$log csv=$csv"

$allowedCompilerSkips = @(
  'tests.test_cli_execution_outcome.CliExecutionOutcomeTests.test_failed_fixture_execution_returns_nonzero_cli_result|host C compiler is required',
  'tests.test_dependency_policy_end_to_end.DependencyPolicyEndToEndTests.test_real_default_and_case_stub_override_build_and_run_without_symbol_collisions|host C compiler is required',
  'tests.test_vc6_fixture_build_e2e.Vc6FixtureBuildEndToEndTests.test_default_fixture_analysis_compiles_and_links_without_mutating_product_tree|host C compiler is required'
)
$compiler = Get-Command gcc, clang, cc -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $compiler) {
  $unexpectedSkips = @($actualSkips | Where-Object { $_ -notin $allowedCompilerSkips })
  $missingSkips = @($allowedCompilerSkips | Where-Object { $_ -notin $actualSkips })
  if ($unexpectedSkips.Count -ne 0 -or $missingSkips.Count -ne 0) {
    throw "local skip set mismatch: unexpected=$($unexpectedSkips -join ',') missing=$($missingSkips -join ',')"
  }
}
elseif ($actualSkips.Count -ne 0) {
  throw ('compiler is available but tests skipped: ' + ($actualSkips -join ','))
}
if ($failuresTotal -ne 0 -or $errorsTotal -ne 0 -or $nonzeroTotal -ne 0 -or $parseFailureTotal -ne 0) {
  throw 'isolated Python gate failed; inspect the recorded log and CSV'
}
```

Record actual module/test/skip/failure/error/nonzero totals. Do not hardcode recovered carrier totals (`117/563`) or current baseline totals (`112/543`) as expected Task 6 totals.

Local compiler-dependent skips must match the documented allowed local skip set exactly. Hosted CI must use the real compiler and have no unexpected skip.

Carrier-free mechanical gate (run before PR creation, immediately before merge, and again at the exact product merge SHA):

```powershell
$startAnchor = '969ce9462a688e94c887d6e77359e40296d8927b'
# Set these to the recorded candidate identities. For the post-merge run,
# keep $gateBase at reviewed_base_sha and set $gateHead to the exact merge SHA.
$gateBase = '<reviewed_base_sha>'
$gateHead = '<candidate_or_merge_sha>'
$carrierHead = '8e27f7552ec1f74d384c864e853aba5f7f90161b'

git merge-base --is-ancestor $startAnchor $gateBase
$startToBaseExit = $LASTEXITCODE
if ($startToBaseExit -ne 0) { throw "Task 6 start anchor is not an ancestor of reviewed base: $startToBaseExit" }

git merge-base --is-ancestor $gateBase $gateHead
$baseToHeadExit = $LASTEXITCODE
if ($baseToHeadExit -ne 0) { throw "reviewed base is not an ancestor of gate head: $baseToHeadExit" }

git diff --check "$gateBase...$gateHead"
$candidateDiffCheckExit = $LASTEXITCODE
if ($candidateDiffCheckExit -ne 0) {
  throw "candidate base-to-head diff check failed: $candidateDiffCheckExit"
}

git merge-base --is-ancestor $carrierHead $gateHead
$ancestorExit = $LASTEXITCODE
if ($ancestorExit -eq 0) { throw 'PR #16 carrier head is an ancestor of the product branch' }
if ($ancestorExit -ne 1) { throw "carrier ancestry check failed: $ancestorExit" }

$carrierPathHistory = @(
  git log --format='%H' --name-only "$startAnchor..$gateHead" -- `
    .github/bootstrap .github/workflows/materialize-p1t6-v3.yml |
    Where-Object { $_.Trim() }
)
if ($LASTEXITCODE -ne 0) { throw 'carrier path history check failed' }
if ($carrierPathHistory.Count -ne 0) {
  throw ('carrier path appeared in product history: ' + ($carrierPathHistory -join ', '))
}

$allowedExact = @(
  'pyproject.toml',
  'docs/superpowers/plans/2026-07-15-phase1-task6-review-decisions-readiness.md',
  'docs/superpowers/plans/2026-07-15-phase1-task6-gate-evidence.md',
  'src/unit_test_runner/atomic_io.py',
  'src/unit_test_runner/build/build_workspace_generator.py',
  'src/unit_test_runner/build_completion/build_completion_analyzer.py',
  'src/unit_test_runner/build_completion/completion_applier.py',
  'src/unit_test_runner/build_probe.py',
  'src/unit_test_runner/c_analyzer/source_digest.py',
  'src/unit_test_runner/c_analyzer/function_location_writer.py',
  'src/unit_test_runner/c_analyzer/signature_writer.py',
  'src/unit_test_runner/review_ids.py',
  'src/unit_test_runner/cli/commands.py',
  'src/unit_test_runner/cli/main.py',
  'src/unit_test_runner/cli/parser.py',
  'src/unit_test_runner/contracts/migrations.py',
  'src/unit_test_runner/contracts/__init__.py',
  'src/unit_test_runner/contracts/consumer.py',
  'src/unit_test_runner/contracts/registry.py',
  'src/unit_test_runner/contracts/validator.py',
  'src/unit_test_runner/dossier/__init__.py',
  'src/unit_test_runner/dossier/artifact_collector.py',
  'src/unit_test_runner/dossier/dossier_models.py',
  'src/unit_test_runner/dossier/dossier_writer.py',
  'src/unit_test_runner/dossier/finalizer.py',
  'src/unit_test_runner/dossier/readiness.py',
  'src/unit_test_runner/dossier/review_assessment.py',
  'src/unit_test_runner/dossier/review_decision_models.py',
  'src/unit_test_runner/dossier/review_decision_repository.py',
  'src/unit_test_runner/review_subject_publisher.py',
  'src/unit_test_runner/dossier/review_workflow.py',
  'src/unit_test_runner/dossier/workflow.py',
  'src/unit_test_runner/reanalysis/snapshot_builder.py',
  'src/unit_test_runner/reanalysis/workflow.py',
  'src/unit_test_runner/build_completion/completion_report_writer.py',
  'src/unit_test_runner/execution/report_loader.py',
  'src/unit_test_runner/execution/evidence_paths.py',
  'src/unit_test_runner/execution/evidence_manifest.py',
  'src/unit_test_runner/execution/execution_runner.py',
  'src/unit_test_runner/execution/run_paths.py',
  'src/unit_test_runner/execution/test_execution.py',
  'src/unit_test_runner/execution/test_result_writer.py',
  'src/unit_test_runner/harness/__init__.py',
  'src/unit_test_runner/harness/c90_writer.py',
  'src/unit_test_runner/harness/dependency_dispatcher.py',
  'src/unit_test_runner/harness/harness_report_writer.py',
  'src/unit_test_runner/harness/harness_skeleton_generator.py',
  'src/unit_test_runner/harness/parameter_init_compat.py',
  'src/unit_test_runner/harness/runner_output_enhancer.py',
  'src/unit_test_runner/harness/state_setup_reflector.py',
  'src/unit_test_runner/harness/target_invocation_compat.py',
  'src/unit_test_runner/schemas/boundary_candidates.schema.json',
  'src/unit_test_runner/schemas/build_completion_history.schema.json',
  'src/unit_test_runner/schemas/build_completion_iteration.schema.json',
  'src/unit_test_runner/schemas/build_completion_plan.schema.json',
  'src/unit_test_runner/schemas/build_context.schema.json',
  'src/unit_test_runner/schemas/build_probe_report.schema.json',
  'src/unit_test_runner/schemas/build_workspace_report.schema.json',
  'src/unit_test_runner/schemas/call_report.schema.json',
  'src/unit_test_runner/schemas/change_impact.schema.json',
  'src/unit_test_runner/schemas/cli_result.schema.json',
  'src/unit_test_runner/schemas/common.schema.json',
  'src/unit_test_runner/schemas/common_v1_0.schema.json',
  'src/unit_test_runner/schemas/coverage_design.schema.json',
  'src/unit_test_runner/schemas/dependency_policy.schema.json',
  'src/unit_test_runner/schemas/dossier_manifest.schema.json',
  'src/unit_test_runner/schemas/dossier_manifest_v1_0.schema.json',
  'src/unit_test_runner/schemas/dsw_discovery.schema.json',
  'src/unit_test_runner/schemas/evidence_manifest.schema.json',
  'src/unit_test_runner/schemas/evidence_source_run.schema.json',
  'src/unit_test_runner/schemas/function_dossier.schema.json',
  'src/unit_test_runner/schemas/function_dossier_v1_0.schema.json',
  'src/unit_test_runner/schemas/function_location.schema.json',
  'src/unit_test_runner/schemas/function_signature.schema.json',
  'src/unit_test_runner/schemas/global_access.schema.json',
  'src/unit_test_runner/schemas/harness_skeleton_report.schema.json',
  'src/unit_test_runner/schemas/input_request.schema.json',
  'src/unit_test_runner/schemas/latest_evidence_pointer.schema.json',
  'src/unit_test_runner/schemas/latest_run_pointer.schema.json',
  'src/unit_test_runner/schemas/latest_suite_run_pointer.schema.json',
  'src/unit_test_runner/schemas/project_membership.schema.json',
  'src/unit_test_runner/schemas/prompt_pack.schema.json',
  'src/unit_test_runner/schemas/quick_summary.schema.json',
  'src/unit_test_runner/schemas/reanalysis_snapshot.schema.json',
  'src/unit_test_runner/schemas/regression_selection.schema.json',
  'src/unit_test_runner/schemas/review_decisions.schema.json',
  'src/unit_test_runner/schemas/review_decisions_v1_0.schema.json',
  'src/unit_test_runner/schemas/source_digest.schema.json',
  'src/unit_test_runner/schemas/source_membership.schema.json',
  'src/unit_test_runner/schemas/state_setup_reflection.schema.json',
  'src/unit_test_runner/schemas/suite_manifest.schema.json',
  'src/unit_test_runner/schemas/suite_run_report.schema.json',
  'src/unit_test_runner/schemas/test_case_reconciliation.schema.json',
  'src/unit_test_runner/schemas/test_execution_report.schema.json',
  'src/unit_test_runner/schemas/test_result.schema.json',
  'src/unit_test_runner/schemas/test_spec_v1_0.schema.json',
  'src/unit_test_runner/test_spec/generation.py',
  'src/unit_test_runner/test_spec/identity.py',
  'src/unit_test_runner/test_spec/exporters.py',
  'src/unit_test_runner/test_spec/patch.py',
  'src/unit_test_runner/test_spec/repository.py',
  'src/unit_test_runner/suite/manager.py',
  'tests/test_build_probe.py',
  'tests/test_build_diagnostics_and_completion.py',
  'tests/test_build_workspace_generation.py',
  'tests/test_contract_registry.py',
  'tests/test_contract_validation.py',
  'tests/test_contract_migrations.py',
  'tests/test_public_artifact_schemas.py',
  'tests/test_wheel_contract.py',
  'tests/test_dossier_review_workflow.py',
  'tests/test_dependency_policy_explicit_harness.py',
  'tests/test_review_decisions.py',
  'tests/test_review_decision_staleness.py',
  'tests/test_dossier_readiness.py',
  'tests/test_dossier_review_authority.py',
  'tests/test_review_decision_integration.py',
  'tests/test_review_decision_cli.py',
  'tests/test_review_subject_publication.py',
  'tests/test_build_and_execution_module_boundaries.py',
  'tests/test_c_source_reading.py',
  'tests/test_execution_evidence.py',
  'tests/test_execution_run_history.py',
  'tests/test_evidence_integrity.py',
  'tests/test_function_analysis_reports.py',
  'tests/test_harness_report_localization.py',
  'tests/test_harness_skeleton_generation.py',
  'tests/test_prepare_evidence_non_destructive.py',
  'tests/test_reanalysis_snapshot_builder.py',
  'tests/test_suite_cli.py',
  'tests/test_suite_manager.py',
  'tests/test_test_spec_contract.py',
  'tests/test_test_spec_generation.py',
  'tests/test_test_spec_repository.py',
  'tests/test_test_spec_formal_review_export_atomicity.py',
  'tests/test_test_spec_formal_review_provenance.py',
  'tests/test_test_spec_formal_review_writer_snapshots.py',
  'tests/test_test_spec_reanalysis.py'
)
$changed = @(git diff --name-only "$gateBase...$gateHead")
if ($LASTEXITCODE -ne 0) { throw 'cannot enumerate Task 6 paths' }
$historyPaths = @(
  git log --format= --name-only "$gateBase..$gateHead" |
    Where-Object { $_.Trim() } |
    Sort-Object -Unique
)
if ($LASTEXITCODE -ne 0) { throw 'cannot enumerate Task 6 history paths' }
$allTouched = @(($changed + $historyPaths) | Sort-Object -Unique)
$unexpected = @($allTouched | Where-Object { $_ -notin $allowedExact })
if ($unexpected.Count -ne 0) {
  throw ('unexpected Task 6 paths require scope review: ' + ($unexpected -join ', '))
}
```

If a legitimate implementation needs another path, add that exact path to this reviewed plan/allowlist before it is changed or committed. Never weaken the gate to a broad `.github/**`, `src/**`, or `tests/**` allowance.

After preliminary gates, write `docs/superpowers/plans/2026-07-15-phase1-task6-gate-evidence.md` with slice RED/GREEN facts and the **tested product tree SHA**, then commit it as `docs: record Phase 1 Task 6 pre-final gate evidence`. That tracked file never claims its own commit SHA, the later final rerun, final reviewer verdict, hosted checks, or merge facts. Those later facts live in the exact-head PR/check evidence and the post-merge closeout document, preventing evidence self-reference.

### Slice 10 — Formal review, product PR, merge, and post-merge accounting

1. Fetch `origin/main`. Require start anchor `969ce9462a688e94c887d6e77359e40296d8927b` to be its ancestor and require `git merge-base origin/main HEAD` to equal `origin/main`. If main advanced and is not already contained, rebase the Task 6 commits onto the new `origin/main`, refresh the pre-final evidence commit without self-SHA claims, then restart Slice 9 and this slice.
2. With the pre-final evidence already committed and a clean worktree, run the focused, related, isolated full, package/schema/installed-wheel-migration, fixture, source-integrity, VS Code, CLI smoke, compile, diff, and carrier-free gates **again at the unchanged candidate HEAD**. The installed-wheel gate must again execute and validate every exact Task 6 migration from its sanitized repository-external working directory under `python -I`; source-tree migration results cannot stand in for it. Store raw logs/CSV outside the checkout; do not edit tracked evidence afterward.
3. Fresh spec reviewer checks `origin/main...HEAD` against every fixed semantic decision and carrier correction.
4. Fresh code-quality reviewer checks the same entire diff, with special focus on the fenced subject snapshot, pre/post-commit outcomes, manual lock recovery, deadlines, exact bytes, immutable schema references, and CLI truthfulness.
5. Resolve and re-review every Critical, Important, and Minor finding. A candidate is accepted only when both fresh reviewers report Critical 0 / Important 0 / Minor 0 (`C0/I0/M0`); no unresolved Minor finding may pass. Keep those final zero-count verdicts in the task record and later exact-head PR evidence, not a new product-branch commit.
6. If any file changes after the final gates or either review, discard the candidate identity, update only preliminary evidence as appropriate, commit that update, and restart at step 1. Reviews and gates are never carried forward to a different commit.
7. At the clean accepted commit, capture in the task record/shell variables (not by editing the branch):
   - `start_anchor_sha = 969ce9462a688e94c887d6e77359e40296d8927b`,
   - `reviewed_base_sha = git rev-parse origin/main` (dynamic but fixed for this candidate),
   - `reviewed_head_sha = git rev-parse HEAD`,
   - `reviewed_tree_sha = git show -s --format=%T HEAD`,
   - both reviewer `C0/I0/M0` verdicts and every final local gate/log identity.
8. Push exactly `reviewed_head_sha` and open one Task 6 product PR against `main`. The PR must contain neither `.github/bootstrap/**` nor `.github/workflows/materialize-p1t6-v3.yml`, and its branch history must pass the carrier ancestry/history/allowlist gate. Put the captured base/head/tree, final local log/CSV identities, totals, and reviewer verdicts in the PR body or an exact-head PR comment without changing the branch.
9. Require all hosted jobs GREEN **for `reviewed_head_sha`**. Parse job logs for actual Python module/test totals, writer-snapshot outcome, Windows alias checks, real compiler path, and non-skipped E2E. Record the check-suite/run head SHA, not only the run URL.
10. Immediately before merge:
   - fetch `origin/main` and require it still equals `reviewed_base_sha`;
   - read the PR through GitHub and require its head SHA equals `reviewed_head_sha`;
   - require every required check belongs to and is GREEN for `reviewed_head_sha`;
   - rerun the carrier-free mechanical gate at `reviewed_head_sha`;
   - require local `HEAD` and tree equal `reviewed_head_sha`/`reviewed_tree_sha` and the worktree is clean.
11. If base, head, tree, checks, or files differ, do not merge. Rebase onto the new base or fix the branch, then restart Slice 9 and this slice at step 1 with new reviewed identities.
12. Merge with a merge commit only. At the exact merge SHA, require:
   - first parent equals `reviewed_base_sha`,
   - second parent equals `reviewed_head_sha`,
   - merge tree equals `reviewed_tree_sha`,
   - the carrier-free ancestry/history/path gate passes again.
13. In a clean post-merge worktree at that exact merge SHA, run focused tests, compileall, CLI help/smoke, diff/status checks, and then monitor the `main` push workflow to all GREEN for the exact merge SHA.
14. After the clean product merge and both the exact-merge-SHA local and hosted `main` verification, close obsolete open draft PRs #11, #12, #13, #14, #15, and #16 through GitHub. Read each PR back and require `state=CLOSED`; if any close or readback fails, stop the closeout. Do not delete any remote branch. These are external actions, not effects of a Git documentation commit.
15. From the verified product merge SHA, create a post-merge closeout documentation branch/commit that:
   - first re-reads these four exact paths from the then-current verified `main`; if any path was renamed or its authority changed, stop and amend/review the closeout allowlist before writing:
     - `docs/superpowers/plans/2026-07-11-unit-test-runner-phase-1-contract-execution-evidence.md` — phase plan; check off only Task 6 requirements proven by the product merge evidence;
     - `docs/superpowers/plans/preflight/phase1-task-6-preflight.md` — Task 6 preflight; replace `not started` with the exact approved/merged/verified identities and handoff;
     - `docs/superpowers/plans/preflight/README.md` — restart handoff; advance the durable integrated boundary to 14/38 and make Task 7 the next task without rewriting historical Task 5 evidence;
     - `docs/superpowers/plans/2026-07-15-phase1-task6-completion.md` — new completion record containing product PR, product merge SHA/tree, hosted run IDs/head SHAs, dynamic local totals/log hashes, limitations, both reviewer `C0/I0/M0` verdicts, post-merge gates, individual GitHub closed-state readback proof for PRs #11 through #16, confirmation that no remote branch was deleted, and the closeout base SHA;
   - permits no fifth path in the documentation-only diff and does not rewrite the pre-final self-SHA-free gate evidence;
   - updates progress from 13/38 to 14/38 and marks Task 6 complete only in those exact documents after all referenced evidence has been read back.
16. Push the closeout documentation branch, open a documentation-only PR, require its exact-head checks GREEN, merge it, and verify the resulting `main` SHA. Progress is not durably **14/38** until this documentation PR is merged and verified.
17. Only after durable 14/38, create a new isolated Task 7 planning branch/worktree from that verified documentation merge SHA. Write, review, commit, and push the Task 7 execution plan before any Task 7 product change; do not mix the Task 7 plan into the Task 6 closeout PR.

---

## 8. Stop conditions

Stop the active slice without committing product code if any of these occurs:

- The product worktree is not based on `969ce946` plus reviewed Task 6 commits.
- The primary checkout's user-owned state would need to be modified.
- A RED is import/setup failure rather than an assertion proving behavior.
- A proposed write accepts pre-resolved current items instead of re-resolving under lock.
- Any current decisionable review item has an empty subject tuple, or the generic fallback becomes ready without an eligible fenced subject.
- Any of the registered ten canonical mutation paths can bypass the common publication lock/newer dirty state; or a real run/evidence publication reintroduces a destructive flat alias.
- Any source-digest/function-location/function-signature fallback writer bypasses publication, a suite converts publication failure to a string and continues, or any cleanup deletes an immutable run/evidence target after its corresponding latest-run/latest-evidence pointer commit.
- Any command handler wraps a `ReviewSubjectPublicationError` as generic CLIError/internal error and loses committed-file/deletion/recovery fields.
- A detached `--out` receives an authoritative manifest/ledger/editable JSON, or the workspace resolver depends on an export root instead of `<workspace>/reports`.
- Discovery accepts a publication marker or dirty/publishing fence, retries beyond the fixed bound, or any automatic path reclaims/recovers subject publication without the exact operator guards.
- A design claims the ledger lock excludes independent subject writers, or allows a decision captured before a concurrent subject change to authorize the changed bytes.
- A 1.0 schema reaches mutable current common definitions.
- A pre-commit failure changes the ledger/revision, returns a produced artifact, masks its primary exception, or leaves cleanup residue without truthful contained recovery metadata.
- A post-commit cleanup failure is reported as no-write, omits its exact committed artifact, or any Task 6 path automatically reclaims/deletes a timed-out marker.
- TestSpec PR #19 writer regressions fail after retry-helper work.
- Task 6 requires unexpected VS Code changes or Phase 2 generation policy.
- Full isolated failures are dismissed as aggregate-run contamination without module-level reproduction and resolution.
- The Slice 1 forced-short-TEMP reproduction shows a different physical file or containment escape and product changes are proposed before this plan is amended and re-reviewed.
- Slice 2 is started before the reconciliation commit is pushed and all six hosted jobs are read back GREEN for that exact head.
- Formal review has any unresolved Critical, Important, or Minor finding, or either fresh review is not `C0/I0/M0` for the exact candidate.
- Hosted CI has an unexpected skip, missing real compiler, or non-GREEN job.
- The carrier head/path/materializer appears in ancestry or branch history, an unreviewed path is outside the allowlist, or reviewed base/head/tree/check identities do not match the merge target.
- Any obsolete PR #11 through #16 is treated as a merge candidate or implementation authority, is closed before the verified product-merge boundary, cannot be read back as `state=CLOSED` after closure, or any remote branch deletion is proposed.

Do not mark the goal blocked merely because a slice is difficult. Preserve the RED and diagnostic evidence, investigate within scope, and resume from the last clean commit.

---

## 9. Handoff record required at each boundary

Each slice handoff records only durable, reviewable facts:

- branch and base/head SHA,
- exact changed files,
- assertion-level RED command and failure reason,
- GREEN commands and counts,
- related regressions and counts,
- reviewer verdict/findings/disposition and exact `C0/I0/M0` acceptance proof,
- known limitations,
- next slice and its entry condition,
- clean/dirty status.

The Slice 1 reconciliation handoff additionally records physical-identity proof for the long/short failure operands, normal and forced-short-TEMP focused results, the required-alias isolated module total, exact commit/pushed/head SHA, hosted run ID, and 6/6 GREEN readback. The post-merge closeout handoff records each of PRs #11 through #16 individually as `state=CLOSED` and confirms that no remote branch was deleted.

Push at the plan checkpoint and at coherent reviewed product boundaries. Do not push transient RED-only or known-broken states unless recovery from the remote checkpoint is explicitly needed and the branch/commit is clearly marked non-mergeable.
