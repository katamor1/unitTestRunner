# unitTestRunner

`unitTestRunner` は、Visual C++ 6.0 / C90 の既存Cプロジェクトから、関数単位のレビュー可能な dossier、TestSpec、外部ハーネス、build/run結果を作る v0.1 ツールです。

完全なC frontendや全関数の自動実行化を目標にはしません。対象sourceは読み取り専用入力として扱い、生成物は必ずsource root外のworkspaceへ保存します。VC6の `.dsw` / `.dsp`、C90、CP932 / Shift-JISを通常入力として扱います。

唯一のactive roadmapは [v0.1 redesign roadmap](docs/v01-redesign-roadmap.md) です。旧38タスクと `docs/superpowers/plans/` 配下の計画はhistoricalです。

## 公開契約

公開JSON artifactは次の8種類だけです。

- `function_dossier`
- `test_spec`
- `review_record`
- `build_probe_report`
- `test_run_report`
- `reanalysis_report`
- `suite_manifest`
- `suite_run_report`

各artifactのrootは `schema_version: "1.0.0"`、`artifact_kind`、`subject`、`data` の4 fieldです。`subject`はsource相対path、source SHA-256、function、project、full configurationを保持します。Markdown、CSV、logは表示用viewであり、独立したschemaではありません。

`--json` のCLI envelopeは次の5 fieldだけです。

```json
{
  "command": "run-tests",
  "outcome": "passed",
  "message": "Test execution completed.",
  "artifacts": [
    {
      "kind": "test_run_report",
      "path": "runs/run-001/test_run_report.json",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ],
  "diagnostics": []
}
```

outcomeは `planned / passed / failed / blocked / timed_out / cancelled / error` の7種です。実行済み成功だけが `passed` です。malformed input、存在しないartifact、outcomeとexit codeの不一致は非0になります。

## セットアップと検証

```powershell
py -m pip install -e ".[test]"
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m unit_test_runner --version
py -m unit_test_runner --help
```

Pythonの全テストはmoduleごとに直列実行します。

```powershell
$modules = Get-ChildItem .\tests -Filter 'test_*.py' -File |
  Sort-Object Name |
  ForEach-Object { 'tests.' + $_.BaseName }
$failed = @()
foreach ($module in $modules) {
  py -m unittest $module -v
  if ($LASTEXITCODE -ne 0) { $failed += $module }
}
if ($failed.Count) { throw ('failed: ' + ($failed -join ', ')) }
```

VS Code adapterは次で検証します。

```powershell
Push-Location vscode\extension
npm.cmd ci
npm.cmd test
Pop-Location
```

## 基本workflow

fixture `tests/fixtures/vc6_project` の `Control_Update` を使う例です。

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$fixture = (Resolve-Path .\tests\fixtures\vc6_project).Path
$out = Join-Path $env:TEMP 'unitTestRunner-v01-Control_Update'

py -m unit_test_runner --json discover-projects `
  --workspace $fixture --dsw "$fixture\Product.dsw"

py -m unit_test_runner --json map-source `
  --workspace $fixture --dsw "$fixture\Product.dsw" `
  --source 'src\control.c' --configuration 'Control - Win32 Debug' `
  --project Control

py -m unit_test_runner --json analyze-function `
  --workspace $fixture --dsw "$fixture\Product.dsw" `
  --source 'src\control.c' --function Control_Update `
  --configuration 'Control - Win32 Debug' --project Control `
  --out $out --phase design

py -m unit_test_runner --json finalize-dossier --workspace $out
```

ここまででcanonical成果物は次の2点です。

- `$out\reports\function_dossier.json`
- `$out\reports\test_spec.json`

TestSpecを確認し、未解決入力をrevision guard付きで反映した後、現在のTestSpec SHAに対するreviewを記録します。

```powershell
py -m unit_test_runner --json get-test-input-form --workspace $out
py -m unit_test_runner --json apply-test-input-form `
  --workspace $out --input .\changes.json --expected-revision 1

$testSpec = Join-Path $out 'reports\test_spec.json'
$sha = (Get-FileHash $testSpec -Algorithm SHA256).Hash.ToLowerInvariant()
py -m unit_test_runner --json review-set `
  --workspace $out --artifact-kind test_spec --artifact-sha256 $sha `
  --decision approved --reviewer $env:USERNAME --comment 'reviewed'
```

`get-test-input-form` は派生viewを
`$out\reports\test_input_form.json` に書き出します。このviewから変更対象の
`item_id` と `subject_fingerprint` を選び、`changes.json` を作成します。

ハーネスを生成し、build planを確認してから実buildと実runへ進みます。

