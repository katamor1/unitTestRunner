# Unit Test Runner Phase 2 VC6 Semantic Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate VC6-compatible C90 tests that execute the exact approved input, state, dependency, and oracle semantics recorded in `test_spec.json`.

**Architecture:** Reconstruct the effective compile context for each source, analyze only active preprocessor regions, and resolve types through one shared resolver. Generate target/static bridges and typed fixtures from resolved types; block unresolved cases rather than emitting lossy C. Prove the vertical slice with real host compile/run fixtures and a protected VC6-native lane.

**Tech Stack:** Python 3.12, VC6 DSP/DSW parsing, deterministic C preprocessor subset, generated C90/CP932/CRLF, host GCC/MSVC verification, self-hosted VC6/NMAKE acceptance.

## Global Constraints

- Phase 1 contracts are available; all generated values and assertions trace to a test-spec semantic ID.
- No `eval()` or host compiler preprocessor is used to decide static analysis results.
- Unknown preprocessor expressions remain unknown and conservative; they are not declared active facts.
- Aggregate, callback, variadic, calling-convention, or incomplete types never fall back to `int`.
- Static targets are exposed only in extracted workspace copies; product source is unchanged.
- Do not use `#define static` to expose targets or state.
- Existing DSP/LIB and dependency-policy decisions remain inputs to the effective compile context.

---

### Task 1: Model source-specific DSP compile settings

**Files:**

- Modify: `src/unit_test_runner/vc6/dsp_models.py`
- Modify: `src/unit_test_runner/vc6/dsp_parser.py`
- Modify: `src/unit_test_runner/vc6/dsp_options.py`
- Create: `src/unit_test_runner/vc6/effective_compile_context.py`
- Modify: `src/unit_test_runner/vc6/__init__.py`
- Modify: `src/unit_test_runner/dossier/workflow.py`
- Modify: `src/unit_test_runner/reanalysis/current_analysis.py`
- Modify: `src/unit_test_runner/build/build_models.py`
- Modify: `src/unit_test_runner/build/build_workspace_generator.py`
- Modify: `tests/test_vc6_dsp_parser.py`
- Create: `tests/test_vc6_source_compile_context.py`
- Create: `tests/fixtures/vc6_per_source_dependency_project/`

**Interfaces:**

```python
@dataclass(frozen=True)
class SourceConfigurationSettings:
    configuration: str
    excluded_from_build: bool
    add_cpp: tuple[str, ...]
    subtract_cpp: tuple[str, ...]
    defines: tuple[str, ...]
    include_dirs: tuple[Path, ...]
    forced_includes: tuple[str, ...]
    pch_mode: str | None
    pch_header: str | None
    language_mode: str | None

def resolve_effective_compile_context(
    project: DspProject,
    source: Path,
    configuration: str,
) -> EffectiveCompileContext: ...
```

- [ ] **Step 1: Add a multi-source DSP fixture**

Create two C entries with different `/D`, `/I`, `/FI`, `/Yu` and `# SUBTRACT CPP`, plus one `Exclude_From_Build 1` source.

- [ ] **Step 2: Parse source sections without leaking options to project scope**

Keep project/base configuration options and per-source options separate in the model.

- [ ] **Step 3: Resolve options in the exact order**

```text
project base -> selected project configuration -> source ADD -> source SUBTRACT
```

Normalize duplicate switches while preserving link/compile order where order matters.

- [ ] **Step 4: Apply per-source settings to compile units**

Each `CompileUnit` receives its own defines, includes, PCH, forced includes, and compiler options. Excluded sources are not implementation candidates and are not compiled.

The fixture must place the target and a dependency-policy `real` callee in different DSP projects with different source-level options. Assert each compile unit receives its own project/source context.

- [ ] **Step 5: Run and commit**

```bash
PYTHONPATH=src python -m unittest tests.test_vc6_dsp_parser tests.test_vc6_source_compile_context -v
git add src/unit_test_runner/vc6 src/unit_test_runner/dossier src/unit_test_runner/reanalysis src/unit_test_runner/build tests
git commit -m "feat: resolve VC6 compile settings per source"
```

---

### Task 2: Evaluate configuration preprocessor expressions and mask inactive source

