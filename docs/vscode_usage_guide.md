# unitTestRunner VS Code利用手順

対象: v0.1 redesign

VS Code拡張はPython CLIのthin adapterです。C/DSW/DSP解析やartifact生成を拡張内で再実装しません。

## 1. インストール

```powershell
code --install-extension .\dist\unit-test-runner-vscode-0.1.0.vsix
```

インストール後、Activity Barの `Unit Test Runner` に `関数テスト` と `テストスイート` が表示されることを確認します。

## 2. workspaceと設定

対象Cファイルを含むworkspace folderを開きます。実行対象は常にactive documentを含むworkspace folderから解決され、過去に操作した別workspaceは使われません。

設定はresource scopeへ保存されます。

| 設定 | 内容 |
|---|---|
| `unitTestRunner.cliPath` | CLIまたはEXE。既定値ではbundled EXEを優先 |
| `unitTestRunner.sourceRoot` | source root。未設定時はactive workspace folder |
| `unitTestRunner.dswPath` | 対象 `.dsw` |
| `unitTestRunner.outputRoot` | source root外の出力先 |
| `unitTestRunner.suiteManifestPath` | suite manifest |
| `unitTestRunner.defaultConfiguration` | full VC6 configuration |
| `unitTestRunner.defaultProject` | 複数membership時の明示project |
| `unitTestRunner.vcvarsPath` | 実build時の環境設定batch |
| `unitTestRunner.commandTimeoutSeconds` | CLI timeout |

実buildと実runの確認dialogは各confirmation設定で制御します。output rootがsource root内、DSW/sourceが不正、CLIが起動不能の場合はspawn前に拒否されます。

## 3. 一方向workflow

`関数テスト` パネルは次の9 stepです。

1. 設定確認
2. 関数を解析
3. dossierを確定
4. TestSpecをレビュー
5. ハーネスを準備
6. build planを確認
7. buildを実行
8. testを実行
9. 完了

fileの存在、open、saveだけではstepは完了しません。validated CLI successか、表示されている明示確認だけが状態を進めます。再解析やTestSpec更新後は下流review/build/run状態が解除されます。

対象Cファイルをactive editorにして、右クリックまたはパネルから `現在の関数を解析` を実行します。選択文字列をfunction名として使う場合は `選択した関数を解析` を使います。

## 4. TestSpec review

`TestSpecをレビュー` は普通のartifact reviewです。runtime authorityやbyte IPCではありません。

1. canonical `reports/test_spec.json` を開く
2. 内容と未解決項目を確認する
3. `approved` または `changes_requested` を選ぶ
4. reviewer名と任意commentを入力する

approvalは現在のTestSpec SHAだけに有効です。TestSpecが変わると自動的にstale扱いになります。canonical TestSpecの構造更新はCLIのrevision guard経由で行い、Markdown/CSV viewを編集しても正本には反映されません。

## 5. build/runとtimeout

`ビルドの事前確認` は未承認でも実行できます。実runには未解決項目0、build-probe成功、現在のTestSpecに対するapprovalが必要です。

拡張全体で1つのsingle-flight gateを共有します。実行中に2件目を開始するとspawn前にbusyで拒否します。success、failure、spawn error、timeoutの全経路でgateを解放し、timeout結果はprocess tree cleanup完了後に返します。

CLIが報告したartifactは、拡張が指定root内のpathとSHA-256を再読してから開きます。

## 6. reanalysis

`現在の関数を再解析` はcandidate TestSpecとreanalysis reportを生成します。canonical TestSpecは自動変更されません。field conflictを解消し、expected revisionとcandidate SHAが一致する場合だけCLIの `apply-reanalysis` で反映します。

## 7. suite

`テストスイート` パネルが提供する操作は次だけです。

- 現在の関数をregister
- entryのenable/disable
- function/tag filter
- entryの明示選択
- 選択entryのrun
- 最新suite reportを開く

自動dependency graph selectionや無制限history dashboardはありません。実行前にsource SHA、TestSpec SHA、harness SHAが一致しないentryはspawn前に `blocked` になります。

## 8. accessibility

button、checkbox、form controlにはaccessible nameがあります。refresh、保存、conflict後は可能な範囲で直前controlへfocusを戻します。keyboardだけで主要workflowを操作できます。

## 9. smoke確認

installed VSIXでは次を確認します。

1. command paletteに16個の `UnitTestRunner:` commandが表示される
2. bundled CLIで対象関数を解析できる
3. dossier/TestSpecを開きreviewを記録できる
4. build/run confirmationが表示される
5. reanalysis reportを生成できる
6. suiteへregisterし、選択entryを実行できる

拡張のunit tests:

```powershell
Push-Location vscode\extension
npm.cmd test
Pop-Location
```
