# 依存関係ポリシーと衝突回避スタブ設計

作成日: 2026-07-11  
対象: 関数単位テストの呼び出し先関数・外部グローバル結合

## 目的

生成スタブが製品ヘッダ内の実在プロトタイプ宣言や外部参照宣言と干渉する問題を解消する。同時に、可読性のために分割された同一機能内の内部関数は実装を通し、機能境界の依存はスタブ化できるようにする。

## 決定事項

### 呼び出し関係ごとのモード

テスト対象関数と呼び出し先の関係ごとに次を指定する。

- `real`: 実関数を呼ぶ
- `stub`: 生成スタブを呼ぶ
- `auto`: 状態連動性を解析して `real` / `stub` / `review_required` に解決する

既定値は `dependency_policy.json` に保存する。テストケース単位の上書きは `test_case_design.json` の `dependency_overrides` に保存し、値は `inherit` / `real` / `stub` とする。

### auto判定

次の証拠を使う。

- 呼び出し元と呼び出し先が同じグローバルを読み書きする
- ポインタ・構造体・配列引数を介して状態が連動する
- 呼び出し先の副作用が対象関数の後続分岐・戻り値へ影響する
- 同一ソース・同一プロジェクトに実装がある
- 実装ソースを安全にビルド対象へ追加できる
- 共有状態がなく、戻り値または呼び出し回数だけを制御すればよい

状態連動性が強く実装が一意なら `real`、機能境界が明確なら `stub`、証拠が拮抗・不足する場合は `review_required` とする。

### シグネチャの正本

次の優先順で解決する。

1. 呼び出し元から到達するヘッダのプロトタイプ
2. 実装Cの関数定義
3. DSP配下の宣言候補
4. 安全な単純型に限る呼び出し式推定

結果は `exact` / `compatible_inferred` / `review_required` とする。戻り値型、引数順、ポインタ階層、qualifier、calling convention、可変引数を比較し、互換でない複数宣言は自動採用しない。

### スタブ衝突回避

実関数名と同名の生成関数を作らない。

- 実関数: `Helper_Update`
- ディスパッチャ: `Utr_Dep_Helper_Update`
- スタブ実体: `Utr_Stub_Helper_Update_Invoke`
- 制御API: `Utr_Stub_Helper_Update_Reset` / `SetReturn` / `GetCallCount`

テストworkspaceへ抽出した対象Cの直接呼び出しだけを `Utr_Dep_<callee>` へ書き換える。本番ソースは変更しない。

マクロ呼び出し、関数ポインタ呼び出し、メンバ経由呼び出し、関数アドレス取得は自動書き換えせず `review_required` とする。

### ケース単位切り替え

1つのテストバイナリ内で、ケース開始時に依存モードを設定する。

1. 全依存をpolicyの既定解決結果へリセット
2. `dependency_overrides` を適用
3. 対象関数を実行

### 外部グローバル

結合先はworkspace単位で固定する。

- `real`: 一意な製品定義元Cをリンクし、生成側では定義しない
- `fixture`: 正式な宣言ヘッダをincludeした生成Cでテスト用実体を1つ定義する
- `auto`: 一意な実定義があれば `real`、宣言だけなら `fixture`、複数定義・型不一致・条件依存なら `review_required`

ケース単位では同じ実体の初期値・期待値だけを変更する。対象関数とreal依存関数でグローバルのアドレス同一性を維持する。

## 成果物

- `reports/dependency_policy.json`
- `reports/dependency_policy.md`
- `generated/dependencies/utr_dependency_dispatch.h`
- `generated/dependencies/utr_dependency_dispatch.c`
- collision-safeな `generated/stubs/stub_<callee>.h/.c`
- `harness_skeleton_report.json` 内のdependency dispatch情報

## 互換性

- 既存の `stub_setups` は維持する
- `dependency_overrides` がない既存test designは `inherit` として扱う
- policyがない明示的な `generate-harness-skeleton` 呼び出しでは、現行互換のauto policyを内部生成する
- C90 / VC6互換を維持する

## 安全条件

- `review_required` の依存は勝手に書き換えない
- exactまたは安全なcompatible signatureがない依存のdispatcherを生成しない
- 実定義がある外部変数をfixtureとして二重定義しない
- 本番ソース、製品ヘッダ、製品DSPを変更しない
