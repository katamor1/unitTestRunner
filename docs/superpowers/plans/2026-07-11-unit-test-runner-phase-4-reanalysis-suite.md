# Unit Test Runner Phase 4 Reanalysis and Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve human-authored tests safely across code/build-context changes and execute portable regression suites without running stale artifacts.

**Architecture:** Separate semantic identity from display order, snapshot all inputs that affect generated behavior, and reconcile base/generated/manual states with a three-way merge. Store suite paths relative to a manifest anchor, validate source/spec/harness/binary fingerprints before execution, execute selected case IDs, and retain immutable suite run history.

**Tech Stack:** Python 3.12 dataclasses, Phase 1 contracts/run store, Phase 2 semantic IDs, existing reanalysis/suite packages, TypeScript suite panels.

## Global Constraints

- Phase 1 canonical test-spec and Phase 2 semantic IDs are prerequisites.
- Human-owned oracle, input, state, stub, and dependency override fields are never overwritten silently.
- Unknown or conflicting changes are selected for regression and review; they are not optimized away.
- A stale executable is never run by default.
- Suite manifest paths are portable and resolved relative to the manifest, not process CWD.
- A dry run is `planned`, not `completed` or `passed`.
- Any selected Not GREEN entry makes a normal suite run nonzero; `--require-green` becomes compatibility syntax, not the only strict mode.

---

### Task 1: Generate stable semantic coverage and case IDs

**Files:**

- Create: `src/unit_test_runner/test_design/semantic_identity.py`
- Modify: `src/unit_test_runner/c_analyzer/coverage_design_analyzer.py`
- Modify: `src/unit_test_runner/c_analyzer/coverage_models.py`
- Modify: `src/unit_test_runner/test_design/test_case_design_generator.py`
- Modify: `src/unit_test_runner/test_design/test_case_models.py`
- Modify: `src/unit_test_runner/schemas/test_spec.schema.json`
- Create: `tests/test_reanalysis_semantic_identity.py`
- Modify: `tests/test_test_case_design_generation.py`

**Interfaces:**

```python
def semantic_coverage_id(*, function_id: str, source_relative_path: str,
                         control_flow_anchor: str, condition_kind: str,
                         normalized_condition: str, branch_role: str) -> str: ...

def semantic_test_case_id(*, function_id: str, coverage_ids: Sequence[str],
                          case_kind: str, logical_variant: str) -> str: ...
```

IDs use a readable prefix plus a truncated SHA-256 fingerprint. `display_order` is a separate integer.

- [ ] **Step 1: Write order-independence tests**

Prepend a new branch/candidate and reorder equivalent coverage. Existing semantic IDs must not change; only display order changes.

- [ ] **Step 2: Normalize semantic inputs**

Normalize whitespace, source-relative path, function semantic ID, condition kind, and branch role. Preserve integer suffix, width, and signedness (`1`, `1U`, and `1L` are not automatically equivalent under VC6). Build `control_flow_anchor` from the enclosing semantic control-flow chain and stable local condition anchor. Human inputs, oracles, titles, branch-body contents, and display order never participate in identity. Store branch-body fingerprint separately in the reanalysis snapshot for change detection.

When two nodes remain semantically indistinguishable, persist an explicit prior-ID mapping and emit a merge conflict rather than assigning by current array order.

- [ ] **Step 3: Generate stable coverage and case IDs**

Retain legacy IDs only as migration aliases. Validate ID uniqueness in the test-spec semantic validator.

- [ ] **Step 4: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_reanalysis_semantic_identity tests.test_test_case_design_generation -v
git add src/unit_test_runner/c_analyzer src/unit_test_runner/test_design src/unit_test_runner/schemas/test_spec.schema.json tests
git commit -m "feat: identify coverage and tests by semantic fingerprint"
```

---

### Task 2: Snapshot and compare every generation-relevant input

**Files:**

- Modify: `src/unit_test_runner/reanalysis/reanalysis_models.py`
- Modify: `src/unit_test_runner/reanalysis/snapshot_builder.py`
- Modify: `src/unit_test_runner/reanalysis/current_analysis.py`
- Modify: `src/unit_test_runner/reanalysis/workflow.py`
- Modify: `src/unit_test_runner/reanalysis/dependency_diff.py`
- Create: `src/unit_test_runner/reanalysis/build_context_diff.py`
- Modify: `tests/test_reanalysis_snapshot_builder.py`
- Create: `tests/test_reanalysis_build_context.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ReanalysisFingerprint:
    source_sha256: str
    signature_sha256: str
    build_context_sha256: str
    dependency_policy_sha256: str
    coverage_sha256: str
    type_context_sha256: str

@dataclass(frozen=True)
class BuildContextChange:
    category: str
    before: tuple[str, ...]
    after: tuple[str, ...]
    affected_source_ids: tuple[str, ...]
    impact: str
