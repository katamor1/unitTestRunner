# Dependency Policy Dispatcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add per-call `real` / `stub` / `auto` dependency policies, case-level overrides, collision-safe dispatchers/stubs, and workspace-level external-object binding.

**Architecture:** A new `dependency_policy` package resolves declarations, definitions, state coupling, and external-object bindings into a persisted report. Harness generation consumes the policy to create uniquely named stubs and runtime dispatchers. Build workspace generation rewrites only eligible direct call sites in the extracted target C and adds required real implementation C files without modifying product sources.

**Tech Stack:** Python 3.12 dataclasses, existing C analyzer/report infrastructure, C90 generated code, `unittest`.

## Global Constraints

- Product source, headers, `.dsw`, and `.dsp` are never modified.
- Only direct function calls are automatically rewritten.
- Macro calls, indirect calls, member calls, and function-address uses are `review_required`.
- Generated C remains C90 and VC6 compatible.
- Function stubs never define the original product symbol name.
- External-object binding is fixed per workspace; test cases only alter values.

---

### Task 1: Dependency policy data model and reports

**Files:**
- Create: `src/unit_test_runner/dependency_policy/__init__.py`
- Create: `src/unit_test_runner/dependency_policy/models.py`
- Create: `src/unit_test_runner/dependency_policy/writer.py`
- Test: `tests/test_dependency_policy_models.py`

- [x] Write failing serialization and report tests.
- [x] Implement dependency, signature, evidence, external-object, and report dataclasses.
- [x] Implement JSON/Markdown writer.
- [x] Run focused tests and commit.

### Task 2: Signature and implementation resolver

**Files:**
- Create: `src/unit_test_runner/dependency_policy/signature_resolver.py`
- Test: `tests/test_dependency_signature_resolver.py`

- [x] Add fixtures with matching header/definition, conflicting declarations, calling convention, variadic, and unresolved calls.
- [x] Resolve reachable-header declarations first, then C definitions, then workspace candidates.
- [x] Normalize signatures and classify `exact`, `compatible_inferred`, or `review_required`.
- [x] Run focused tests and commit.

### Task 3: State-coupling auto policy and external-object binding

**Files:**
- Create: `src/unit_test_runner/dependency_policy/analyzer.py`
- Test: `tests/test_dependency_policy_analyzer.py`

- [x] Test shared-global/internal-function => `real`.
- [x] Test return-only external dependency => `stub`.
- [x] Test ambiguous/macro/function-pointer => `review_required`.
- [x] Test external object unique definition => `real`, declaration-only => `fixture`, multiple definitions => `review_required`.
- [x] Preserve explicit configured modes from an existing policy.
- [x] Run focused tests and commit.

### Task 4: Workflow and test-design integration

**Files:**
- Modify: `src/unit_test_runner/dossier/workflow.py`
- Modify: `src/unit_test_runner/test_design/test_case_models.py`
- Modify: `src/unit_test_runner/test_design/test_case_design_generator.py`
- Modify: `src/unit_test_runner/test_design/test_case_design_writer.py`
- Test: `tests/test_dependency_policy_workflow.py`

- [x] Generate `dependency_policy.json/md` after call analysis.
- [x] Add `dependency_overrides` to each test case with backward-compatible empty default.
- [x] Preserve edited explicit policy modes when a workspace is regenerated.
- [x] Add policy paths to the dossier.
- [x] Run focused tests and commit.

### Task 5: Collision-safe stubs and runtime dispatchers

**Files:**
- Create: `src/unit_test_runner/harness/dependency_dispatcher.py`
- Modify: `src/unit_test_runner/harness/harness_models.py`
- Modify: `src/unit_test_runner/harness/harness_report_writer.py`
- Modify: `src/unit_test_runner/harness/__init__.py`
- Modify: `src/unit_test_runner/harness/harness_skeleton_generator.py`
- Modify: `src/unit_test_runner/harness/parameter_init_compat.py`
- Test: `tests/test_dependency_dispatcher_generation.py`

- [x] Verify generated stub symbols never equal product symbols.
- [x] Generate exact-signature `Utr_Dep_*` and `Utr_Stub_*_Invoke` functions.
- [x] Generate default-mode reset and per-dependency setter APIs.
- [x] Apply case overrides before target invocation.
- [x] Include dispatch metadata in harness report.
- [x] Run focused tests and commit.

### Task 6: Direct-call rewriting and real implementation source inclusion

**Files:**
- Create: `src/unit_test_runner/build/dependency_rewriter.py`
- Modify: `src/unit_test_runner/build/build_workspace_generator.py`
- Modify: `src/unit_test_runner/build/workspace_compat_fixes.py`
- Test: `tests/test_dependency_call_rewriter.py`
- Test: `tests/test_dependency_real_source_inclusion.py`

- [x] Rewrite only exact source positions for eligible direct calls.
- [x] Leave macro/function-pointer/address uses unchanged and report diagnostics.
- [x] Add unique real implementation C files required by policy.
- [x] Keep header references rather than copying header trees.
- [x] Run focused tests and commit.

### Task 7: External-object duplicate-definition prevention

**Files:**
- Modify: `src/unit_test_runner/build/workspace_compat_fixes.py`
- Test: `tests/test_dependency_external_object_binding.py`

- [x] Do not generate fixture definitions for `real` external objects.
- [x] Generate one declaration-compatible fixture for `fixture` objects.
- [x] Block automatic generation for multiple/incompatible definitions.
- [x] Verify target and real dependency use the same object symbol.
- [x] Run focused tests and commit.

### Task 8: Integration regression and documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/vscode_quick_check_usage.md`
- Modify: `tests/test_harness_skeleton_generation.py`
- Create: `tests/test_dependency_policy_end_to_end.py`
- Delete: `.github/workflows/export-dependency-policy-workspace.yml`

- [x] Add an end-to-end fixture containing an internal state-coupled helper and an external boundary dependency.
- [x] Verify one case uses real and another overrides the same dependency to stub.
- [x] Verify product prototypes and extern declarations do not conflict.
- [x] Run all new focused tests, the harness/build suites, and VS Code compile/tests.
- [x] Remove the temporary export workflow and commit.

## Verification Record

- Dependency-policy focused suite: 38 tests passed.
- All `test_dependency*.py` tests: 33 tests passed.
- Related build, harness, Quick Check, CLI, test-design, VC6 project, and execution-evidence suite: 28 passed; one stale pre-existing execution-parser expectation failed on both this branch and the parent branch.
- `python -m compileall -q src`: passed.
- VS Code TypeScript compilation: passed.
- VS Code full test suite: 38 passed / 5 failed; the same five Windows-path assertions fail on the parent branch under Linux.
