# Unit Test Runner Phase 1 Contract, Execution, and Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every machine-readable result versioned and validated, make test outcomes truthful at the process boundary, and make execution/evidence immutable and reviewable.

**Architecture:** Introduce a contract kernel used by artifact readers/writers, then split test execution from evidence preparation. Build a versioned CLI envelope on semantic outcomes, introduce `test_spec.json` as the only editable test definition, and persist review decisions against artifact revisions and hashes.

**Tech Stack:** Python 3.12 dataclasses and `StrEnum`, JSON Schema Draft 2020-12, `jsonschema>=4.23,<5`, existing CLI and report models, TypeScript CLI adapter.

## Global Constraints

- Phase 0 is GREEN before this phase starts.
- Artifact kind and artifact version are independent; different valid artifact versions may coexist.
- Compatible reads may migrate in memory; strict reads reject non-current versions.
- Input artifacts are never rewritten as a side effect of loading or validation.
- `prepare-evidence` never executes tests and never rewrites execution results or logs.
- Failed tests may have complete review evidence, but can never be GREEN.
- CSV/Markdown are export-only and never become workflow approval inputs.
- `review_decisions.json` is the only approval authority. Test specs and typed values contain review-item references, never an independent approved flag.
- All Python, CLI, dossier, VS Code, and suite terminal results use `RunOutcome`: `planned`, `passed`, `failed`, `blocked`, `inconclusive`, `cancelled`, `timed_out`, or `error`.

---

### Task 1: Add the contract kernel and artifact registry

**Files:**

