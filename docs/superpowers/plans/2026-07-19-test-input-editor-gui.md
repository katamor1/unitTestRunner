# Test Input Editor GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated VS Code editor that lets users enter and confirm unresolved test inputs, state values, stub settings, expected values, and other review-required fields without directly editing canonical JSON.

**Architecture:** Keep the VS Code extension as a thin adapter. A new Python `test_input_form` service reads and validates `reports/test_spec.json`, builds a strict GUI form model, applies revision- and fingerprint-guarded changes, and promotes or demotes test cases safely. The TypeScript side owns rendering, in-session drafts, conflict presentation, temporary request files, and asynchronous Workflow summary caching; it never writes canonical JSON directly.

**Tech Stack:** Python 3.12, `dataclasses`, `pathlib`, `hashlib`, `json`, existing `jsonschema` contracts, `unittest`; TypeScript 5.4, VS Code Webview API 1.85, Node.js 20 built-ins, `node:test`.

## Global Constraints

- Treat `reports/test_spec.json` as the only editable source of truth. Do not import edits from `test_spec.md`, `test_spec.csv`, or legacy `test_case_design.json`.
- Do not change canonical `test_spec` schema version `1.1.0` or add GUI-only fields to it.
- Keep formal review authority unchanged: never edit `review_item_ids`, review decision ledgers, reviewer identity, decision resolution, readiness, provenance, source identity, function identity, schema version, or case identity.
- The VS Code extension must not parse domain semantics or write canonical JSON. Validation, revision checks, fingerprint checks, confirmation state, promotion, demotion, and persistence belong to Python.
- Do not run CLI commands from `renderWorkflowHtml()` or any other synchronous render path. Workflow summaries are fetched asynchronously and cached in `workspaceState`.
- Use exact, bounded form contracts: input file at most 4 MiB, at most 1,000 changed items, at most 16 changed leaves per item, C expressions at most 4,096 Unicode code points, multiline text at most 16,384 Unicode code points.
- Preserve the existing atomic canonical save path through `save_test_spec_snapshot()`. Validate all changes before the first canonical write.
- If canonical JSON saves but Markdown/CSV view export fails, keep the new JSON revision, return a warning with `views_written: false`, and never roll back the canonical file.
- Maintain VC6/C90 behavior. C expressions are stored as text and are never evaluated inside VS Code or Python form validation.
- Use TDD for every task: add a focused failing test, run it and inspect the intended failure, add the minimum implementation, rerun the focused test, then commit.
- Literal values beginning with `TBD`, `TODO`, `UNKNOWN`, or `UNRESOLVED` in this plan are domain placeholders under test, not unfinished implementation-plan sections.

## File Structure Map

### Python core

- Create `src/unit_test_runner/test_input_form/__init__.py` — public query/apply interfaces and typed errors.
- Create `src/unit_test_runner/test_input_form/models.py` — strict form-output and change-input data models.
- Create `src/unit_test_runner/test_input_form/field_catalog.py` — allowlisted collections, editable leaves, control kinds, required rules, and locator attributes.
- Create `src/unit_test_runner/test_input_form/field_locator.py` — semantic locators, opaque item IDs, subject fingerprints, and ambiguity detection.
- Create `src/unit_test_runner/test_input_form/validation.py` — normalization, unresolved-value detection, hard validation, and C-expression warnings.
- Create `src/unit_test_runner/test_input_form/suggestions.py` — evidence-backed candidate values from analysis artifacts and canonical siblings.
- Create `src/unit_test_runner/test_input_form/service.py` — current-snapshot loading, form construction, summary calculation, change application, case reclassification, save, and view export.
- Modify `src/unit_test_runner/cli/parser.py` — add `get-test-input-form` and `apply-test-input-form`.
- Modify `src/unit_test_runner/cli/commands.py` — dispatch and handlers for both commands.
- Modify `src/unit_test_runner/cli/errors.py` and `src/unit_test_runner/cli/main.py` — preserve structured form/conflict error codes in the v1 CLI envelope.
- Modify `tests/spec_support.py` — reusable canonical workspaces with unresolved executable cases and intentional additional candidates.
- Create focused Python test modules named in the tasks below.

### VS Code adapter

- Modify `vscode/extension/src/cli/commandBuilder.ts` — canonical consumer paths plus form query/apply invocations.
- Modify `vscode/extension/src/reports/reportPathResolver.ts` — canonical `testSpecJson`, `testSpecMd`, and `testSpecCsv` paths.
- Modify `vscode/extension/src/cli/cliEnvelope.ts` — map canonical TestSpec artifacts from v1 results.
- Create `vscode/extension/src/testInputEditor/contracts.ts` — strict CLI details and Webview-message parsing.
- Create `vscode/extension/src/testInputEditor/cliClient.ts` — CLI execution, typed failures, temporary request files, and cleanup.
- Create `vscode/extension/src/testInputEditor/draftState.ts` — pure draft reducer and conflict merge rules.
- Create `vscode/extension/src/testInputEditor/renderer.ts` — escaped, nonce-protected editor HTML.
- Create `vscode/extension/src/testInputEditor/controller.ts` — testable save/discard/reload orchestration with injected ports.
- Create `vscode/extension/src/testInputEditor/panel.ts` — thin VS Code Webview Panel wrapper and per-workspace singleton.
- Create `vscode/extension/src/testInputEditor/summaryCache.ts` — summary cache model and refresh/invalidation helpers.
- Modify `vscode/extension/src/workflow/workflowState.ts` and `workflowPanelBase.ts` — cached count, blocking emphasis, and editor action.
- Modify `vscode/extension/src/extension.ts`, `commands/commandRegistry.ts`, and `package.json` — registration, activation, callbacks, and startup refresh.
- Create focused TypeScript test modules named in the tasks below.

---

### Task 1: Switch existing VS Code consumers to canonical TestSpec paths

**Files:**
- Modify: `vscode/extension/src/cli/commandBuilder.ts`
- Modify: `vscode/extension/src/reports/reportPathResolver.ts`
- Modify: `vscode/extension/src/cli/cliEnvelope.ts`
- Modify: `vscode/extension/src/test/adapter.test.ts`
- Modify: `vscode/extension/src/test/cliEnvelope.test.ts`

**Interfaces:**
- `buildReanalyzeFunctionInvocation()` passes `--previous-test-spec <workspace>/reports/test_spec.json`.
- `buildGenerateHarnessSkeletonInvocation()` passes `--test-spec <workspace>/reports/test_spec.json`.
- `ReportPaths` exposes `testSpecJson`, `testSpecMd`, and `testSpecCsv` while retaining legacy view fields for compatibility.
- V1 produced artifacts named `test_spec.json`, `test_spec.md`, and `test_spec.csv` resolve to canonical report keys.

- [ ] **Step 1: Replace the legacy path expectations with failing canonical-path assertions**

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

Add resolver and envelope assertions:

