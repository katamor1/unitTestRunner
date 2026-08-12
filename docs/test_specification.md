# unitTestRunner v0.1 テスト仕様

## 固定gate

- public schema exact 8、全ref解決、extra/malformed拒否
- CLI command exact 18、outcome exact 7、exit整合、artifact SHA再読
- canonical dossier/TestSpec/review/run persistence
- VC6 target/config/source selection、CP932/Shift-JIS、path containment
- representative normal/input-error/timeout-cleanup
- Control_Updateとpractical fixtureのreviewed path
- reanalysis candidate/apply guards
- explicit case/tag/all selector
- suite revision/stale/aggregation
- VS Code resource scope、single-flight、timeout cleanup、accessible controls
- source CLI / packaged EXE / bundled VSIX / installed VSIX smoke

## 実行budget

各Taskのfocused acceptanceは最大20件、新規または大幅変更testは最大8件です。中間Taskでは変更subsystemだけを実行します。serial Python full suiteとVS Code full suiteはbaselineとfinal cutoverで各1回です。

## Representative checks

1. `tests.test_v01_public_contract`
2. `tests.test_v01_workspace_persistence`
3. `tests.test_cli_entry_point_contract`
4. `tests.test_fixture_cli_smoke`
5. `tests.test_process_control`
6. `tests.test_c_source_reading`
7. `tests.test_vc6_dsw_parser`
8. `tests.test_vc6_dsp_parser`
9. `tests.test_harness_skeleton_generation`
10. `tests.test_practical_vc6_fixture`
11. `tests.test_reanalysis_models`
12. `tests.test_suite_manager`
13. `tests.test_distribution_build_script`
14. `tests.test_vscode_adapter`

VS Code側はadapter、CLI envelope、process tree、workflow panel、settings persistence、suite UIを固定対象にします。

## Final commands

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m compileall -q src tests

$modules = Get-ChildItem .\tests -Filter 'test_*.py' -File |
  Sort-Object Name |
  ForEach-Object { 'tests.' + $_.BaseName }
$failed = @()
foreach ($module in $modules) {
  py -m unittest $module -v
  if ($LASTEXITCODE -ne 0) { $failed += $module }
}
if ($failed.Count) { throw ('failed: ' + ($failed -join ', ')) }

Push-Location vscode\extension
npm.cmd test
Pop-Location

git diff --check
```

## Final smoke

- S1: source CLIでVC6 fixtureからdossier/TestSpec/build-probe/run
- S2: packaged EXEとVSIX build、release/bundled/VSIX entry hash一致
- S3: isolated installed VSIXでanalyze、review、build/run confirmation、reanalysis、suite

完了条件は固定property全PASS、Task起因regression 0、in-scope blocker 0です。open-endedなfinding countは使用しません。
