# VC6 DSW/DSPパース実機スモーク

この手順は、DSW/DSPパーサをCLI経由で実行し、レビュー可能なJSON/Markdown成果物を作るための実機確認環境です。既定では `tests/fixtures/vc6_practical_project` を使い、`.dsw` から2つの `.dsp` を発見し、`src\device_control.c` が複数プロジェクトに所属することまで確認します。

## 実行

リポジトリルートから実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_vc6_parse_smoke.ps1
```

出力先を明示する場合は `-OutRoot` を指定します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_vc6_parse_smoke.ps1 `
  -OutRoot "$env:TEMP\unitTestRunner-vc6-parse-smoke"
```

## 出力

既定の出力先は `$env:TEMP\unitTestRunner-vc6-parse-smoke` です。

- `dsw_dsp_projects.json`: DSW discoveryと各DSPの構成、define、include、source/header/resource件数
- `dsw_dsp_projects.md`: DSW/DSP発見結果の人間レビュー用Markdown
- `source_membership_all.json`: 対象sourceの全DSP所属候補
- `source_membership_all.md`: source所属候補の人間レビュー用Markdown
- `source_membership_devicecontrol_debug.json`: project/configurationで絞り込んだsource所属
- `summary.txt`: 実行条件と成果物一覧

## 実プロジェクトでの確認

実プロジェクトへ差し替える場合は、workspace root、DSW、source、project、configurationを指定します。`-Dsw` は workspace root からの相対パス、または絶対パスを受け付けます。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_vc6_parse_smoke.ps1 `
  -FixtureRoot "D:\work\legacy_product" `
  -Dsw "Product.dsw" `
  -Source "src\control.c" `
  -Project "Control" `
  -Configuration "Control - Win32 Debug" `
  -ExpectedSecondProject "" `
  -ExpectedDefine "WIN32" `
  -OutRoot "D:\work\unitTestRunner-smoke\parse"
```

複数DSP所属を期待しない実プロジェクトでは `-ExpectedSecondProject ""` を指定します。特定defineを検証しない場合は `-ExpectedDefine ""` を指定します。

## 回帰テスト

このスモーク環境自体は、以下のテストで検証します。

```powershell
py -m unittest tests.test_vc6_parse_smoke_environment
```

広めに確認する場合は、DSW/DSP関連の既存テストも合わせて実行します。

```powershell
py -m unittest tests.test_vc6_dsw_parser tests.test_vc6_dsp_parser tests.test_vc6_workspace_discovery_cli tests.test_vc6_parse_smoke_environment
```