**Files:**

- Create: `src/unit_test_runner/c_analyzer/preprocessor_expression.py`
- Create: `src/unit_test_runner/c_analyzer/active_source.py`
- Create: `src/unit_test_runner/c_analyzer/macro_environment.py`
- Modify: `src/unit_test_runner/c_analyzer/preprocessor.py`
- Modify: `src/unit_test_runner/c_analyzer/source_digest.py`
- Modify: `src/unit_test_runner/c_analyzer/source_models.py`
- Modify: `tests/test_c_source_reading.py`
- Create: `tests/test_preprocessor_expression.py`
- Create: `tests/test_configuration_active_source.py`

**Interfaces:**

```python
class TruthValue(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

def parse_defines(options: Sequence[str]) -> dict[str, str]: ...
def evaluate_preprocessor_expression(expression: str,
                                     macros: Mapping[str, str]) -> TruthValue: ...

@dataclass(frozen=True)
class SourceRegion:
    start_offset: int
    end_offset: int
    state: Literal["active", "inactive", "unknown"]
    condition_ids: tuple[str, ...]

@dataclass(frozen=True)
class EffectivePreprocessorContext:
    command_line_macros: Mapping[str, str]
    forced_include_macros: Mapping[str, str]
    pch_macros: Mapping[str, str]
    unresolved_headers: tuple[str, ...]

def build_active_source(text: str, context: EffectivePreprocessorContext) -> ActiveSource: ...
```

`ActiveSource.masked_text` masks only proven inactive code and preserves offsets/newlines. `region_map` retains UNKNOWN provenance for every analyzer.

- [ ] **Step 1: Write expression truth-table tests**

Cover `defined`, integer/hex literals, identifiers, parentheses, comparison, logical operators, bit operators, `/D SIZE=10`, `#define`, and `#undef`.

- [ ] **Step 2: Write branch-frame tests**

Assert `#if 1` makes later `#elif 1` inactive, nested parent inactivity wins, and an unknown condition remains `unknown` rather than active/inactive.

- [ ] **Step 3: Implement a deterministic parser/evaluator**

Use tokenization plus precedence parsing. Build the macro environment from command-line defines, parsed forced includes, and PCH/header provenance. Reject function-like macros, unreadable headers, and unsupported tokens as UNKNOWN; never call Python `eval()`.

- [ ] **Step 4: Route all analyzers through active masked text**

Function location, calls, globals, coverage, and boundary discovery ignore inactive regions, retain UNKNOWN provenance, and attach related condition IDs. If target identity/signature, a generated input/oracle, call dependency, or coverage obligation depends on UNKNOWN code, harness generation is `blocked` with the condition IDs; UNKNOWN is never reported as a confirmed fact.

- [ ] **Step 5: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_preprocessor_expression tests.test_configuration_active_source \
  tests.test_c_source_reading -v
git add src/unit_test_runner/c_analyzer tests
git commit -m "feat: analyze only active VC6 configuration source"
```

---

### Task 3: Create one shared C type resolver

**Files:**

- Create: `src/unit_test_runner/c_analyzer/type_resolver.py`
- Modify: `src/unit_test_runner/c_analyzer/signature_models.py`
- Modify: `src/unit_test_runner/c_analyzer/signature_extractor.py`
- Refactor: `src/unit_test_runner/dependency_policy/signature_resolver.py`
- Create: `tests/test_type_resolver.py`
- Modify: `tests/test_dependency_signature_resolver.py`

**Interfaces:**

```python
class CTypeKind(StrEnum):
    VOID = "void"
    SCALAR = "scalar"
    ENUM = "enum"
    POINTER = "pointer"
    ARRAY = "array"
    AGGREGATE = "aggregate"
    FUNCTION_POINTER = "function_pointer"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class ResolvedCType:
    spelling: str
    canonical_spelling: str
    kind: CTypeKind
    pointer_level: int
    complete: bool
    defining_header: Path | None
    calling_convention: str | None
    array_extents: tuple[str, ...]
    confidence: str

def resolve_c_type(type_text: str, headers: Sequence[HeaderSource],
                   macros: Mapping[str, str]) -> ResolvedCType: ...
