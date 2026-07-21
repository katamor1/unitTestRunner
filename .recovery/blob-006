# unitTestRunner 配布用バイナリ作成手順書

作成日: 2026-07-05  
対象版数: v0.1  
対象配布物: Windows向け `unit-test-runner.exe`、CLI同梱VS Code拡張VSIX

## 1. 目的

本書は、`unitTestRunner` の初回配布物として以下を作成・検証する手順を定義する。

- `dist\unit-test-runner.exe`
- `dist\unit-test-runner-vscode-0.1.0.vsix`

Python packageのwheel/sdist公開、PyPI公開、DOCX/PDF文書化は対象外とする。

通常の配布ビルドでは、以降の個別手順を手で組み立てず、リポジトリルートから次の標準スクリプトを実行する。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_distribution.ps1
```

このスクリプトが、exe生成、終了コード35のブロッカーレポート実動スモーク、VS Codeテスト、CLI同梱VSIX生成、同梱exeのSHA-256一致確認までを一括で行う。以下の章は、スクリプト内部の工程を確認・診断するための参考手順である。

## 2. 前提

Windows PowerShellでリポジトリルートから実行する。

必要なツール:

- Python 3.12以上
- Node.js 20
- npm
- VS Code CLI `code`。VSIXインストール確認を行う場合のみ必要
- ネットワーク接続。`pip` と `npm` が依存パッケージを取得する場合に必要

事前確認:

```powershell
py --version
py -0p
node --version
npm --version
git status --short
```

`git status --short` に意図しない変更がある場合は、配布作業前に内容を確認する。`py -0p` でPython 3.12以上が表示されない場合は、Python 3.12以上を導入してから続行する。

## 3. 事前検証

配布物を作る前に、ソースツリーの標準テストを実行する。

```powershell
py -m unittest discover -s tests -p "test_*.py"
```

CLIの登録状態を確認する。

```powershell
$env:PYTHONPATH = "$PWD\src"
py -m unit_test_runner --version
py -m unit_test_runner --help
```

VS Code adapterを検証する。

```powershell
Push-Location vscode\extension
npm ci
npm.cmd test
Pop-Location
```

## 4. CLI exeの作成

配布用の仮想環境を作成する。Python launcherで複数バージョンが見える場合は、配布に使う3.12以上のバージョンを明示する。この環境で3.13を使う例は `py -3.13 -m venv .venv-release` である。

```powershell
py -m venv .venv-release
.\.venv-release\Scripts\python.exe -m pip install --upgrade pip
```

ビルドに使う基本パッケージを入れる。

```powershell
.\.venv-release\Scripts\python.exe -m pip install setuptools wheel
```

リポジトリをeditable installする。

```powershell
.\.venv-release\Scripts\python.exe -m pip install -e .
```

PyInstallerを入れる。初回は依存取得に数分かかる場合がある。

```powershell
.\.venv-release\Scripts\python.exe -m pip install pyinstaller
```

単体exeを作成する。

```powershell
.\.venv-release\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --console --name unit-test-runner --paths src scripts\pyinstaller_entry.py
```

期待される成果物:

```text
dist\unit-test-runner.exe
```

`build\`、`dist\`、`unit-test-runner.spec` はPyInstallerが生成する作業・成果物である。配布対象は `dist\unit-test-runner.exe` のみとする。

## 5. CLI exeの検証

versionとhelpを確認する。

```powershell
.\dist\unit-test-runner.exe --version
.\dist\unit-test-runner.exe --help
```

代表fixtureでdossier生成を確認する。

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
```

生成されたdossierを後続コマンドに渡せることを確認する。

```powershell
.\dist\unit-test-runner.exe --json prepare-review --dossier "$out\reports\function_dossier.json"
.\dist\unit-test-runner.exe build-probe --dossier "$out\reports\function_dossier.json" --dry-run
.\dist\unit-test-runner.exe generate-test-design --dossier "$out\reports\function_dossier.json"
```

確認するファイル:

- `$out\reports\function_dossier.json`
- `$out\reports\function_dossier.md`
- `$out\reports\test_case_design.csv`
- `$out\reports\review_checklist.md`
- `$out\reports\next_actions.md`

## 6. CLI exeをVS Code拡張へ同梱する

`unit-test-runner.exe` の配置場所が端末ごとにばらつくことを避けるため、VSIXにはWindows x64向けCLI exeを同梱する。拡張機能は `unitTestRunner.cliPath` が未指定または既定値 `unit-test-runner` の場合、VSIX内の同梱exeを優先して使う。

```powershell
New-Item -ItemType Directory -Force vscode\extension\bin\win32-x64 | Out-Null
Copy-Item -Force dist\unit-test-runner.exe vscode\extension\bin\win32-x64\unit-test-runner.exe
```

