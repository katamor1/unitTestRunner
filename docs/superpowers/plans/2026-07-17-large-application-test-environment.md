# Large Application Test Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate disposable VC6-style workspaces with 7,000 / 16,000 / 31,000 source entries for `unitTestRunner` large-application smoke testing.

**Architecture:** A standalone Python script copies the existing practical fixture to a guarded external directory, adds C90-compatible generated sources to the `DeviceControl` DSP, and writes a manifest. A small `unittest` module verifies the generator without creating a production-sized fixture.

**Tech Stack:** Python 3.12, standard library (`argparse`, `pathlib`, `shutil`, `json`, `unittest`), VC6 DSP/DSW text fixtures.

## Global Constraints

- Do not modify the base fixture or any production source tree.
- Delete only directories beneath the selected performance root whose basename starts with `unit-test-runner-large-`.
- Preserve detected DSP encoding for UTF-8 BOM, UTF-8, CP932, and Shift-JIS inputs.
- Keep generated C compatible with C90/VC6 syntax.
- Do not add third-party dependencies or generate large tiers in normal CI.

---

### Task 1: Specify generator safety and scale behavior

**Files:**
- Create: `tests/test_large_vc6_fixture_generator.py`

**Interfaces:**
- Consumes: a temporary base fixture containing `Product.dsw` and `DeviceControl/DeviceControl.dsp`
- Produces: executable contracts for `parse_tier_entries`, `build_parser`, `assert_safe_output`, and `generate_fixture`

- [x] **Step 1: Write failing tests for tier parsing and the default tier flag**

```python
self.assertEqual((7000, 16000, 31000), parse_tier_entries("7000,16000,31000"))
args = build_parser().parse_args(["--tiers"])
self.assertEqual("7000,16000,31000", args.tiers)
```

- [x] **Step 2: Run the focused tests and verify the generator is missing**

Run:

```powershell
py -m unittest tests.test_large_vc6_fixture_generator -v
```

Expected: failure while loading `scripts/generate_large_vc6_fixture.py`.

- [x] **Step 3: Add failing tests for safe output, generation, CP932 preservation, regeneration, and manifest file counts**

```python
assert_safe_output(perf_root / "unit-test-runner-large-8", perf_root)
summary = generate_fixture(base, output, 4, perf_root)
self.assertEqual(4, summary["source_entries_in_target_project"])
self.assertEqual(actual_file_count, summary["total_files_on_disk"])
```

- [x] **Step 4: Add a failing CLI test for an explicitly empty tier list**

```python
with self.assertRaisesRegex(ValueError, "at least one positive integer"):
    main(["--base", str(base), "--root", str(perf_root), "--tiers", ""])
```

- [x] **Step 5: Verify each new assertion fails for the intended missing behavior**

Run the focused test method after each assertion is introduced and confirm the failure message identifies the missing contract.

### Task 2: Implement the guarded large fixture generator

**Files:**
- Create: `scripts/generate_large_vc6_fixture.py`
- Test: `tests/test_large_vc6_fixture_generator.py`

**Interfaces:**
- Consumes: `base_root: Path | str`, `output_root: Path | str`, `source_entries: int`, `perf_root: Path | str`
- Produces: `generate_fixture(...) -> dict[str, object]` and CLI JSON output

- [x] **Step 1: Implement tier parsing and path derivation**

```python
DEFAULT_TIER_ENTRIES = (7000, 16000, 31000)
OUTPUT_PREFIX = "unit-test-runner-large-"

def output_root_for_entries(perf_root, entries):
    return Path(perf_root) / f"{OUTPUT_PREFIX}{entries}"
```

- [x] **Step 2: Implement the deletion boundary before any reset**

```python
relative = output.resolve().relative_to(perf_root.resolve())
if not relative.parts or not output.name.startswith(OUTPUT_PREFIX):
    raise ValueError("unsafe output")
```

