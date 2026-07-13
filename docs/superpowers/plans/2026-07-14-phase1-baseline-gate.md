# Phase 1 Baseline Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge a maintenance-only pull request that restores the Phase 1 baseline, makes isolated Python module execution the CI contract, and makes the VC6 fixture smoke fail when no host compiler is available.

**Architecture:** Work only in the existing isolated worktree on `codex/p1-baseline-gate`. First change the CI contract test and observe RED, then update the workflow to satisfy it. In a separate reviewed task, align two stale test assertions with already-established canonical contracts, run the complete isolated baseline gate, and record only locally knowable evidence before publication.

**Tech Stack:** Python 3.12, `unittest`, PowerShell, GitHub Actions on `windows-latest`, Git worktrees.

## Global Constraints

- Do not modify, unstage, commit, or delete `C:\Users\stell\source\repos\unitTestRunner\build.ps1`.
- Do not implement in the primary checkout. Work in `C:\Users\stell\source\repos\unitTestRunner-sdd` on `codex/p1-baseline-gate`.
- This pull request contains maintenance tests, CI configuration, design/plan documents, and a baseline evidence record only. It contains no Phase 1 Task 6 product implementation.
- For the authoritative Python gate, run every actual `tests/test_*.py` module serially in a fresh Python process. Focused RED/GREEN commands run one module per process.
- The VC6 fixture smoke job must fail before running tests when none of `gcc`, `clang`, or `cc` is available on `PATH`; a skipped compiler E2E is not an acceptable GitHub gate.
- Keep CLI envelope 1.0.0 and assert `data.outcome`, `data.exit_code`, and `data.details.build_probe.status`.
- Canonical TestSpec consumer values must equal the canonical envelope values; tests must not freeze obsolete identifier literals.
- Committed evidence must not claim a pull-request URL, Actions URL, review verdict, merge SHA, or its own commit SHA before that value exists.
- Every task requires a task-scoped review with both spec-compliance and code-quality approval. The complete branch requires a fresh whole-branch review with Critical 0 and Important 0 before publication.

---

### Task 1: Make isolated Python execution and compiler presence executable CI contracts

**Files:**
- Modify: `tests/test_ci_contract.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: six-job workflow shape and the isolated verification policy in `docs/superpowers/plans/preflight/README.md`.
- Produces: a contract-tested PowerShell loop that executes each Python module in a fresh process and a VC6 smoke precondition that requires a supported host compiler.

- [ ] **Step 1: Change the Python CI contract test before the workflow**

Replace the monolithic discovery assertion in
`test_github_actions_runs_python_and_vscode_extension_gates` with:

```python
self.assertNotIn(
    'python -m unittest discover -s tests -p "test_*.py"',
    text,
)
self.assertIn(
    "Get-ChildItem -LiteralPath .\\tests -Filter 'test_*.py' -File",
    text,
)
self.assertIn("foreach ($module in $modules)", text)
self.assertIn("& python -m unittest $module -v", text)
self.assertIn(
    '"isolated_modules=$($modules.Count) failures=$($failed.Count)"',
    text,
)
```

Extend `test_github_actions_runs_activation_fixture_and_failure_log_contracts`
with:

```python
self.assertIn(
    "Get-Command gcc, clang, cc -ErrorAction SilentlyContinue",
    text,
)
self.assertIn("if ($null -eq $compiler)", text)
self.assertIn(
    "VC6 fixture smoke requires gcc, clang, or cc on PATH.",
    text,
)
```

- [ ] **Step 2: Run the changed contract and verify RED**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_ci_contract -v
```

Expected: the module fails because the workflow still contains monolithic
discovery and has no compiler precondition. An import, syntax, or setup error
is not acceptable RED evidence.

- [ ] **Step 3: Replace monolithic discovery with isolated module processes**

Replace the `Run Python tests` step in `.github/workflows/ci.yml` with:

