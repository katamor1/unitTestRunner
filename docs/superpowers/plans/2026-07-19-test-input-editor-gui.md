# Test Input Editor GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated VS Code editor that lets users enter and confirm unresolved test inputs, state values, stub settings, expected values, and other review-required fields without directly editing canonical JSON.

**Architecture:** Keep the VS Code extension as a thin adapter. A new Python `test_input_form` service reads and validates `reports/test_spec.json`, builds a strict GUI form model, applies revision- and fingerprint-guarded changes, and safely promotes or demotes cases. TypeScript owns rendering, in-session drafts, conflict presentation, temporary request files, and asynchronous Workflow summary caching; it never writes canonical JSON directly.

**Tech Stack:** Python 3.12, `dataclasses`, `pathlib`, `hashlib`, `json`, existing TestSpec contracts, `unittest`; TypeScript 5.4, VS Code Webview API 1.85, Node.js 20 built-ins, `node:test`.

## Global Constraints

- `reports/test_spec.json` is the only editable source of truth. Do not import edits from generated Markdown/CSV or legacy `test_case_design.json`.
- Keep canonical TestSpec schema version `1.1.0`; do not add GUI-only fields to it.
- Never edit case/spec identity, source/function identity, provenance, `coverage_links`, `candidate_links`, `review_item_ids`, review-decision ledgers, reviewer identity, review resolution, or formal readiness.
- The VS Code extension must not implement domain validation, confirmation semantics, promotion/demotion, or canonical persistence.
- Never invoke the CLI from `renderWorkflowHtml()` or another synchronous render path. Fetch summaries asynchronously and cache them in `workspaceState`.
- Validate every submitted item before the first canonical write. Persist through `save_test_spec_snapshot()` exactly once per successful save.
- If canonical JSON saves but Markdown/CSV export fails, retain the new canonical revision and return `views_written: false`; do not roll back JSON.
- Bound all inputs: request file ≤ 4 MiB, changes ≤ 1,000, changed leaves per item ≤ 16, C expression ≤ 4,096 Unicode code points, multiline text ≤ 16,384 Unicode code points.
- C expressions are text. Neither Python nor VS Code evaluates them.
- Use TDD task by task: add a focused failing test, run it and inspect the intended failure, implement the smallest complete behavior, rerun, then commit.
- Literal prefixes `TBD`, `TODO`, `UNKNOWN`, and `UNRESOLVED` below are domain values under test, not unfinished plan sections.

## File Structure Map

### Python

- Create `src/unit_test_runner/test_input_form/__init__.py` — public query/apply API and typed errors.
- Create `src/unit_test_runner/test_input_form/models.py` — strict form and change-request contracts.
- Create `src/unit_test_runner/test_input_form/field_catalog.py` — editable collection/leaf allowlist and dynamic required/blocking rules.
- Create `src/unit_test_runner/test_input_form/field_locator.py` — semantic locators, opaque IDs, fingerprints, and ambiguity detection.
- Create `src/unit_test_runner/test_input_form/validation.py` — normalization, unresolved detection, hard errors, and advisory C-expression warnings.
- Create `src/unit_test_runner/test_input_form/suggestions.py` — evidence-backed values from current artifacts and canonical siblings.
- Create `src/unit_test_runner/test_input_form/service.py` — strict snapshot load, form query, apply, reclassification, save, and view export.
- Modify `src/unit_test_runner/cli/parser.py`, `commands.py`, `errors.py`, and `main.py` — two new CLI commands and structured error codes.
- Modify `tests/spec_support.py`; create focused tests named in the tasks.

### VS Code

- Modify `vscode/extension/src/cli/commandBuilder.ts` — canonical TestSpec consumers and form invocations.
- Modify `vscode/extension/src/reports/reportPathResolver.ts`, `cli/cliEnvelope.ts`, and `cli/cliResultParser.ts` — canonical TestSpec paths.
- Create `vscode/extension/src/testInputEditor/contracts.ts` — strict form/apply envelope and Webview-message parsing.
- Create `vscode/extension/src/testInputEditor/cliClient.ts` — query/apply calls, typed errors, temporary request lifecycle.
- Create `vscode/extension/src/testInputEditor/draftState.ts` — pure draft and conflict reducer.
- Create `vscode/extension/src/testInputEditor/renderer.ts` — escaped nonce-protected HTML.
- Create `vscode/extension/src/testInputEditor/controller.ts` — testable orchestration with injected ports.
- Create `vscode/extension/src/testInputEditor/panel.ts` — thin VS Code wrapper and per-workspace singleton.
- Create `vscode/extension/src/testInputEditor/summaryCache.ts` — asynchronous cache state and invalidation.
- Modify Workflow, command registry, extension activation, manifest, and focused tests.

---

### Task 1: Switch existing VS Code consumers to canonical TestSpec

**Files:**
- Modify: `vscode/extension/src/cli/commandBuilder.ts`
- Modify: `vscode/extension/src/reports/reportPathResolver.ts`
- Modify: `vscode/extension/src/cli/cliEnvelope.ts`
- Modify: `vscode/extension/src/cli/cliResultParser.ts`
- Modify: `vscode/extension/src/test/adapter.test.ts`
- Modify: `vscode/extension/src/test/cliEnvelope.test.ts`

**Interfaces:**
- Reanalysis uses `--previous-test-spec <workspace>/reports/test_spec.json`.
- Harness generation uses `--test-spec <workspace>/reports/test_spec.json`.
- `ReportPaths` exposes `testSpecJson`, `testSpecMd`, and `testSpecCsv`; legacy view fields remain for compatibility only.