- Create: `src/unit_test_runner/contracts/__init__.py`
- Create: `src/unit_test_runner/contracts/kinds.py`
- Create: `src/unit_test_runner/contracts/models.py`
- Create: `src/unit_test_runner/contracts/registry.py`
- Create: `src/unit_test_runner/contracts/validator.py`
- Create: `src/unit_test_runner/contracts/migrations.py`
- Create: `src/unit_test_runner/schemas/__init__.py`
- Create: `src/unit_test_runner/schemas/common.schema.json`
- Create: `src/unit_test_runner/schemas/cli_result.schema.json`
- Create: `src/unit_test_runner/schemas/input_request.schema.json`
- Create: `src/unit_test_runner/schemas/dsw_discovery.schema.json`
- Create: `src/unit_test_runner/schemas/source_membership.schema.json`
- Create: `src/unit_test_runner/schemas/project_membership.schema.json`
- Create: `src/unit_test_runner/schemas/build_context.schema.json`
- Create: `src/unit_test_runner/schemas/source_digest.schema.json`
- Create: `src/unit_test_runner/schemas/function_location.schema.json`
- Create: `src/unit_test_runner/schemas/function_signature.schema.json`
- Create: `src/unit_test_runner/schemas/global_access.schema.json`
- Create: `src/unit_test_runner/schemas/call_report.schema.json`
- Create: `src/unit_test_runner/schemas/coverage_design.schema.json`
- Create: `src/unit_test_runner/schemas/boundary_candidates.schema.json`
- Create: `src/unit_test_runner/schemas/dependency_policy.schema.json`
- Create: `src/unit_test_runner/schemas/test_spec.schema.json`
- Create: `src/unit_test_runner/schemas/harness_skeleton_report.schema.json`
- Create: `src/unit_test_runner/schemas/build_workspace_report.schema.json`
- Create: `src/unit_test_runner/schemas/build_probe_report.schema.json`
- Create: `src/unit_test_runner/schemas/build_completion_plan.schema.json`
- Create: `src/unit_test_runner/schemas/build_completion_iteration.schema.json`
- Create: `src/unit_test_runner/schemas/build_completion_history.schema.json`
- Create: `src/unit_test_runner/schemas/test_execution_report.schema.json`
- Create: `src/unit_test_runner/schemas/test_result.schema.json`
- Create: `src/unit_test_runner/schemas/evidence_manifest.schema.json`
- Create: `src/unit_test_runner/schemas/function_dossier.schema.json`
- Create: `src/unit_test_runner/schemas/dossier_manifest.schema.json`
- Create: `src/unit_test_runner/schemas/state_setup_reflection.schema.json`
- Create: `src/unit_test_runner/schemas/review_decisions.schema.json`
- Create: `src/unit_test_runner/schemas/change_impact.schema.json`
- Create: `src/unit_test_runner/schemas/test_case_reconciliation.schema.json`
- Create: `src/unit_test_runner/schemas/regression_selection.schema.json`
- Create: `src/unit_test_runner/schemas/reanalysis_snapshot.schema.json`
- Create: `src/unit_test_runner/schemas/suite_manifest.schema.json`
- Create: `src/unit_test_runner/schemas/suite_run_report.schema.json`
- Create: `src/unit_test_runner/schemas/latest_run_pointer.schema.json`
- Create: `src/unit_test_runner/schemas/latest_evidence_pointer.schema.json`
- Create: `src/unit_test_runner/schemas/latest_suite_run_pointer.schema.json`
- Create: `src/unit_test_runner/schemas/evidence_source_run.schema.json`
- Create: `src/unit_test_runner/schemas/prompt_pack.schema.json`
- Create: `src/unit_test_runner/schemas/quick_summary.schema.json`
- Delete: `schemas/function_dossier.schema.json`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_contract_registry.py`
- Test: `tests/test_contract_validation.py`
- Test: `tests/test_contract_migrations.py`
- Test: `tests/test_public_artifact_schemas.py`
- Test: `tests/test_wheel_contract.py`

**Interfaces:**

```python
class ArtifactKind(StrEnum):
    CLI_RESULT = "cli_result"
    INPUT_REQUEST = "input_request"
    DSW_DISCOVERY = "dsw_discovery"
    SOURCE_MEMBERSHIP = "source_membership"
    PROJECT_MEMBERSHIP = "project_membership"
    BUILD_CONTEXT = "build_context"
    SOURCE_DIGEST = "source_digest"
    FUNCTION_LOCATION = "function_location"
    FUNCTION_SIGNATURE = "function_signature"
    GLOBAL_ACCESS = "global_access"
    CALL_REPORT = "call_report"
    COVERAGE_DESIGN = "coverage_design"
    BOUNDARY_CANDIDATES = "boundary_candidates"
    DEPENDENCY_POLICY = "dependency_policy"
    TEST_SPEC = "test_spec"
    HARNESS_SKELETON_REPORT = "harness_skeleton_report"
    BUILD_WORKSPACE_REPORT = "build_workspace_report"
    BUILD_PROBE_REPORT = "build_probe_report"
    BUILD_COMPLETION_PLAN = "build_completion_plan"
    BUILD_COMPLETION_ITERATION = "build_completion_iteration"
    BUILD_COMPLETION_HISTORY = "build_completion_history"
    TEST_EXECUTION_REPORT = "test_execution_report"
    TEST_RESULT = "test_result"
    EVIDENCE_MANIFEST = "evidence_manifest"
    FUNCTION_DOSSIER = "function_dossier"
    DOSSIER_MANIFEST = "dossier_manifest"
    STATE_SETUP_REFLECTION = "state_setup_reflection"
    REVIEW_DECISIONS = "review_decisions"
    CHANGE_IMPACT = "change_impact"
    TEST_CASE_RECONCILIATION = "test_case_reconciliation"
    REGRESSION_SELECTION = "regression_selection"
    REANALYSIS_SNAPSHOT = "reanalysis_snapshot"
    SUITE_MANIFEST = "suite_manifest"
    SUITE_RUN_REPORT = "suite_run_report"
    LATEST_RUN_POINTER = "latest_run_pointer"
    LATEST_EVIDENCE_POINTER = "latest_evidence_pointer"
    LATEST_SUITE_RUN_POINTER = "latest_suite_run_pointer"
    EVIDENCE_SOURCE_RUN = "evidence_source_run"
    PROMPT_PACK = "prompt_pack"
    QUICK_SUMMARY = "quick_summary"

class ContractMode(StrEnum):
    COMPATIBLE = "compatible"
    STRICT = "strict"

class RunOutcome(StrEnum):
    PLANNED = "planned"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    ERROR = "error"

@dataclass(frozen=True)
class ContractViolation:
    code: str
    json_path: str
    message: str
    severity: str

@dataclass(frozen=True)
class LoadedArtifact:
    kind: ArtifactKind
    source_version: str
    current_version: str
    payload: dict[str, Any]
    migrated: bool
    violations: tuple[ContractViolation, ...]

def load_artifact(path: Path, *, expected_kind: ArtifactKind,
                  mode: ContractMode = ContractMode.COMPATIBLE) -> LoadedArtifact: ...
def validate_payload(kind: ArtifactKind,
                     payload: Mapping[str, Any]) -> tuple[ContractViolation, ...]: ...
def migrate_payload(kind: ArtifactKind, payload: Mapping[str, Any], *,
                    target_version: str) -> dict[str, Any]: ...
