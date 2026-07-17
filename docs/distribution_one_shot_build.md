# exe・VSIX 一括ビルド

## 実行

Windows PowerShellでリポジトリルートから次を実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_distribution.ps1
```

処理は途中で失敗した時点で停止します。正常終了時は、生成したexeとVSIXの絶対パスをJSONで表示します。

## 一括で行う処理

1. `.venv-release` を作り直す
2. Python 3.12以上を確認する
3. Python依存関係とPyInstallerをインストールする
4. Pythonテストをモジュール単位で実行する
5. `unit-test-runner.exe` を生成する
6. 生成exeで `--version`、`--help`、`analyze-function --finalize-dossier`、`prepare-review` を実行する
7. exeを `vscode/extension/bin/win32-x64/` へコピーする
8. `npm ci` とVS Code拡張テストを実行する
9. VSIXを生成する
10. VSIX内に同梱exeが存在し、空でないことを確認する

## Schema同梱

PyInstallerは、文字列で指定された動的importとJSONデータを自動では必ずしも検出しません。このスクリプトは次の指定を付けてビルドします。

```text
--hidden-import unit_test_runner.schemas
--collect-data unit_test_runner.schemas
```

さらに、生成したexeでfinalize付き関数解析を実行します。Schema packageまたはSchema JSONが欠落している場合、VSIX作成へ進む前に失敗します。

## 出力

```text
dist/unit-test-runner.exe
dist/unit-test-runner-vscode-<package-version>.vsix
vscode/extension/bin/win32-x64/unit-test-runner.exe
```

VSIX名の版数は `vscode/extension/package.json` の `version` から取得します。

## オプション

### テストを省略する

依存関係の復元、exe実動スモーク、VSIX内exe確認は省略しません。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_distribution.ps1 `
  -SkipTests
```

### 既存のrelease venvを再利用する

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_distribution.ps1 `
  -ReuseReleaseVenv
```

### Python launcherの版を指定する

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_distribution.ps1 `
  -PythonVersion 3.13
```

`-PythonVersion` は `py` launcherを使う場合だけ指定できます。別のPython実行ファイルを使う場合は `-PythonLauncher` にそのパスを指定します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_distribution.ps1 `
  -PythonLauncher C:\Python313\python.exe
```

## 失敗時の確認

exeの実動スモークが失敗した場合、診断用workspaceは削除されず、警告に保存先が表示されます。

代表的な確認箇所:

- `.venv-release`
- `build/release/pyinstaller`
- `build/release/spec`
- `dist/unit-test-runner.exe`
- 警告に表示された `%TEMP%\unitTestRunner-release-smoke-*`

再実行時に仮想環境も作り直す場合は、`-ReuseReleaseVenv` を付けずに実行します。