同梱後に、拡張ルートから存在を確認する。

```powershell
Test-Path vscode\extension\bin\win32-x64\unit-test-runner.exe
```

## 7. VSIXの作成

VS Code adapterの依存関係を復元し、テストを実行する。

```powershell
Push-Location vscode\extension
npm ci
npm.cmd test
```

VSIXを作成する。

```powershell
npm.cmd exec --package @vscode/vsce -- vsce package --out ..\..\dist\unit-test-runner-vscode-0.1.0.vsix
Pop-Location
```

期待される成果物:

```text
dist\unit-test-runner-vscode-0.1.0.vsix
```

VSIX作成ログの `Files included in the VSIX` に以下が含まれることを確認する。

```text
extension/bin/win32-x64/unit-test-runner.exe
```

## 8. VSIXの検証

VS Code CLIでインストールする。

```powershell
code --install-extension .\dist\unit-test-runner-vscode-0.1.0.vsix
```

VS Codeで対象Cプロジェクトを開き、settingsに以下を設定する。`unitTestRunner.cliPath` は通常は設定しない。同梱exeではなく外部CLIを使う場合だけ、絶対パスで上書きする。

```json
{
  "unitTestRunner.sourceRoot": "D:/work/product",
  "unitTestRunner.dswPath": "D:/work/product/Product.dsw",
  "unitTestRunner.outputRoot": "D:/work/unit_test_workspace",
  "unitTestRunner.defaultConfiguration": "Win32 Debug",
  "unitTestRunner.defaultProject": "Control",
  "unitTestRunner.finalizeDossierAfterAnalyze": true
}
```

確認項目:

- command paletteに `UnitTestRunner:` コマンドが表示される
- `UnitTestRunner: Analyze Current Function` または `UnitTestRunner: Analyze Selected Function` がVSIX同梱CLIを起動する
- 出力先workspaceに `reports/function_dossier.json` が生成される
- `UnitTestRunner: Open Function Dossier` がMarkdownまたはJSON dossierを開く
- `Run Build Probe` や `Run Tests` など実行系コマンドでは確認が表示される

## 9. 配布パッケージ内容

初回配布では、通常はVSIXだけでVS Code利用を開始できる。CLI単体利用者向けにはexeも併せて配る。

```text
dist/
  unit-test-runner.exe
  unit-test-runner-vscode-0.1.0.vsix
```

利用者には以下も案内する。

- VS Code利用時は `unitTestRunner.cliPath` を通常設定しない
- CLI単体利用時は `unit-test-runner.exe --help` と `unit-test-runner.exe --version` を確認する
- READMEの基本スモーク
- VS Code setting例
- 生成物は本番ソースツリー外の `outputRoot` に出ること

## 10. トラブルシュート

| 症状 | 確認内容 | 対処 |
|---|---|---|
| `.venv-release\Scripts\python` が見つからない | venv未作成、またはPython launcherの指定バージョンがない | `py -0p` で3.12以上を確認し、`py -m venv .venv-release` または `py -3.13 -m venv .venv-release` を先に実行する |
| PyInstallerでimport error | `--paths src` の指定 | 手順通り `--paths src` を付ける |
| exeのhelpにコマンドが出ない | 古い成果物を実行していないか | `dist\unit-test-runner.exe` を削除して再作成する |
| `npm.cmd test` が失敗する | `npm ci` 実行有無、Node 20 | `vscode\extension` で `npm ci` からやり直す |
| `vsce` が見つからない | `npm.cmd exec --package @vscode/vsce -- vsce ...` を使っているか | ローカル依存に固定せず `npm exec` 経由で実行する |
| VS CodeからCLIが見つからない | VSIXに `extension/bin/win32-x64/unit-test-runner.exe` が含まれるか | copy手順後にVSIXを作り直す。外部CLIを使う場合だけ `unitTestRunner.cliPath` にexeの絶対パスを設定する |

## 11. リリース前チェックリスト

- [ ] `py -m unittest discover -s tests -p "test_*.py"` が成功した
- [ ] `py -m unit_test_runner --help` が成功した
- [ ] `npm.cmd test` が成功した
- [ ] `dist\unit-test-runner.exe --version` が成功した
- [ ] `dist\unit-test-runner.exe --help` が成功した
- [ ] exeで `analyze-function --finalize-dossier` が成功した
- [ ] exeで `build-probe --dossier ... --dry-run` が成功した
- [ ] exeで `generate-test-design --dossier ...` が成功した
- [ ] `vscode\extension\bin\win32-x64\unit-test-runner.exe` にexeをコピーした
- [ ] `dist\unit-test-runner-vscode-0.1.0.vsix` が生成された
- [ ] VSIXに `extension/bin/win32-x64/unit-test-runner.exe` が含まれた
- [ ] VSIXをVS Codeへインストールできた
