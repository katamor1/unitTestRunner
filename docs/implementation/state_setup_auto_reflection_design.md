# state_setups 自動反映設計

## 目的

`reports/test_case_design.json` の `test_cases[].state_setups[]` に記録したケースごとのグローバル変数・状態の前提値を、生成テストソースへ自動反映する。

現状、`state_setups` はテストケース設計の正本として存在するが、`generated/tests/test_<Function>.c` の各テスト関数には自動出力されていない。そのため、ユーザーが `test_case_design.json` に前提値を記録しても、実行時の初期化コードには反映されない。

## 対象範囲

対象は以下の 2 種類に分ける。

1. **直接代入できる状態**
   - 例: `g_count = 0;`
   - `scope` が `file` / `extern` / `global` などで、生成テストから参照可能なもの。
2. **fixture オブジェクトが必要な状態**
   - 例: `g_com = &fixture_g_com; fixture_g_com.ptr = &fixture_gbl1; fixture_gbl1.test = 0;`
   - ポインタ、構造体、ネストしたメンバ、テスト用ストレージが必要なもの。

`file_static` など直接参照できないものは、原則として自動代入せず、wrapper / 初期化 API / ビルド時 expose 方針のレビュー項目として扱う。

## 入力スキーマ

既存の `state_setups` フィールドを正本とする。既存フィールドは維持する。

```json
{
  "variable_name": "g_count",
  "scope": "file",
  "value_expression": "0",
  "setup_method_hint": "direct_assignment",
  "source_candidate_id": null,
  "review_required": false,
  "confidence": "high"
}
```

fixture が必要なケースでは、後方互換を壊さないため、追加フィールドを任意フィールドとして許可する。

```json
{
  "variable_name": "g_com",
  "scope": "extern",
  "value_expression": "&fixture_g_com",
  "setup_method_hint": "fixture_pointer",
  "source_candidate_id": null,
  "review_required": true,
  "confidence": "medium",
  "fixture_declarations": [
    "static gbl1 fixture_gbl1",
    "static gbl_com fixture_g_com"
  ],
  "setup_statements": [
    "fixture_g_com.ptr = &fixture_gbl1",
    "fixture_gbl1.test = 0"
  ]
}
```

### 追加フィールド

| フィールド | 用途 |
|---|---|
| `target_expression` | `variable_name` だけでは表せない代入先。例: `g_com->ptr->test` |
| `fixture_declarations` | C90 のブロック先頭に出す fixture 用宣言。セミコロンはあってもなくてもよい |
| `setup_statements` | 代入前に実行する補助セットアップ文。セミコロンはあってもなくてもよい |
| `teardown_statements` | 将来拡張用。現段階では未使用 |

## 生成ルール

### 1. 宣言の生成

`_render_test_function()` で、通常のローカル変数宣言に加えて、各 `state_setup.fixture_declarations[]` を関数先頭の宣言部に出す。

C90 互換のため、宣言は必ず実行文より前に出す。

```c
void Test_TC_Shared_001(void)
{
    int actual_return;
    static gbl1 fixture_gbl1;
    static gbl_com fixture_g_com;

    ...
}
```

### 2. 直接代入の生成

`setup_method_hint == "direct_assignment"` の場合は、以下を生成する。

```c
<target_expression または variable_name> = <value_expression>;
```

例:

```json
{
  "variable_name": "g_count",
  "scope": "file",
  "value_expression": "0",
  "setup_method_hint": "direct_assignment"
}
```

生成:

```c
g_count = 0;
```

### 3. fixture pointer の生成

`setup_method_hint == "fixture_pointer"` の場合は、`fixture_declarations`、`setup_statements`、最後に `variable_name = value_expression;` を出す。

例:

```json
{
  "variable_name": "g_com",
  "scope": "extern",
  "value_expression": "&fixture_g_com",
  "setup_method_hint": "fixture_pointer",
  "fixture_declarations": [
    "static gbl1 fixture_gbl1",
    "static gbl_com fixture_g_com"
  ],
  "setup_statements": [
    "fixture_g_com.ptr = &fixture_gbl1",
    "fixture_gbl1.test = 0"
  ]
}
```

生成:

