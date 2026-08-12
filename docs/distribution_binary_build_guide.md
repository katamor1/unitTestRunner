# unitTestRunner 配布用バイナリ作成手順

対象: v0.1 redesign / Windows EXE / bundled CLI入りVSIX

## 1. 出力

- `dist\unit-test-runner.exe`
- `dist\unit-test-runner-vscode-0.1.0.vsix`
- `vscode\extension\bin\win32-x64\unit-test-runner.exe`

wheel/sdist公開、PyPI公開、VC6-native certificationは対象外です。

## 2. 前提

- Windows PowerShell
- Python 3.12以上
- Node.js 20以上とnpm
- VSIX実機確認時だけVS Code CLI `code`

```powershell
py --version
node --version
npm.cmd --version
git status --short
```

意図しないdirty changeがあるcheckoutからrelease buildを行いません。

## 3. source gate

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m compileall -q src tests

$modules = Get-ChildItem .\tests -Filter 'test_*.py' -File |
  Sort-Object Name |
  ForEach-Object { 'tests.' + $_.BaseName }
$failed = @()
foreach ($module in $modules) {
  py -m unittest $module -v
  if ($LASTEXITCODE -ne 0) { $failed += $module }
}
if ($failed.Count) { throw ('failed: ' + ($failed -join ', ')) }

Push-Location vscode\extension
npm.cmd ci
npm.cmd test
Pop-Location

git diff --check
```

## 4. one-shot build

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_distribution.ps1
```

scriptは次を順に行います。

1. release venv作成とPyInstaller build
2. EXE `--version` / `--help`
3. packaged EXEでfixtureをharness phaseまで解析
4. `finalize-dossier`
5. current TestSpec SHAへ `review-set`
6. `build-probe --dry-run`
7. `run-tests --all --plan`
8. VS Code tests
9. bundled EXE copy
10. VSIX packageとZIP entry検証

smoke失敗時の一時workspaceは診断用に保持し、成功時だけ削除します。

## 5. hash一致

```powershell
$releaseExe = '.\dist\unit-test-runner.exe'
$bundledExe = '.\vscode\extension\bin\win32-x64\unit-test-runner.exe'
(Get-FileHash $releaseExe -Algorithm SHA256).Hash
(Get-FileHash $bundledExe -Algorithm SHA256).Hash
```

2つのsizeとSHA-256が一致することを確認します。さらにVSIXをZIPとして開き、`extension/bin/win32-x64/unit-test-runner.exe` が同じbytesであることを確認します。build scriptはこのentry存在を自動検証します。

## 6. isolated installed VSIX smoke

```powershell
$root = Join-Path $env:TEMP ('utr-vscode-smoke-' + [guid]::NewGuid().ToString('N'))
code --user-data-dir "$root\user" --extensions-dir "$root\extensions" `
  --install-extension .\dist\unit-test-runner-vscode-0.1.0.vsix --force
```

isolated VS Codeで次を確認します。

1. `UnitTestRunner:` commandが表示される
2. bundled CLIでVC6 fixtureを解析できる
3. dossier/TestSpecを開いてreviewを記録できる
4. build/run confirmationまで進める
5. reanalysis reportを生成できる
6. suiteへregisterし、entryを明示選択してrunできる

actual build/runをキャンセルした場合は、その事実をsmoke記録へ残し、実行成功と扱いません。

## 7. release gate

- public schemaはexact 8
- CLI commandはexact 18
- Python残存test GREEN
- VS Code残存test GREEN
- compileall PASS
- fixture/source tree不変
- output root外書込みなし
- `git diff --check` PASS
- EXE/bundled EXE/VSIX entry hash一致
- installed VSIX representative workflow確認

open-endedなseverity countはrelease条件にしません。固定propertyの全PASS、Task起因regression 0、in-scope blocker 0を条件にします。