```

- [ ] **Step 1: Write build-context-only change tests**

Change only define value, include path, PCH mode, source exclusion, linked library, dependency policy mode, and type-defining header. Each must appear in change impact even when target source bytes are unchanged.

- [ ] **Step 2: Persist normalized payload fingerprints**

Hash canonical JSON with sorted keys and normalized workspace-relative paths. Store artifact contract version and producer version with each fingerprint.

- [ ] **Step 3: Implement all published reanalysis policy switches or remove them**

`compare_build_context`, `compare_dependencies`, `compare_coverage`, `preserve_manual_edits`, `reuse_test_case_ids`, and `select_regression_tests` must change behavior in on/off tests. Since the product is unreleased, delete any option that has no supported use case.

- [ ] **Step 4: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_reanalysis_snapshot_builder tests.test_reanalysis_build_context \
  tests.test_reanalysis_diff -v
git add src/unit_test_runner/reanalysis tests
git commit -m "feat: detect source dependency and build-context changes"
```

---

### Task 3: Replace pairwise reconciliation with a three-way merge

**Files:**

- Rewrite: `src/unit_test_runner/reanalysis/test_case_reconciler.py`
- Create: `src/unit_test_runner/reanalysis/generated_base_store.py`
- Modify: `src/unit_test_runner/reanalysis/reanalysis_models.py`
- Modify: `src/unit_test_runner/reanalysis/workflow.py`
- Modify: `src/unit_test_runner/test_spec/models.py`
- Modify: `src/unit_test_runner/test_spec/repository.py`
- Modify: `tests/test_test_case_reconciler.py`
- Modify: `tests/test_reanalysis_cli.py`
- Create: `tests/test_test_spec_three_way_merge.py`
- Create: `tests/test_generated_base_store.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class MergeConflict:
    case_id: str
    field_path: str
    base_value: Any
    manual_value: Any
    generated_value: Any
    reason: str

@dataclass
class ThreeWayMergeResult:
    merged_spec: TestSpec
    preserved_fields: list[str]
    generated_updates: list[str]
    new_required_case_ids: list[str]
    obsolete_case_ids: list[str]
    conflicts: list[MergeConflict]

def merge_test_specs(base_generated: TestSpec, manual_current: TestSpec,
                     newly_generated: TestSpec) -> ThreeWayMergeResult: ...

def save_generated_base(workspace: Path, spec: TestSpec) -> ArtifactReference: ...
def load_generated_base(workspace: Path,
                        artifact: ArtifactReference) -> TestSpec: ...
```

- [ ] **Step 1: Write ownership/conflict tests**

Cover manual-only oracle edit, generator-only coverage update, both editing the same field, dependency override preservation, new coverage with a colliding legacy display ID, removed coverage, and reordered cases.

- [ ] **Step 2: Store the generated base revision**

Every generated base is stored immutably under `history/generated/<spec_id>/<revision>-<sha256>.json`. Every manual spec references that exact path, revision, and hash. Refuse three-way merge when the base bytes are missing or hash-invalid.

- [ ] **Step 3: Implement field-level merge**

Human-owned fields are inputs, state, stubs, dependency overrides, oracles, titles/notes, and review-item associations. Approval state is never stored in TestSpec; it is derived from the decision ledger. Generator-owned fields are source/coverage provenance and fresh analysis links. Both-changed fields produce `MergeConflict`.

- [ ] **Step 4: Always materialize new required cases**

Append every new semantic case to `merged_spec.test_cases` with stable review-item IDs and unresolved items; do not add a `review_required` status field and do not merely list the case in a report. The decision ledger derives it as open until approved. Ensure exactly one case per new semantic requirement.

- [ ] **Step 5: Write atomically with revision guard and rollback copy**

Require current revision and validate the merged contract. If any conflict exists, write only a merge-proposal/report under history and leave canonical `test_spec.json` byte-for-byte unchanged. With zero conflicts, write temporary, rename atomically, and retain the previous revision under workspace history.

- [ ] **Step 6: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_test_case_reconciler tests.test_test_spec_three_way_merge \
  tests.test_generated_base_store \
  tests.test_reanalysis_cli -v
git add src/unit_test_runner/reanalysis src/unit_test_runner/test_spec tests
git commit -m "feat: merge generated and manual tests with three-way reconciliation"
```

---

### Task 4: Make regression selection conservative and case-executable

**Files:**

- Modify: `src/unit_test_runner/reanalysis/regression_selector.py`
- Modify: `src/unit_test_runner/reanalysis/reanalysis_models.py`
- Modify: `src/unit_test_runner/execution/test_execution.py`
- Modify: `src/unit_test_runner/execution/execution_models.py`
- Modify: `src/unit_test_runner/cli/parser.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `tests/test_regression_selector.py`
- Create: `tests/test_case_filtered_execution.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class RegressionCaseSelection:
    case_id: str
    selected: bool
    reasons: tuple[str, ...]
    confidence: str
    blocking: bool

def select_regression_cases(change_set: ChangeSet,
                            spec: TestSpec) -> list[RegressionCaseSelection]: ...

def execute_test_run(request: TestRunRequest,
                     case_ids: Sequence[str] | None = None) -> TestExecutionReport: ...
```