```

- [x] **Step 1: Write registry and negative-schema tests**

Cover missing `artifact_kind`, unsupported version, invalid enum, missing nested field, unknown property, duplicate ID, invalid reference, and invalid relative path.

Run:

```bash
PYTHONPATH=src python -m unittest \
  tests.test_contract_registry tests.test_contract_validation -v
```

Expected: import failure before the package exists.

- [x] **Step 2: Add the runtime dependency and common schema**

Every public JSON root must contain:

```json
{
  "artifact_kind": "test_spec",
  "schema_version": "1.0.0",
  "producer": {"name": "unit-test-runner", "version": "0.1.0", "commit": "ec85f0fe81a486a5ce4bba67be79c3a4624a7763"},
  "subject": {"function_id": "fn_control_update_7a32c11d", "source_path": "src/control.c", "source_sha256": "7b18e68b2afcf1b0f0a1b857c5d1fcb2cf9db4d1540d778a266dbeaa3aa176a8"},
  "data": {},
  "extensions": {}
}
```

Use `additionalProperties: false` at modeled object boundaries and an explicit `extensions` object for future additions.

- [x] **Step 3: Implement registry, structural validation, and semantic hooks**

The registry maps `(ArtifactKind, version)` to schema path, migration path, and semantic validator. Schema files must be included in the wheel/package.

The scope is every JSON written by a public CLI command or stored in a generated workspace, including input request, build context, project membership, state-setup reflection, dossier manifest, completion history, reanalysis, suite, pointers, and quick summary. CSV/Markdown/C sources are validated by their own writers and are not JSON artifact kinds. `test_case_design.json` is a legacy v0.1 input kind handled only by the TEST_SPEC migration and is not written after the v1 switch.

Load schemas with `importlib.resources.files("unit_test_runner.schemas")`; configure setuptools package data for `*.json`. Do not rely on the repository-root `schemas/` directory at runtime.

- [x] **Step 4: Implement v0.1 compatible migration**

Compatible mode converts existing top-level `schema_version: "0.1"` payloads in memory. Strict mode reports `unsupported_version` without modifying bytes.

- [x] **Step 5: Run all contract tests and commit**

Before commit, build a wheel into a temporary directory, install it into a fresh virtual environment, run `python -m unit_test_runner --help`, and load every registry schema through `importlib.resources`. Add this as the required CI `package-contract` job.

```bash
PYTHONPATH=src python -m unittest \
  tests.test_contract_registry tests.test_contract_validation \
  tests.test_contract_migrations tests.test_public_artifact_schemas \
  tests.test_wheel_contract -v
git add pyproject.toml .github/workflows/ci.yml src/unit_test_runner/contracts src/unit_test_runner/schemas schemas/function_dossier.schema.json tests/test_contract_*.py tests/test_public_artifact_schemas.py tests/test_wheel_contract.py
git commit -m "feat: add versioned artifact contract kernel"
```

Local verification record (2026-07-11, Linux 6.12.47 x86_64, Python 3.12.13):

- Contract registry, structural/semantic validation, migration, public-schema, and wheel tests: 21 passed.
- CI contract, tracked-source, and dossier compatibility tests: 14 passed.
- Full Python discovery: 298 passed with 2 expected platform skips.
- The built wheel was installed into a fresh venv with its already-downloaded runtime dependency set; CLI help succeeded and all 40 artifact schemas plus the common schema loaded through `importlib.resources`.
- The `package-contract` Windows job performs the complete online dependency installation from the wheel and remains the required remote package evidence.

---

### Task 2: Integrate contract status into dossier collection and readiness inputs

**Files:**

- Modify: `src/unit_test_runner/dossier/artifact_collector.py`
- Modify: `src/unit_test_runner/dossier/dossier_models.py`
- Modify: `src/unit_test_runner/dossier/dossier_validator.py`
- Modify: `src/unit_test_runner/dossier/finalizer.py`
- Modify: `src/unit_test_runner/harness/harness_report_writer.py`
- Modify: `src/unit_test_runner/build/build_report_writer.py`
- Test: `tests/test_dossier_review_workflow.py`
- Create: `tests/test_dossier_contract_status.py`
- Create: `tests/test_artifact_provenance_hashes.py`
- Modify: `tests/test_harness_report_localization.py`

**Interfaces:**

```python
@dataclass
class DossierArtifact:
    # existing fields
    contract_status: Literal[
        "valid", "missing", "parse_error", "schema_error",
        "unsupported_version", "stale"
    ]
    contract_violations: list[ContractViolation]
