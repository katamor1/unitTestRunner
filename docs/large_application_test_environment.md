# 大規模アプリケーション向けテスト環境

## 概要

`scripts/generate_large_vc6_fixture.py` は、`tests/fixtures/vc6_practical_project` を読み取り専用の base としてコピーし、`DeviceControl` project の source entry を数千から数万件へ拡張します。

生成物はリポジトリ外の性能 fixture root に置かれます。既存の実用 fixture と本番ソースは変更しません。

既定の解析対象は次のままです。

- workspace: `Product.dsw`
- project: `DeviceControl`
- configuration: `DeviceControl - Win32 Debug`
- source: `src/device_control.c`
- function: `DeviceControl_Update`

## 生成規模

参考にした `vscodeTree` の大規模 fixture と同じ段階を利用できます。

| source entry 総数 | 用途 |
|---:|---|
| 7,000 | 最初の大規模 smoke、日常的な比較 |
| 16,000 | 中間規模の時間・メモリ傾向確認 |
| 31,000 | 最大規模の手動 stress 確認 |

件数は `DeviceControl.dsp` に登録される C/C++ source entry の総数です。base に含まれる source も総数へ含みます。

## 前提

リポジトリルートから PowerShell で実行します。

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$perfRoot = Join-Path $env:TEMP "unitTestRunner_perf_samples"
```

`--root` を省略する場合は、環境変数 `UNIT_TEST_RUNNER_PERF_ROOT`、未設定なら OS の一時ディレクトリ配下 `unitTestRunner_perf_samples` を使います。

## 7,000 entry を生成する

```powershell
py .\scripts\generate_large_vc6_fixture.py `
  --root $perfRoot `
  --entries 7000
```

出力先は次です。

```text
<perfRoot>/unit-test-runner-large-7000
```

別の出力名を使う場合も、`--output` は `--root` 配下かつ `unit-test-runner-large-` prefix が必要です。

```powershell
py .\scripts\generate_large_vc6_fixture.py `
  --root $perfRoot `
  --output (Join-Path $perfRoot "unit-test-runner-large-custom") `
  --entries 12000
```

## 3段階をまとめて生成する

値を省略した `--tiers` は 7,000 / 16,000 / 31,000 を生成します。

```powershell
py .\scripts\generate_large_vc6_fixture.py `
  --root $perfRoot `
  --tiers
```

明示的な段階も指定できます。

```powershell
py .\scripts\generate_large_vc6_fixture.py `
  --root $perfRoot `
  --tiers 1000,5000,10000
```

`--tiers` は `--entries` または `--output` と同時に指定できません。

## 生成物

各出力ディレクトリには次が含まれます。

- base からコピーした `Product.dsw`
- base からコピーした project、source、header
- `src/generated/large_module_XXXXX.c`
- 生成 source を追加した `DeviceControl/DeviceControl.dsp`
- 件数と対象情報を記録した `manifest.json`

生成 C は C90 形式で、ファイルごとの関数、隣接関数呼び出し、分岐、外部 global `g_system_tick` への access を持ちます。

## CLI smoke

7,000 entry の fixture でプロジェクト発見から build probe dry-run まで確認します。

```powershell
$fixture = Join-Path $perfRoot "unit-test-runner-large-7000"
$out = Join-Path $env:TEMP "unitTestRunner-large-smoke\DeviceControl_Update"
$projects = Join-Path $env:TEMP "unitTestRunner-large-projects.json"

py -m unit_test_runner discover-projects `
  --workspace $fixture `
  --dsw "$fixture\Product.dsw" `
  --out $projects

py -m unit_test_runner map-source `
  --workspace $fixture `
  --dsw "$fixture\Product.dsw" `
  --source src\device_control.c

py -m unit_test_runner analyze-function `
  --workspace $fixture `
  --dsw "$fixture\Product.dsw" `
  --source src\device_control.c `
  --function DeviceControl_Update `
  --configuration "DeviceControl - Win32 Debug" `
  --project DeviceControl `
  --out $out

py -m unit_test_runner build-probe `
  --dossier "$out\reports\function_dossier.json" `
  --dry-run
```

生成器は JSON summary を標準出力へ出します。各 fixture の詳細は `<fixture>/manifest.json` で確認できます。

## 安全性

再生成時は対象出力ディレクトリをいったん削除します。削除は次の条件をすべて満たす場合だけ実行します。

- 出力先が選択した性能 fixture root の配下である
- 出力先が `unitTestRunner` リポジトリの外側である
- basename が `unit-test-runner-large-` で始まる
- 性能 fixture root 自体ではない
- base と output が同一または親子関係ではない

条件に合わないパスでは処理を中止します。リポジトリ内を `--root` または `--output` に指定した場合も拒否します。

## エンコーディング

DSP は UTF-8 BOM、UTF-8、CP932、Shift-JIS を読み取り、検出したエンコーディングで書き戻します。base 内のその他のファイルはコピーされ、内容を書き換えません。生成 C と `manifest.json` は UTF-8 です。

## 単体テスト

通常 CI では大規模 tier を生成せず、小さな一時 fixture で生成器の契約だけを確認します。

```powershell
py -m unittest tests.test_large_vc6_fixture_generator -v
```

## 環境変数

| 変数 | 用途 |
|---|---|
| `UNIT_TEST_RUNNER_PERF_ROOT` | `--root` の既定値 |
| `UNIT_TEST_RUNNER_LARGE_ENTRIES` | `--entries` 未指定時の既定値。未設定時は 7,000 |
