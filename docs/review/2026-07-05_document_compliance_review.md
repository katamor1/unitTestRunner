# 2026-07-05 Document Compliance Review

## Scope

This review checks the current implementation against the repository documents listed below.

- `docs/function_level_vc6_unit_test_codex_design.md`
- `docs/adr/0001-cli-layer-language-selection.md`
- `docs/implementation/step02_cli_entry_point_plan.md` through `step18_vscode_thin_adapter_plan.md`
- `README.md`, `docs/v0.1_smoke_sample.md`, `templates/vscode/tasks.json`

The review focuses on omissions, contract violations, stale documentation, and risks that can mislead an operator. It does not include functional fixes.

## Executive Summary

Overall status: **partial compliance with blocking documentation/contract gaps**.

The implemented CLI, VC6 parsing, analysis pipeline, build probe, evidence preparation, finalizer, and VS Code thin adapter are broadly aligned with the Step 02-18 direction. The strongest evidence is the existing test suite, current CLI smoke behavior for the relative-source workflow, and the VS Code adapter unit tests.

However, the review found four material gaps:

1. Finalized `function_dossier.json` no longer matches the repository schema or the original dossier contract.
2. `analyze-function --source` fails with exit 10 for an absolute source path, even though plans and examples use `--source PATH` and some examples show absolute paths.
3. Step17 stale/cross-artifact validation is only partially implemented.
4. Operator-facing docs and the VS Code task template still describe mostly the Step16-compatible flow and omit the Step17/18 review workflow path.

## Findings

### DCR-001: Finalized dossier schema diverges from `schemas/function_dossier.schema.json`

Severity: **High**

Status: **Open**

Relevant documents:

- `docs/function_level_vc6_unit_test_codex_design.md` defines `function_dossier.json` with `schema_version`, `target`, `project_membership`, `build_context`, `function`, `test_design`, and `diagnostics`.
- `schemas/function_dossier.schema.json` requires the same fields.
- `docs/implementation/step17_function_dossier_finalizer_review_workflow_plan.md` adds final dossier fields such as `artifact_index`, `traceability`, `review_items`, `unresolved_items`, `next_actions`, and `readiness`.

Observed behavior:

- `analyze-function --finalize-dossier` overwrites `reports/function_dossier.json` with a Step17 final dossier shape.
- The generated final dossier keys were:
  - `schema_version`
  - `function`
  - `workspace_root`
  - `created_at`
  - `artifact_index`
  - `summaries`
  - `traceability`
  - `review_items`
  - `unresolved_items`
  - `next_actions`
  - `readiness`
  - `warnings`
- Required schema fields missing from the finalized dossier:
  - `target`
  - `project_membership`
  - `build_context`
  - `test_design`
  - `diagnostics`

Impact:

- A consumer validating `reports/function_dossier.json` against the checked-in schema will reject finalized dossiers.
- `build-probe --dossier` and `generate-test-draft --dossier` semantics become ambiguous after finalization because the same filename is used for two incompatible dossier shapes.
- The design document, schema, and finalizer contract no longer describe one stable public artifact.

Recommendation:

- Either update `schemas/function_dossier.schema.json` to cover the finalized Step17 shape, or split schemas into legacy analysis dossier and finalized dossier.
- Preserve the original analysis context under stable final dossier keys, or store the pre-finalized dossier separately with an explicit name.
- Add a regression that validates both normal `analyze-function` output and `--finalize-dossier` output against the intended schema.

### DCR-002: Absolute `--source` path exits 10 instead of normalizing or rejecting cleanly

Severity: **High**

Status: **Open**

Relevant documents:

- Public interfaces describe `--source <c-file>` / `--source PATH`.
- Several implementation-plan examples use absolute paths for source inputs.
- Step02 requires input errors to exit 1, missing files to exit 2, and unexpected exceptions only for true internal failures.
- The design requires production source trees to be read-only inputs.

Observed behavior:

Command shape used in review:

```powershell
py -m unit_test_runner --json analyze-function `
  --workspace <fixture-root> `
  --dsw <fixture-root>\Product.dsw `
  --source <fixture-root>\src\control.c `
  --function Control_Update `
  --configuration "Win32 Debug" `
  --project Control `
  --out <temp-output>
