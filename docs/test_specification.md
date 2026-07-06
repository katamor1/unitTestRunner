# unitTestRunner テスト仕様書

作成日: 2026-07-05  
対象版数: v0.1

## 1. 目的

本書は、`unitTestRunner` のPython CLI、VC6/C90解析、dossier生成、VS Code adapter、配布物を検証するためのテスト仕様を定義する。

## 2. テスト対象

| 区分 | 対象 | 主な確認内容 |
|---|---|---|
| Python unit | `src/unit_test_runner` | parser、analyzer、dossier、build、execution、reanalysis |
| CLI smoke | `py -m unit_test_runner` | command registration、help、fixture flow |
| Fixture | `tests/fixtures/vc6_project` | 標準スモーク、`Control_Update` |
| Practical fixture | `tests/fixtures/vc6_practical_project` | globals/statics/call tree/function pointer/macro |
| VS Code adapter | `vscode/extension` | command builder、settings、CLI result parser、report path resolver |
| CI | `.github/workflows/ci.yml` | Windows上のPython testとNode test |
| Distribution | `dist/` 配布物 | exe help/version、fixture smoke、VSIX package |

## 3. 標準検証コマンド

### 3.1 Python broad gate

```powershell
py -m unittest discover -s tests -p "test_*.py"
```

期待結果:

- `Ran 0 tests` ではない
- 失敗、エラーがない

### 3.2 CLI registration smoke

```powershell
$env:PYTHONPATH = "$PWD\src"
py -m unit_test_runner --help
```

期待結果:

- `doctor`
- `discover-projects`
- `map-source`
- `list-functions`
- `analyze-function`
- `reanalyze-function`
- `generate-harness-skeleton`
- `build-probe`
- `analyze-build-errors`
- `complete-build`
- `run-tests`
- `prepare-evidence`
- `finalize-dossier`
- `prepare-review`
- `generate-test-design`
- `reconcile-test-cases`
- `select-regression-tests`
- `suite-register`
- `suite-list`
- `suite-remove`
- `suite-run`

がhelpに表示される。

### 3.3 VS Code adapter gate

```powershell
Push-Location vscode\extension
npm ci
npm.cmd test
Pop-Location
```

期待結果:

- TypeScript compileが成功する
- Node testが成功する

## 4. 機能テスト項目

| ID | 種別 | 操作 | 期待結果 |
|---|---|---|---|
| CLI-001 | help | `py -m unit_test_runner --help` | 全公開コマンドが表示される |
| CLI-002 | version | `py -m unit_test_runner --version` | `0.1.0` 系のversionが表示される |
| CLI-003 | json | `--json analyze-function ...` | JSON payloadが標準出力に出る |
| VC6-001 | discover | `discover-projects --workspace ... --dsw ...` | `.dsw` 内のproject候補を取得する |
| VC6-002 | map | `map-source --source src\control.c` | 対象sourceのproject membershipを返す |
| SRC-001 | list | `list-functions --source ...` | Cソース内の関数定義を列挙する |
| DOS-001 | analyze | `analyze-function ... --out <out>` | `<out>\reports\function_dossier.json` を生成する |
| DOS-002 | finalize | `analyze-function ... --finalize-dossier` | review workflow fieldsを含むdossierを生成する |
| DOS-003 | review | `prepare-review --dossier ...` | checklist、next actions、traceabilityを生成する |
| SUITE-001 | register | `suite-register --suite <suite> --workspace <out>` | 関数workspaceがmanifestへ登録される |
| SUITE-002 | list | `suite-list --suite <suite> --tag selected` | タグに一致する登録済み関数だけを返す |
| SUITE-003 | run | `suite-run --suite <suite> --tag selected --dry-run` | suite run report JSON/Markdown/CSVを生成する |
| SUITE-004 | green | `suite-run --suite <suite> --all --run --require-green` | 非GREENがある場合は終了コード32で失敗する |
| BLD-001 | dry-run | `build-probe --dossier ... --dry-run` | 実ビルドせずbuild probe計画を生成する |
| TST-001 | design | `generate-test-design --dossier ...` | test case designを生成する |
| EXE-001 | dry-run | `run-tests --workspace <out> --dry-run` | 実行せずexecution evidenceを準備する |
| EVD-001 | evidence | `prepare-evidence --workspace <out>` | evidence manifest/packageを生成する |
| REA-001 | reanalysis | `reanalyze-function ...` | 前回dossierとの差分と再利用候補を生成する |
| VSC-001 | adapter | `npm.cmd test` | CLI wiringとreport path解決のテストが通る |