- [ ] **Step 1: Replace legacy expectations with failing canonical assertions**

```typescript
assert.deepEqual(
  reanalyze.args.slice(
    reanalyze.args.indexOf('--previous-test-spec'),
    reanalyze.args.indexOf('--previous-test-spec') + 2,
  ),
  ['--previous-test-spec', path.join(target.outputWorkspace, 'reports', 'test_spec.json')],
);
assert.equal(reanalyze.args.includes('--previous-test-case-design'), false);
assert.deepEqual(
  harness.args.slice(harness.args.indexOf('--test-spec'), harness.args.indexOf('--test-spec') + 2),
  ['--test-spec', path.join(target.outputWorkspace, 'reports', 'test_spec.json')],
);
assert.equal(harness.args.includes('--test-case-design'), false);
```

Add resolver and v1 artifact assertions for all three canonical files.

- [ ] **Step 2: Run the focused tests and verify the current legacy path fails**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/adapter.test.js dist/test/cliEnvelope.test.js
Pop-Location
```

- [ ] **Step 3: Implement the exact canonical arguments and mappings**

In `commandBuilder.ts` replace only the legacy option/value pairs. In `reportPathResolver.ts` add:

```typescript
testSpecJson: dialect.join(reports, 'test_spec.json'),
testSpecMd: dialect.join(reports, 'test_spec.md'),
testSpecCsv: dialect.join(reports, 'test_spec.csv'),
```

In `cliEnvelope.ts` add:

```typescript
'test_spec.json': 'test_spec_json',
'test_spec.md': 'test_spec_md',
'test_spec.csv': 'test_spec_csv',
```

In `cliResultParser.ts` map those reported keys explicitly:

```typescript
testSpecJson: reportPath(reportSource.test_spec_json),
testSpecMd: reportPath(reportSource.test_spec_md),
testSpecCsv: reportPath(reportSource.test_spec_csv),
```

- [ ] **Step 4: Rerun the focused tests**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/adapter.test.js dist/test/cliEnvelope.test.js
Pop-Location
```

Expected: pass, with no normal-path legacy argument assertion.

- [ ] **Step 5: Commit**

```powershell
git add vscode/extension/src/cli/commandBuilder.ts vscode/extension/src/reports/reportPathResolver.ts vscode/extension/src/cli/cliEnvelope.ts vscode/extension/src/cli/cliResultParser.ts vscode/extension/src/test/adapter.test.ts vscode/extension/src/test/cliEnvelope.test.ts
git commit -m "refactor: use canonical test spec in vscode adapter"
```

### Task 2: Define strict Python form contracts and field catalog

**Files:**
- Create: `src/unit_test_runner/test_input_form/__init__.py`
- Create: `src/unit_test_runner/test_input_form/models.py`
- Create: `src/unit_test_runner/test_input_form/field_catalog.py`
- Create: `tests/test_test_input_form_models.py`

**Interfaces:**
- `TestInputFormError` carries stable `.code` and `.message`.
- Output and input use transient schema version `1.0` with exact-key validation.
- `FIELD_RULES` is the sole editable-field authority.

- [ ] **Step 1: Write failing strict-request tests**

Cover a valid request, extra/missing properties, wrong schema version, invalid hashes, duplicate IDs, >1,000 changes, >16 leaves, nonboolean `confirmed`, and invalid value types.

```python
request = parse_test_input_change_request(
    {
        "schema_version": "1.0",
        "changes": [
            {
                "item_id": "item-" + "a" * 64,
                "subject_fingerprint": "b" * 64,
                "values": {"value_expression": "MODE_AUTO"},
                "confirmed": True,
            }
        ],
    }
)
self.assertEqual("MODE_AUTO", request.changes[0].values["value_expression"])
```

- [ ] **Step 2: Write failing allowlist tests**

Assert exact collections and leaves:

```text
input_assignments: value_expression
state_setups: value_expression, setup_method_hint
stub_setups: value_expression, call_behavior
expected_observations: expected_expression, note
preconditions: description
execution_steps: detail
dependency_overrides: mode, rationale
```

Also assert:

- `mode` enum is exactly `inherit|real|stub`;
- rationale is required only for explicit `real`/`stub`;
- stub value is not execution-required for `call_count_observation` or `argument_capture`;
- no identity, provenance, review authority, warning evidence, coverage, candidate, or call identity is editable.

- [ ] **Step 3: Run and confirm missing-package failure**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models -v
```

- [ ] **Step 4: Implement immutable models**

Use these principal shapes and add exact `to_dict()` methods:

```python
@dataclass(frozen=True)
class FormSuggestion:
    value: str
    label: str
    source: str
    confidence: str

@dataclass(frozen=True)
class FormControl:
    name: str
    control_kind: str
    required_for_confirmation: bool
    value: Any
    suggestions: tuple[FormSuggestion, ...] = ()
    enum_values: tuple[str, ...] = ()

@dataclass(frozen=True)
class FormItem:
    item_id: str
    subject_fingerprint: str
    kind: str
    label: str
    confirmed: bool
    blocking: bool
    editable: bool
    controls: tuple[FormControl, ...]
    warnings: tuple[dict[str, str], ...] = ()

@dataclass(frozen=True)
class FormCase:
    case_id: str
    location: str
    promotion_eligible: bool
    items: tuple[FormItem, ...]

@dataclass(frozen=True)
class FormSummary:
    attention_count: int
    unresolved_count: int
    unconfirmed_count: int
    execution_blocking_count: int
    warning_count: int