```

- [ ] **Step 1: Add malformed-shape and mixed-version tests**

An array where an object is required must produce `schema_error`, not internal exit 10. Two artifact kinds with different supported versions must be valid.

- [ ] **Step 2: Replace `.get()`-based shape assumptions with `load_artifact()`**

Map parse and validation errors to dossier warnings and blocked reasons. Do not catch them as generic internal errors.

- [ ] **Step 3: Correct strict version semantics**

`--strict-schema-version` means every loaded artifact is already current for its own kind; remove cross-artifact version equality.

- [ ] **Step 4: Make artifact hashes reproducible**

Do not put a file's own SHA-256 inside bytes that are rewritten after the hash is computed. Hash final artifact bytes from the external artifact index/manifest, or use a detached sidecar. Add a regeneration test asserting every recorded hash matches the final file.

- [ ] **Step 5: Keep machine enums stable**

Remove Japanese replacement of `placeholder_kind`, `hint_kind`, and `severity` from JSON writers. Add display labels only to Markdown/UI rendering.

- [ ] **Step 6: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_dossier_review_workflow tests.test_dossier_contract_status \
  tests.test_artifact_provenance_hashes tests.test_harness_report_localization -v
git add src/unit_test_runner/dossier src/unit_test_runner/harness/harness_report_writer.py src/unit_test_runner/build/build_report_writer.py tests
git commit -m "feat: validate dossier artifacts by contract kind"
```

---

### Task 3: Separate immutable test runs from evidence preparation

**Files:**

- Create: `src/unit_test_runner/execution/run_paths.py`
- Create: `src/unit_test_runner/execution/evidence_paths.py`
- Create: `src/unit_test_runner/execution/report_loader.py`
- Create: `src/unit_test_runner/execution/evidence_validator.py`
- Modify: `src/unit_test_runner/schemas/latest_run_pointer.schema.json`
- Modify: `src/unit_test_runner/schemas/latest_evidence_pointer.schema.json`
- Modify: `src/unit_test_runner/execution/test_execution.py`
- Modify: `src/unit_test_runner/execution/execution_models.py`
- Modify: `src/unit_test_runner/execution/test_result_writer.py`
- Modify: `src/unit_test_runner/execution/evidence_manifest.py`
- Modify: `src/unit_test_runner/cli/parser.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Test: `tests/test_execution_run_history.py`
- Test: `tests/test_prepare_evidence_non_destructive.py`
- Test: `tests/test_evidence_integrity.py`
- Modify: `tests/test_execution_evidence.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class TestRunRequest:
    workspace: Path
    executable: Path | None
    timeout_seconds: int
    allow_placeholder_tests: bool
    run_id: str | None = None

@dataclass(frozen=True)
class RunPaths:
    run_id: str
    root: Path
    execution_report: Path
    result_json: Path
    result_csv: Path
    stdout_log: Path
    stderr_log: Path
    combined_log: Path

@dataclass(frozen=True)
class EvidencePaths:
    evidence_id: str
    source_run_id: str
    root: Path
    evidence_manifest: Path
    evidence_package: Path

def create_run_paths(workspace: Path, run_id: str | None = None) -> RunPaths: ...
def execute_test_run(request: TestRunRequest) -> TestExecutionReport: ...
def load_test_execution_report(workspace: Path,
                               run_id: str | None = None) -> TestExecutionReport: ...
def prepare_evidence_from_existing_run(
    workspace: Path, run_id: str | None = None
) -> tuple[EvidencePaths, TestExecutionReport, EvidenceManifest]: ...
```

- [ ] **Step 1: Write a hash-preservation regression test**

Execute a fixture once, hash execution JSON and logs, call `prepare-evidence`, and assert every pre-existing hash is unchanged.

- [ ] **Step 2: Write two-run history tests**

Two runs must create two directories and update only `reports/latest_run.json` to the second run.

Two evidence preparations for one run must create two evidence revision directories, leaving both the execution run and earlier evidence revision unchanged.

- [ ] **Step 3: Implement run paths and writers**

Use:

```text
<workspace>/runs/<run_id>/
  test_execution_report.json
  test_result.json
  test_result.csv
  logs/stdout.log
  logs/stderr.log
  logs/test_execution.log
<workspace>/evidence/<evidence_id>/
  source_run.json
  evidence_manifest.json
  evidence_package.md
