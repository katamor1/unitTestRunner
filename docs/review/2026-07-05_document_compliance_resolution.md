# 2026-07-05 Document Compliance Review Resolution

This document records the implementation response to
`docs/review/2026-07-05_document_compliance_review.md`.

## Resolution Summary

All five reviewed items have been addressed in the `codex/dcr-review-fixes` worktree.

| Finding | Resolution |
|---|---|
| DCR-001 finalized dossier schema divergence | `function_dossier.json` now preserves the original public dossier contract fields after dossier review finalization and adds review workflow fields alongside them. Regression coverage verifies the required schema keys and downstream `build-probe --dossier` / `generate-test-design --dossier` behavior. |
| DCR-002 absolute `--source` path exits 10 | `analyze-function` now normalizes absolute source paths under `--workspace` to workspace-relative paths. Absolute sources outside the workspace are rejected as input errors instead of internal errors. |
| DCR-003 stale artifact / cross-reference validation incomplete | Artifact index entries now include `modified_at`; artifacts older than `input/request.json` are marked `stale_candidate`; function/source mismatches flag the related artifact as stale and emit review warnings. |
| DCR-004 operator docs and task template behind dossier review / VS Code adapter work | README, smoke sample, and VS Code task template now document/use the finalized review flow with `--json` and `--finalize-dossier`, while keeping the analysis and test design flow visible. |
| DCR-005 VS Code adapter acceptance coverage representative only | VS Code adapter tests now directly cover timeout handling, missing report-path fallback warnings, command palette activation declarations, and copy-last-command contribution. |

## Verification Evidence

Commands run in the separated worktree:

```powershell
py -m unittest tests.test_dossier_review_workflow.DossierReviewWorkflowTests.test_cli_finalize_prepare_review_and_analyze_function_dossier_review
py -m unittest tests.test_cli_entry_point_contract.CliEntryPointContractTests.test_analyze_function_accepts_absolute_source_inside_workspace tests.test_cli_entry_point_contract.CliEntryPointContractTests.test_analyze_function_rejects_absolute_source_outside_workspace_as_input_error
py -m unittest tests.test_dossier_review_workflow.DossierReviewWorkflowTests.test_finalize_marks_source_mismatch_and_old_artifacts_as_stale_candidates
py -m unittest tests.test_vscode_adapter.VscodeAdapterTests.test_vscode_task_template_uses_json_and_finalized_review_flow
py -m unittest tests.test_dossier_review_workflow tests.test_cli_entry_point_contract tests.test_cli_workflow tests.test_vscode_adapter
py -m unittest discover -s tests -p "test_*.py"
py -m compileall src tests
npm.cmd test
```

Observed results before this document was added:

- Python focused regression groups: pass.
- Python full suite: 96 tests, OK.
- Python compileall: exit 0.
- VS Code extension suite: 8 tests, pass.

## Remaining Notes

- Real VC6 execution remains an optional/manual acceptance check, consistent with the v0.1 assumptions.
- `function_dossier.json` is still the stable public path. Finalization enriches it rather than replacing it with an incompatible shape.