@dataclass(frozen=True)
class TestInputFormDocument:
    revision: int
    spec_sha256: str
    function_name: str
    summary: FormSummary
    cases: tuple[FormCase, ...] | None
    schema_version: str = "1.0"

@dataclass(frozen=True)
class TestInputChange:
    item_id: str
    subject_fingerprint: str
    values: Mapping[str, Any]
    confirmed: bool

@dataclass(frozen=True)
class TestInputChangeRequest:
    changes: tuple[TestInputChange, ...]
    schema_version: str = "1.0"
```

Use only these form error codes:

```python
FORM_ERROR_CODES = frozenset(
    {
        "test_input_form_invalid",
        "test_input_revision_conflict",
        "test_input_subject_conflict",
        "test_input_validation",
        "stale_test_spec",
    }
)
```

- [ ] **Step 5: Implement catalog data and total rule functions**

Define immutable `ControlRule` and `FieldRule`. Export these callable contracts:

```text
required_for_confirmation(rule, control, parent) -> bool
execution_value_required(rule, parent) -> bool
label_for_parent(rule, parent) -> str
editable_control_names(rule) -> frozenset[str]
```

Each function must return a value for every catalog rule; callers must not switch on collection names.

- [ ] **Step 6: Rerun and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models -v
git add src/unit_test_runner/test_input_form tests/test_test_input_form_models.py
git commit -m "feat: define test input form contracts"
```

### Task 3: Build semantic locators, stable item IDs, and fingerprints

**Files:**
- Create: `src/unit_test_runner/test_input_form/field_locator.py`
- Modify: `src/unit_test_runner/test_input_form/__init__.py`
- Create: `tests/test_test_input_form_locator.py`

**Interfaces:**
- `locate_form_items(spec)` scans both case collections.
- `item_id` is independent of array index and independent of whether the case currently lives in `test_cases` or `additional_case_candidates`.
- Internal mutation coordinates may contain current collection/index, but they are never hashed or serialized.
- Duplicate semantic locators are ambiguous and not writable.

- [ ] **Step 1: Write failing reorder and cross-location stability tests**

Create the same case/item payload, reorder arrays, then move the case from candidates to executable cases. Assert the item ID remains identical in all three snapshots.

- [ ] **Step 2: Write locator identity tests**

Use these exact identity fields:

```text
input: target_kind, target_name, source_candidate_id
state: scope, variable_name, source_candidate_id
stub: stub_name, setup_kind, related_call_id, source_candidate_id
expected: observation_kind, target_name, source
dependency: callee
precondition: source
execution step: order, action
```

- [ ] **Step 3: Write ambiguity and fingerprint tests**

Assert duplicate locators are `ambiguous=True` and `editable=False`. Assert changing any parent-object meaning changes `subject_fingerprint`, while reordering sibling arrays does not.

- [ ] **Step 4: Run and confirm missing implementation**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_locator -v
```

- [ ] **Step 5: Implement canonical hashing**

```python
def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
```

Hash this locator shape exactly; do **not** include case collection/location:

```python
locator = {
    "case_id": case_id,
    "collection": rule.collection,
    "kind": rule.kind,
    "identity": {name: parent.get(name) for name in rule.locator_fields},
}
item_id = "item-" + digest(locator)
subject_fingerprint = digest(parent)
```

- [ ] **Step 6: Implement two-pass ambiguity detection**

Build all current items with internal `case_location`, `case_index`, and `item_index`; group by `item_id`; mark every member of a non-singleton group ambiguous. Never append an index or location suffix.

- [ ] **Step 7: Rerun and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models tests.test_test_input_form_locator -v
git add src/unit_test_runner/test_input_form/field_locator.py src/unit_test_runner/test_input_form/__init__.py tests/test_test_input_form_locator.py
git commit -m "feat: locate editable test spec items safely"
```

### Task 4: Query current form, summary, warnings, and suggestions

**Files:**
- Create: `src/unit_test_runner/test_input_form/validation.py`
- Create: `src/unit_test_runner/test_input_form/suggestions.py`
- Create: `src/unit_test_runner/test_input_form/service.py`
- Modify: `tests/spec_support.py`
- Create: `tests/test_test_input_form_query.py`

**Interfaces:**
- `build_test_input_form(workspace, summary_only=False) -> TestInputFormDocument`.
- Summary counts unique item IDs, not leaves.
- Suggestions carry `source` and `confidence`; no evidence means no suggestion.

- [ ] **Step 1: Add an unresolved canonical fixture helper**

Write one unresolved generated main case in `additional_case_candidates`, one intentional additional candidate with no execution objects, current source/provenance files, and a boundary candidate linked by `source_candidate_id`. Return canonical path and case IDs.

- [ ] **Step 2: Write failing extraction and grouping tests**

Assert:

- `review_required: true` parents appear;
- unresolved execution values appear even if `review_required` is false;
- one state parent produces one card with `value_expression` and `setup_method_hint` controls;
- an execution object missing boolean `review_required` is read-only with warning;
- cases with no visible items are omitted.

- [ ] **Step 3: Write failing summary tests**

Build overlapping unresolved, unconfirmed, blocking, and warning states. Calculate each count using a set of `item_id`; assert `attention_count` is their union.

- [ ] **Step 4: Write failing summary-only, eligibility, suggestion, and stale tests**

Assert:

- summary-only validates freshness but serializes no `cases` key;
- unresolved generated main candidate is promotion-eligible;
- intentional empty candidate is not eligible and is absent from the form;
- boundary candidate, proven pointer `NULL`, obvious flag `0/1`, unique enum values, and concrete same-target canonical values are suggested only with evidence;
- stale source raises `TestInputFormError.code == "stale_test_spec"`.