```c
static gbl1 fixture_gbl1;
static gbl_com fixture_g_com;

fixture_g_com.ptr = &fixture_gbl1;
fixture_gbl1.test = 0;
g_com = &fixture_g_com;
```

### 4. custom statements の生成

`setup_method_hint == "custom_statements"` の場合は、`setup_statements` のみを出す。これは reviewer が確認した C 文をそのまま出す用途に限定する。

### 5. not_directly_accessible の扱い

`setup_method_hint == "not_directly_accessible"` の場合は代入コードを出さない。代わりにコメントと warning を出す。

```c
/* REVIEW REQUIRED: g_state is not directly accessible. Add wrapper or initialization path. */
```

## 生成位置

各テスト関数内の順序は以下にする。

1. ローカル変数宣言
2. fixture 宣言
3. stub reset
4. state setup
5. stub return setup
6. input assignment
7. target invocation
8. assertions

この順にすることで、対象関数呼び出し前にグローバル状態と stub 状態が必ず確定する。

## include / extern 宣言

state setup で参照するグローバル変数は、生成テストソースから見えている必要がある。

1. `global_access.file_scope_declarations` に型情報がある場合は、`extern <type> <name>;` を生成する。
2. ヘッダに `extern` 宣言がある場合は、対象ヘッダを include するか、既存の include 経路で型定義が見えるようにする。
3. 型が分からない場合は自動代入せず、review warning にする。

`generated/stubs/utr_extern_globals.c` はリンク用のプレースホルダ定義であり、ケースごとの値を決める場所ではない。ケースごとの値は各テスト関数の state setup で代入する。

## 安全性ルール

代入先は C の lvalue として安全な文字列だけ許可する。

許可例:

- `g_count`
- `g_com`
- `g_com->ptr->test`
- `state.value`
- `buffer[0]`

拒否例:

- `foo();`
- `a = b`
- `x, y`
- `#define X 1`

拒否した場合は C コードを出さず、`state_setup_not_auto_reflected` warning とレビュー項目を出す。

## 具体例: Shared

`Shared` のケースで、`g_count` と `g_com` を前提値として設定する場合:

```json
{
  "test_case_id": "TC_Shared_001",
  "state_setups": [
    {
      "variable_name": "g_count",
      "scope": "file",
      "value_expression": "0",
      "setup_method_hint": "direct_assignment",
      "source_candidate_id": null,
      "review_required": false,
      "confidence": "high"
    },
    {
      "variable_name": "g_com",
      "scope": "extern",
      "value_expression": "&fixture_g_com",
      "setup_method_hint": "fixture_pointer",
      "source_candidate_id": null,
      "review_required": true,
      "confidence": "medium",
      "fixture_declarations": [
        "static gbl1 fixture_gbl1",
        "static gbl_com fixture_g_com"
      ],
      "setup_statements": [
        "fixture_g_com.ptr = &fixture_gbl1",
        "fixture_gbl1.test = 0"
      ]
    }
  ]
}
```

生成テスト関数:

```c
void Test_TC_Shared_001(void)
{
    int actual_return;
    static gbl1 fixture_gbl1;
    static gbl_com fixture_g_com;

    fixture_g_com.ptr = &fixture_gbl1;
    fixture_gbl1.test = 0;
    g_count = 0;
    g_com = &fixture_g_com;

    actual_return = Target_Invoke_Shared();

    UTR_ASSERT_EQ_INT(TBD_EXPECTED_RETURN_INT, actual_return);
}
```

## 実装タスク

1. `harness_skeleton_generator._render_test_function()` に state setup 反映を追加する。
2. `fixture_declarations` / `setup_statements` / `target_expression` を dict 入力として許可する。
3. lvalue / expression の安全チェック関数を追加する。
4. `not_directly_accessible` や不正 lvalue の warning / unresolved placeholder を出す。
5. `test_case_design.md` に追加フィールドが見えるようにする。
6. `next_actions.md` から `test_case_design.md` と `generated/tests/test_<Function>.c` へリンクする。
7. fixture pointer と direct assignment のユニットテストを追加する。

## 非対象

- 本物の製品初期化処理を推定して自動生成すること。
- `file_static` 変数を無理に外部公開すること。
- 任意 C コードを無検証で挿入すること。
