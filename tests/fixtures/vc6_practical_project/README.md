# VC6実用プロジェクトfixture

このfixtureは、解析回帰テストと手動スモーク確認に使う小さなVC6/C90風プロジェクトです。ソースファイルは小さく保ちながら、関数単位dossier生成で重要になるコード形状を含めています。

## 対象

主対象関数は以下です。

```text
src/device_control.c
DeviceControl_Update
```

呼び出し木の概形は以下です。

```text
DeviceControl_RunScheduler
  -> DeviceControl_Update
       -> ValidateInput
       -> NormalizeSample
       -> ComputeDuty
       -> ApplyOutput
       -> PushHistory
       -> Platform_ReadAdc
       -> Platform_WritePwm
       -> Audit_Record
       -> callback
```

## 解析ケース

- file-scope static変数: `s_state`, `s_history`, `s_history_pos`, `s_fault_hook`
- externグローバル: `g_system_tick`, `g_active_device`, `g_device_table`, `g_calibration`
- 構造体メンバと配列: `input->raw_samples[i]`, `out->channels[...]`, `s_state.filtered`, `g_device_table[...].status`
- 関数ポインタ: callback引数と登録済みfault hook
- object-like macro: `DEVICE_HISTORY_SIZE`, `ACTIVE_DEVICE`
- function-like macro: `RAW_SAMPLE(input, i)`, `LIMIT_DUTY(value)`
- VC6プロジェクト文脈: Debug/Release構成、`/D`, `/I`, `/FI"config_alias.h"`, `/Yu"stdafx.h"`
- 複数プロジェクト所属: `src/device_control.c` は `DeviceControl.dsp` と `FactoryTest.dsp` に含まれる

## 手動スモーク

リポジトリルートから実行します。

```powershell
$env:PYTHONPATH = "$PWD\src"
$fixture = "$PWD\tests\fixtures\vc6_practical_project"
$out = "$env:TEMP\unitTestRunner-practical\DeviceControl_Update"

py -m unit_test_runner discover-projects `
  --workspace $fixture `
  --dsw "$fixture\Product.dsw" `
  --out "$env:TEMP\unitTestRunner-practical-projects.json"

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

レビュー用dossierまで生成する場合は、`analyze-function` に `--finalize-dossier` を追加します。

```powershell
py -m unit_test_runner --json analyze-function `
  --workspace $fixture `
  --dsw "$fixture\Product.dsw" `
  --source src\device_control.c `
  --function DeviceControl_Update `
  --configuration "DeviceControl - Win32 Debug" `
  --project DeviceControl `
  --out $out `
  --finalize-dossier
```