```yaml
      - name: Run Python tests in isolated processes
        shell: pwsh
        run: |
          $log = Join-Path $env:RUNNER_TEMP "python-tests.log"
          $modules = Get-ChildItem -LiteralPath .\tests -Filter 'test_*.py' -File |
            Sort-Object Name |
            ForEach-Object { 'tests.' + $_.BaseName }
          $failed = @()
          foreach ($module in $modules) {
            "`n=== $module ===" | Tee-Object -FilePath $log -Append
            & python -m unittest $module -v *>&1 |
              Tee-Object -FilePath $log -Append
            if ($LASTEXITCODE -ne 0) { $failed += $module }
          }
          "isolated_modules=$($modules.Count) failures=$($failed.Count)" |
            Tee-Object -FilePath $log -Append
          if ($failed.Count -ne 0) {
            throw ('isolated Python failures: ' + ($failed -join ', '))
          }
```

Keep the existing `Upload Python failure log` step and
`python-test-failure` artifact name unchanged.

- [ ] **Step 4: Add an explicit compiler precondition to fixture smoke**

Insert this step after fixture-job dependency installation and before
`Run fixture smoke`:

```yaml
      - name: Require host C compiler
        shell: pwsh
        run: |
          $compiler = Get-Command gcc, clang, cc -ErrorAction SilentlyContinue |
            Select-Object -First 1
          if ($null -eq $compiler) {
            throw 'VC6 fixture smoke requires gcc, clang, or cc on PATH.'
          }
          "fixture_compiler=$($compiler.Source)"
```

Do not install a compiler dynamically in the test step. The runner image must
expose the compiler before the E2E begins, and absence must be a visible job
failure.

- [ ] **Step 5: Run focused GREEN verification**

```powershell
py -m unittest tests.test_ci_contract -v
py -m unittest tests.test_repository_source_tracking -v
git diff --check
```

Expected: both modules pass and `git diff --check` exits 0.

- [ ] **Step 6: Commit the CI contract slice**

```powershell
git add -- tests/test_ci_contract.py .github/workflows/ci.yml
git diff --cached --check
git commit -m "ci: isolate Python modules and require fixture compiler"
```

The implementer report must include the exact RED command/output, GREEN
command/output, changed files, and self-review result.

---

### Task 2: Align stale baseline assertions and record the local gate

**Files:**
- Modify: `tests/test_test_spec_consumers.py`
- Modify: `tests/test_vc6_fixture_build_e2e.py`
- Create: `docs/review/2026-07-14-phase1-baseline-gate.md`

**Interfaces:**
- Consumes: canonical TestSpec envelope `data.spec_id` and
  `data.test_cases[].test_case_id`; CLI result envelope 1.0.0.
- Produces: baseline tests that verify current public contracts and a local
  evidence record for the maintenance pull request.

- [ ] **Step 1: Reproduce the TestSpec baseline RED**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unittest tests.test_test_spec_consumers -v
```

Expected: six tests run and exactly
`test_canonical_envelope_is_normalized_to_consumer_data_and_views_are_rejected`
fails because `spec-control-update` differs from
`spec-fn_control_update_cdd351ecf31d`.

- [ ] **Step 2: Compare normalized values with the canonical envelope**

In
`test_canonical_envelope_is_normalized_to_consumer_data_and_views_are_rejected`,
replace the two obsolete literal assertions with:

```python
canonical = json.loads(path.read_text(encoding="utf-8"))
payload = load_test_spec_for_consumer(path)

self.assertEqual(canonical["data"]["spec_id"], payload["spec_id"])
self.assertEqual(
    canonical["data"]["test_cases"][0]["test_case_id"],
    payload["test_cases"][0]["test_case_id"],
)
```

Keep the generated Markdown view rejection assertion unchanged.

- [ ] **Step 3: Assert CLI envelope 1.0.0 in the compiler E2E**

Replace:

```python
self.assertEqual("build_probe_succeeded", probe_payload["status"])
```

with:

```python
self.assertEqual("passed", probe_payload["data"]["outcome"])
self.assertEqual(0, probe_payload["data"]["exit_code"])
self.assertEqual(
    "succeeded",
    probe_payload["data"]["details"]["build_probe"]["status"],
)
```

This is a test-only correction to an established contract. On this local host
the module is expected to skip because no supported compiler is on `PATH`; the
GitHub compiler-required job must execute it without skip.

- [ ] **Step 4: Run focused GREEN verification**

```powershell
py -m unittest tests.test_test_spec_consumers -v
py -m unittest tests.test_cli_result_contract -v
py -m unittest tests.test_vc6_fixture_build_e2e -v
git diff --check
```

Expected locally: TestSpec consumer and CLI contract modules pass; VC6 E2E
reports one compiler skip; diff check exits 0.