```typescript
const reports = resolveReportPaths(target.outputWorkspace);
assert.equal(reports.testSpecJson, path.join(target.outputWorkspace, 'reports', 'test_spec.json'));
assert.equal(reports.testSpecMd, path.join(target.outputWorkspace, 'reports', 'test_spec.md'));
assert.equal(reports.testSpecCsv, path.join(target.outputWorkspace, 'reports', 'test_spec.csv'));
```

- [ ] **Step 2: Run the focused adapter tests and verify they fail on the current legacy arguments**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/adapter.test.js dist/test/cliEnvelope.test.js
Pop-Location
```

Expected: assertions report missing `--previous-test-spec`, missing `--test-spec`, or missing canonical report fields.

- [ ] **Step 3: Change only the command arguments and canonical path mappings**

Use these exact argument substitutions in `commandBuilder.ts`:

```typescript
'--previous-test-spec',
path.join(reports, 'test_spec.json'),
```

```typescript
'--test-spec',
path.join(reports, 'test_spec.json'),
```

Add these conventional paths:

```typescript
testSpecJson: dialect.join(reports, 'test_spec.json'),
testSpecMd: dialect.join(reports, 'test_spec.md'),
testSpecCsv: dialect.join(reports, 'test_spec.csv'),
```

Add these filename mappings in `cliEnvelope.ts`:

```typescript
'test_spec.json': 'test_spec_json',
'test_spec.md': 'test_spec_md',
'test_spec.csv': 'test_spec_csv',
```

Map those keys in `cliResultParser.ts` if its `reportsFromSource()` switch requires explicit fields.

- [ ] **Step 4: Rerun the focused tests**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/adapter.test.js dist/test/cliEnvelope.test.js
Pop-Location
```

Expected: both files pass and no assertion still references a legacy consumer argument.

- [ ] **Step 5: Commit the canonical-path migration**

```powershell
git add vscode/extension/src/cli/commandBuilder.ts vscode/extension/src/reports/reportPathResolver.ts vscode/extension/src/cli/cliEnvelope.ts vscode/extension/src/cli/cliResultParser.ts vscode/extension/src/test/adapter.test.ts vscode/extension/src/test/cliEnvelope.test.ts
git commit -m "refactor: use canonical test spec in vscode adapter"
```

### Task 2: Define strict Python form contracts and the editable-field catalog

**Files:**
- Create: `src/unit_test_runner/test_input_form/__init__.py`
- Create: `src/unit_test_runner/test_input_form/models.py`
- Create: `src/unit_test_runner/test_input_form/field_catalog.py`
- Create: `tests/test_test_input_form_models.py`

**Interfaces:**
- `TestInputFormError(code: str, message: str)` carries a stable machine error code.
- Immutable output models serialize to form schema version `1.0`.
- `parse_test_input_change_request(value)` rejects missing, extra, mistyped, duplicate, or oversized data.
- `FIELD_RULES` is the only authority for editable collections and leaves.

- [ ] **Step 1: Write failing tests for strict change-request parsing**

Cover a valid request, an unknown top-level field, a duplicate `item_id`, more than 1,000 changes, more than 16 leaves, a non-boolean `confirmed`, and an unsupported control leaf.

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

with self.assertRaisesRegex(TestInputFormError, "unknown properties"):
    parse_test_input_change_request(
        {"schema_version": "1.0", "changes": [], "unexpected": True}
    )
```

- [ ] **Step 2: Write failing catalog tests for every approved collection and control**

Assert the exact allowlist:

```python
self.assertEqual(
    {
        "input_assignments",
        "state_setups",
        "stub_setups",
        "expected_observations",
        "preconditions",
        "execution_steps",
        "dependency_overrides",
    },
    set(FIELD_RULES),
)
self.assertEqual(
    ("value_expression", "setup_method_hint"),
    tuple(control.name for control in FIELD_RULES["state_setups"].controls),
)
```

Also assert:

- `dependency_overrides.mode` is enum `inherit|real|stub`.
- `dependency_overrides.rationale` becomes required only for explicit `real` or `stub`.
- `stub_setups.value_expression` is not execution-required for `call_count_observation` or `argument_capture`.
- No rule exposes `review_item_ids`, `coverage_links`, `candidate_links`, identity, provenance, or warning evidence.

- [ ] **Step 3: Run the focused tests and verify import failures**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models -v
```

Expected: failure because `unit_test_runner.test_input_form` does not exist.

- [ ] **Step 4: Implement immutable models and strict parsers**

Use these public shapes in `models.py`:

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

`TestInputFormError` must expose `.code` and use codes from this finite set:

```python
FORM_ERROR_CODES = {
    "test_input_form_invalid",
    "test_input_revision_conflict",
    "test_input_subject_conflict",
    "test_input_validation",
    "stale_test_spec",
}
```

- [ ] **Step 5: Implement the catalog as data plus small rule functions**

Use immutable rules:

```python
@dataclass(frozen=True)
class ControlRule:
    name: str
    control_kind: str
    required_by_default: bool
    enum_values: tuple[str, ...] = ()

@dataclass(frozen=True)
class FieldRule:
    collection: str
    kind: str
    locator_fields: tuple[str, ...]
    controls: tuple[ControlRule, ...]
    execution_value_field: str | None = None
```

Provide these total functions, with no caller-side special cases:

```python
def required_for_confirmation(rule: FieldRule, control: ControlRule, parent: Mapping[str, Any]) -> bool: ...
def execution_value_required(rule: FieldRule, parent: Mapping[str, Any]) -> bool: ...
def label_for_parent(rule: FieldRule, parent: Mapping[str, Any]) -> str: ...
def editable_control_names(rule: FieldRule) -> frozenset[str]: ...
```

- [ ] **Step 6: Rerun the focused tests**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models -v
```

Expected: all strict parser and catalog tests pass.

- [ ] **Step 7: Commit the form-contract foundation**

```powershell
git add src/unit_test_runner/test_input_form tests/test_test_input_form_models.py
git commit -m "feat: define test input form contracts"
```

### Task 3: Build semantic item locators, opaque IDs, and fingerprints

**Files:**
- Create: `src/unit_test_runner/test_input_form/field_locator.py`
- Create: `tests/test_test_input_form_locator.py`
- Modify: `src/unit_test_runner/test_input_form/__init__.py`

**Interfaces:**
- `locate_form_items(spec: TestSpec) -> tuple[LocatedFormItem, ...]` scans both case collections.
- `item_id` is `item-` plus SHA256 of canonical semantic locator JSON.
- `subject_fingerprint` is SHA256 of canonical parent-object JSON.
- Array indices exist only as internal coordinates for the current snapshot; they are never serialized into `item_id`.
- Duplicate semantic locators are marked ambiguous and are never writable.

- [ ] **Step 1: Write a stable-ID test that reorders cases and item arrays**

```python
first = {item.semantic_key: item.item_id for item in locate_form_items(spec)}
reordered = copy.deepcopy(spec)
reordered.test_cases.reverse()
reordered.test_cases[0]["input_assignments"].reverse()
second = {item.semantic_key: item.item_id for item in locate_form_items(reordered)}
self.assertEqual(first, second)
```

- [ ] **Step 2: Write locator-identity tests for all collections**

Assert these identity attributes:

```text
input: target_kind, target_name, source_candidate_id
state: scope, variable_name, source_candidate_id
stub: stub_name, setup_kind, related_call_id, source_candidate_id
expected: observation_kind, target_name, source
dependency: callee
precondition: source
execution step: order, action
```

- [ ] **Step 3: Write an ambiguity test**

Create two parent objects with the same semantic locator and assert both entries have `ambiguous is True`, `editable is False`, and the resolver refuses that `item_id`.

- [ ] **Step 4: Run the locator tests and verify missing implementation failures**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_locator -v
```