- [ ] **Step 1: Add conservative selection tests**

Signature, dependency, build context, type, coverage, unresolved mapping, merge conflict, and stale review changes select related cases. Unknown mapping selects all cases for the function.

- [ ] **Step 2: Connect selected case IDs to execution**

Pass exact case IDs to the generated runner. Report requested, started, completed, and not-run IDs; missing selected output is non-GREEN.

- [ ] **Step 3: Explain every selection**

JSON/Markdown/CSV contain deterministic reason codes and source change IDs, not only a selected boolean.

- [ ] **Step 4: Run and commit**

```bash
PYTHONPATH=src python -m unittest tests.test_regression_selector tests.test_case_filtered_execution -v
git add src/unit_test_runner/reanalysis src/unit_test_runner/execution src/unit_test_runner/cli tests
git commit -m "feat: execute conservative case-level regression selections"
```

---

### Task 5: Make suite manifests portable and preserve manual metadata

**Files:**

- Modify: `src/unit_test_runner/suite/models.py`
- Modify: `src/unit_test_runner/suite/manager.py`
- Create: `src/unit_test_runner/suite/repository.py`
- Create: `src/unit_test_runner/suite/path_resolver.py`
- Modify: `src/unit_test_runner/schemas/suite_manifest.schema.json`
- Modify: `src/unit_test_runner/contracts/kinds.py`
- Modify: `src/unit_test_runner/contracts/registry.py`
- Modify: `src/unit_test_runner/cli/parser.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `tests/test_suite_manager.py`
- Modify: `tests/test_suite_cli.py`
- Create: `tests/test_suite_portability.py`

**Interfaces:**

```python
@dataclass
class SuiteEntry:
    entry_id: str
    enabled: bool
    tags: list[str]
    function_id: str
    workspace_uri: str
    test_spec_revision: int
    fingerprints: SuiteEntryFingerprints
    registered_at: str

@dataclass
class SuiteManifest:
    suite_id: str
    revision: int
    entries: list[SuiteEntry]

def resolve_suite_uri(manifest_path: Path, uri: str) -> Path: ...
def register_entry(manifest: SuiteManifest, candidate: SuiteEntry, *,
                   replace_metadata: bool = False) -> SuiteManifest: ...
def save_suite_manifest(path: Path, manifest: SuiteManifest, *,
                        expected_revision: int) -> ProducedArtifact: ...
```

- [ ] **Step 1: Write relocation and CWD-independence tests**

Move the entire suite/output tree and load from an unrelated process CWD. All entries must resolve to the moved tree.

- [ ] **Step 2: Replace absolute paths with manifest-relative URIs**

Use normalized POSIX relative URIs. Reject traversal outside an allowed suite/output root unless explicitly external and read-only.

- [ ] **Step 3: Preserve manual tags and enabled state on re-registration**

Default re-registration updates generated fingerprints/target metadata only. Replace tags/enabled only under explicit `replace_metadata=True`.

- [ ] **Step 4: Reject empty selectors**

Unknown tags, all-disabled selections, or missing entry IDs return input/non-GREEN status rather than successful total=0.

- [ ] **Step 5: Add revision-checked suite management commands**

Add:

```text
suite-entry-update --suite <path> --entry-id <id> --expected-revision <n>
  [--tags <csv>] [--enabled true|false]
suite-entry-remove --suite <path> --entry-id <id> --expected-revision <n>
```

Update the Phase 1 `suite_manifest` schema and registry entry for the portable revisioned shape, validate before atomic replacement, and return the new manifest revision/hash.

- [ ] **Step 6: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_suite_manager tests.test_suite_cli tests.test_suite_portability -v
git add src/unit_test_runner/suite src/unit_test_runner/schemas/suite_manifest.schema.json src/unit_test_runner/contracts src/unit_test_runner/cli tests
git commit -m "feat: make suite manifests portable and metadata-safe"
```

---

### Task 6: Prevent stale execution and retain immutable suite history

**Files:**