<workspace>/reports/latest_run.json
<workspace>/reports/latest_evidence.json
```

Generate IDs from UTC timestamp plus random suffix. Create directories with exclusive semantics; never reuse a run or evidence directory. `source_run.json` pins run ID, execution report path/hash, and log hashes.

- [ ] **Step 4: Make `prepare-evidence` load-only**

If no terminal execution report exists, return input error. It must not call the old combined execution/evidence function and must not write a dry-run report. It may write only a new `evidence/<evidence_id>` revision and `latest_evidence.json` pointer.

- [ ] **Step 5: Model evidence integrity explicitly**

```python
@dataclass
class EvidenceFile:
    path: Path
    file_kind: str
    required: bool
    exists: bool
    sha256: str | None
    integrity_status: Literal["valid", "missing", "hash_mismatch"]
```

`ready_for_review` is true only when required evidence exists and hashes validate. `test_green` is a separate field.

- [ ] **Step 6: Add v0.1 import without source overwrite**

Copy an existing `reports/test_execution_report.json` into `runs/imported-<timestamp>/`, migrate the copy, and write the pointer. Preserve the original.

- [ ] **Step 7: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_execution_run_history tests.test_prepare_evidence_non_destructive \
  tests.test_evidence_integrity tests.test_execution_evidence -v
git add src/unit_test_runner/execution src/unit_test_runner/cli src/unit_test_runner/schemas/latest_run_pointer.schema.json src/unit_test_runner/schemas/latest_evidence_pointer.schema.json tests
git commit -m "feat: preserve immutable test runs and evidence"
```

---

### Task 4: Normalize CLI outcomes, artifacts, and exit codes

**Files:**

- Create: `src/unit_test_runner/cli/outcomes.py`
- Create: `src/unit_test_runner/cli/artifacts.py`
- Modify: `src/unit_test_runner/cli/result.py`
- Modify: `src/unit_test_runner/cli/main.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `src/unit_test_runner/cli/exit_codes.py`
- Create: `vscode/extension/src/cli/cliEnvelope.ts`
- Modify: `vscode/extension/src/cli/cliResultParser.ts`
- Test: `tests/test_cli_result_contract.py`
- Test: `tests/test_cli_execution_exit_codes.py`
- Test: `tests/test_cli_artifact_references.py`
- Test: `vscode/extension/src/test/cliEnvelope.test.ts`

**Interfaces:**

```python
@dataclass(frozen=True)
class ProducedArtifact:
    kind: str
    path: str
    exists: bool
    sha256: str | None
    schema_version: str | None

@dataclass(frozen=True)
class DomainOutcome:
    kind: str
    state: RunOutcome
    green: bool | None

def classify_test_run(report: TestExecutionReport, *,
                      execution_requested: bool) -> tuple[DomainOutcome, int]: ...
```

Exit rules:

| Test outcome | Exit |
|---|---:|
| all passed | 0 |
| assertion failure or crash | 32 |
| inconclusive or unreached case | 33 |
| timed_out | 34 |
| precondition blocked | 35 |
| cancelled | 36 |
| internal/contract error | 10 |
| explicit plan/no execution | 0 |

- [ ] **Step 1: Write a table-driven CLI outcome test**

Cover `passed`, `failed` (including crash/assertion failure), `inconclusive`, `timed_out`, `blocked`, `cancelled`, `error`, and `planned`. Assert process exit equals envelope `exit_code` and the same `RunOutcome` reaches dossier and suite fixtures.

- [ ] **Step 2: Replace generic `test_executed` status**

Serialize lifecycle (`queued`/`running`/`finished`), `outcome`, `invocation_id`, tool version, diagnostics, and artifacts. Artifacts must exist and have a matching hash. Do not create a second terminal-status vocabulary.

- [ ] **Step 3: Remove `_reports_from_dossier_path()`**

Return only files the command actually produced or updated. Put future paths under `expected_artifacts`; the VS Code workflow may not treat them as complete.

- [ ] **Step 4: Deprecate execution-shaped dry run**

Introduce `--plan`; keep `--dry-run` as a warning alias for one compatibility version. A plan does not write an execution report or evidence.

- [ ] **Step 5: Validate the envelope in TypeScript**

The adapter accepts v1 only after schema/shape validation. v0.1 fallback is read-only, emits a migration warning, and never fabricates an artifact as produced.

- [ ] **Step 6: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_cli_result_contract tests.test_cli_execution_exit_codes \
  tests.test_cli_artifact_references -v
cd vscode/extension && npm test
git add src/unit_test_runner/cli vscode/extension/src/cli tests
git commit -m "feat: make CLI outcomes and artifact references truthful"
```