```

- [ ] **Step 1: Add scalar typedef, pointer typedef, enum, aggregate, callback, and incomplete tests**

Include typedef chains and conflicting definitions. Require provenance for every non-builtin type.

- [ ] **Step 2: Move dependency signature type logic into the shared resolver**

Dependency and target invocation must classify the same spelling identically.

- [ ] **Step 3: Block ambiguous and incomplete by-value types**

Pointers to incomplete objects are allowed; incomplete values/returns are blocked.

- [ ] **Step 4: Run and commit**

```bash
PYTHONPATH=src python -m unittest tests.test_type_resolver tests.test_dependency_signature_resolver -v
git add src/unit_test_runner/c_analyzer src/unit_test_runner/dependency_policy tests
git commit -m "refactor: share C type resolution across target and dependencies"
```

---

### Task 4: Replace compat monkey patches with explicit target/type bridge generation

**Files:**

- Modify: `src/unit_test_runner/harness/type_bridge.py`
- Create: `src/unit_test_runner/build/translation_unit_bridge.py`
- Create: `src/unit_test_runner/harness/test_function_renderer.py`
- Modify: `src/unit_test_runner/harness/harness_skeleton_generator.py`
- Modify: `src/unit_test_runner/harness/__init__.py`
- Remove: `src/unit_test_runner/harness/target_invocation_compat.py`
- Remove: `src/unit_test_runner/harness/parameter_init_compat.py`
- Modify: `src/unit_test_runner/build/build_workspace_generator.py`
- Modify: `tests/test_target_invocation_compat.py`
- Create: `tests/test_static_target_bridge.py`
- Modify: `tests/test_build_and_execution_module_boundaries.py`
- Modify: `tests/test_build_output_encoding.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class TargetBridgePlan:
    public_prototype: str
    required_headers: tuple[str, ...]
    same_translation_unit: bool
    generated_symbol: str
    state_accessors: tuple[StateAccessorPlan, ...]
    blocked_reasons: tuple[str, ...]

def plan_target_bridge(signature: FunctionSignatureReport,
                       types: TypeResolutionSet) -> TargetBridgePlan: ...
def append_same_tu_bridge(extracted_source: Path,
                          plan: TargetBridgePlan) -> ProducedArtifact: ...
```

- [ ] **Step 1: Write static target and file-static state tests**

Require a static target to link through a generated same-TU symbol. Generate setter/getter only for resolved scalar/enum/pointer state.

- [ ] **Step 2: Generate exact public prototypes**

Include verified defining headers in the bridge header. Do not use `void *` or `int` if a complete type is known.

- [ ] **Step 3: Generate same-TU access without changing product source**

Append a bridge to the extracted C copy. Do not redefine `static`, do not modify the original, and record original/generated hashes.

- [ ] **Step 4: Remove import-time monkey-patch application**

Wire explicit renderer/bridge dependencies through normal functions and update module-boundary tests.

- [ ] **Step 5: Enforce strict CP932 generation**

Do not use `errors="replace"` for extracted/generated C. If a character is not representable, return a structured encoding diagnostic and block that compile unit. Preserve encoding/newline metadata in the build report.

- [ ] **Step 6: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_target_invocation_compat tests.test_static_target_bridge \
  tests.test_build_and_execution_module_boundaries tests.test_build_output_encoding -v
git add src/unit_test_runner/harness src/unit_test_runner/build tests
git commit -m "refactor: generate explicit typed and static target bridges"
```

---

### Task 5: Model typed inputs, state, stub behavior, and oracles

**Files:**

- Modify: `src/unit_test_runner/test_design/test_case_models.py`
- Modify: `src/unit_test_runner/test_design/input_assignment_builder.py`
- Modify: `src/unit_test_runner/test_design/expected_observation_builder.py`
- Modify: `src/unit_test_runner/test_design/state_setup_builder.py`
- Modify: `src/unit_test_runner/test_design/stub_setup_builder.py`
- Modify: `src/unit_test_runner/test_spec/models.py`
- Modify: `src/unit_test_runner/schemas/test_spec.schema.json`
- Create: `tests/test_typed_test_spec_values.py`

**Interfaces:**