- Create: `src/unit_test_runner/suite/staleness.py`
- Create: `src/unit_test_runner/suite/run_store.py`
- Modify: `src/unit_test_runner/suite/models.py`
- Modify: `src/unit_test_runner/suite/manager.py`
- Modify: `src/unit_test_runner/suite/report_writer.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `src/unit_test_runner/schemas/suite_run_report.schema.json`
- Modify: `src/unit_test_runner/schemas/latest_suite_run_pointer.schema.json`
- Create: `tests/test_suite_staleness.py`
- Create: `tests/test_suite_run_history.py`
- Modify: `tests/test_suite_manager.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class StalenessResult:
    stale: bool
    changed_inputs: tuple[str, ...]
    diagnostics: tuple[str, ...]

@dataclass(frozen=True)
class SuiteEntryRunRef:
    entry_id: str
    function_run_id: str
    execution_report_uri: str
    execution_report_sha256: str
    test_spec_revision: int
    test_spec_sha256: str
    harness_sha256: str
    binary_sha256: str
    outcome: RunOutcome

def assess_suite_entry_staleness(entry: SuiteEntry,
                                 manifest_path: Path) -> StalenessResult: ...
def create_suite_run_paths(suite_root: Path,
                           run_id: str | None = None) -> SuiteRunPaths: ...
```

- [ ] **Step 1: Add source/spec/harness/binary staleness tests**

Changing any fingerprint blocks default execution before spawning a binary and provides exact changed inputs.

- [ ] **Step 2: Store immutable run results**

Write `runs/<run_id>/suite_run_report.{json,md,csv}` and update only `reports/latest.json`. Two executions retain two histories. Each result stores `SuiteEntryRunRef` pointing to the immutable Phase 1 function run by run ID, report URI/hash, and the exact spec/harness/binary fingerprints; it never points only to a mutable `latest` file.

- [ ] **Step 3: Normalize suite outcomes**

Use the shared `RunOutcome` only. `running` is lifecycle, `not_green` is a derived display grouping, and stale preflight becomes `blocked` with diagnostic code `stale_input`. A plan is not passed; any selected outcome other than `passed` produces a nonzero process exit.

- [ ] **Step 4: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_suite_staleness tests.test_suite_run_history tests.test_suite_manager -v
git add src/unit_test_runner/suite src/unit_test_runner/cli src/unit_test_runner/schemas/suite_run_report.schema.json src/unit_test_runner/schemas/latest_suite_run_pointer.schema.json tests
git commit -m "feat: block stale suite entries and preserve run history"
```

---

### Task 7: Add complete suite management and history UX

**Files:**

- Modify: `vscode/extension/src/suite/suiteViewModel.ts`
- Modify: `vscode/extension/src/suite/suitePanel.ts`
- Modify: `vscode/extension/src/suite/suiteDashboard.ts`
- Modify: `vscode/extension/src/extension.ts`
- Create: `vscode/extension/src/test/suiteManagement.test.ts`
- Create: `vscode/extension/src/test/suiteHistory.test.ts`
- Modify: `vscode/extension/src/test/extensionHost/index.ts`

**Interfaces:**

```typescript
export interface SuiteFilters {
  query: string;
  tags: readonly string[];
  state: 'all' | 'enabled' | 'disabled' | 'stale' | 'not_green';
  sort: 'function' | 'lastRun' | 'duration' | 'status';
}
```

- [ ] **Step 1: Add tag/edit/enable/remove operations through CLI commands**

Do not edit manifest JSON directly in Webview code. Require revision checks and show conflicts.

- [ ] **Step 2: Disable invalid selections visibly**

Disabled or stale entries cannot be checked. Render accessible labels and the exact reason.

- [ ] **Step 3: Add search, tag filters, sort, and bulk selection**

Scope selection by manifest identity, prune removed IDs, and never carry hidden selections across manifest changes.

- [ ] **Step 4: Add run history drill-down**

Show run ID, time, duration, status, fingerprints, changed/stale reasons, and per-case failures. All suite runs use the Phase 3 execution coordinator.

- [ ] **Step 5: Run and commit**

```bash
cd vscode/extension
npm run compile
node --test --test-name-pattern="suite management|suite history" dist/test/*.test.js
npm run test:extension-host
git add vscode/extension/src
git commit -m "feat: manage portable suite entries and run history"
```

---

## Phase 4 Completion Check

- [ ] Coverage/case IDs are independent of generation order.
- [ ] Build-context-only and dependency-policy changes are detected.
- [ ] Three-way merge preserves manual fields and emits explicit conflicts.
- [ ] New required cases are inserted exactly once.
- [ ] Regression selection is conservative, explained, and executable by case ID.
- [ ] Suite paths remain valid after relocation and CWD changes.
- [ ] Re-registration preserves tags and enabled state.
- [ ] Empty selectors do not report success.
- [ ] Stale inputs block before binary spawn.
- [ ] Every suite run has immutable history and a truthful exit status.
- [ ] Suite GUI supports accessible management, filtering, and failure/history drill-down.