- [ ] **Step 5: Implement canonical hashing and current-snapshot coordinates**

```python
def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()
```

Use this serialized locator shape exactly:

```python
locator = {
    "case_id": case_id,
    "case_location": case_location,
    "collection": rule.collection,
    "kind": rule.kind,
    "identity": {name: parent.get(name) for name in rule.locator_fields},
}
item_id = "item-" + _digest(locator)
subject_fingerprint = _digest(parent)
```

Define `LocatedFormItem` with `case_index` and `item_index` for mutation, plus `locator`, `item_id`, `subject_fingerprint`, `rule`, `parent`, and `ambiguous`.

- [ ] **Step 6: Detect ambiguity in a second pass instead of appending an index**

Group by `item_id`; if a group length is not one, replace each member with `ambiguous=True`. Do not invent suffixes or use array positions as fallback identities.

- [ ] **Step 7: Rerun locator and model tests**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models tests.test_test_input_form_locator -v
```

- [ ] **Step 8: Commit the locator boundary**

```powershell
git add src/unit_test_runner/test_input_form/field_locator.py src/unit_test_runner/test_input_form/__init__.py tests/test_test_input_form_locator.py
git commit -m "feat: locate editable test spec items safely"
```

### Task 4: Query the current form, calculate summaries, warnings, and suggestions

**Files:**
- Create: `src/unit_test_runner/test_input_form/validation.py`
- Create: `src/unit_test_runner/test_input_form/suggestions.py`
- Create: `src/unit_test_runner/test_input_form/service.py`
- Create: `tests/test_test_input_form_query.py`
- Modify: `tests/spec_support.py`
- Modify: `src/unit_test_runner/test_input_form/__init__.py`

**Interfaces:**
- `build_test_input_form(workspace: Path, *, summary_only: bool = False) -> TestInputFormDocument`.
- `is_unresolved(value)` recognizes `None`, blank text, and case-insensitive prefixes `TBD`, `TODO`, `UNKNOWN`, and `UNRESOLVED`.
- Summary counts unique item cards, never editable leaves.
- Suggestions always include `source` and `confidence`; absence of reliable evidence yields no suggestion.

- [ ] **Step 1: Extend fixture support with an unresolved canonical workspace**

Add a helper that writes:

- one unresolved main case in `additional_case_candidates` with `input_assignments`, `state_setups`, `stub_setups`, and `expected_observations` carrying boolean `review_required`;
- one intentional additional candidate with no execution-required objects;
- current source and all provenance files required by `build_current_artifact_context()`;
- a boundary candidate whose `source_candidate_id` maps to `MODE_AUTO`.

Return the canonical path and expected case IDs so tests do not depend on hard-coded array positions.

- [ ] **Step 2: Write failing query tests for item aggregation and forced unresolved extraction**

Assert that one `state_setups` parent becomes one item with two controls:

```python
state_item = next(item for item in case.items if item.kind == "state_setup")
self.assertEqual(
    {"value_expression", "setup_method_hint"},
    {control.name for control in state_item.controls},
)
```

Also assert an unresolved execution value is shown even when its parent currently has `review_required: false`.

- [ ] **Step 3: Write failing summary tests**

Use overlapping unresolved, unconfirmed, warning, and blocking states and assert:

```python
self.assertEqual(4, form.summary.attention_count)
self.assertEqual(2, form.summary.unresolved_count)
self.assertEqual(3, form.summary.unconfirmed_count)
self.assertEqual(2, form.summary.execution_blocking_count)
self.assertEqual(1, form.summary.warning_count)
```

Each count must be based on a set of `item_id` values.

- [ ] **Step 4: Write failing tests for summary-only, promotion eligibility, suggestions, and stale artifacts**

Assert:

- `summary_only=True` returns `cases is None` but performs the same strict freshness validation.
- the unresolved main candidate is `promotion_eligible=True`.
- the intentional empty additional candidate is absent from the case list and never promotion-eligible.
- the input control suggests `MODE_AUTO` from `boundary_candidate` with its confidence.
- pointer input suggests `NULL` only when signature evidence says pointer.
- an obvious flag target suggests `0` and `1`.
- stale source bytes raise `TestInputFormError` with code `stale_test_spec`.

- [ ] **Step 5: Run the query tests and confirm the service is missing**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_query -v
```

- [ ] **Step 6: Implement normalization and warning primitives**

```python
UNRESOLVED_PREFIXES = ("TBD", "TODO", "UNKNOWN", "UNRESOLVED")


def is_unresolved(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.upper().startswith(UNRESOLVED_PREFIXES)
```

Provide:

```python
def normalize_c_expression(value: Any) -> str: ...
def normalize_multiline(value: Any) -> str: ...
def normalize_enum(value: Any, allowed: tuple[str, ...]) -> str: ...
def c_expression_warnings(value: str, *, type_hint: Mapping[str, Any] | None, suggestions: tuple[FormSuggestion, ...]) -> tuple[dict[str, str], ...]: ...
```

Hard normalization rules:

- C expression: trim, reject CR/LF and NUL, enforce 4,096 code points.
- Multiline: normalize CRLF/CR to LF, reject NUL, enforce 16,384 code points.
- Enum: exact ASCII token from the approved set.

Warnings may cover unbalanced delimiters/quotes, likely scalar/string or pointer mismatch, unknown identifiers/macros, likely non-C90 constructs, missing type evidence, and free input outside suggestions. They must not block query or save by themselves.

- [ ] **Step 7: Implement evidence-backed suggestions**

Read only files already bound to the canonical snapshot:

```text
reports/boundary_equivalence_candidates.json
reports/function_signature.json
reports/test_spec.json
```

Index boundary candidates by `candidate_id`; index concrete canonical values by semantic target. Add `NULL` only for proven pointer inputs, `0/1` only for explicit boolean/flag evidence, and enum constants only when a unique enum list is present in signature evidence. Deduplicate by value while preserving the strongest evidence order.

- [ ] **Step 8: Implement strict current-snapshot loading and form construction**

Use the existing freshness path:

```python
snapshot = load_test_spec_snapshot(path, mode=ContractMode.STRICT)
context = build_current_artifact_context(workspace, snapshot.spec)
violations = validate_test_spec(snapshot.spec, current_context=context)
if violations:
    raise TestSpecContractError(violations)
```

For each located item:

