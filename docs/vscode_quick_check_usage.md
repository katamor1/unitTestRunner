# VS Code Quick Check 利用メモ

作成日: 2026-07-08  
対象: `unit-test-runner-vscode` Quick Check / Full Gate

## 目的

Quick Check は、機能設計や実装中に関数単位の解析結果を少ない手数で反復確認するための入口である。

現行 Workflow パネルのフルチェックは、レビュー前の正式確認、dossier確定、レビュー項目確認、build/test/evidence確認に使う。Quick Check はその前段で、普段使いの軽い確認ループとして使う。

## 使い分け

| 場面 | 使う操作 | 生成物 |
|---|---|---|
| 実装中に関数の副作用・分岐・テスト観点を確認したい | `UnitTestRunner: Quick Check Current Function` | `_quick/.../reports/quick_summary.md` |
| 関数名を明示して軽く確認したい | `UnitTestRunner: Quick Check Selected Function` | `_quick/.../reports/quick_summary.md` |
| レビュー前に正式成果物へ進めたい | `UnitTestRunner: Full Gate for Current Function` | 通常workspaceの `function_dossier.md` / review workflow |

## Quick Check の挙動

Quick Check は `analyze-function` を軽量 profile で呼び出す。

- `--finalize-dossier` は付けない
- 既定 profile は `design`
- 出力先は既定で `<outputRoot>/_quick/<source>_<function>_<hash>/`
- `quick_summary.md` を自動で開く
- build/test 実行は既定では行わない

## Quick Check profile

| profile | CLI phase | 用途 |
|---|---|---|
| `design` | `--phase design` | 解析結果とテスト設計候補を確認する通常モード |
| `harness` | `--phase harness` | ハーネス雛形生成まで確認する |
| `build-dry-run` | `--phase build` | build workspace / build probe dry-run まで確認する |

## 設定例

```json
{
  "unitTestRunner.quickProfile": "design",
  "unitTestRunner.quickOutputRoot": "",
  "unitTestRunner.quickAutoOpenSummary": true
}
```

`quickOutputRoot` が空の場合は `outputRoot/_quick` を使う。`quickOutputRoot` を指定する場合も、本番ソースツリー外に置く。

## quick_summary.md の内容

`quick_summary.md` には以下を短く出す。

- 関数名、ソース、profile、workspace
- グローバル read/write 数
- 外部呼び出し候補数
- 分岐候補数
- branch / condition カバレッジ観点数
- スタブ候補数
- diagnostics 数
- `function_dossier.md` / `test_case_design.md` / `harness_skeleton_report.md` / `build_probe_report.md` へのパス


## 呼び出し先の real / stub 選択

Quick Checkでは `reports/dependency_policy.md` と `reports/dependency_policy.json` も生成する。呼び出し先ごとの既定方針は `real` / `stub` / `auto` で、`auto` は共有グローバル、ポインタ引数、副作用、実装の所在などから状態連動性を判定する。

- 同じ機能を可読性のために分割した内部関数など、状態連動が強い依存は `real` 候補
- 外部I/Oや戻り値だけを制御したい機能境界は `stub` 候補
- 根拠が不足・競合する場合は `review_required`

関係ごとの既定値を変更する場合は `dependency_policy.json` の `configured_mode` を編集し、Quick Checkまたは関数解析を再実行して解決結果を更新する。特定ケースだけ切り替える場合は `test_case_design.json` の `dependency_overrides` に `inherit` / `real` / `stub` を指定してから、ハーネスとbuild workspaceを再生成する。

生成スタブは製品関数と同名にせず、`Utr_Stub_<callee>_Invoke` を使う。抽出済み対象Cの安全に検証できた直接呼び出しだけが `Utr_Dep_<callee>` へ書き換えられる。マクロ、関数ポインタ、メンバ経由呼び出し、関数アドレス利用は自動変換せず、詳細レポートでレビューする。

外部グローバルの結合先はworkspace単位で固定される。`real` は製品定義を使用し、`fixture` は宣言互換のテスト実体を1つだけ生成する。ケース単位では値だけを設定し、対象関数と実呼び出し先が同じオブジェクトを共有できるようにする。

## 推奨運用

1. 実装中は Quick Check を反復実行する。
2. `quick_summary.md` と必要な詳細レポートだけを見る。
3. レビューへ出す前に `Full Gate for Current Function` を実行する。
4. Full Gate 後は Workflow パネルの詳細表示で review checklist、unresolved items、next actions、build/test/evidence を確認する。
