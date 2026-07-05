# VC6 Practical Project Fixture

This fixture is a compact VC6/C90-style project for analyzer regression tests and manual smoke checks.
It intentionally keeps source files small while covering the code shapes that matter for function-level
unit test dossier generation.

## Target

Primary target function:

```text
src/device_control.c
DeviceControl_Update
```

Call tree shape:

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

## Analysis Cases

- file-scope static variables: `s_state`, `s_history`, `s_history_pos`, `s_fault_hook`
- extern globals: `g_system_tick`, `g_active_device`, `g_device_table`, `g_calibration`
- struct members and arrays: `input->raw_samples[i]`, `out->channels[...]`, `s_state.filtered`,
  `g_device_table[...].status`
- function pointers: callback parameter and registered fault hook
- object-like macros: `DEVICE_HISTORY_SIZE`, `ACTIVE_DEVICE`
- function-like macros: `RAW_SAMPLE(input, i)`, `LIMIT_DUTY(value)`
- VC6 project context: Debug/Release configurations, `/D`, `/I`, `/FI"config_alias.h"`, `/Yu"stdafx.h"`
- multiple source membership: `src/device_control.c` appears in `DeviceControl.dsp` and `FactoryTest.dsp`

## Manual Smoke

Run from the repository root:

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