- show it when `review_required is True` or an execution-required control is unresolved;
- emit a read-only warning when execution-required data has no boolean `review_required`;
- set `confirmed` to the inverse of boolean `review_required`;
- set `blocking` from the catalog execution rule;
- omit cases with no visible item;
- calculate `promotion_eligible` from the pre-save candidate snapshot;
- build summary sets from the final item list.

Map stale contract failures to `TestInputFormError("stale_test_spec", message)`.

- [ ] **Step 9: Rerun query, locator, and model tests**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models tests.test_test_input_form_locator tests.test_test_input_form_query -v
```

- [ ] **Step 10: Commit the read/query service**

```powershell
git add src/unit_test_runner/test_input_form tests/spec_support.py tests/test_test_input_form_query.py
git commit -m "feat: build test input form views"
```

### Task 5: Apply partial changes with confirmation and conflict guards

**Files:**
- Modify: `src/unit_test_runner/test_input_form/service.py`
- Modify: `src/unit_test_runner/test_input_form/validation.py`
- Create: `tests/test_test_input_form_apply.py`

**Interfaces:**
- `apply_test_input_form(workspace, request, *, expected_revision) -> TestInputApplyResult`.
- All item IDs and fingerprints are resolved against one current strict snapshot before any mutation.
- A value change defaults the parent to unconfirmed unless the same request explicitly sends `confirmed: true` and all required controls are concrete.
- Partial saves modify only submitted items.

- [ ] **Step 1: Write a failing partial-save test**

Change one input item while leaving all other unresolved items untouched. Assert:

- exactly one parent object changes;
- canonical revision increments exactly once;
- unsent parents remain byte-for-byte equal inside the payload;
- the changed parent has `review_required: true` when `confirmed` is false.

- [ ] **Step 2: Write failing confirmation tests**

Cover:

```python
# Value change and explicit confirmation in the same save.
change = TestInputChange(
    item_id=item.item_id,
    subject_fingerprint=item.subject_fingerprint,
    values={"value_expression": "MODE_AUTO"},
    confirmed=True,
)
```

Assert `review_required` becomes false. Then assert these operations are rejected without any canonical byte change:

- `confirmed=True` with blank or placeholder required control;
- unknown or ambiguous item ID;
- fingerprint mismatch;
- duplicate item ID in one request;
- enum value outside `inherit|real|stub`;
- parent `review_required` is not boolean;
- a leaf not present in the catalog.

- [ ] **Step 3: Write a failing formal-authority invariance test**

Capture before/after projections of:

```text
spec.review_item_ids
case.review_item_ids
unresolved_items
source
function
generated_from
coverage_links
candidate_links
```

Assert all are equal after a successful form save.

- [ ] **Step 4: Write limits and atomicity tests**

Assert the entire operation fails before writing when:

- the request has 1,001 changes;
- one item has 17 values;
- a C expression exceeds 4,096 code points or contains newline/NUL;
- multiline text exceeds 16,384 code points or contains NUL;
- the second change in a multi-change request is invalid.

For the last case compare the complete canonical bytes before and after.

- [ ] **Step 5: Run the apply tests and verify missing behavior**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_apply -v
```

- [ ] **Step 6: Implement all-target resolution before mutation**

Use this order inside `apply_test_input_form()`:

```text
load strict snapshot
build and validate current artifact context
compare expected revision
locate every current item
validate request IDs, uniqueness, editability, fingerprints, leaves, and value shapes
copy the TestSpec payload
apply every normalized change to the copy
validate every requested confirmation
validate the candidate canonical contract
save once
```

Do not call `save_test_spec_snapshot()` until all request items have passed validation.

- [ ] **Step 7: Apply confirmation state at the parent-object boundary**

```python
parent["review_required"] = not change.confirmed
```

If any value changes and `change.confirmed` is false, the parent remains review-required. If `change.confirmed` is true, validate all controls whose catalog rule returns `required_for_confirmation=True`; reject unresolved required values.

- [ ] **Step 8: Save through the canonical repository and return an exact snapshot**

```python
saved_snapshot, canonical_artifact = save_test_spec_snapshot(
    path,
    candidate,
    expected_revision=expected_revision,
    current_context=context,
)
```

Return updated count, confirmed count, canonical snapshot/artifact, empty promotion/demotion arrays for now, and the latest summary built from the saved snapshot.

- [ ] **Step 9: Rerun apply and query tests**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_apply tests.test_test_input_form_query -v
```

- [ ] **Step 10: Commit guarded partial updates**

```powershell
git add src/unit_test_runner/test_input_form/service.py src/unit_test_runner/test_input_form/validation.py tests/test_test_input_form_apply.py
git commit -m "feat: apply guarded test input changes"
```

### Task 6: Promote ready candidates, demote touched unsafe cases, and export views durably

**Files:**
- Modify: `src/unit_test_runner/test_input_form/service.py`
- Create: `tests/test_test_input_form_reclassification.py`
- Modify: `tests/test_test_input_form_apply.py`

**Interfaces:**
- Promotion uses eligibility captured from the pre-save snapshot.
- Demotion is limited to executable cases whose execution-required item was touched in this request.
- Case order and all formal/provenance fields are preserved.
- Markdown/CSV export is attempted after canonical save and may yield a warning without rolling back JSON.

- [ ] **Step 1: Write a failing intentional-candidate test**

An additional candidate with no execution-required parent objects must remain in `additional_case_candidates` even when every visible review field is confirmed.

- [ ] **Step 2: Write a failing promotion test**

For an unresolved main candidate, submit concrete confirmed values for all execution-required parents. Assert:

- the case moves to the end of `test_cases`;
- it is removed from `additional_case_candidates`;
- its case payload, review IDs, coverage links, and provenance fields are otherwise unchanged;
- `coverage_summary` and canonical `unresolved_items` are unchanged;
- `promoted_case_ids` contains only that ID.

- [ ] **Step 3: Write failing demotion and no-op classification tests**

Assert:

- changing an executable input to an unresolved value demotes the touched case;
- changing confirmation to false on a touched execution-required parent demotes it;
- editing only `note`, `setup_method_hint`, `call_behavior`, precondition text, execution detail, or dependency rationale does not move the case;
- untouched legacy executable cases are never reclassified;
- duplicate case IDs across source and destination cause total failure before save.

- [ ] **Step 4: Write a view-export failure test**

Patch `export_test_spec_snapshot_views()` to raise after canonical save. Assert:

- canonical revision advanced and contains the requested values;
- result has `views_written is False`;
- result warnings include code `test_spec_view_export_failed`;
- the old revision is not restored.

- [ ] **Step 5: Run reclassification tests and verify failures**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_reclassification -v
```

- [ ] **Step 6: Implement execution-object helpers**

Provide total helpers:

```python
def execution_objects(case: Mapping[str, Any]) -> tuple[tuple[str, Mapping[str, Any], str], ...]: ...
def candidate_is_promotion_eligible(case: Mapping[str, Any], executable_ids: frozenset[str]) -> bool: ...
def execution_case_is_ready(case: Mapping[str, Any]) -> bool: ...
def reclassify_cases(spec: TestSpec, *, eligible_before: frozenset[str], touched_execution_case_ids: frozenset[str]) -> tuple[list[str], list[str]]: ...
```