## 5. Fixture別シナリオ

### 5.1 標準fixture: `vc6_project`

対象:

```text
tests/fixtures/vc6_project
src/control.c
Control_Update
```

手順:

```powershell
$env:PYTHONPATH = "$PWD\src"
$fixture = "$PWD\tests\fixtures\vc6_project"
$out = "$env:TEMP\unitTestRunner-smoke\Control_Update"

py -m unit_test_runner analyze-function `
  --workspace $fixture `
  --dsw "$fixture\Product.dsw" `
  --source src\control.c `
  --function Control_Update `
  --configuration "Win32 Debug" `
  --project Control `
  --out $out `
  --finalize-dossier

py -m unit_test_runner build-probe --dossier "$out\reports\function_dossier.json" --dry-run
py -m unit_test_runner generate-test-design --dossier "$out\reports\function_dossier.json"
```

期待結果:

- `reports/function_dossier.json` が存在する
- `reports/function_dossier.md` が存在する
- `reports/test_case_design.csv` が存在する
- `build-probe --dry-run` が実バイナリを起動しない

### 5.2 実用fixture: `vc6_practical_project`

対象:

```text
tests/fixtures/vc6_practical_project
src/device_control.c
DeviceControl_Update
```

確認観点:

- file-scope static
- extern global
- struct member / array access
- callback / function pointer
- object-like macro
- function-like macro
- multiple `.dsp` membership

手順:

```powershell
$env:PYTHONPATH = "$PWD\src"
$fixture = "$PWD\tests\fixtures\vc6_practical_project"
$out = "$env:TEMP\unitTestRunner-practical\DeviceControl_Update"

py -m unit_test_runner map-source --workspace $fixture --dsw "$fixture\Product.dsw" --source src\device_control.c
py -m unit_test_runner analyze-function --workspace $fixture --dsw "$fixture\Product.dsw" --source src\device_control.c --function DeviceControl_Update --configuration "DeviceControl - Win32 Debug" --project DeviceControl --out $out
py -m unit_test_runner build-probe --dossier "$out\reports\function_dossier.json" --dry-run
```

期待結果:

- `DeviceControl_Update` のdossierが生成される
- 複数project membershipの情報が失われない
- build probe dry-runがdossier入力で動く

## 6. 配布物テスト

### 6.1 CLI exe

対象成果物:

```text
dist\unit-test-runner.exe
```

手順:

```powershell
.\dist\unit-test-runner.exe --version
.\dist\unit-test-runner.exe --help
```

期待結果:

- versionが表示される
- helpに公開コマンドが表示される

fixture smoke:

```powershell
$fixture = "$PWD\tests\fixtures\vc6_project"
$out = "$env:TEMP\unitTestRunner-release-smoke\Control_Update"

.\dist\unit-test-runner.exe --json analyze-function `
  --workspace $fixture `
  --dsw "$fixture\Product.dsw" `
  --source src\control.c `
  --function Control_Update `
  --configuration "Win32 Debug" `
  --project Control `
  --out $out `
  --finalize-dossier

.\dist\unit-test-runner.exe build-probe --dossier "$out\reports\function_dossier.json" --dry-run
```

### 6.2 VSIX

対象成果物:

```text
dist\unit-test-runner-vscode-0.1.0.vsix
```

手順:

```powershell
code --install-extension .\dist\unit-test-runner-vscode-0.1.0.vsix
```

期待結果:

- VS Codeに拡張がインストールされる
- command paletteに `UnitTestRunner:` コマンドが表示される
- `unitTestRunner.cliPath` に配布exeまたはCLIパスを指定できる

## 7. CI仕様

GitHub ActionsではWindows上で以下を実行する。

1. Python 3.12セットアップ
2. `py -m unittest discover -s tests -p "test_*.py"`
3. Node 20セットアップ
4. `vscode/extension` で `npm ci`
5. `npm.cmd test`

## 8. 判定方針

- 0件テストの成功は合格扱いしない
- build/testの実行系はdry-runと実行を区別して確認する
- 生成物は本番fixtureツリーではなく外部ワークスペースに出ることを確認する
- JSON/Markdown/CSVの存在だけでなく、後続コマンドが消費できることを確認する