```python
class CValueKind(StrEnum):
    INTEGER = "integer"
    FLOAT = "float"
    ENUM = "enum"
    MACRO = "macro"
    NULL = "null"
    ADDRESS = "address"
    STRING = "string"
    AGGREGATE = "aggregate"
    BINARY = "binary"

@dataclass(frozen=True)
class TypedCValue:
    kind: CValueKind
    type_id: str
    literal: IntegerLiteral | FloatLiteral | None
    enum_member: EnumMemberRef | None
    macro: MacroValueRef | None
    null_value: bool
    address: FixtureAddressRef | None
    string_value: EncodedStringValue | None
    aggregate_members: tuple[AggregateMemberValue, ...]
    binary_expression: BinaryValueExpression | None
    review_item_id: str | None

@dataclass(frozen=True)
class OracleSpec:
    kind: str
    target: str
    expected: TypedCValue | None
    comparison: ComparisonSpec
    review_item_id: str
```

`IntegerLiteral` stores original spelling, base, bit width, and signedness. `MacroValueRef` stores name, defining artifact/hash, and expansion fingerprint. `EncodedStringValue` stores encoding and exact bytes. `BinaryValueExpression` permits only an enum of reviewed arithmetic/bitwise operators over typed operands; arbitrary C expression text is not accepted. `ComparisonSpec` is a tagged union for exact, integer range, float absolute/relative tolerance, byte sequence, string+length, call count, and argument sequence.

- [ ] **Step 1: Add round-trip schema tests**

Round-trip NULL, `0x10U`, enum, macro+definition hash, `X-1` as a typed binary AST, encoded string bytes, aggregate members, pointer fixture+length, exact stub call count, typed argument observation, float tolerance, and global/output-buffer oracle. Reject raw expression injection.

- [ ] **Step 2: Build typed values from candidates**

Preserve literal spelling/width/signedness and resolve macro/enum values only with the selected compile context. An unresolved macro/value AST remains unresolved and blocks execution.

- [ ] **Step 3: Require approved oracles for executable cases**

Static analysis creates an oracle review item, but only a non-stale `APPROVED` decision in `review_decisions.json` authorizes assertion generation. `OracleSpec` and `TypedCValue` contain review-item IDs, not approval flags. Remove default-zero oracle behavior.

- [ ] **Step 4: Migrate v0.1 string values in memory**

Classify obvious literals/NULL; for every other legacy string create an unresolved review item ID with no approval decision. Do not claim approval during migration.

- [ ] **Step 5: Run and commit**

```bash
PYTHONPATH=src python -m unittest tests.test_typed_test_spec_values tests.test_test_spec_contract -v
git add src/unit_test_runner/test_design src/unit_test_runner/test_spec src/unit_test_runner/schemas/test_spec.schema.json tests
git commit -m "feat: represent test inputs and oracles as typed values"
```

---

### Task 6: Lower approved typed values and oracles into C90 faithfully

**Files:**

- Create: `src/unit_test_runner/harness/value_lowering.py`
- Create: `src/unit_test_runner/harness/oracle_renderer.py`
- Modify: `src/unit_test_runner/harness/test_function_renderer.py`
- Modify: `src/unit_test_runner/harness/harness_skeleton_generator.py`
- Modify: `src/unit_test_runner/harness/dependency_dispatcher.py`
- Modify: `src/unit_test_runner/harness/harness_models.py`
- Create: `tests/test_typed_harness_generation.py`
- Create: `tests/test_reviewed_oracle_generation.py`
- Modify: `tests/test_harness_skeleton_generation.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class LoweredValue:
    declarations: tuple[str, ...]
    setup_statements: tuple[str, ...]
    expression: str
    blocked_reason: str | None

@dataclass(frozen=True)
class LoweredOracle:
    assertion_statements: tuple[str, ...]
    blocked_reason: str | None

def lower_value(value: TypedCValue, resolved_type: ResolvedCType,
                decisions: ReviewDecisionSet,
                current_artifacts: Sequence[ArtifactReference]) -> LoweredValue: ...
def render_oracle(oracle: OracleSpec, actual_expression: str,
                  resolved_type: ResolvedCType,
                  decisions: ReviewDecisionSet) -> LoweredOracle: ...

def assess_case_generation_gate(case: TestCaseDesign,
                                decisions: ReviewDecisionSet,
                                current_artifacts: Sequence[ArtifactReference]) -> GenerationGate: ...
```

