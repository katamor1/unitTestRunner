# 検証機向けビルドツールチェーン

実機環境では VC6 を使い、VC6 が入っていない検証機ではホスト側の C コンパイラで生成済みワークスペースをビルドできます。

## 使い方

通常どおり関数解析とハーネス生成を行います。

```powershell
py -m unit_test_runner analyze-function `
  --workspace C:\work\product `
  --dsw C:\work\product\Product.dsw `
  --source src/control.c `
  --function Control_Update `
  --configuration "Win32 Debug" `
  --project Control `
  --phase execution `
  --out D:\unit-test-output\Control_Update
```

VC6 が無い検証機では、`build-probe` に検証用ツールチェーンを指定します。

```powershell
py -m unit_test_runner --json build-probe `
  --workspace D:\unit-test-output\Control_Update `
  --run `
  --toolchain verification `
  --cc gcc
```

Visual Studio Build Tools / Visual Studio Community の `vcvars32.bat` で `cl` を使う場合は、`--toolchain verification` と `--vcvars` を併用します。

```powershell
py -m unit_test_runner --json build-probe `
  --workspace D:\unit-test-output\Control_Update `
  --run `
  --toolchain verification `
  --vcvars "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"
```

`--cc` を省略した場合は、`UNIT_TEST_RUNNER_CC`、`CC`、`cl`、`gcc`、`clang`、`clang-cl`、`cc` の順で利用可能なコンパイラを探します。`--vcvars` を指定した場合は、そのバッチを呼び出したうえで `cl` を使います。

ビルドに成功すると、従来どおり `reports/build_probe_report.json` の状態が `succeeded` になり、`bin/utr_probe.exe` が生成されます。その後のテスト実行は通常と同じです。

```powershell
py -m unit_test_runner --json run-tests `
  --workspace D:\unit-test-output\Control_Update `
  --run
```

## 実機環境の扱い

既定値は `--toolchain vc6` です。実機環境では従来どおり `build/build.bat` と VC6/nmake を使います。

```powershell
py -m unit_test_runner --json build-probe `
  --workspace D:\unit-test-output\Control_Update `
  --run `
  --vcvars "C:\Program Files\Microsoft Visual Studio\VC98\Bin\VCVARS32.BAT"
```

## 注意

検証用ツールチェーンは、VC6 互換性そのものを保証するものではありません。目的は、VC6 が無い検証機でも生成済みハーネス、スタブ、ランナーのビルドとテスト実行フロー全体を先に確認できるようにすることです。最終確認は実機環境の VC6 ビルドで行ってください。
