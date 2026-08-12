# Windows EXE + VSIX one-shot build

リポジトリルートから実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_distribution.ps1
```

scriptはPyInstaller build、packaged EXEによるharness解析、`finalize-dossier`、current TestSpecへの`review-set`、build/run plan、VS Code tests、bundled EXE copy、VSIX packageとZIP entry確認を行います。

事前にserial Python suiteと `git diff --check` をPASSさせます。VSIXの実機確認は [配布用バイナリ作成手順](distribution_binary_build_guide.md) に従います。