- [ ] **Step 1: Add forbidden-pattern assertions**

Generated C must not contain `0 /* candidate:`, `TBD_EXPECTED_RETURN_INT`, `GetCallCount() >= 0`, or a `double[512]` opaque pointer fixture.

- [ ] **Step 2: Lower values by type and intent**

- NULL emits `NULL`.
- Integer/hex/enum/approved macro retains the approved expression.
- Pointer fixtures use pointee type and required element count.
- Aggregates use typed initializers.
- Unresolved values return a blocked reason and no executable test function.

Before lowering any input, state, stub setup, dependency override, or oracle, call `assess_case_generation_gate()`. Every referenced review item must have a current non-stale approval pinned to the same artifact revision/hash. `lower_value()` repeats the value-level check defensively. A missing/stale/changes-requested/open decision returns a blocked reason and emits no executable case.

- [ ] **Step 3: Render exact approved oracles**

Support return/global/buffer/stub count/stub argument assertions with typed comparison parameters. Reject stale/missing review decisions and invalid macro fingerprints through `blocked_reason`. Stub call count uses `exact`, `range`, or `never`; never a tautology.

- [ ] **Step 4: Correct placeholder accounting**

Remove `count or 1`. A fully resolved case reports zero placeholders. Blocked cases state each unresolved semantic ID.

- [ ] **Step 5: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_typed_harness_generation tests.test_reviewed_oracle_generation \
  tests.test_harness_skeleton_generation -v
git add src/unit_test_runner/harness tests
git commit -m "feat: lower approved typed tests into faithful C90"
```

---

### Task 7: Require explicit project/configuration identity when ambiguous

**Files:**

- Modify: `src/unit_test_runner/vc6/__init__.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `src/unit_test_runner/cli/errors.py`
- Modify: `src/unit_test_runner/dossier/workflow.py`
- Create: `tests/test_vc6_project_context_selection.py`

**Interfaces:**

```python
class AmbiguousProjectContextError(ValueError):
    candidates: tuple[ProjectContextCandidate, ...]
```

- [ ] **Step 1: Add multiple-membership tests**

Without `--project`, two valid memberships return a structured ambiguity error. With an exact project/configuration, the selected effective context is used.

- [ ] **Step 2: Remove first-match selection**

Auto-select only when there is exactly one valid membership. Return candidates and evidence otherwise.

- [ ] **Step 3: Include target identity in every generated artifact**

Use source-relative path, source hash, function semantic location, project, and configuration; do not identify output by function name alone.

- [ ] **Step 4: Run and commit**

```bash
PYTHONPATH=src python -m unittest tests.test_vc6_project_context_selection tests.test_practical_vc6_fixture -v
git add src/unit_test_runner/vc6 src/unit_test_runner/cli src/unit_test_runner/dossier tests
git commit -m "fix: require explicit VC6 project context when ambiguous"
```

---

### Task 8: Add real compile/run fixtures and VC6-native certification

**Files:**