```powershell
py -m unit_test_runner --json analyze-function `
  --workspace $fixture --dsw "$fixture\Product.dsw" `
  --source 'src\control.c' --function Control_Update `
  --configuration 'Control - Win32 Debug' --project Control `
  --out $out --phase harness

py -m unit_test_runner --json build-probe --workspace $out --dry-run
py -m unit_test_runner --json build-probe --workspace $out --run
py -m unit_test_runner --json run-tests --workspace $out --all --plan
py -m unit_test_runner --json run-tests --workspace $out --all --run
```

実runには、未解決項目0、成功したbuild-probe、現在のTestSpec SHAに対する `approved` review_recordが必要です。planとbuild-probeは未承認でも実行できます。placeholderや常真oracleが残る場合はreview-only scaffoldになり、実runは `blocked` です。

## reanalysis

reanalysisはcanonical TestSpecを直接変更しません。candidate TestSpecと `reanalysis_report` を生成し、conflictが0でrevisionとcandidate SHAが一致する場合だけ反映します。

```powershell
py -m unit_test_runner --json reanalyze-function `
  --workspace $fixture --dsw "$fixture\Product.dsw" `
  --source 'src\control.c' --function Control_Update `
  --configuration 'Control - Win32 Debug' --project Control --out $out

py -m unit_test_runner --json apply-reanalysis `
  --workspace $out --candidate "$out\reports\candidate_test_spec.json" `
  --candidate-sha256 $candidateSha --expected-revision 2
```

function IDとcase IDはsource相対path、function、coverage anchor、case kindから決定的に生成されます。同一case IDの人間入力はcandidateへコピーされ、競合はfield単位で報告されます。

## 明示selectorとsuite

`run-tests` は `--case-id`、`--tag`、`--all` のいずれかを必須とします。unknown、empty、disabled selectorはinput errorです。run reportはrequested / started / completed / not-run case IDを記録します。

suite manifestはmanifest-relative POSIX workspace path、entry ID、enabled、tags、function subject、TestSpec SHA、harness SHAを保持します。更新系commandはrevision guard付きatomic writeです。

```powershell
$suite = Join-Path $env:TEMP 'unitTestRunner-suite\suite_manifest.json'

py -m unit_test_runner --json suite-register `
  --suite $suite --workspace $out --tags 'smoke,regression' `
  --expected-revision 0

py -m unit_test_runner --json suite-list --suite $suite
py -m unit_test_runner --json suite-update `
  --suite $suite --entry-id $entryId --enabled true --expected-revision 1
py -m unit_test_runner --json suite-run --suite $suite --entry-id $entryId --plan
py -m unit_test_runner --json suite-run --suite $suite --entry-id $entryId --run
```

suite実行前にはsource SHA、TestSpec SHA、harness SHAだけを比較します。不一致はbinary spawn前に `blocked` です。選択entryが1件でも `passed` 以外ならCLIは非0です。

## VS Code thin adapter

VS Code拡張はPython CLIを呼び出すだけのadapterです。C/DSW/DSP解析ロジックを持ちません。active documentを含むworkspace folderとresource-scoped設定から対象を解決し、global last-workspaceは実行対象に使いません。

主要設定:

- `unitTestRunner.cliPath`
- `unitTestRunner.sourceRoot`
- `unitTestRunner.dswPath`
- `unitTestRunner.outputRoot`
- `unitTestRunner.suiteManifestPath`
- `unitTestRunner.defaultConfiguration`
- `unitTestRunner.defaultProject`
- `unitTestRunner.vcvarsPath`
- `unitTestRunner.commandTimeoutSeconds`

Workflowは「設定→解析→dossier確定→TestSpec review→harness→build plan→build→run→完了」の一方向です。fileの存在・open・saveだけでは完了やapprovalになりません。CLIのvalidated successかユーザーの明示確認だけが状態を進めます。extension全体で1つのsingle-flight gateを共有し、timeout時はprocess tree cleanup後に結果を返します。

詳細は [VS Code利用手順](docs/vscode_usage_guide.md) を参照してください。

## 配布

Windows EXEとbundled CLI入りVSIXは次で作成します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_distribution.ps1
```

scriptはPyInstaller、packaged EXE smoke、VS Code tests、VSIX package、bundled EXE同梱確認を順に実行します。詳細は [配布用バイナリ作成手順](docs/distribution_binary_build_guide.md) を参照してください。

## v0.1の非目標

- 完全C preprocessor / 全C型system / C++ frontend
- 全関数の完全自動harness生成
- VC6-native toolchainの環境横断certification
- immutable history chain、runtime review IPC、再帰authority
- Python installation / DLL / repository全読取のprovenance証明
- hostile same-user mutationやFILE_OBJECT同一性への防御
- 自動regression dependency graph、高度なsuite analytics

ローカルhost、Python、Git、Node、SystemRootはdeveloper-controlled TCBです。上記が必要になった場合は、現Taskへ暗黙追加せずPhase 2またはscope-expansion requestとして扱います。