- [ ] **Step 5: Commit the baseline assertion slice**

```powershell
git add -- tests/test_test_spec_consumers.py tests/test_vc6_fixture_build_e2e.py
git diff --cached --check
git commit -m "test: align phase 1 baseline contracts"
```

- [ ] **Step 6: Run the authoritative isolated baseline gate**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$modules = Get-ChildItem -LiteralPath .\tests -Filter 'test_*.py' -File |
  Sort-Object Name |
  ForEach-Object { 'tests.' + $_.BaseName }
$failed = @()
$tests = 0
$skips = 0
$log = Join-Path (Resolve-Path .\.superpowers\sdd) 'baseline-isolated.log'
if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log }
foreach ($module in $modules) {
  $output = & py -m unittest $module -v 2>&1
  $exitCode = $LASTEXITCODE
  $output | Tee-Object -FilePath $log -Append
  foreach ($line in $output) {
    if ($line -match '^Ran (\d+) test') { $tests += [int]$Matches[1] }
    if ($line -match '^OK \(skipped=(\d+)\)$') { $skips += [int]$Matches[1] }
  }
  if ($exitCode -ne 0) { $failed += $module }
}
"isolated_modules=$($modules.Count) tests=$tests skips=$skips failures=$($failed.Count)"
if ($failed.Count -ne 0) {
  throw ('isolated Python failures: ' + ($failed -join ', '))
}
py -m compileall -q src tests
py -m unit_test_runner --help
git diff --check
```

Expected on the approved base plus Tasks 1 and 2: `111` modules, `521` tests,
`3` local skips, `0` failing modules, compileall exit 0, CLI help exit 0, and
diff check exit 0. If fresh output differs, record the actual counts and
investigate every failure before proceeding.

- [ ] **Step 7: Create the baseline evidence record from observed facts**

Create `docs/review/2026-07-14-phase1-baseline-gate.md` with exactly these
sections:

```markdown
# Phase 1 Baseline Gate Evidence

## Scope
## Base and code commits
## Focused RED evidence
## Focused GREEN evidence
## Authoritative isolated gate
## Local compiler limitation
## Publication boundary
```

Populate each section only from commands already run in this task. Record the
base SHA `b66790165a2d4f82943cd199b3b499e1f1725fc3`, the two code commit SHAs,
module/test/skip/failure totals, compileall and CLI results, and the local
compiler skip. Under `Publication boundary`, state that PR URL, Actions URLs,
review verdict, and merge SHA live in GitHub after publication and are not
claimed by this pre-publication record.

- [ ] **Step 8: Commit the evidence record**

```powershell
git add -- docs/review/2026-07-14-phase1-baseline-gate.md
git diff --cached --check
git commit -m "docs: record phase 1 baseline gate evidence"
git status --short --branch
```

Expected: the branch is clean except ignored `.superpowers` evidence.

---

## Branch Integration Gate

After both tasks have task-scoped approval:

1. Generate a complete `origin/main..HEAD` review package and obtain a fresh
   whole-branch review with Critical 0 and Important 0.
2. Push `codex/p1-baseline-gate` and open a draft pull request titled
   `Restore Phase 1 baseline and isolated CI gate` against `main`.
3. Require these six jobs to pass: Source integrity, Python tests, VS Code unit
   tests, VS Code Extension Host activation, VC6 fixture smoke, Package
   contract.
4. Confirm the VC6 fixture smoke log names a compiler and runs the E2E without
   skip.
5. Resolve all review threads and mark the pull request ready only while the
   complete head is GREEN and approved.
6. Merge with a merge commit.
7. In a separate clean worktree at merged `origin/main`, rerun the focused
   baseline modules, authoritative isolated Python gate, compileall, CLI help,
   and diff check.
8. Only after post-merge verification, write the detailed Task 6 recovery
   implementation plan from the approved staged-recovery design.

## Self-Review Results

- Spec coverage: both approved baseline responsibilities and their publication
  gate have explicit tasks and commands.
- Placeholder scan: no deferred implementation marker or unknowable
  pre-publication claim is required.
- Type consistency: TestSpec and CLI envelope field names match their current
  contracts.
- Scope: no Task 6 product file, carrier payload, or materialization workflow
  belongs to this plan.
