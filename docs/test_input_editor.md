# TestSpec入力とreview

v0.1のcanonical入力は `reports/test_spec.json` です。VS Code拡張は独自のTestSpec modelや保存authorityを持ちません。

## 通常review

Workflowの `TestSpecをレビュー` でcanonical JSONを開き、`approved` または `changes_requested` を記録します。review_recordはartifact kind、artifact SHA、decision、reviewer、時刻、commentだけを保持します。TestSpec bytesが変わると旧approvalは無効です。

## 未解決入力の反映

入力候補を確認します。

```powershell
py -m unit_test_runner --json get-test-input-form --workspace $out
```

派生viewは `$out\reports\test_input_form.json` に保存されます。これは
canonical artifactではなく、変更requestを作るための現在revision付きviewです。

変更requestをJSON fileに保存し、current revisionを指定して反映します。

```powershell
py -m unit_test_runner --json apply-test-input-form `
  --workspace $out `
  --input .\changes.json `
  --expected-revision 1
```

revisionが変わっていればnonzeroで拒否されます。Markdown/CSV view、fileのopen/save、VS Code内の一時stateはcanonical TestSpecを変更しません。

## review後のgate

未解決項目0、build-probe成功、現在のTestSpec SHAに対するapprovalが揃った場合だけ実runできます。review UIは通常のartifact reviewであり、runtime protocolではありません。