Execution values are exactly:

```text
input_assignments[].value_expression
state_setups[].value_expression
stub_setups[].value_expression, except call_count_observation and argument_capture
expected_observations[].expected_expression
```

- [ ] **Step 7: Implement stable-order promotion and demotion**

Promotions append eligible ready candidates in their original candidate order. Demotions append touched unsafe executable cases in their original executable order. Validate case IDs are unique before and after movement.

- [ ] **Step 8: Export views after the canonical save**

```python
try:
    view_export = export_test_spec_snapshot_views(
        saved_snapshot,
        path.parent,
        canonical_path=path,
    )
    views_written = view_export.written
except (OSError, ValueError, TestSpecViewDurabilityError) as error:
    views_written = False
    warnings.append(
        {"code": "test_spec_view_export_failed", "message": str(error)}
    )
```

Do not catch canonical save failures in this block.

- [ ] **Step 9: Run all Python form tests**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_models tests.test_test_input_form_locator tests.test_test_input_form_query tests.test_test_input_form_apply tests.test_test_input_form_reclassification -v
```

- [ ] **Step 10: Commit safe case reclassification**

```powershell
git add src/unit_test_runner/test_input_form/service.py tests/test_test_input_form_apply.py tests/test_test_input_form_reclassification.py
git commit -m "feat: reclassify completed test input cases"
```

### Task 7: Expose strict form query/apply commands through the CLI

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
- Success details use the exact form/apply keys from the design.
- Expected failures carry a stable error code in `data.errors[].code`.

- [ ] **Step 1: Write failing parser tests**

```python
args = build_parser().parse_args(
    ["get-test-input-form", "--workspace", "out", "--summary-only"]
)
self.assertTrue(args.summary_only)

args = build_parser().parse_args(
    [
        "apply-test-input-form",
        "--workspace", "out",
        "--input", "changes.json",
        "--expected-revision", "3",
    ]
)
self.assertEqual(3, args.expected_revision)
```

- [ ] **Step 2: Write failing subprocess tests for successful query and apply**

Use the existing v1 CLI envelope pattern and assert values under `payload["data"]["details"]`:

```python
self.assertEqual("1.0", details["schema_version"])
self.assertEqual(1, details["revision"])
self.assertRegex(details["spec_sha256"], r"^[0-9a-f]{64}$")
self.assertIn("summary", details)
```

For apply, assert revision, updated count, promoted/demoted arrays, summary, `views_written`, and produced TestSpec artifacts.

- [ ] **Step 3: Write failing structured-error tests**

Cover stale revision, fingerprint conflict, invalid confirmation, oversized input file, malformed JSON, and stale source. Assert nonzero exit and exact codes such as:

```python
self.assertEqual(
    "test_input_revision_conflict",
    payload["data"]["errors"][0]["code"],
)
```

Compare canonical bytes before/after every rejected apply call.

- [ ] **Step 4: Run the CLI tests and verify missing subcommands**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_cli -v
```

- [ ] **Step 5: Add parser entries beside `get-test-spec` and `update-test-spec`**

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

- [ ] **Step 6: Preserve machine error codes through `CLIError`**

```python
class CLIError(Exception):
    def __init__(
        self,
        message: str,
        exit_code: int,
        command: str = "unknown",
        code: str = "error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.command = command
        self.code = code
```

In `main.py`, emit:

```python
errors=[{"code": exc.code, "message": exc.message}],
```

Keep the default code so existing callers remain compatible.

- [ ] **Step 7: Implement handlers and dispatch mapping**

`handle_get_test_input_form()` returns `document.to_dict()` directly in CLI details. `handle_apply_test_input_form()` must:

- reject input files larger than 4 MiB before JSON parsing;
- parse UTF-8-sig JSON as an object;
- call the strict request parser;
- call `apply_test_input_form()`;
- return canonical artifact always and Markdown/CSV artifacts only when written;
- convert `TestInputFormError.code` into structured `CLIError.code`.

Use `EXIT_INPUT_ERROR` for form, conflict, stale, and validation failures; keep unexpected failures on the existing internal-error path.

- [ ] **Step 8: Rerun CLI and existing TestSpec CLI tests**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_cli tests.test_test_spec_cli -v
```

- [ ] **Step 9: Commit the CLI surface**

```powershell
git add src/unit_test_runner/cli src/unit_test_runner/test_input_form/__init__.py tests/test_test_input_form_cli.py
git commit -m "feat: expose test input form cli commands"
```

### Task 8: Prove the canonical Python workflow end to end

**Files:**
- Create: `tests/test_test_input_form_end_to_end.py`
- Modify: `tests/spec_support.py`

**Interfaces:**
- Exercises the real CLI sequence from form query through harness and build-probe dry-run.
- Verifies the legacy `test_case_design.json` file is not used or modified.

- [ ] **Step 1: Create an analysis-backed fixture workspace**

Use `tests/fixtures/vc6_project` and run:

```text
analyze-function --phase harness
get-test-input-form
apply-test-input-form
generate-harness-skeleton --test-spec
build-probe --workspace --dry-run
```

Before apply, add one intentional additional candidate with no execution objects using the canonical repository fixture helper, not a raw text replacement.

- [ ] **Step 2: Write the failing end-to-end test**

The test must:

1. query the form and collect every execution-blocking item;
2. build a valid request using concrete expressions (`0`, `1`, `NULL`, or an existing suggestion) and `confirmed: true`;
3. apply at the queried revision;
4. query `get-test-spec` and assert the main case moved to `test_cases`;
5. assert the intentional additional candidate stayed in `additional_case_candidates`;
6. regenerate the harness with `--test-spec reports/test_spec.json`;
7. assert generated C contains the concrete expressions and no replaced domain placeholder;
8. run `build-probe --workspace <out> --dry-run --overwrite` successfully;
9. assert canonical revision advanced once and Markdown/CSV identities match that revision/SHA;
10. assert legacy `test_case_design.json` bytes are unchanged.

- [ ] **Step 3: Run the end-to-end test and diagnose the first missing link**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_end_to_end -v
```

- [ ] **Step 4: Fix only integration seams exposed by the test**

Acceptable fixes are limited to:

- service data passed to the existing harness consumer;
- CLI artifact reporting;
- fixture completeness;
- canonical report paths;
- build-probe prerequisites already generated by the harness-phase analysis.

Do not add a legacy fallback to make the test pass.