---

### Task 5: Introduce `test_spec.json` as the only editable test contract

**Files:**

- Create: `src/unit_test_runner/test_spec/__init__.py`
- Create: `src/unit_test_runner/test_spec/models.py`
- Create: `src/unit_test_runner/test_spec/repository.py`
- Create: `src/unit_test_runner/test_spec/exporters.py`
- Create: `src/unit_test_runner/test_spec/migration.py`
- Modify: `src/unit_test_runner/test_design/test_case_design_generator.py`
- Modify: `src/unit_test_runner/test_design/test_case_design_writer.py`
- Modify: `src/unit_test_runner/dossier/workflow.py`
- Modify: `src/unit_test_runner/harness/harness_skeleton_generator.py`
- Modify: `src/unit_test_runner/reanalysis/workflow.py`
- Modify: `src/unit_test_runner/cli/parser.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Test: `tests/test_test_spec_contract.py`
- Test: `tests/test_test_spec_repository.py`
- Test: `tests/test_test_spec_migration.py`
- Test: `tests/test_test_spec_exports.py`

**Interfaces:**

```python
@dataclass
class TestSpec:
    spec_id: str
    revision: int
    source: SourceReference
    function: FunctionReference
    generated_from: list[ArtifactReference]
    generation_policy: TestCaseGenerationPolicy
    test_cases: list[TestCaseDesign]
    additional_case_candidates: list[TestCaseDesign]
    coverage_summary: CoverageTestDesignSummary
    unresolved_items: list[UnresolvedTestDesignItem]
    warnings: list[TestCaseDesignWarning]
    review_item_ids: list[str]
    schema_version: str = "1.0.0"

def load_test_spec(path: Path, *, mode: ContractMode) -> TestSpec: ...
def save_test_spec(path: Path, spec: TestSpec, *,
                   expected_revision: int | None) -> ProducedArtifact: ...
def export_test_spec_views(spec: TestSpec, out_dir: Path) -> dict[str, Path]: ...
```

- [ ] **Step 1: Write revision, reference, and approval tests**

Reject duplicate case IDs, missing coverage/dependency/review-item references, stale source/signature hashes, executable cases with unresolved values/oracles, and stale expected revision. Approval is not stored in TestSpec; it is resolved from `review_decisions.json`.

- [ ] **Step 2: Implement repository and optimistic revision checks**

Write canonical `reports/test_spec.json`. Save atomically through a sibling temporary file and increment revision only after validation.

- [ ] **Step 3: Convert existing design output to exports**

Write `test_spec.md` and UTF-8-BOM `test_spec.csv`. Include `spec_id`, revision, and canonical SHA-256. Add a visible “generated view; edits are not imported” notice.

- [ ] **Step 4: Switch harness and reanalysis readers**

`generate-harness-skeleton --test-spec` consumes only the canonical contract. Keep `--test-case-design` and v0.1 reading as one-version aliases that migrate in memory.

- [ ] **Step 5: Add revision-checked test-spec update commands**

Add:

```text
get-test-spec --workspace <path>
update-test-spec --workspace <path> --patch <json-file> --expected-revision <n>
```

The patch uses case IDs and JSON field paths, validates the full resulting spec, writes atomically, and returns the new revision/artifact hash. It is the only mutation path used by the Phase 3 Webview.

- [ ] **Step 6: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_test_spec_contract tests.test_test_spec_repository \
  tests.test_test_spec_migration tests.test_test_spec_exports -v
git add src/unit_test_runner/test_spec src/unit_test_runner/test_design src/unit_test_runner/harness src/unit_test_runner/reanalysis src/unit_test_runner/cli tests
git commit -m "feat: make test spec the canonical editable contract"
```

---

### Task 6: Persist review decisions and calculate semantic readiness

**Files:**