- Create: `tests/fixtures/vc6_execution_project/`
- Create: `tests/test_vc6_fixture_execution_e2e.py`
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/vc6-e2e.yml`
- Create: `docs/vc6_acceptance_matrix.md`

**Interfaces:** Fixture includes approved test spec cases for scalar, NULL, typedef, aggregate, static target, extern global, real/stub mixed dependency, and crash isolation.

- [ ] **Step 1: Create a deterministic reviewed fixture**

Each case has an approved oracle and expected semantic ID. Include one deliberately wrong-spec copy for exit-code verification.

- [ ] **Step 2: Add host compile/run E2E**

Run discover -> analyze -> load approved spec -> harness -> build -> execute -> evidence. Assert all passed, exit 0, complete evidence, and unchanged product hashes. The wrong-spec variant must exit 32.

- [ ] **Step 3: Add a protected self-hosted VC6 workflow**

Use `workflow_dispatch` and scheduled execution on a labeled Windows/VC6 runner. Exercise NMAKE, PCH, CP932 paths, DSP Debug/Release, generated EXE, timeout, and crash cases.

- [ ] **Step 4: Publish an acceptance matrix**

Separate PR-required host verification from release-required VC6-native results. Record compiler version and fixture revisions.

- [ ] **Step 5: Run and commit**

```bash
PYTHONPATH=src python -m unittest tests.test_vc6_fixture_execution_e2e -v
git add tests/fixtures/vc6_execution_project tests/test_vc6_fixture_execution_e2e.py .github/workflows docs/vc6_acceptance_matrix.md
git commit -m "test: add host and VC6 semantic execution acceptance"
```

---

### Task 9: Cache VC6 workspace discovery and expose measurable progress

**Files:**

- Create: `src/unit_test_runner/vc6/workspace_index.py`
- Create: `src/unit_test_runner/vc6/index_store.py`
- Create: `src/unit_test_runner/cli/progress.py`
- Create: `src/unit_test_runner/schemas/progress_event.schema.json`
- Modify: `src/unit_test_runner/vc6/__init__.py`
- Modify: `src/unit_test_runner/vc6/source_membership.py`
- Modify: `src/unit_test_runner/vc6/dsp_parser.py`
- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `src/unit_test_runner/cli/result.py`
- Modify: `vscode/extension/src/cli/cliRunner.ts`
- Create: `vscode/extension/src/cli/progressEvent.ts`
- Create: `tests/test_vc6_workspace_index.py`
- Create: `tests/test_vc6_workspace_index_invalidation.py`
- Create: `tests/test_large_workspace_performance.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class WorkspaceIndexKey:
    dsw_path: str
    dsw_sha256: str
    dsp_fingerprints: tuple[tuple[str, str], ...]

def load_or_build_workspace_index(workspace: Path, dsw: Path,
                                  cache_root: Path) -> WorkspaceIndex: ...
```

- [ ] **Step 1: Count parser calls in repeated workflow tests**

One Quick Check must not parse every DSP once for discovery and again for source mapping. A second unchanged run must reuse the index.

- [ ] **Step 2: Implement content/stat-keyed indexing**

Index DSW project/dependency data, DSP source memberships, per-source compile contexts, and header/type lookup metadata. Store outside product source.

- [ ] **Step 3: Implement precise invalidation**

Changing one DSP invalidates that project and dependent context, not unrelated projects. DSW changes invalidate project/dependency topology. Source/header changes invalidate analysis/type entries only.

- [ ] **Step 4: Emit structured progress events**

Emit lines with the exact prefix `UTR_EVENT ` followed by one JSON object validated by `progress_event.schema.json`. Use stderr only; stdout remains the one final CLI envelope. Unprefixed stderr remains diagnostic text. `cliRunner.ts` parses prefixed lines into `ProgressEvent`, forwards them to the coordinator, and keeps malformed prefixed lines as diagnostics rather than corrupting the final result.

- [ ] **Step 5: Add a performance budget fixture**

Use generated metadata for hundreds of projects/sources without committing huge binaries. Assert warm-run parser calls and elapsed-time ratio rather than a brittle absolute workstation time.

- [ ] **Step 6: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_vc6_workspace_index tests.test_vc6_workspace_index_invalidation \
  tests.test_large_workspace_performance -v
git add src/unit_test_runner/vc6 src/unit_test_runner/cli tests
git commit -m "perf: cache VC6 workspace discovery and analysis context"
```

---

## Phase 2 Completion Check

- [ ] Per-source DSP options match the selected configuration.
- [ ] Inactive preprocessor branches do not affect function/call/global/coverage reports.
- [ ] Target and dependency signatures use the same type resolver.
- [ ] Static targets link through same-TU generated bridges.
- [ ] Approved NULL, macro, enum, boundary, pointer, aggregate, and oracle values retain their meaning.
- [ ] Unresolved values/types block before compile.
- [ ] Forbidden lossy generated patterns are absent.
- [ ] Host E2E passes and the negative oracle exits nonzero.
- [ ] Repeated unchanged analysis reuses a validated workspace index and reports progress.
- [ ] Protected VC6-native acceptance is GREEN before release.
