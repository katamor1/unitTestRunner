# unitTestRunner v0.1 詳細設計

## 1. Artifact envelope

```json
{
  "schema_version": "1.0.0",
  "artifact_kind": "test_spec",
  "subject": {
    "source_path": "src/control.c",
    "source_sha256": "<64 lowercase hex>",
    "function": "Control_Update",
    "project": "Control",
    "configuration": "Control - Win32 Debug"
  },
  "data": {}
}
```

rootとsubjectはclosedです。旧version、extra property、wrong kind、subject/data不一致は拒否します。旧workspaceはmigrationせずregeneration errorにします。

canonical paths:

- `reports/function_dossier.json`
- `reports/test_spec.json`
- `reports/review_record.json`
- `reports/build_probe_report.json`
- `reports/reanalysis_report.json`
- `runs/<run_id>/test_run_report.json`
- user-selected `suite_manifest.json`
- `reports/suite_run_report.json`

writeはtemporary file、flush、atomic replaceで行います。run IDはpath componentを含められず、既存runを上書きしません。hash chainやlatest pointerは作りません。

## 2. CLI boundary

formal commandは18個です。parserにaliasを置きません。JSON success/failureは同じ5-field envelopeを使い、artifactはpathと再読SHA-256を返します。`passed/planned`だけがexit 0で、他outcomeはnonzeroです。

## 3. Target selection

DSWでproject候補を列挙し、DSPからfull configurationとsource membershipを求めます。project/config/sourceが一意でない場合は候補をdiagnosticへ返し、outputを作りません。build settingはproject base、configuration、source-specific ADD/SUBTRACTの順に適用します。

pathはlexical normalizationとresolved containmentを確認し、output rootがsource root内またはreparse/symlinkで逸脱する場合は拒否します。

## 4. C facts

選択defineで確実にinactiveなpreprocessor領域だけ除外し、UNKNOWN条件は診断と未解決項目に残します。target/dependency/globalは共通の小さな型分類を使い、曖昧型を `int` にしません。

正式対応するdependency modeは `real`、`stub`、`review_required` です。function pointer、macro、member call、表現不能値はreview-requiredです。

## 5. Harness/build/run

実行可能harnessにplaceholderや常真oracleを残しません。未解決があればreview-only scaffoldを生成し、実runをblockedにします。生成CはC90、CP932、CRLFです。

build-probeは外部workspaceだけを変更します。planは未承認でも可能です。実run前に次を確認します。

1. TestSpec未解決項目0
2. build-probe成功
3. current TestSpec SHAに対するapproved review_record
4. selectorがknown/enabled/nonempty

run reportはrequested、started、completed、not-run case IDを保持します。

## 6. Reanalysis

function/case identityはsource相対path、function、coverage anchor、case kindから決定します。reanalysisはcandidate TestSpecとreportだけを書きます。同一case IDの人間入力をコピーし、conflictをfield単位で列挙します。

applyはexpected revision一致、candidate SHA一致、conflict 0の場合だけcanonical TestSpecをatomic replaceします。immutable base storeやautomatic three-way mergeはありません。

## 7. Suite

manifest entryはrelative workspace、entry ID、enabled、tags、function subject、TestSpec SHA、harness SHAを持ちます。traversal、duplicate、unknown、empty selectionは拒否します。register/update/removeはrevision guard付きatomic writeです。

run前にsource/TestSpec/harnessの3 SHAを確認し、staleならspawn前にblockedです。各entryは単体run gateを再利用し、選択entryが1件でもnon-passedならsuite CLIはnonzeroです。

## 8. VS Code adapter

active documentのworkspace folderとresource-scoped settingだけを使用します。extension全体でsingle-flightを共有し、2件目はspawn前に拒否します。timeoutはprocess tree cleanup後に返します。

workflow stateはvalidated CLI successまたは明示確認だけで進みます。review UIはordinary artifact reviewです。suite UIはregister、enable/disable、filter、explicit selection、run、latest reportだけを提供します。