- [ ] **Step 5: Rerun focused Python integration and consumer tests**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_input_form_end_to_end tests.test_test_spec_consumers tests.test_dependency_policy_end_to_end -v
```

- [ ] **Step 6: Commit the canonical end-to-end proof**

```powershell
git add tests/test_test_input_form_end_to_end.py tests/spec_support.py
git commit -m "test: cover canonical test input workflow"
```

### Task 9: Add strict TypeScript form contracts and the CLI client

**Files:**
- Modify: `vscode/extension/src/cli/commandBuilder.ts`
- Create: `vscode/extension/src/testInputEditor/contracts.ts`
- Create: `vscode/extension/src/testInputEditor/cliClient.ts`
- Create: `vscode/extension/src/test/testInputCliClient.test.ts`

**Interfaces:**
- `buildGetTestInputFormInvocation(settings, workspace, summaryOnly)`.
- `buildApplyTestInputFormInvocation(settings, workspace, inputPath, expectedRevision)`.
- Strict parsers expose typed `TestInputFormModel`, `TestInputApplyResult`, and structured `TestInputCliError`.
- Apply requests are written under a supplied storage root and deleted in `finally`.

- [ ] **Step 1: Write failing command-builder tests**

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

- [ ] **Step 2: Write strict parser tests using complete v1 envelopes**

Assert accepted query/apply results, and reject:

- unknown keys at every form level;
- wrong schema version;
- malformed SHA256 values;
- duplicate item/control IDs;
- unsupported control kind;
- noninteger counts/revision;
- an error envelope without a supported machine code.

- [ ] **Step 3: Write a temporary-file cleanup test**

Inject fake `run`, `writeFile`, `mkdir`, and `rm` functions. Assert `rm` runs after success, CLI failure, timeout, and parser failure, and the path is below the configured storage root.

- [ ] **Step 4: Run the focused TypeScript test and verify missing modules**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputCliClient.test.js
Pop-Location
```

- [ ] **Step 5: Implement command builders**

```typescript
export function buildGetTestInputFormInvocation(
  settings: AdapterSettings,
  workspace: string,
  summaryOnly = false,
): CliInvocation {
  const args = jsonPrefix(settings).concat([
    'get-test-input-form', '--workspace', workspace,
  ]);
  if (summaryOnly) {
    args.push('--summary-only');
  }
  return invocation(settings, args, false);
}

export function buildApplyTestInputFormInvocation(
  settings: AdapterSettings,
  workspace: string,
  inputPath: string,
  expectedRevision: number,
): CliInvocation {
  return invocation(settings, jsonPrefix(settings).concat([
    'apply-test-input-form',
    '--workspace', workspace,
    '--input', inputPath,
    '--expected-revision', String(expectedRevision),
  ]), false);
}
```

- [ ] **Step 6: Implement strict contracts without `any`**

Expose these principal types:

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

Parse CLI v1 `data.details` after `parseCliEnvelopeValue()`; do not trust `parsedJson` through casts.

- [ ] **Step 7: Implement the injected CLI client and typed errors**

The client must expose:

```typescript
load(workspace: string, summaryOnly?: boolean): Promise<TestInputFormModel>
apply(workspace: string, revision: number, changes: readonly TestInputChangeDraft[]): Promise<TestInputApplyResult>
```

Serialize exactly:

```typescript
{
  schema_version: '1.0',
  changes: changes.map(toWireChange),
}
```

Create a random JSON filename with `crypto.randomUUID()`, use UTF-8, and delete in `finally`.

- [ ] **Step 8: Rerun client, adapter, and envelope tests**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputCliClient.test.js dist/test/adapter.test.js dist/test/cliEnvelope.test.js
Pop-Location
```

- [ ] **Step 9: Commit the TypeScript CLI boundary**

```powershell
git add vscode/extension/src/cli/commandBuilder.ts vscode/extension/src/testInputEditor vscode/extension/src/test/testInputCliClient.test.ts
git commit -m "feat: add test input editor cli client"
```

### Task 10: Implement pure draft state and secure editor rendering

**Files:**
- Create: `vscode/extension/src/testInputEditor/draftState.ts`
- Create: `vscode/extension/src/testInputEditor/renderer.ts`
- Create: `vscode/extension/src/test/testInputEditorState.test.ts`
- Create: `vscode/extension/src/test/testInputEditorRenderer.test.ts`

**Interfaces:**
- Pure state updates do not import `vscode`.
- Editing any control automatically clears that item’s confirmation in the draft.
- Reload merge reuses a draft only when item ID exists and the original fingerprint still matches.
- Renderer escapes all model text and emits nonce-protected CSP with no external resources or inline event attributes.

- [ ] **Step 1: Write failing draft-state tests**

Cover:

- select case;
- edit a C expression and auto-unconfirm;
- set confirmation explicitly after editing;
- build a request containing only dirty items;
- discard all drafts;
- keep a draft across hide/show;
- detect dirty title/footer state.

```typescript
const edited = editControl(state, item.itemId, 'value_expression', 'MODE_AUTO');
assert.equal(edited.drafts[item.itemId].confirmed, false);
assert.equal(edited.dirtyCount, 1);
```

- [ ] **Step 2: Write failing reload/conflict tests**

Assert:

- same item ID and unchanged baseline fingerprint reapply the draft;
- changed fingerprint creates a conflict;
- removed or ambiguous item becomes orphaned/read-only;
- choosing latest deletes the draft;
- choosing draft rebases it onto the latest fingerprint and keeps it dirty.

- [ ] **Step 3: Write failing renderer security and layout tests**

Assert the HTML contains:

- header with function/workspace/revision/summary;
- left case list and status counts;
- right sections for input, state, stub, expected, preconditions, execution, dependency, and other review items;
- editable input after a suggestion is chosen;
- one confirmation checkbox per item card;
- footer discard/save buttons and dirty count;
- empty-state text when there are zero items;
- `default-src 'none'`, nonce style/script, and no `onclick=`;
- escaped malicious label, path, expression, and warning values.

- [ ] **Step 4: Run focused state and renderer tests**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputEditorState.test.js dist/test/testInputEditorRenderer.test.js
Pop-Location
```

- [ ] **Step 5: Implement the pure reducer**

Expose these functions:

```typescript
createDraftState(model, workspace): TestInputEditorState
selectCase(state, caseId): TestInputEditorState
editControl(state, itemId, controlName, value): TestInputEditorState
setItemConfirmed(state, itemId, confirmed): TestInputEditorState
discardDrafts(state): TestInputEditorState
buildChangeDrafts(state): readonly TestInputChangeDraft[]
mergeReloadedModel(state, latest): TestInputEditorState
resolveConflictWithLatest(state, itemId): TestInputEditorState
resolveConflictWithDraft(state, itemId): TestInputEditorState
```

Use immutable copies so each transition is independently testable.

- [ ] **Step 6: Implement the renderer and browser script**

`renderTestInputEditorHtml()` receives the model/state, workspace display string, and nonce. The browser script may only:

- switch selected case;
- update input/textarea/select controls;
- apply a suggestion value to the still-editable input;
- toggle confirmation;
- send save/discard/reload/conflict-resolution messages;
- persist visual selection/scroll state with `getState()/setState()`.

All domain decisions remain outside the browser script.