- Create: `src/unit_test_runner/dossier/review_decision_models.py`
- Create: `src/unit_test_runner/dossier/review_decision_repository.py`
- Create: `src/unit_test_runner/dossier/review_assessment.py`
- Modify: `src/unit_test_runner/dossier/review_workflow.py`
- Modify: `src/unit_test_runner/dossier/readiness.py`
- Modify: `src/unit_test_runner/dossier/finalizer.py`
- Modify: `src/unit_test_runner/cli/parser.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Test: `tests/test_review_decisions.py`
- Test: `tests/test_review_decision_staleness.py`
- Test: `tests/test_dossier_readiness.py`

**Interfaces:**

```python
class ReviewResolution(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    WAIVED = "waived"

@dataclass(frozen=True)
class ReviewDecision:
    review_id: str
    resolution: ReviewResolution
    reviewer: str
    rationale: str
    decided_at: str
    subject_artifacts: list[ArtifactReference]

def record_review_decision(path: Path, decision: ReviewDecision, *,
                           expected_revision: int) -> ReviewDecisionSet: ...
def assess_review_completion(review_items, decisions,
                             current_artifacts) -> ReviewAssessment: ...
```

- [ ] **Step 1: Write persistence and stale-hash tests**

An approval remains valid after reload and becomes stale when any subject hash changes. A waiver requires rationale.

Add a contradiction test proving that no approval/status field exists in TestSpec, TypedCValue, or OracleSpec; the decision ledger is the sole authority.

- [ ] **Step 2: Generate stable review IDs**

Use category + function ID + optional case ID + semantic subject key; do not use ordinal `REVIEW_001` IDs.

- [ ] **Step 3: Add the CLI command**

```text
record-review-decision --workspace C:\work\utr\Control_Update --review-id expected-return:TC_control_update_low
  --resolution approved|changes_requested|waived|open
  --reviewer reviewer01 --rationale "Reviewed against requirement REQ-42"
  --expected-revision 3 --expected-subject-sha256 7b18e68b2afcf1b0f0a1b857c5d1fcb2cf9db4d1540d778a266dbeaa3aa176a8
```

The backend resolves the current review item to its subject artifacts and pins their paths, revisions, and hashes in the decision. The caller cannot supply a different subject list. A subject-hash mismatch is a revision conflict and writes nothing.

- [ ] **Step 4: Replace existence-based readiness**

Readiness uses valid, current, non-stale artifacts, `RunOutcome`, and only the decision ledger for approval. Add separate `review_complete`, `evidence_ready`, and `test_green` fields. A failed execution may be reviewable evidence but never GREEN.

- [ ] **Step 5: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_review_decisions tests.test_review_decision_staleness \
  tests.test_dossier_readiness -v
git add src/unit_test_runner/dossier src/unit_test_runner/cli tests
git commit -m "feat: persist review decisions and semantic readiness"
```

---

### Task 7: Switch VS Code and documentation to the v1 contracts

**Files:**

- Modify: `vscode/extension/src/cli/commandBuilder.ts`
- Modify: `vscode/extension/src/cli/cliResultParser.ts`
- Modify: `vscode/extension/src/reports/reportPathResolver.ts`
- Modify: `vscode/extension/src/workflow/workflowState.ts`
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts`
- Modify: `README.md`
- Modify: `vscode/extension/README.md`
- Modify: `docs/vscode_usage_guide.md`
- Modify: `docs/test_specification.md`
- Test: `vscode/extension/src/test/adapter.test.ts`
- Test: `vscode/extension/src/test/workflowPanel.test.ts`

**Interfaces:** The adapter advances only from a validated v1 envelope, artifact contract status, review decision, and execution outcome.

- [ ] **Step 1: Replace report-path inference with produced artifacts**

`fs.existsSync()` may control whether a file can be opened; it may not mark a workflow step complete.

- [ ] **Step 2: Replace “saved as confirmed” actions**

The UI records an explicit review decision. A text-document save does not advance the workflow.

- [ ] **Step 3: Add migration messaging**

Show source artifact, migrated version, backup/original path, and action required. Do not auto-save migrated v0.1 content.

- [ ] **Step 4: Update documentation and tests**

Document canonical/editable versus generated/export artifacts and the exact outcome/exit table.

- [ ] **Step 5: Run phase verification and commit**

```bash
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
cd vscode/extension && npm test
git add vscode/extension README.md docs
git commit -m "feat: adopt v1 contracts in the VS Code workflow"
```

---

### Task 8: Close dead CLI/policy options and validate traceability references

**Files:**

- Modify: `src/unit_test_runner/cli/parser.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `src/unit_test_runner/dossier/workflow.py`
- Modify: `src/unit_test_runner/dossier/traceability.py`
- Modify: `src/unit_test_runner/dossier/dossier_models.py`
- Modify: `src/unit_test_runner/test_design/test_case_models.py`
- Modify: `src/unit_test_runner/harness/harness_models.py`
- Modify: `src/unit_test_runner/execution/execution_models.py`
- Modify: `src/unit_test_runner/build_completion/completion_loop.py`
- Modify: `src/unit_test_runner/build_completion/completion_models.py`
- Modify: `src/unit_test_runner/build_completion/completion_applier.py`
- Modify: `src/unit_test_runner/build_probe.py`
- Modify: `src/unit_test_runner/process_control.py`
- Create: `tests/test_public_policy_options.py`
- Create: `tests/test_analysis_phase_contract.py`
- Create: `tests/test_build_completion_loop.py`
- Modify: `tests/test_process_control.py`
- Create: `tests/test_traceability_integrity.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class TraceabilityEdge:
    edge_id: str
    source_ref: ArtifactEntityRef
    target_ref: ArtifactEntityRef
    relation: str
    source_artifact_sha256: str
    target_artifact_sha256: str

def validate_traceability(edges: Sequence[TraceabilityEdge],
                          artifacts: Sequence[LoadedArtifact]) -> tuple[ContractViolation, ...]: ...
```

- [ ] **Step 1: Add on/off behavior tests for every public option**

Cover dossier include/optional/detail policy, test-design emit/policy switches, harness overwrite/placeholder policy, execution placeholder switches, `--emit-json/md/csv`, `--analyze-build-errors`, `prepare-evidence --out`, `--allow-missing-optional-artifacts`, `--run-probe-after-apply`, and `--max-iterations`.

- [ ] **Step 2: Apply the fixed public-option decisions**

- Implement dossier include/optional/detail policy as artifact selection and readiness-level inputs.
- Implement test-design and `--emit-json/md/csv` switches as writer selection; required canonical JSON cannot be disabled for downstream phases.
- Keep harness overwrite and make it protect human-owned files exactly as documented.
- Keep `--allow-placeholder-tests`: false blocks before process spawn; true executes but forces `inconclusive`.
- Remove `--treat-placeholder-as-inconclusive`; placeholders are always inconclusive and may never PASS.
- Implement `--analyze-build-errors` as structured diagnostic classification.
- Remove `prepare-evidence --out`; evidence revisions always use the immutable evidence store.
- Implement `--allow-missing-optional-artifacts` for artifacts whose schema marks them optional; it never waives required artifacts.
- Implement `--run-probe-after-apply` and `--max-iterations` through the completion loop.

Add parser/help snapshot tests so removed options fail as unknown and retained options have a tested on/off effect.

- [ ] **Step 3: Make every phase independently valid**

`analyze-function --phase analysis` must not call a writer with `None`. Every public phase returns a valid envelope and only its produced artifacts.

- [ ] **Step 4: Implement the advertised completion loop**

When requested, apply one safe completion set, rerun the probe, compare progress, and stop on success, no progress, unsafe diagnostics, or `max_iterations`. Persist each iteration; do not report an iteration that did not run.

- [ ] **Step 5: Build a complete traceability chain**

Validate source -> condition -> candidate -> case -> generated C symbol -> execution case. Include `link_id` in CSV, require unique IDs and existing endpoints, and reject cross-function/source-hash links.

- [ ] **Step 6: Route every subprocess through the common timeout contract**

Legacy dossier `build-probe`, completion probe reruns, VC6/NMAKE, host compiler/linker, and test executables all use `run_process_tree`. Convert timeout to `RunOutcome.TIMED_OUT`, preserve partial logs, and verify parent/child/grandchild termination. No raw `subprocess.run()` path may bypass the configured timeout.

- [ ] **Step 7: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_public_policy_options tests.test_analysis_phase_contract \
  tests.test_build_completion_loop tests.test_traceability_integrity \
  tests.test_process_control -v
git add src/unit_test_runner tests
git commit -m "fix: enforce public policies phases and traceability contracts"
```

---

## Phase 1 Completion Check

- [ ] Every public JSON kind has a registered schema and semantic validator.
- [ ] `prepare-evidence` leaves execution report/log hashes unchanged.
- [ ] Two test runs produce two immutable run directories.
- [ ] CLI process exit equals envelope exit for every outcome.
- [ ] The CLI reports only real, hashable produced artifacts.
- [ ] `test_spec.json` is the sole editable test definition.
- [ ] Review decisions survive restart and become stale after subject changes.
- [ ] `review_complete`, `evidence_ready`, and `test_green` are distinct.
- [ ] Every retained CLI/policy option changes tested behavior; unused options are removed.
- [ ] Analysis-only phase, completion iteration, and traceability references validate end to end.
- [ ] Python and VS Code full suites are GREEN.
