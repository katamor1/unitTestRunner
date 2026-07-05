# unitTestRunner

Function-level VC6/C90 unit test dossier generator.

This repository implements the v0.1 scope from `docs/function_level_vc6_unit_test_codex_design.md`.
The initial goal is not to generate a complete executable harness. It collects VC6 project context
and function-level analysis into reviewable JSON, Markdown, and CSV artifacts outside the production
source tree.

## Development

Run the unit and CLI smoke tests:

```powershell
py -m unittest discover -s tests -p "test_*.py"
```

Run the CLI from a checkout without installing:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -m unit_test_runner --help
```

After packaging or editable install, the console entry point is:

```powershell
unit-test-runner --help
```

## Smoke Sample

The repository includes a VC6-style fixture under `tests/fixtures/vc6_project`.

```powershell
$env:PYTHONPATH = "$PWD\src"
$fixture = "$PWD\tests\fixtures\vc6_project"
$out = "$env:TEMP\unitTestRunner-smoke\Control_Update"

py -m unit_test_runner discover-projects --workspace $fixture --dsw "$fixture\Product.dsw" --out "$env:TEMP\unitTestRunner-projects.json"
py -m unit_test_runner map-source --workspace $fixture --dsw "$fixture\Product.dsw" --source src\control.c
py -m unit_test_runner list-functions --source "$fixture\src\control.c"
py -m unit_test_runner analyze-function --workspace $fixture --dsw "$fixture\Product.dsw" --source src\control.c --function Control_Update --configuration "Win32 Debug" --project Control --out $out
py -m unit_test_runner build-probe --dossier "$out\reports\function_dossier.json" --dry-run
py -m unit_test_runner generate-test-draft --dossier "$out\reports\function_dossier.json"
```

Primary outputs:

- `$out\reports\function_dossier.json`
- `$out\reports\function_dossier.md`
- `$out\reports\test_case_draft.csv`
- `$out\generated\build\Makefile`
- `$out\reports\build_probe.log`

For a denser regression and manual-review sample, use `tests/fixtures/vc6_practical_project`.
It includes extern globals, file-scope static state, function pointers, struct members, arrays,
function-like macros, and a multi-function call tree around `DeviceControl_Update`.

```powershell
$env:PYTHONPATH = "$PWD\src"
$fixture = "$PWD\tests\fixtures\vc6_practical_project"
$out = "$env:TEMP\unitTestRunner-practical\DeviceControl_Update"

py -m unit_test_runner map-source --workspace $fixture --dsw "$fixture\Product.dsw" --source src\device_control.c
py -m unit_test_runner analyze-function --workspace $fixture --dsw "$fixture\Product.dsw" --source src\device_control.c --function DeviceControl_Update --configuration "DeviceControl - Win32 Debug" --project DeviceControl --out $out
py -m unit_test_runner build-probe --dossier "$out\reports\function_dossier.json" --dry-run
```

## VS Code Thin Adapter

The TypeScript adapter under `vscode/extension` only invokes the CLI. It does not contain parser or
report-generation logic.

```powershell
cd vscode\extension
npm install
npm test
```

Required VS Code settings:

```json
{
  "unitTestRunner.cliPath": "unit-test-runner",
  "unitTestRunner.workspaceRoot": "D:/work/product",
  "unitTestRunner.dswPath": "D:/work/product/Product.dsw",
  "unitTestRunner.outputRoot": "D:/work/unit_test_workspace",
  "unitTestRunner.defaultConfiguration": "Win32 Debug"
}
```

Commands:

- `UnitTestRunner: Analyze Selected Function`
- `UnitTestRunner: Open Last Function Dossier`

## Scope

v0.1 deliberately excludes full harness generation, measured runtime coverage, realtime behavior,
interrupt simulation, and hardware I/O reproduction. Those are Phase 2+ concerns.

## Encoding Policy

VC6 project files and target C sources are treated as legacy Windows inputs. The reader accepts
`utf-8-sig`, `cp932`, and `shift_jis`; Shift-JIS/CP932 source comments are a normal case, not an
exception path. Extracted source/header files are copied byte-for-byte.

Generated C-family artifacts for future mocks, stubs, and runners must be written as CP932 with
CRLF line endings so they stay friendly to the target VC6 workflow. JSON and Markdown reports remain
UTF-8 unless a later workflow requires a different reviewer-facing format.