```

Result:

- Exit code: `10`
- JSON status: `internal_error`
- Error came from the extraction/copy path handling an absolute source path incorrectly.

Impact:

- A documented input form produces an internal error rather than a user-actionable input error.
- The copy target can collapse onto the production source path when an absolute source is combined with `out/extracted`, which violates the read-only-source-tree safety intent even if the current failure prevents a successful write.

Recommendation:

- Normalize absolute source paths to workspace-relative paths when they are under `--workspace`.
- Reject sources outside `--workspace` with exit 1 or exit 2 and a clear JSON error.
- Add regression tests for absolute source inside workspace, relative source, and source outside workspace.

### DCR-003: Step17 stale artifact / cross-reference validation is incomplete

Severity: **Medium**

Status: **Open**

Relevant documents:

- Step17 requires artifact existence, hash, schema version, stale artifact candidate detection, function-name consistency, source-path consistency, and cross-reference inconsistency detection.

Observed behavior:

- Artifact collection records existence, SHA-256, and schema version.
- Function-name mismatch is checked.
- `DossierArtifact.stale_candidate` exists but no current code path sets it to `true`.
- Source path is discovered, but source path consistency is not compared across artifacts.
- Cross-reference validation is not yet a strict consistency pass; traceability gaps are represented conservatively.

Impact:

- A mixed workspace containing stale reports from a prior run can be marked reviewable without clearly flagging stale artifact candidates.
- Reviewers may trust a dossier that combines artifacts from different source/function generations.

Recommendation:

- Record artifact modified timestamps and compare them to `input/request.json`, source digest, function name, and source path.
- Set `stale_candidate` with warnings when function/source/timestamp/hash consistency is suspicious.
- Add stale-artifact and mismatched-source tests.

### DCR-004: Operator docs and task template are behind Step17/18

Severity: **Medium**

Status: **Open**

Relevant documents:

- Step17 adds `finalize-dossier`, `prepare-review`, `analyze-function --finalize-dossier`, and review artifacts.
- Step18 makes `--finalize-dossier` the default VS Code analyze path through the extension setting.

Observed behavior:

- `README.md` and `docs/v0.1_smoke_sample.md` still primarily show the Step16-compatible flow:
  - `analyze-function`
  - `build-probe --dossier <reports/function_dossier.json>`
  - `generate-test-draft --dossier <reports/function_dossier.json>`
- They do not document the review-finalization path:
  - `analyze-function --finalize-dossier`
  - `finalize-dossier --workspace`
  - `prepare-review --dossier`
  - `run-tests`
  - `prepare-evidence`
- `templates/vscode/tasks.json` does not pass `--json` or `--finalize-dossier`, even though Step18's extension path does.

Impact:

- Operators can follow current docs and miss Step17 review artifacts such as `dossier_manifest.json`, `traceability_matrix.csv`, `review_checklist.md`, `unresolved_items.md`, and `next_actions.md`.
- Operators can accidentally use the same `function_dossier.json` filename for both legacy and finalized shapes without understanding the difference.

Recommendation:

- Update README and smoke docs with two explicit flows:
  - Step16-compatible legacy analysis flow for `build-probe --dossier`.
  - Step17 finalized review flow for human review and VS Code integration.
- Update `templates/vscode/tasks.json` or add a second task for finalized analysis.
- Call out the schema/filename distinction from DCR-001 once resolved.

### DCR-005: Step18 acceptance coverage is representative, not one-to-one

Severity: **Low**

Status: **Open**

Relevant documents:

- Step18 lists VSC-001 through VSC-017 and completion items for settings, function target resolution, command building, JSON parsing, report opening, safety confirmation, timeout handling, and copying the last command.

Observed behavior:

- `npm.cmd test` covers core adapter behavior in one consolidated suite.
- The suite verifies settings warnings, regex target resolution, command argv construction, report path parsing, and confirmation behavior.
- Some Step18 items are not directly asserted one-to-one, notably timeout behavior, missing-report warning behavior, command palette activation, and copy-last-command behavior.

Impact:

- Current tests are useful smoke/regression coverage, but they do not fully prove every Step18 acceptance row.

Recommendation:

- Either add tests named around VSC-001 through VSC-017 or update Step18 to state which acceptance rows are covered by consolidated adapter tests and which remain manual.

## Compliance Matrix

| Area | Status | Evidence / Notes |
|---|---|---|
| Step02 CLI entry point | Pass with one related gap | CLI package split, global options, `doctor`, JSON stdout, log file, exit codes, and `not_implemented` helper are implemented. Absolute `--source` path handling is covered by DCR-002. |
| Step03 DSW parser | Pass | DSW parser exists, CP932 fallback is supported, and tests cover minimal, dependencies, malformed, missing DSP, multiple projects, and spaces in paths. |
| Step04 DSP parser | Pass | DSP parser extracts configurations, files, defines, includes, PCH flags, forced includes, unresolved macros, and full/short configuration names. |
| Step05 lexer/masker | Pass | Source reader supports `utf-8-sig`, `utf-8`, `cp932`, and `shift_jis`; masker tests cover comments/strings and fake braces. |
| Step06 function locator | Pass | Function location and list-functions paths are implemented and tested. |
| Step07-11 analyzers | Pass with residual heuristic risk | Signature, globals, calls, coverage/branch design, and boundary/equivalence candidates are generated and tested. The implementation remains intentionally lightweight. |
| Step12 test case draft | Pass | JSON/Markdown/CSV draft generation and CLI paths are covered. |
| Step13 harness skeleton | Pass with residual compiler risk | Generated C artifacts are CP932/CRLF and avoid known C99 markers. A real VC6 compile remains optional/manual. |
| Step14 build workspace/probe | Pass | Dry-run generation works without VC6; log parser handles include, PCH, unresolved symbol, and VC6 compatibility diagnostics. |
| Step15 build completion loop | Pass | Build completion planning and safe generated-stub application are implemented with review-required outputs. |
| Step16 evidence preparation | Pass | Dry-run execution evidence, result files, evidence manifest, and evidence package are implemented. |
| Step17 dossier finalizer | Partial | Finalizer, review files, traceability, readiness, and partial dossier handling exist. Schema divergence and stale/cross-reference validation gaps remain. |
| Step18 VS Code thin adapter | Partial | Thin adapter is implemented and tested at core seams. Some acceptance rows remain covered only indirectly or manually. |
| ADR-0001 language/encoding | Pass | Runtime Python core has no project dependencies; TypeScript is confined to VS Code adapter; generated C writer uses CP932/CRLF. |
| Production tree read-only policy | Partial | Relative-source smoke preserves fixture source. Absolute `--source` path handling has a safety bug; see DCR-002. |
| Documentation freshness | Partial | Implementation plans exist through Step18. README, smoke sample, schema, and task template need updates for finalized review flow. |

## Verification Performed During Review

Commands and observations:

- `git ls-files | Select-String -Pattern '__pycache__|\.pyc$|node_modules|dist/'`
  - No generated Python/Node build outputs are tracked.
- `git status --short --ignored | Select-String -Pattern '__pycache__|\.pyc|node_modules|dist|^!!|^\?\?'`
  - Generated caches and VS Code build outputs are ignored.
- Absolute source CLI reproduction:
  - `analyze-function` with an absolute `--source` exited `10` with JSON status `internal_error`.
- Finalized dossier schema reproduction:
  - `analyze-function --finalize-dossier` produced a final dossier missing current schema-required keys `target`, `project_membership`, `build_context`, `test_design`, and `diagnostics`.

Full test gates should be rerun after committing this review document. Because this change is documentation-only, any test failure after this point should be treated as pre-existing implementation behavior unless the review document itself is wired into a docs gate.

## Recommended Next Actions

1. Fix DCR-001 before treating finalized `function_dossier.json` as a stable public artifact.
2. Fix DCR-002 before recommending absolute source paths in docs or VS Code settings.
3. Implement or explicitly defer stale artifact validation from DCR-003.
4. Refresh README, smoke sample, and VS Code task template after the schema/filename decision is made.
5. Expand Step18 adapter tests or mark specific VSC rows as manual acceptance checks.