- [ ] **Step 7: Rerun focused tests**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputEditorState.test.js dist/test/testInputEditorRenderer.test.js
Pop-Location
```

- [ ] **Step 8: Commit pure editor state and HTML**

```powershell
git add vscode/extension/src/testInputEditor/draftState.ts vscode/extension/src/testInputEditor/renderer.ts vscode/extension/src/test/testInputEditorState.test.ts vscode/extension/src/test/testInputEditorRenderer.test.ts
git commit -m "feat: render secure test input editor"
```

### Task 11: Add the testable controller, VS Code panel, singleton, save, and conflict flow

**Files:**
- Create: `vscode/extension/src/testInputEditor/controller.ts`
- Create: `vscode/extension/src/testInputEditor/panel.ts`
- Modify: `vscode/extension/src/testInputEditor/contracts.ts`
- Create: `vscode/extension/src/test/testInputEditorController.test.ts`

**Interfaces:**
- One panel per normalized function workspace.
- Closing and reopening in the same extension session restores drafts only when revision remains compatible.
- Save keeps the panel open, reloads the latest model, and notifies Workflow through an injected callback.
- Conflicts preserve drafts and require explicit latest/draft choice.

- [ ] **Step 1: Write strict Webview-message parser tests**

Allow only explicit message shapes such as:

```typescript
{ type: 'selectCase', caseId: 'TC_Control_Update_001' }
{ type: 'editControl', itemId, controlName: 'value_expression', value: 'MODE_AUTO' }
{ type: 'setConfirmed', itemId, confirmed: true }
{ type: 'save' }
{ type: 'discard' }
{ type: 'reload' }
{ type: 'resolveConflict', itemId, resolution: 'latest' }
{ type: 'resolveConflict', itemId, resolution: 'draft' }
```

Reject unknown properties, overlong strings, unknown control names, and malformed booleans before controller dispatch.

- [ ] **Step 2: Write controller tests with fake ports**

Inject a fake client and view port. Cover:

- initial load and render;
- save sends only dirty items;
- save success reloads, clears saved drafts, retains panel, and calls `onSaved(workspace)`;
- apply conflict preserves drafts and renders conflict actions;
- discard asks for confirmation when dirty and reloads canonical values;
- reload merges safe drafts and marks changed fingerprints as conflicts;
- zero-item form remains usable and offers canonical spec open action;
- CLI error keeps drafts and exposes an Output Channel action.

- [ ] **Step 3: Run the focused controller test**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputEditorController.test.js
Pop-Location
```

- [ ] **Step 4: Implement controller ports and orchestration**

Define injected boundaries:

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

The controller owns state transitions and never imports `vscode`.

- [ ] **Step 5: Implement the thin VS Code panel wrapper**

`TestInputEditorPanel.open()` must:

- normalize workspace key with platform path semantics;
- reveal an existing panel for that workspace instead of creating another;
- create `vscode.window.createWebviewPanel()` with scripts enabled and no retained external resource roots;
- use `context.storageUri ?? context.globalStorageUri` for the CLI client’s temporary root;
- parse every received message before controller dispatch;
- preserve controller/draft state in an in-memory map on dispose;
- restore only within the current extension process;
- update title with an unsaved marker;
- dispose subscriptions and remove the singleton entry cleanly.

- [ ] **Step 6: Implement explicit conflict presentation**

When revision or fingerprint conflict is returned:

1. keep current drafts;
2. load the latest model;
3. call `mergeReloadedModel()`;
4. render per-item `最新値を使う` and `下書きを採用` actions;
5. never resubmit automatically;
6. keep deleted/ambiguous drafts visible but excluded from `buildChangeDrafts()`.