- [ ] **Step 5: Run and confirm missing service**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_query -v
```

- [ ] **Step 6: Implement normalization and unresolved detection**

```python
UNRESOLVED_PREFIXES = ("TBD", "TODO", "UNKNOWN", "UNRESOLVED")


def is_unresolved(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.upper().startswith(UNRESOLVED_PREFIXES)
```

Implement and test:

```text
normalize_c_expression(value): trim; reject CR/LF/NUL; enforce 4,096 code points
normalize_multiline(value): normalize CRLF/CR to LF; reject NUL; enforce 16,384 code points
normalize_enum(value, allowed): require exact ASCII member
c_expression_warnings(value, type_hint, suggestions): return advisory warning records only
```

Warnings cover unbalanced delimiters/quotes, likely scalar/string or pointer mismatch, unknown identifiers/macros, likely non-C90 constructs, missing type evidence, and values outside suggestions.

- [ ] **Step 7: Implement evidence-backed suggestions**

Read only current canonical provenance files. Index boundary candidates by ID, signature parameters by target, and concrete canonical values by semantic target. Deduplicate by value and prefer stronger evidence. Do not infer enums or pointers when evidence is ambiguous.

- [ ] **Step 8: Implement strict form construction**

Load strict snapshot, call `build_current_artifact_context()`, validate the TestSpec against that context, locate items, build controls, and calculate summary sets. Map freshness/contract mismatch to `stale_test_spec`.

Display an item when its parent has `review_required: true` or an execution-required control is unresolved. Set `confirmed` only from boolean `review_required is False`.

- [ ] **Step 9: Rerun and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models tests.test_test_input_form_locator tests.test_test_input_form_query -v
git add src/unit_test_runner/test_input_form tests/spec_support.py tests/test_test_input_form_query.py
git commit -m "feat: build test input form views"
```

### Task 5: Apply partial changes, confirmation, reclassification, and durable views

**Files:**
- Modify: `src/unit_test_runner/test_input_form/service.py`
- Modify: `src/unit_test_runner/test_input_form/validation.py`
- Create: `tests/test_test_input_form_apply.py`
- Create: `tests/test_test_input_form_reclassification.py`

**Interfaces:**
- `apply_test_input_form(workspace, request, expected_revision) -> TestInputApplyResult`.
- Resolve and validate all targets before mutating a copied TestSpec.
- Promotion uses pre-save eligibility; demotion affects only touched execution items.

- [ ] **Step 1: Write failing partial-save and confirmation tests**

Assert one submitted item changes, unsent parents remain equal, revision increments once, `confirmed:false` writes `review_required:true`, and same-save concrete value plus `confirmed:true` writes `review_required:false`.

- [ ] **Step 2: Write failing rejection and atomicity tests**

Reject without byte changes:

- confirmed required control blank or prefixed by an unresolved marker;
- missing/ambiguous/noneditable item;
- fingerprint mismatch;
- duplicate change ID;
- unsupported leaf or enum;
- nonboolean current `review_required`;
- stale revision/source;
- oversized request/control;
- second item invalid in a multi-item request.

- [ ] **Step 3: Write formal-authority invariance tests**

Capture and compare before/after:

```text
spec and case review_item_ids
unresolved_items
source
function
generated_from
coverage_links
candidate_links
warning identity/evidence
```

- [ ] **Step 4: Write promotion/demotion tests**

Assert:

- intentional additional candidate with no execution objects never promotes;
- eligible candidate promotes only when every execution-required parent is concrete and confirmed;
- promotion appends in original candidate order and preserves all nonlocation data;
- touched executable case demotes if an execution value becomes unresolved or its execution parent becomes unconfirmed;
- nonexecution edits and untouched executable cases never move;
- duplicate case IDs reject the entire save;
- `coverage_summary` and historical `unresolved_items` remain unchanged.

Execution fields are exactly:

```text
input_assignments[].value_expression
state_setups[].value_expression
stub_setups[].value_expression except call_count_observation and argument_capture
expected_observations[].expected_expression
```

- [ ] **Step 5: Write view-export failure test**

Patch view export to fail after canonical save. Assert canonical revision/value remain, `views_written` is false, warning code is `test_spec_view_export_failed`, and JSON is not rolled back.

- [ ] **Step 6: Run and inspect failures**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_apply tests.test_test_input_form_reclassification -v
```

- [ ] **Step 7: Implement all-target validation before mutation**

Use this exact order:

```text
strict load and current-context validation
expected revision check
current semantic location of every submitted item
unique/editable/fingerprint/leaf/type/length validation for every change
copy TestSpec payload
normalize and apply every value
write parent review_required from confirmed
validate every confirmed required control
reclassify eligible/touched cases
validate canonical contract
save once with save_test_spec_snapshot
export views
build latest summary/result
```

If a value changes, the request’s mandatory `confirmed` value controls the new parent state. `confirmed:true` is accepted only after all required controls are concrete.

- [ ] **Step 8: Implement reclassification with stable item identity**

Precompute eligible candidate case IDs before mutation. Promote ready eligible cases; demote only cases whose execution item appears in the submitted change set and is unsafe afterward. Moving a case must not alter its item IDs because location is absent from the semantic hash.

- [ ] **Step 9: Export views after canonical save**

Catch only expected view-export exceptions after save. Return the canonical artifact always; return Markdown/CSV artifacts only when the pair was written. Never catch canonical save errors in the view block.

- [ ] **Step 10: Rerun all form tests and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models tests.test_test_input_form_locator tests.test_test_input_form_query tests.test_test_input_form_apply tests.test_test_input_form_reclassification -v
git add src/unit_test_runner/test_input_form/service.py src/unit_test_runner/test_input_form/validation.py tests/test_test_input_form_apply.py tests/test_test_input_form_reclassification.py
git commit -m "feat: apply and reclassify test input changes"
```

### Task 6: Expose form query/apply through the CLI

**Files:**
- Modify: `src/unit_test_runner/cli/parser.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `src/unit_test_runner/cli/errors.py`
- Modify: `src/unit_test_runner/cli/main.py`
- Modify: `src/unit_test_runner/test_input_form/__init__.py`
- Create: `tests/test_test_input_form_cli.py`

**Interfaces:**
- `get-test-input-form --workspace <path> [--summary-only]`.
- `apply-test-input-form --workspace <path> --input <json> --expected-revision <int>`.
- Expected failures preserve form error code in v1 `data.errors[].code`.

- [ ] **Step 1: Write failing parser and success-envelope tests**

Assert parser attributes, form schema/revision/SHA/summary, apply counts, promotion/demotion arrays, `views_written`, and produced canonical/view artifacts.

- [ ] **Step 2: Write failing structured-error tests**

Cover stale revision, subject conflict, validation error, >4 MiB file, malformed JSON, and stale source. Assert exact code and unchanged canonical bytes.

- [ ] **Step 3: Run and confirm missing subcommands**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_cli -v
```

- [ ] **Step 4: Add parser entries**

```python
get_form = subcommands.add_parser(
    "get-test-input-form",
    help="Build a validated form model for editable test inputs.",
)
get_form.add_argument("--workspace", required=True)
get_form.add_argument("--summary-only", action="store_true")

apply_form = subcommands.add_parser(
    "apply-test-input-form",
    help="Apply revision-checked test input form changes.",
)
apply_form.add_argument("--workspace", required=True)
apply_form.add_argument("--input", required=True)
apply_form.add_argument("--expected-revision", required=True, type=int)
```

- [ ] **Step 5: Add structured `CLIError.code` without breaking existing callers**

Default the new constructor argument to `"error"`; emit `{"code": exc.code, "message": exc.message}` for caught `CLIError`. Keep argument-parse and unexpected-error behavior compatible.

- [ ] **Step 6: Implement handlers**

`get` returns `document.to_dict()`. `apply` checks file size before UTF-8-sig JSON parsing, parses an object through the strict request parser, calls the service, reports canonical artifact always, and reports view artifacts only when written. Convert every `TestInputFormError` to `CLIError` with the same code and `EXIT_INPUT_ERROR`.

- [ ] **Step 7: Rerun CLI contracts and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_cli tests.test_test_spec_cli tests.test_cli_entry_point_contract -v
git add src/unit_test_runner/cli src/unit_test_runner/test_input_form/__init__.py tests/test_test_input_form_cli.py
git commit -m "feat: expose test input form cli commands"
```

### Task 7: Prove the canonical Python workflow end to end

**Files:**
- Create: `tests/test_test_input_form_end_to_end.py`
- Modify: `tests/spec_support.py`

**Interfaces:**
- Real sequence: analyze/harness workspace → query → apply → get canonical spec → regenerate harness with `--test-spec` → build-probe dry-run.
- Legacy design file bytes remain unchanged.

- [ ] **Step 1: Write the failing integration test**

Use `tests/fixtures/vc6_project`. Query real item IDs/fingerprints, submit concrete confirmed values for every blocking item, then assert:

- revision advances once;
- generated main candidate moves to `test_cases`;
- intentional empty candidate remains additional;
- Markdown/CSV identities match saved revision/SHA;
- generated C contains concrete values instead of replaced placeholders;
- build-probe dry-run succeeds;
- legacy `test_case_design.json` bytes are unchanged.

- [ ] **Step 2: Run and identify the first real seam failure**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_end_to_end -v
```

- [ ] **Step 3: Fix only canonical integration seams**

Allowed changes: fixture completeness, CLI artifact paths, canonical consumer input, and existing build-probe prerequisites. Do not add a legacy fallback.

- [ ] **Step 4: Run adjacent consumers and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_end_to_end tests.test_test_spec_consumers tests.test_dependency_policy_end_to_end -v
git add tests/test_test_input_form_end_to_end.py tests/spec_support.py
git commit -m "test: cover canonical test input workflow"
```

### Task 8: Add strict TypeScript form contracts and CLI client

**Files:**
- Modify: `vscode/extension/src/cli/commandBuilder.ts`
- Create: `vscode/extension/src/testInputEditor/contracts.ts`
- Create: `vscode/extension/src/testInputEditor/cliClient.ts`
- Create: `vscode/extension/src/test/testInputCliClient.test.ts`

**Interfaces:**
- Query/apply command builders.
- Strict parsers for v1 details and Webview-independent client types.
- Temporary input deleted in `finally` on every outcome.

- [ ] **Step 1: Write failing builder tests**

```typescript
const get = buildGetTestInputFormInvocation(settings, workspace, true);
assert.deepEqual(get.args.slice(0, 4), ['--json', 'get-test-input-form', '--workspace', workspace]);
assert.ok(get.args.includes('--summary-only'));

const apply = buildApplyTestInputFormInvocation(settings, workspace, inputPath, 3);
assert.deepEqual(
  apply.args.slice(apply.args.indexOf('--expected-revision')),
  ['--expected-revision', '3'],
);
```

- [ ] **Step 2: Write strict envelope-parser tests**

Accept complete query/apply v1 envelopes. Reject unknown keys at every level, wrong form version, invalid SHA/count/revision, duplicate IDs, unknown control kind, and malformed structured errors.

- [ ] **Step 3: Write temporary-file tests with injected filesystem/process functions**

Assert the random path is below supplied storage root and deletion runs after success, nonzero CLI, timeout, and parser failure.

- [ ] **Step 4: Run and confirm missing modules**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputCliClient.test.js
Pop-Location
```

- [ ] **Step 5: Implement builders and strict types**

Principal public types:

```typescript
export interface TestInputFormSummary {
  attentionCount: number;
  unresolvedCount: number;
  unconfirmedCount: number;
  executionBlockingCount: number;
  warningCount: number;
}

export interface TestInputFormModel {
  schemaVersion: '1.0';
  revision: number;
  specSha256: string;
  functionName: string;
  summary: TestInputFormSummary;
  cases?: readonly TestInputFormCase[];
}

export interface TestInputChangeDraft {
  itemId: string;
  subjectFingerprint: string;
  values: Readonly<Record<string, string>>;
  confirmed: boolean;
}
```

Parse v1 `data.details` after `parseCliEnvelopeValue()`; do not cast arbitrary `parsedJson` to a model.

- [ ] **Step 6: Implement client methods**

```typescript
load(workspace: string, summaryOnly?: boolean): Promise<TestInputFormModel>
apply(workspace: string, revision: number, changes: readonly TestInputChangeDraft[]): Promise<TestInputApplyResult>
```

Serialize transient schema `1.0`, create filename with `crypto.randomUUID()`, write UTF-8 under supplied storage root, and delete in `finally`. Convert machine error codes to typed `TestInputCliError`.

- [ ] **Step 7: Rerun and commit**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputCliClient.test.js dist/test/adapter.test.js dist/test/cliEnvelope.test.js
Pop-Location
git add vscode/extension/src/cli/commandBuilder.ts vscode/extension/src/testInputEditor/contracts.ts vscode/extension/src/testInputEditor/cliClient.ts vscode/extension/src/test/testInputCliClient.test.ts
git commit -m "feat: add test input editor cli client"
```

### Task 9: Implement pure draft state and secure editor rendering

**Files:**
- Create: `vscode/extension/src/testInputEditor/draftState.ts`
- Create: `vscode/extension/src/testInputEditor/renderer.ts`
- Create: `vscode/extension/src/test/testInputEditorState.test.ts`
- Create: `vscode/extension/src/test/testInputEditorRenderer.test.ts`

**Interfaces:**
- Pure modules do not import `vscode`.
- Editing any control auto-unconfirms the item.
- Reload reuses a draft only when baseline fingerprint still matches.
- HTML escapes all data and uses nonce CSP with no external resources or inline handlers.

- [ ] **Step 1: Write failing reducer tests**

Cover select, edit, auto-unconfirm, explicit reconfirm, dirty-only request, discard, hide/show retention, and dirty title/footer.

- [ ] **Step 2: Write failing conflict-merge tests**

Cover unchanged-fingerprint reapply, changed-fingerprint conflict, deleted/ambiguous orphan, choose latest, and choose draft rebased to latest fingerprint.

- [ ] **Step 3: Write failing renderer tests**

Require header/summary, case list, all eight item sections, suggestion buttons that leave the input editable, one confirmation checkbox per card, footer actions, zero-item state, `default-src 'none'`, nonce style/script, no `onclick=`, and escaped hostile values.

- [ ] **Step 4: Run and confirm missing behavior**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputEditorState.test.js dist/test/testInputEditorRenderer.test.js
Pop-Location
```

- [ ] **Step 5: Implement immutable reducer API**

```text
createDraftState
selectCase
editControl
setItemConfirmed
discardDrafts
buildChangeDrafts
mergeReloadedModel
resolveConflictWithLatest
resolveConflictWithDraft
```

Only dirty, nonorphaned, nonambiguous items may enter `buildChangeDrafts()`.

- [ ] **Step 6: Implement renderer and minimal browser script**

Browser code may switch cases, edit controls, apply a suggestion, toggle confirmation, send save/discard/reload/conflict messages, and retain visual state with `getState()/setState()`. It must not calculate domain validity or mutate canonical data.

- [ ] **Step 7: Rerun and commit**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputEditorState.test.js dist/test/testInputEditorRenderer.test.js
Pop-Location
git add vscode/extension/src/testInputEditor/draftState.ts vscode/extension/src/testInputEditor/renderer.ts vscode/extension/src/test/testInputEditorState.test.ts vscode/extension/src/test/testInputEditorRenderer.test.ts
git commit -m "feat: render secure test input editor"
```

### Task 10: Add controller, panel singleton, save, and conflict flow

**Files:**
- Create: `vscode/extension/src/testInputEditor/controller.ts`
- Create: `vscode/extension/src/testInputEditor/panel.ts`
- Modify: `vscode/extension/src/testInputEditor/contracts.ts`
- Create: `vscode/extension/src/test/testInputEditorController.test.ts`

**Interfaces:**
- One panel per normalized function workspace.
- In-session draft cache only; no restart persistence.
- Save keeps panel open, reloads latest model, and notifies Workflow.
- Conflict never auto-resubmits.

- [ ] **Step 1: Write strict Webview-message tests**

Allow exact shapes for select/edit/confirm/save/discard/reload/conflict resolution/open canonical. Reject unknown keys, unknown controls, malformed booleans, and overlong strings before dispatch.

- [ ] **Step 2: Write controller tests with fake client/view ports**

Cover initial load, dirty-only save, successful reload/callback, conflict preservation, discard confirmation, safe draft reapply, orphan display, zero-item canonical-open action, and CLI failure with drafts intact.

- [ ] **Step 3: Run and confirm missing controller**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputEditorController.test.js
Pop-Location
```

- [ ] **Step 4: Implement injected ports**

```typescript
export interface TestInputEditorClientPort {
  load(workspace: string, summaryOnly?: boolean): Promise<TestInputFormModel>;
  apply(workspace: string, revision: number, changes: readonly TestInputChangeDraft[]): Promise<TestInputApplyResult>;
}

export interface TestInputEditorViewPort {
  render(state: TestInputEditorState): void;
  setTitle(title: string): void;
  confirmDiscard(): Promise<boolean>;
  showError(message: string, actions: readonly string[]): Promise<string | undefined>;
}
```

Controller owns state and does not import `vscode`.

- [ ] **Step 5: Implement thin panel wrapper**

Normalize workspace key; reveal existing panel; create a script-enabled Webview Panel; use `context.storageUri ?? context.globalStorageUri`; parse every message; retain drafts in a process-memory map on dispose; update unsaved title; dispose subscriptions and singleton entry.

- [ ] **Step 6: Implement explicit conflict sequence**

Keep drafts, load latest, merge by item ID and old fingerprint, render per-item `最新値を使う` / `下書きを採用`, never save automatically, and exclude unresolved orphan drafts from requests.

- [ ] **Step 7: Rerun and commit**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputCliClient.test.js dist/test/testInputEditorState.test.js dist/test/testInputEditorRenderer.test.js dist/test/testInputEditorController.test.js
Pop-Location
git add vscode/extension/src/testInputEditor vscode/extension/src/test/testInputEditorController.test.ts
git commit -m "feat: add test input editor panel workflow"
```

### Task 11: Integrate asynchronous summary and editor action into Workflow

**Files:**
- Create: `vscode/extension/src/testInputEditor/summaryCache.ts`
- Modify: `vscode/extension/src/workflow/workflowState.ts`
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts`
- Modify: `vscode/extension/src/workflow/workflowPanel.ts`
- Modify: `vscode/extension/src/commands/commandRegistry.ts`
- Modify: `vscode/extension/src/extension.ts`
- Modify: `vscode/extension/package.json`
- Modify: `vscode/extension/src/test/workflowPanel.test.ts`
- Modify: `vscode/extension/src/test/commandRegistry.test.ts`
- Modify: `vscode/extension/src/test/uiCopy.test.ts`
- Create: `vscode/extension/src/test/testInputSummaryCache.test.ts`

**Interfaces:**
- Command: `unitTestRunner.openTestInputEditor`.
- Label: `未確定項目を入力（N件）`; zero: `入力内容を確認（0件）`.
- Blocking or summary failure uses warning emphasis; editor never auto-opens.

- [ ] **Step 1: Write failing cache tests**

Cover exact workspace/revision/SHA key, workspace change, analyze/reanalyze/save invalidation, late-response rejection, ready/error states, and proof that refresh is an explicit async operation.

Use a discriminated state so an error never masquerades as a zero count:

```typescript
export type TestInputSummaryState =
  | {
      status: 'ready';
      workspace: string;
      revision: number;
      specSha256: string;
      summary: TestInputFormSummary;
      updatedAt: string;
    }
  | {
      status: 'error';
      workspace: string;
      message: string;
      updatedAt: string;
    };
```

- [ ] **Step 2: Write failing Workflow/manifest/registry tests**

Assert count label, zero label, danger class for blocking, count-less warning action for refresh failure, absence without canonical TestSpec, command data attribute, activation event, Japanese command title, and exact one-to-one registry.

- [ ] **Step 3: Run and confirm missing integration**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputSummaryCache.test.js dist/test/workflowPanel.test.js dist/test/commandRegistry.test.js dist/test/uiCopy.test.js
Pop-Location
```

- [ ] **Step 4: Extend state/availability without render-time I/O**

Add `testSpec` availability from `reports.testSpecJson` and optional cached summary state to `WorkflowState`. `renderWorkflowHtml()` reads only supplied state/availability; it receives no client, callback, or promise.

- [ ] **Step 5: Render editor action in simple and detailed modes**

Place near test-design review. Show attention, unresolved, unconfirmed, and blocking counts. Update copy from legacy manual JSON editing to canonical editor usage.

- [ ] **Step 6: Register panel and command**

Add activation event, command contribution titled `UnitTestRunner: 未確定テスト項目を入力`, command-registry ID, complete handler map, one client/panel factory during activation, and save callback to summary refresh.

- [ ] **Step 7: Refresh only at approved lifecycle boundaries**

Invalidate before and refresh after successful analyze, reanalyze, explicit test-design generation, form save, and activation restoration. Ignore late responses for a no-longer-current workspace. Cache error without blocking unrelated Workflow operations.

- [ ] **Step 8: Run full VS Code suite and commit**

```powershell
Push-Location vscode\extension
npm test
Pop-Location
git add vscode/extension/src/testInputEditor/summaryCache.ts vscode/extension/src/workflow vscode/extension/src/commands/commandRegistry.ts vscode/extension/src/extension.ts vscode/extension/package.json vscode/extension/src/test
git commit -m "feat: surface unresolved test inputs in workflow"
```

### Task 12: Document, run complete regression, smoke real output, and package

**Files:**
- Create: `docs/test_input_editor.md`
- Modify: `docs/vscode_usage_guide.md`
- Modify: `README.md`
- Modify: `vscode/extension/src/test/uiCopy.test.ts`
- Verify: all implementation files

- [ ] **Step 1: Add failing documentation/copy assertions**

Require command title, count labels, `確認済み` semantics, canonical `test_spec.json`, and absence of normal-path instructions to edit legacy `test_case_design.json`.

- [ ] **Step 2: Write dedicated guide**

Document manual open, statuses, hybrid suggestions/free C expressions, explicit partial save, item confirmation versus formal approval, hard errors versus warnings, promotion/demotion, revision/fingerprint conflict, stale reanalysis, and canonical CLI commands.

- [ ] **Step 3: Update README and general VS Code guide**

Add editor to Workflow, outputs, command list, and reanalysis. Mention legacy alias only as compatibility behavior.

- [ ] **Step 4: Run every Python module in isolation**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$modules = Get-ChildItem -LiteralPath .\tests -Filter 'test_*.py' -File |
  Sort-Object Name |
  ForEach-Object { 'tests.' + $_.BaseName }
if ($modules.Count -eq 0) { throw 'isolated Python test discovery returned no modules' }
$failed = @()
foreach ($module in $modules) {
  & py -m unittest $module -v
  if ($LASTEXITCODE -ne 0) { $failed += $module }
}
if ($failed.Count -ne 0) {
  throw ('isolated Python failures: ' + ($failed -join ', '))
}
```

- [ ] **Step 5: Run full VS Code suite from clean install**

```powershell
Push-Location vscode\extension
npm ci
npm test
Pop-Location
```

- [ ] **Step 6: Run a real smoke using queried revision, IDs, fingerprints, and current values**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$fixture = "$PWD\tests\fixtures\vc6_project"
$out = "$env:TEMP\unitTestRunner-input-editor-smoke\Control_Update"
$changesPath = Join-Path $env:TEMP ("unitTestRunner-input-changes-" + [guid]::NewGuid().ToString("N") + ".json")

py -m unit_test_runner --json analyze-function --workspace $fixture --dsw "$fixture\Product.dsw" --source src\control.c --function Control_Update --configuration "Win32 Debug" --project Control --out $out --phase harness
$formEnvelope = py -m unit_test_runner --json get-test-input-form --workspace $out | ConvertFrom-Json
$form = $formEnvelope.data.details
$changes = @()
foreach ($case in @($form.cases)) {
  foreach ($item in @($case.items)) {
    if (-not $item.blocking) { continue }
    $values = [ordered]@{}
    foreach ($control in @($item.controls)) {
      if (-not $control.required_for_confirmation) { continue }
      $current = [string]$control.value
      $isUnresolved = [string]::IsNullOrWhiteSpace($current) -or $current -match '^(?i:TBD|TODO|UNKNOWN|UNRESOLVED)'
      if (-not $isUnresolved) {
        $values[$control.name] = $current
        continue
      }
      $suggestion = @($control.suggestions) | Select-Object -First 1
      $values[$control.name] = if ($null -ne $suggestion) { [string]$suggestion.value } else { '0' }
    }
    $changes += [ordered]@{
      item_id = [string]$item.item_id
      subject_fingerprint = [string]$item.subject_fingerprint
      values = $values
      confirmed = $true
    }
  }
}
[ordered]@{ schema_version = '1.0'; changes = $changes } |
  ConvertTo-Json -Depth 12 |
  Set-Content -LiteralPath $changesPath -Encoding utf8

try {
  py -m unit_test_runner --json apply-test-input-form --workspace $out --input $changesPath --expected-revision ([int]$form.revision)
  py -m unit_test_runner --json get-test-spec --workspace $out
  py -m unit_test_runner --json generate-harness-skeleton --function-signature "$out\reports\function_signature.json" --global-access "$out\reports\global_access.json" --call-report "$out\reports\call_report.json" --test-spec "$out\reports\test_spec.json" --dependency-policy "$out\reports\dependency_policy.json" --out $out --overwrite
  py -m unit_test_runner --json build-probe --workspace $out --dry-run --overwrite
}
finally {
  Remove-Item -LiteralPath $changesPath -Force -ErrorAction SilentlyContinue
}
```

Expected: no hard-coded ID, fingerprint, or revision; apply advances one revision; blocking count falls; promoted case reaches generated C; build-probe dry-run passes.

- [ ] **Step 7: Build distribution**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_distribution.ps1
```

Verify packaged CLI `--help` lists both commands and VSIX manifest contains the editor command.

- [ ] **Step 8: Inspect final diff**

```powershell
git diff --check
git status --short
git diff -- src/unit_test_runner/schemas/test_spec.schema.json
```

Expected: no whitespace/temp files, no unapproved canonical schema change, no normal-path legacy consumer, no formal-review mutation.

- [ ] **Step 9: Commit docs**

```powershell
git add README.md docs/test_input_editor.md docs/vscode_usage_guide.md vscode/extension/src/test/uiCopy.test.ts
git commit -m "docs: explain test input editor workflow"
```

## Completion Gate

Before declaring completion, verify from fresh command output:

- strict bounded freshness-validated form contracts;
- item IDs stable across reorder and promotion/demotion, with no array index or case location in the hash;
- ambiguous items not writable;
- atomic partial save and one revision increment;
- confirmed unresolved values rejected, advisory C warnings saveable;
- formal review/provenance/history unchanged;
- only eligible ready candidates promote;
- intentional candidates stay additional;
- only touched unsafe executable cases demote;
- view-export failure does not roll back canonical JSON;
- VS Code uses canonical `--test-spec` and `--previous-test-spec`;
- Webview escape/CSP/no direct canonical write;
- in-session draft retention only;
- explicit conflict resolution with draft preservation;
- no CLI process during Workflow render;
- Python suite, VS Code suite, canonical smoke, and distribution build all pass.