- [x] **Step 3: Copy the base, generate C90 sources, and update the Source Files group**

```python
shutil.copytree(base, output)
for index in range(generated_count):
    generated_file.write_text(
        render_generated_source(index, generated_count, width),
        encoding="utf-8",
    )
```

- [x] **Step 4: Preserve the detected DSP encoding without newline translation**

```python
updated_dsp = append_dsp_sources(base_dsp, generated_paths)
output_dsp.write_bytes(updated_dsp.encode(dsp_encoding))
```

- [x] **Step 5: Write the manifest with the final on-disk file count**

```python
manifest_path = output / "manifest.json"
manifest = {
    "schema_version": 1,
    "source_entries_in_target_project": source_entries,
    "generated_source_files": generated_count,
    "total_files_on_disk": count_files(output) + (0 if manifest_path.exists() else 1),
    "target": dict(TARGET),
}
```

- [x] **Step 6: Distinguish an omitted tier flag from an explicitly empty value**

```python
if args.tiers is not None:
    tiers = parse_tier_entries(args.tiers)
```

- [x] **Step 7: Run the generator tests**

Run:

```powershell
py -m unittest tests.test_large_vc6_fixture_generator -v
```

Expected: seven tests pass.

### Task 3: Document generation and smoke execution

**Files:**
- Create: `docs/large_application_test_environment.md`
- Create: `docs/superpowers/specs/2026-07-17-large-application-test-environment-design.md`
- Create: `docs/superpowers/plans/2026-07-17-large-application-test-environment.md`

**Interfaces:**
- Consumes: generator CLI and existing `unit_test_runner` CLI commands
- Produces: copy-pasteable PowerShell workflows for one scale and all reference tiers

- [x] **Step 1: Document a single 7,000-entry generation command**

```powershell
py .\scripts\generate_large_vc6_fixture.py --root $perfRoot --entries 7000
```

- [x] **Step 2: Document generation of all reference tiers**

```powershell
py .\scripts\generate_large_vc6_fixture.py --root $perfRoot --tiers
```

- [x] **Step 3: Document discover, map, analyze, and build-probe smoke commands**

```powershell
py -m unit_test_runner discover-projects --workspace $fixture --dsw "$fixture\Product.dsw" --out $projects
py -m unit_test_runner map-source --workspace $fixture --dsw "$fixture\Product.dsw" --source src\device_control.c
py -m unit_test_runner analyze-function --workspace $fixture --dsw "$fixture\Product.dsw" --source src\device_control.c --function DeviceControl_Update --configuration "DeviceControl - Win32 Debug" --project DeviceControl --out $out
py -m unit_test_runner build-probe --dossier "$out\reports\function_dossier.json" --dry-run
```

### Task 4: Verify the final artifact

**Files:**
- Verify: `scripts/generate_large_vc6_fixture.py`
- Verify: `tests/test_large_vc6_fixture_generator.py`

**Interfaces:**
- Consumes: the completed generator and tests
- Produces: fresh evidence for Python syntax, unit contracts, CLI generation, manifest consistency, and generated C90 syntax

- [x] **Step 1: Compile Python sources**

```powershell
py -m compileall -q scripts tests
```

Expected: exit code 0.

- [x] **Step 2: Run the focused unit tests**

```powershell
py -m unittest tests.test_large_vc6_fixture_generator -v
```

Expected: seven tests pass with zero failures.

- [x] **Step 3: Generate an eight-entry temporary fixture**

```powershell
py .\scripts\generate_large_vc6_fixture.py --base $base --root $perfRoot --entries 8
```

Expected: JSON reports eight source entries and seven generated C files.

- [x] **Step 4: Check all generated files as C90**

```bash
for file in "$out"/src/generated/*.c; do
  cc -std=c90 -pedantic -Wall -Wextra -I "$out/include" -fsyntax-only "$file"
done
```

Expected: seven files pass syntax checking.