- [ ] **Step 7: Rerun all editor tests**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputCliClient.test.js dist/test/testInputEditorState.test.js dist/test/testInputEditorRenderer.test.js dist/test/testInputEditorController.test.js
Pop-Location
```

- [ ] **Step 8: Commit the panel runtime**

```powershell
git add vscode/extension/src/testInputEditor vscode/extension/src/test/testInputEditorController.test.ts
git commit -m "feat: add test input editor panel workflow"
```

### Task 12: Integrate summary caching and the editor action into Workflow

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
- Command ID: `unitTestRunner.openTestInputEditor`.
- Workflow cache is keyed by workspace, revision, and canonical SHA256.
- Button label is `未確定項目を入力（N件）`; zero becomes `入力内容を確認（0件）`.
- Execution-blocking count applies warning emphasis, but never auto-opens the editor.

- [ ] **Step 1: Write failing summary-cache tests**

Cover:

- store and retrieve by exact workspace/revision/SHA;
- invalidate on workspace change;
- invalidate after analyze, reanalyze, or TestSpec save;
- reject a stale async response whose workspace is no longer current;
- preserve an error state separately from a valid count;
- summary refresh is an explicit async function, not part of HTML rendering.

- [ ] **Step 2: Write failing Workflow rendering tests**

Build `WorkflowState` values with cached summaries and assert:

```typescript
assert.match(html, /未確定項目を入力（7件）/);
assert.match(html, /data-command-id="unitTestRunner\.openTestInputEditor"/);
assert.match(blockingHtml, /class="[^"]*danger/);
assert.match(zeroHtml, /入力内容を確認（0件）/);
```

Assert no editor button appears when canonical `test_spec.json` is unavailable, and summary failure shows a count-less action plus warning text.

- [ ] **Step 3: Write failing manifest and registry tests**

Add the command to activation events, contributed commands, `UNIT_TEST_RUNNER_COMMAND_IDS`, and the handler map. The existing registry test must still prove exact one-to-one registration.

Use this Japanese title:

```text
UnitTestRunner: 未確定テスト項目を入力
```

- [ ] **Step 4: Run focused Workflow tests and verify failures**

```powershell
Push-Location vscode\extension
npm run compile
node --test dist/test/testInputSummaryCache.test.js dist/test/workflowPanel.test.js dist/test/commandRegistry.test.js dist/test/uiCopy.test.js
Pop-Location
```

- [ ] **Step 5: Extend state and availability without starting CLI work in render**

Add a serializable cached state:

```typescript
export interface TestInputSummaryState {
  workspace: string;
  revision: number;
  specSha256: string;
  summary: TestInputFormSummary;
  error?: string;
  updatedAt: string;
}
```

Add `testSpec` to `WorkflowReportAvailability`, derived from `reports.testSpecJson`. `renderWorkflowHtml()` may read only `WorkflowState` and file availability passed to it; it must not receive a client callback or promise.

- [ ] **Step 6: Render the editor card in both simple and detailed modes**

Place the action near test-design review. Include current attention, unresolved, unconfirmed, and blocking counts. Use warning styling only when `executionBlockingCount > 0` or summary refresh failed.

Update workflow copy so canonical `test_spec.json` and the dedicated editor replace instructions to edit legacy JSON manually. Keep legacy filenames only where compatibility is explicitly documented.

- [ ] **Step 7: Register the panel and command in `extension.ts`**

Create one CLI client and panel factory during activation. Add handler:

```typescript
'unitTestRunner.openTestInputEditor': async () => {
  const workspace = await lastWorkspace(context);
  await testInputEditor.open(workspace);
},
```

The panel save callback triggers an async summary refresh and `workflowPanel.refresh()`.

- [ ] **Step 8: Refresh summaries only at lifecycle boundaries**

Call summary-only refresh:

- after successful analyze;
- after successful reanalyze;
- after successful explicit test-design generation;
- after successful form save;
- once at activation when the restored Workflow state has a workspace and canonical TestSpec.

Invalidate before starting those operations. Ignore late responses for a no-longer-current workspace. On failure cache the error and keep the command available; do not block unrelated Workflow rendering.

- [ ] **Step 9: Rerun focused and full VS Code tests**

```powershell
Push-Location vscode\extension
npm test
Pop-Location
```

- [ ] **Step 10: Commit Workflow integration**

```powershell
git add vscode/extension/src/testInputEditor/summaryCache.ts vscode/extension/src/workflow vscode/extension/src/commands/commandRegistry.ts vscode/extension/src/extension.ts vscode/extension/package.json vscode/extension/src/test
git commit -m "feat: surface unresolved test inputs in workflow"
```

### Task 13: Document usage, run full regression, and verify distribution packaging

**Files:**
- Create: `docs/test_input_editor.md`
- Modify: `docs/vscode_usage_guide.md`
- Modify: `README.md`
- Modify: `vscode/extension/src/test/uiCopy.test.ts`
- Verify: all files changed by Tasks 1–12

**Interfaces:**
- User documentation explains manual opening, hybrid input, explicit partial save, confirmation semantics, promotion, warnings, revision conflicts, and reanalysis.
- Final verification covers Python, TypeScript, CLI smoke, canonical harness consumption, and packaged VSIX/CLI.

- [ ] **Step 1: Add documentation assertions before writing prose**

Extend `uiCopy.test.ts` and, if needed, a lightweight Python docs test to require:

- command title `未確定テスト項目を入力`;
- Workflow labels with count and blocking language;
- no instruction to edit `test_case_design.json` as the normal path;
- references to canonical `test_spec.json` and `確認済み` semantics.

- [ ] **Step 2: Write the dedicated usage guide**

`docs/test_input_editor.md` must include:

1. prerequisites and how the current function workspace is selected;
2. the Workflow button and why the tab never auto-opens;
3. case list and item status meanings;
4. suggestion selection plus free C-expression editing;
5. explicit save and partial save;
6. difference between value entry, item confirmation, and formal review approval;
7. hard errors versus warnings;
8. automatic promotion and limited demotion;
9. revision/fingerprint conflict resolution;
10. stale-source reanalysis flow;
11. canonical CLI reproduction commands.

Use copy-pasteable commands:

```powershell
py -m unit_test_runner --json get-test-input-form --workspace $out
py -m unit_test_runner --json apply-test-input-form --workspace $out --input $changes --expected-revision 3
py -m unit_test_runner --json generate-harness-skeleton --function-signature "$out\reports\function_signature.json" --global-access "$out\reports\global_access.json" --call-report "$out\reports\call_report.json" --test-spec "$out\reports\test_spec.json" --dependency-policy "$out\reports\dependency_policy.json" --out $out --overwrite
```

- [ ] **Step 3: Update README and the general VS Code guide**

Add the dedicated editor to the normal Workflow, outputs, command list, and reanalysis description. Replace the statement that reanalysis reads `reports/test_case_design.json` with canonical `reports/test_spec.json`; mention the legacy alias only as compatibility behavior.

- [ ] **Step 4: Run every Python test module in isolation**

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

Expected: all modules pass, including every new form test and all existing contract, harness, execution, and reanalysis tests.

- [ ] **Step 5: Run the full VS Code suite from a clean install**

```powershell
Push-Location vscode\extension
npm ci
npm test
Pop-Location
```

Expected: TypeScript compiles in strict mode and all Node tests pass.

- [ ] **Step 6: Run the real canonical smoke sequence**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$fixture = "$PWD\tests\fixtures\vc6_project"
$out = "$env:TEMP\unitTestRunner-input-editor-smoke\Control_Update"

py -m unit_test_runner --json analyze-function --workspace $fixture --dsw "$fixture\Product.dsw" --source src\control.c --function Control_Update --configuration "Win32 Debug" --project Control --out $out --phase harness
py -m unit_test_runner --json get-test-input-form --workspace $out
# Build changes.json from the returned item IDs and current fingerprints, using concrete reviewed expressions.
py -m unit_test_runner --json apply-test-input-form --workspace $out --input "$out\changes.json" --expected-revision 1
py -m unit_test_runner --json get-test-spec --workspace $out
py -m unit_test_runner --json generate-harness-skeleton --function-signature "$out\reports\function_signature.json" --global-access "$out\reports\global_access.json" --call-report "$out\reports\call_report.json" --test-spec "$out\reports\test_spec.json" --dependency-policy "$out\reports\dependency_policy.json" --out $out --overwrite
py -m unit_test_runner --json build-probe --workspace $out --dry-run --overwrite
```

The smoke operator must create `changes.json` from the actual query output; do not hard-code item IDs or fingerprints in documentation or scripts.

Expected: apply succeeds, canonical revision advances once, form summary shrinks, promoted cases appear in generated C, and build-probe dry-run succeeds.

- [ ] **Step 7: Build the distributable CLI and VSIX**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_distribution.ps1
```

Expected: the packaged executable recognizes both new subcommands and the VSIX manifest contains the editor command. Run the packaged executable with `--help` and verify `get-test-input-form` and `apply-test-input-form` are listed.

- [ ] **Step 8: Inspect the final diff for forbidden or accidental changes**

```powershell
git diff --check
git status --short
git diff -- src/unit_test_runner/schemas/test_spec.schema.json
```

Expected:

- no whitespace errors;
- no unintended generated files or temporary form request files;
- no change to canonical TestSpec schema unless a separately approved migration was introduced;
- no new normal-path dependency on legacy `test_case_design.json`;
- no formal review mutation in the form service.

- [ ] **Step 9: Commit documentation and final verification adjustments**

```powershell
git add README.md docs/test_input_editor.md docs/vscode_usage_guide.md vscode/extension/src/test/uiCopy.test.ts
git commit -m "docs: explain test input editor workflow"
```

## Completion Gate

Before declaring implementation complete, verify all of the following from fresh command output:

- The Python form model is strict, bounded, and freshness-validated.
- IDs are semantic and index-independent; ambiguous subjects are not writable.
- Partial saves are atomic and revision-guarded.
- Confirmed unresolved values are rejected; suspicious C expressions are warnings only.
- Formal review authority, provenance, and historical unresolved records are unchanged.
- Eligible unresolved main cases promote only when every execution-required parent is concrete and confirmed.
- Intentional additional candidates do not promote.
- Only touched unsafe executable cases demote; unrelated saves do not reclassify cases.
- Markdown/CSV export failure does not roll back canonical JSON.
- The VS Code adapter uses canonical `--test-spec` and `--previous-test-spec` paths.
- Webview content is escaped, CSP-protected, and free of direct canonical writes.
- Drafts survive panel hide/close within one extension session, but not VS Code restart.
- Conflicts retain drafts and require explicit resolution.
- Workflow render never launches a CLI process, and cached counts refresh at approved lifecycle boundaries.
- Python tests, VS Code tests, canonical end-to-end smoke, and distribution build all pass.
