# Unit Test Runner for VS Code

VC6/C90向け `unitTestRunner` CLIを呼び出すv0.1 thin adapterです。解析ロジックは拡張内に持ちません。

## 操作

- active C documentのworkspace folderとresource-scoped設定からtargetを解決
- dossier / TestSpec生成と通常review
- harness、build plan、build、explicit test run
- non-destructive reanalysis
- portable suiteのregister、enable/disable、filter、explicit selection、run

Workflowは設定、解析、dossier確定、TestSpec review、harness、build plan、build、run、完了の9 stepです。fileのopen/saveだけでは完了しません。

## 主な設定

- `unitTestRunner.cliPath`
- `unitTestRunner.sourceRoot`
- `unitTestRunner.dswPath`
- `unitTestRunner.outputRoot`
- `unitTestRunner.suiteManifestPath`
- `unitTestRunner.defaultConfiguration`
- `unitTestRunner.defaultProject`
- `unitTestRunner.vcvarsPath`
- `unitTestRunner.commandTimeoutSeconds`

output rootはsource root外に置きます。実build/runのconfirmationは対応するboolean設定で制御します。

## 安全境界

- extension全体でsingle-flight
- 2件目はspawn前にbusy
- timeoutはprocess tree cleanup後に返却
- CLI success envelopeをstrict parse
- reported artifactをroot containmentとSHA-256で再読
- canonical TestSpec更新はPython CLIのrevision guard経由

## 開発

```powershell
npm.cmd ci
npm.cmd test
```

利用手順はリポジトリの [VS Code利用手順](../../docs/vscode_usage_guide.md) を参照してください。
