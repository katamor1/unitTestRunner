# テスト入力編集GUI 設計書

- 日付: 2026-07-19
- 状態: ユーザー承認済み
- 対象: `unitTestRunner` の VS Code 拡張と Python CLI core
- 実装ブランチ: `design/test-input-editor-gui`

## 1. 背景

`unitTestRunner` が生成するテスト仕様には、解析だけでは確定できない入力値、事前状態、スタブ戻り値、期待値などが残る。代表例は `TBD_VALID_VALUE` のようなプレースホルダーである。現在は JSON、Markdown、CSV を開いて人が確認できるが、値の入力、確認状態の更新、候補ケースの実行対象化を一貫して行える画面がない。

この機能では、現在の関数に対応する canonical `reports/test_spec.json` を対象に、レビューが必要な項目を専用の VS Code タブへ集約する。利用者は候補値を参考にしながら C 式を直接入力し、項目単位で「確認済み」を明示し、入力した項目だけをまとめて保存できる。

VS Code 拡張は表示、下書き、CLI 呼び出しに限定する。契約検証、revision 競合検出、項目解決、保存、候補ケースの昇格は Python CLI core が担当する。

## 2. 目的

この設計の目的は次のとおり。

1. `review_required: true` の編集可能項目と未解決の実行値を、JSON を直接編集せず入力できるようにする。
2. 数値候補、列挙値、`NULL` などの補助を表示しつつ、任意の C 式を入力できるようにする。
3. 値の入力とレビュー完了判断を分離し、項目ごとの「確認済み」を明示できるようにする。
4. 入力済み項目だけの部分保存を許可する。
5. revision 競合や古い解析成果物を安全に検出し、正本を部分更新しない。
6. 未解決値が原因で候補側に置かれたケースを、実行必須項目の解決後に実行対象へ移せるようにする。
7. canonical `test_spec.json` への編集が、その後の再解析、ハーネス生成、ビルド確認へ確実に引き継がれるようにする。

## 3. 成功条件

次の状態を満たしたとき、この機能を完了とみなす。

- Workflow パネルから現在の関数の専用編集タブを手動で開ける。
- パネルに未確定件数が表示され、後工程を阻害する場合だけ強調される。
- 編集タブで入力値、事前状態、スタブ設定、期待値、レビュー継続項目をケース別に確認できる。
- 候補を選んだ後も C 式を直接編集できる。
- 「確認済み」でない具体値も部分保存できる。
- 「確認済み」なのに空欄またはプレースホルダーの項目は保存できない。
- revision 競合時は正本を変更せず、下書きを保持できる。
- 保存時に `test_spec.json` の revision が進み、Markdown と CSV の派生ビューが再生成される。
- 昇格条件を満たした候補ケースが `test_cases` に移り、canonical 仕様を入力とするハーネスへ反映される。
- 正式レビューの `review_item_ids`、レビュー判断台帳、生成元、ID、schema version は GUI から変更できない。

## 4. 対象外

初期実装では次を扱わない。

- スイート内の複数関数を一括編集する画面
- 任意の workspace を編集タブから選ぶ機能
- 完全な C90 パーサーまたはコンパイラ相当の式検証
- 自動保存
- 正式レビュー判断の記録、承認、waive
- canonical スキーマへの GUI 専用フィールド追加
- legacy `test_case_design.json` を正本として編集する機能
- VS Code 再起動後まで下書きを永続化する機能
- 解析根拠の弱い値を自動確定する機能

## 5. 主要な設計判断

- 画面は Workflow サイドパネル内へ詰め込まず、専用 Webview Panel とする。
- 編集対象は Workflow が保持する現在の関数 workspace 一つに限定する。
- タブは自動で開かない。Workflow パネルの件数付きボタンから手動で開く。
- 保存は「保存して反映」を押したときだけ行う。
- 部分保存を許可する。
- 値の入力と「確認済み」を別操作にする。
- 入力は C 式の自由入力を基本とし、根拠のある候補だけ補助表示する。
- 確実な誤りは保存不可、構文上の疑いは警告として保存可能にする。
- VS Code 拡張は `test_spec.json` を直接書き換えない。
- CLI が revision 検証、項目解決、保存、候補ケース昇格を一括して行う。
- 正式レビュー権限は既存のレビュー判断フローに残し、項目確認と混同しない。

## 6. 現行構造との関係

canonical テスト仕様は `reports/test_spec.json` であり、既存 CLI には次の基盤がある。

- `get-test-spec`: canonical 仕様の読み込み、現在の成果物コンテキスト検証、revision と SHA256 の返却
- `update-test-spec`: revision 付き差分更新、契約検証、正本保存、Markdown/CSV 再生成
- `save_test_spec_snapshot`: revision 更新と snapshot 保存
- `export_test_spec_snapshot_views`: canonical snapshot から派生ビューを出力

新機能はこれらを再利用し、GUI 用のフォームモデルとケース昇格だけを専用サービスとして追加する。フォーム入出力は canonical 仕様とは別の strict schema version `1.0` とし、unknown property を拒否する。canonical `test_spec` へ GUI 専用 field を追加しないため、canonical schema version は上げない。

また、VS Code 拡張の一部は現在も legacy alias を使うため、新機能と同時に canonical 経路へ統一する。

- ハーネス生成は `--test-case-design` ではなく `--test-spec reports/test_spec.json` を渡す。
- 再解析は `--previous-test-case-design` ではなく `--previous-test-spec reports/test_spec.json` を渡す。
- `ReportPaths` に `testSpecJson`、`testSpecMd`、`testSpecCsv` を追加する。
- legacy alias は CLI の後方互換として残すが、VS Code の通常経路では使用しない。

## 7. 全体アーキテクチャ

### 7.1 Workflow パネル

Workflow パネルへ次のアクションを追加する。

```text
未確定項目を入力（7件）
```

表示規則は次のとおり。

- canonical `test_spec.json` が存在する場合に表示する。
- 件数は CLI が返すフォーム summary の `attention_count` を使う。
- 専用タブの case 一覧には item を一件以上持つ case だけを表示する。編集可能 item を持たない意図的な追加候補は一覧へ混ぜない。
- 未解決の実行値がある場合、またはその値が後工程を止めた場合は警告色で強調する。
- 未確定件数が 0 の場合は「入力内容を確認（0件）」として控えめに表示する。編集タブを開いた場合は「現在、入力が必要な項目はありません」と表示し、canonical spec を開く補助 action だけを出す。
- ボタンを押すまで編集タブを開かない。
- 保存成功後に summary-only を再取得して表示を更新する。
- summary cache は function workspace、revision、spec SHA256 を一組として保持し、解析・再解析・仕様保存で無効化する。
- summary 取得に失敗した場合は件数なしのボタンと警告アイコンを表示し、編集タブを開いた時に詳細エラーを出す。

新しい VS Code コマンド ID は次とする。

```text
unitTestRunner.openTestInputEditor
```

### 7.2 専用編集タブ

新しい `TestInputEditorPanel` を Webview Panel として実装する。画面は次の領域で構成する。

- ヘッダー: 関数名、workspace、revision、全体進捗、再読込
- 左ペイン: テストケース一覧、未入力数、未確認数、警告数、ケース種別
- 右ペイン: 選択ケースの編集フォーム
- フッター: 未保存件数、「変更を破棄」、「保存して反映」

右ペインは項目を次のセクションへ分ける。

1. 入力値
2. 事前状態
3. スタブ設定
4. 期待値
5. 前提条件
6. 実行手順
7. 依存関係
8. その他のレビュー継続項目

Webview は表示と下書きだけを担当し、正本の JSON Pointer や配列 index を保存ロジックとして信用しない。item card は親 object に対応し、その中へ allowlist に含まれる leaf control を一つ以上配置する。

### 7.3 Python CLI core

新しいパッケージ境界を `unit_test_runner.test_input_form` とする。責務は次のように分ける。

- `models.py`: フォーム出力、変更入力、summary、warning のモデル
- `field_catalog.py`: 編集可能な collection と leaf の定義
- `field_locator.py`: 安定した項目 ID の生成と現在仕様への再解決
- `suggestions.py`: 解析成果物からの候補抽出
- `validation.py`: 必須検証、プレースホルダー判定、C 式ヒューリスティック
- `service.py`: フォーム構築、変更適用、候補ケース昇格、結果 summary
- CLI parser/commands: JSON 入出力、既存 repository API との接続

ファイル名は実装計画で既存構成に合わせて微調整できるが、責務境界は維持する。

## 8. CLI 契約

### 8.1 フォーム取得

コマンド:

```text
unit-test-runner --json get-test-input-form --workspace <function-workspace>
```

主な処理:

1. `reports/test_spec.json` を strict mode で読み込む。
2. 現在のソース、関数シグネチャ、生成元との整合を検証する。
3. `test_cases` と `additional_case_candidates` の両方を走査する。
4. 編集対象 item を安定した `item_id` 付きで返す。
5. 候補値と警告を付ける。
6. 件数 summary を返す。

出力例:

```json
{
  "schema_version": "1.0",
  "revision": 3,
  "spec_sha256": "64桁のSHA256",
  "function": {
    "name": "Control_Update"
  },
  "summary": {
    "attention_count": 9,
    "unresolved_count": 4,
    "unconfirmed_count": 7,
    "execution_blocking_count": 4,
    "warning_count": 1
  },
  "cases": [
    {
      "case_id": "TC_Control_Update_001",
      "location": "additional_case_candidates",
      "promotion_eligible": true,
      "items": [
        {
          "item_id": "opaque-item-id",
          "subject_fingerprint": "64桁のSHA256",
          "kind": "input_assignment",
          "label": "引数 mode",
          "confirmed": false,
          "blocking": true,
          "editable": true,
          "controls": [
            {
              "name": "value_expression",
              "control_kind": "c_expression",
              "required_for_confirmation": true,
              "value": "TBD_VALID_VALUE",
              "suggestions": [
                {
                  "value": "MODE_AUTO",
                  "label": "MODE_AUTO",
                  "source": "boundary_candidate",
                  "confidence": "high"
                }
              ]
            }
          ],
          "warnings": []
        }
      ]
    }
  ]
}
```

`item_id` は Webview にとって不透明な文字列とし、JSON Pointer として解釈させない。

summary の件数は leaf 数ではなく、重複を除いた item 数とする。

- `unresolved_count`: required control が未解決の item
- `unconfirmed_count`: `review_required: true` の item
- `execution_blocking_count`: `blocking: true` かつ未解決の item。実行中ケースでは生成・実行を、候補ケースでは昇格を阻害する
- `warning_count`: warning が一件以上ある item
- `attention_count`: 上記四集合の和集合

Workflow パネルは頻繁に再描画されるため、同じコマンドへ `--summary-only` を追加する。summary-only では case/item 本体を返さず、同じ strict validation と summary 計算だけを行う。拡張は解析成功、再解析成功、保存成功、起動時の最終 workspace 復元時に summary-only を非同期実行して workspaceState へ cache し、通常の HTML render 中には CLI を起動しない。

### 8.2 フォーム適用

コマンド:

```text
unit-test-runner --json apply-test-input-form \
  --workspace <function-workspace> \
  --input <changes.json> \
  --expected-revision <number>
```

入力ファイル:

```json
{
  "schema_version": "1.0",
  "changes": [
    {
      "item_id": "opaque-item-id",
      "subject_fingerprint": "64桁のSHA256",
      "values": {
        "value_expression": "MODE_AUTO"
      },
      "confirmed": true
    }
  ]
}
```

`changes` では同じ `item_id` を一度だけ指定する。`values` は変更する allowlist leaf だけを含み、確認状態だけを変更する場合は空 object とする。`confirmed` は変更後の item 全体の確認状態として必須である。

主な処理:

1. 現在の canonical snapshot を strict mode で読み込む。
2. `expected_revision` を検査する。
3. 各 `item_id` を現在仕様へ一意に再解決する。
4. `subject_fingerprint` を検査する。
5. 全変更をメモリ上の copy へ適用する。
6. 値と確認状態を検証する。
7. 候補ケースの昇格または変更済み実行ケースの安全な降格を判定する。
8. canonical 契約を検証する。
9. snapshot を一度だけ保存する。
10. Markdown と CSV を再生成する。
11. 最新 summary と変更結果を返す。

成功出力例:

```json
{
  "status": "test_input_form_applied",
  "revision": 4,
  "updated_item_count": 5,
  "confirmed_item_count": 4,
  "promoted_case_ids": [
    "TC_Control_Update_001"
  ],
  "demoted_case_ids": [],
  "summary": {
    "attention_count": 4,
    "unresolved_count": 1,
    "unconfirmed_count": 3,
    "execution_blocking_count": 1,
    "warning_count": 1
  },
  "views_written": true
}
```

フォーム入力ファイルは VS Code の `context.storageUri ?? context.globalStorageUri` 配下へランダム名で作成し、CLI 終了後に `finally` で削除する。製品ソースツリーと関数出力 workspace の正本領域には置かない。

## 9. 編集対象

編集対象は allowlist 方式で決める。任意の JSON leaf をフォーム化しない。

| collection | 編集 leaf | control | 実行阻害 |
|---|---|---|---|
| `input_assignments` | `value_expression` | C 式 | はい |
| `state_setups` | `value_expression` | C 式 | はい |
| `state_setups` | `setup_method_hint` | 複数行テキスト | いいえ |
| `stub_setups` | `value_expression` | C 式 | 条件付き |
| `stub_setups` | `call_behavior` | 複数行テキスト | いいえ |
| `expected_observations` | `expected_expression` | C 式 | はい |
| `expected_observations` | `note` | 複数行テキスト | いいえ |
| `preconditions` | `description` | 複数行テキスト | いいえ |
| `execution_steps` | `detail` | 複数行テキスト | いいえ |
| `dependency_overrides` | `mode` | `inherit` / `real` / `stub` | いいえ |
| `dependency_overrides` | `rationale` | 複数行テキスト | いいえ |

次の情報は編集しない。

- `test_case_id`
- `spec_id`
- `revision`
- `schema_version`
- `source`
- `function`
- `generated_from`
- `coverage_links`
- `candidate_links`
- `review_item_ids`
- 正式レビュー判断
- warning の識別情報と解析根拠
- provenance 用 ID、candidate ID、call ID

表の一行は編集可能 leaf を示すが、同じ parent object に属する leaf は一つの item card にまとめる。確認状態と warning は item card 単位で扱う。

各 control は `required_for_confirmation` を持つ。

- 実行必須 value/expected control は `true`
- precondition description と execution detail は `true`
- `setup_method_hint`、`call_behavior`、expected note は `false`
- dependency mode は `true`
- dependency rationale は mode が `real` または `stub` へ明示変更された場合だけ `true`

`confirmed: true` にするには、同じ item の required control がすべて具体値でなければならない。optional control は空でもよい。

フォームへ item を表示する条件は次のとおり。

- 親 object の `review_required` が `true`
- または、実行必須 leaf が未解決
- または、同じタブで保存後も未確認として残っている

実行必須 object に boolean の `review_required` がない場合は、契約上の不整合として読み取り専用警告にし、自動的に確認済みとは扱わない。

## 10. 項目 ID と再解決

配列 index は再解析や正規化で変わる可能性があるため、`item_id` の主要部分には使わない。CLI は次の意味情報から locator を作る。

- case ID
- collection 名
- item の種類
- 親 object を一意にする安定した識別属性

編集 leaf 名は item ID に含めず、item の `controls[].name` として allowlist 検証する。これにより、同じ object に複数の編集 control があっても確認単位は一つに保たれる。

識別属性の例:

- input: `target_kind`, `target_name`, `source_candidate_id`
- state: `scope`, `variable_name`, `source_candidate_id`
- stub: `stub_name`, `setup_kind`, `related_call_id`, `source_candidate_id`
- expected: `observation_kind`, `target_name`, `source`
- dependency: `callee`
- precondition: `source`
- execution step: `order`, `action`

`item_id` は locator の canonical JSON を SHA256 で要約した不透明 ID とする。`subject_fingerprint` は対象 parent object の保存開始時点の意味内容を要約する。

同じ locator が複数 object に一致する場合は自動で index を付けず、項目を ambiguous として保存不可にする。これにより、誤った配列要素へ値を入れることを防ぐ。

revision が一致していても `subject_fingerprint` が一致しない場合は、その項目を競合として拒否する。これは将来、部分的な再読込や下書き再適用を実装しても安全に扱うための二重ガードである。

## 11. 確認状態

フォームの確認単位は JSON の親 object 一つとする。一つの object に `value_expression` と `setup_method_hint` のような複数の編集 leaf があっても、画面では一つの item card にまとめ、確認チェックは一つだけ表示する。leaf ごとに別々の確認状態を作らない。

フォームの `confirmed` は、対象 object の `review_required` の反転として扱う。

- `confirmed: true` → `review_required: false`
- `confirmed: false` → `review_required: true`

item 内のいずれかの値を変更した時点で Webview の下書き上では、その item の `confirmed` を自動的に `false` へ戻す。利用者は変更後の値を見て、改めて「確認済み」を選ぶ。

CLI はクライアントの自動解除を信用せず、`values` のいずれかが基準 fingerprint の内容と異なるのに確認状態の変更が明示されていない場合も、変更後 object を `review_required: true` とする。値の変更と確認を同じ保存で行う場合は、利用者が明示した `confirmed: true` を受け付ける。

項目確認は正式レビュー判断ではない。`unresolved_count` は実値から再計算し、canonical の `unresolved_items` 配列長を流用しない。値を解決しても `unresolved_items`、case/spec の `review_item_ids`、review decision ledger はこの操作では削除・承認しない。正式レビュー画面では、入力済みであっても関連 review item が open のまま残り得る。

次の情報は変更しない。

- case または spec の `review_item_ids`
- review decision ledger
- reviewer
- resolution
- rationale
- decided_at
- formal readiness

## 12. 未解決値と検証

未解決値は trim 後、次のいずれかである値とする。

- `null`
- 空文字
- 大文字小文字を無視して `TBD`、`TODO`、`UNKNOWN`、`UNRESOLVED` で始まる文字列

### 12.1 保存不可

次の場合は操作全体を拒否する。

- `confirmed: true` なのに required control が未解決
- `item_id` が存在しない、複数に一致する、または編集 allowlist 外
- `subject_fingerprint` が一致しない
- 同じ `item_id` が変更配列へ複数回現れる
- revision が一致しない
- canonical 仕様または関連ソースが stale
- 禁止領域の変更が含まれる
- enum control の値が許可集合外
- `review_required` の型が boolean ではない
- 適用後の canonical 契約検証に失敗する
- 昇格先または降格先に同じ case ID が存在する

### 12.2 警告付きで保存可能

次は警告に留める。

- 括弧、角括弧、引用符の対応が不自然
- 数値型らしい対象に文字列リテラルが入力された
- ポインタ型らしい対象に `NULL`、アドレス式、既知のポインタ候補以外が入力された
- 未知の識別子またはマクロを含む
- C90 では使えない可能性がある構文
- 型情報が不足している
- 候補値と異なる自由入力が使われた

入力正規化は次のとおり。

- C 式は前後空白を除去し、改行と NUL を拒否する。最大 4,096 Unicode code point。
- 複数行テキストは改行を `\n` へ正規化し、NUL を拒否する。最大 16,384 Unicode code point。
- enum 値は定義済み ASCII token の完全一致とする。

完全な C コンパイルは保存処理では行わない。最終的な妥当性はハーネス生成と build probe で確認する。

## 13. 候補値

候補値は入力補助であり、確定値ではない。根拠と confidence を必ず付ける。

候補元:

- `boundary_equivalence_candidates` の選択候補
- `source_candidate_id` が指す値
- 関数シグネチャから判定できるポインタ向け `NULL`
- 明確な boolean/flag に対する `0`、`1`
- 列挙定数を解析成果物から一意に取得できる場合の enum 値
- 同じ target に対して canonical spec 内で既に使われている具体値

根拠が弱い場合は候補を出さず、自由入力だけを表示する。候補を選択した後も入力欄は編集可能とする。

## 14. ケースの昇格と降格

### 14.1 実行必須 leaf

既存の canonical 生成判定と同じ範囲を使う。

- `input_assignments[].value_expression`
- `state_setups[].value_expression`
- `stub_setups[].value_expression`
- `expected_observations[].expected_expression`

ただし、`stub_setups[].setup_kind` が `call_count_observation` または `argument_capture` の場合は値を必須としない。

### 14.2 昇格対象

`additional_case_candidates` には、未解決のため候補へ移された主ケースと、意図的に生成された追加候補の両方が存在する。後者を勝手に実行対象へ入れない。

候補ケースを `promotion_eligible: true` とする条件は、保存前 snapshot で次をすべて満たすこととする。

1. ケース内に実行必須 object が一つ以上ある。
2. その object の少なくとも一つが未解決または `review_required: true` である。
3. case ID が `test_cases` 側に存在しない。

生成器が作る意図的な追加候補は通常、実行必須 object を持たないため昇格対象にならない。

昇格条件は次のとおり。

1. すべての実行必須値が具体値である。
2. すべての実行必須 object が `review_required: false` である。
3. case ID が一意である。
4. canonical 契約検証を通る。

複数ケースを昇格する場合は、元の `additional_case_candidates` の順序を維持して `test_cases` の末尾へ追加する。ケース内の `review_item_ids` と provenance は保持する。`coverage_summary` と `unresolved_items` は設計・正式レビューの履歴として変更しない。正式レビュー判断を自動承認しない。

この判定は、意図的な追加候補が実行必須 object を持たない現在の生成契約を前提とする。将来、意図的な追加候補にも実行必須 object を生成する場合は、candidate origin を canonical schema へ明示する schema revision を先に導入し、この推測へ依存しない。

### 14.3 実行ケースの安全な降格

既存 `test_cases` を無関係な保存で一括再分類しない。従来データに具体値だが `review_required: true` の項目がある可能性を考慮する。

ただし、今回の保存で実行必須 leaf を変更したケースについて、変更後の値が未解決、または変更した object が未確認になった場合は、そのケースを `additional_case_candidates` へ降格する。未解決または未確認のケースを実行対象に残さないためである。

複数ケースを降格する場合は、元の `test_cases` の順序を維持し、既存 `additional_case_candidates` の末尾へ追加する。非実行項目だけを変更した場合は、ケース位置を変えない。

## 15. 画面状態と操作

各 item は次の状態を持つ。

- 未入力
- 入力済み・未確認
- 確認済み
- 警告あり
- 保存不可
- 保存済み
- 競合

ケース一覧は次のように表示する。

```text
TC_Control_Update_001   未入力 2 / 未確認 1
TC_Control_Update_002   警告 1
TC_Control_Update_003   完了
```

上部 summary:

```text
入力済み 8 / 12
確認済み 6 / 12
実行阻害 3
```

操作規則:

- item の入力変更時にタブタイトルとフッターへ未保存表示を出す。
- 同じ関数 workspace の編集タブは一つだけ開き、再実行時は既存タブへフォーカスする。
- パネルを隠しただけでは下書きを失わない。
- 拡張プロセス内のメモリ cache に、workspace、revision、item ID ごとの item 下書きを保持する。
- タブを閉じて同じ VS Code セッション内に開き直した場合、revision が一致すれば下書きを復元する。
- revision が変わっていれば自動適用せず、競合再読込フローへ進む。
- VS Code 再起動後は下書きを復元しない。
- 「変更を破棄」は確認後、canonical 値を再取得する。
- 保存成功後もタブは閉じず、残件を続けて編集できる。

## 16. revision 競合と再読込

revision 競合時は正本を変更せず、入力中の下書きを保持する。

「最新状態を読み込む」は次の処理を行う。

1. 最新フォームモデルを取得する。
2. 同じ `item_id` が存在し、最新の `subject_fingerprint` が編集開始時と同じなら下書きを再適用する。
3. fingerprint が変わった項目は競合として表示する。
4. 利用者が「最新値を使う」または「下書きを採用」を項目ごとに選ぶ。
5. 下書きを採用した項目は、新しい fingerprint を基準に再度保存する。
6. 自動上書きしない。

case が削除または locator が曖昧になった場合、下書きは画面上で参照できるよう残すが保存対象から除外する。

## 17. stale 成果物

`get-test-input-form` と `apply-test-input-form` は `get-test-spec` と同等の current artifact context 検証を行う。

ソース、関数シグネチャ、生成元が stale の場合は編集開始または保存を拒否し、次を案内する。

```text
このテスト仕様は現在のソースと一致しません。
先に「現在の関数を再解析」を実行してください。
```

再解析後の値引き継ぎは既存の reconciliation を使う。VS Code 再解析経路を canonical `--previous-test-spec` に切り替えることが、この機能の必須範囲である。

## 18. 原子性と派生ビュー

変更適用、確認状態更新、昇格・降格は一つの candidate `TestSpec` をメモリ上で構築してから検証する。検証完了前に正本へ書き込まない。

正本の保存は既存 repository API を使い、一回の snapshot 更新として扱う。入力変更の途中だけが反映された状態を作らない。

正本保存後に Markdown/CSV の再生成だけが失敗した場合:

- `test_spec.json` の保存成功は維持する。
- 結果は warning status とする。
- `views_written: false` を返す。
- Workflow パネルへ「表示ファイルを再生成」を案内する。
- 正本を古い revision へ巻き戻さない。

## 19. セキュリティと境界

- Webview は nonce 付き CSP を使い、`default-src 'none'` とする。
- 画面へ埋め込む値、ラベル、C 式、パス、警告は HTML escape する。
- Webview message は TypeScript 側で shape、型、件数上限、文字列長を検証する。
- CLI 側でも同じ制約を再検証する。
- `item_id` を path として使用しない。
- VS Code adapter は input JSON を `context.storageUri ?? context.globalStorageUri` 配下へ作成し、製品ツリーや関数 workspace へ一時入力を置かない。
- CLI は指定された input JSON を読み取り専用で扱い、そのファイル自体を書き換えない。
- canonical workspace の外側へ CLI が書き込まない既存方針を維持する。
- input JSON は最大 4 MiB、`changes` は最大 1,000 item、1 item の `values` は最大 16 leaf とする。
- 文字列長は C 式 4,096、複数行テキスト 16,384 Unicode code point を上限とする。
- C 式はコードとして VS Code 拡張内で評価しない。

## 20. エラー表示

| 状況 | 動作 |
|---|---|
| canonical spec がない | クイックチェックまたはテスト設計生成を案内 |
| revision 競合 | 保存せず下書きを保持し、最新状態の読込を案内 |
| stale source | 保存せず再解析を案内 |
| 確認済み項目が未解決 | 対象 item へ移動して保存不可表示 |
| C 式が疑わしい | 警告を表示し、明示保存を許可 |
| item が一意に解決できない | 対象 item を保存不可にし、再解析を案内 |
| canonical 契約違反 | 全変更を拒否し、CLI 詳細を表示 |
| CLI 異常終了 | 下書きを保持し、Output Channel を開く導線を表示 |
| 派生ビューだけ失敗 | 正本保存成功を表示し、再生成を案内 |

## 21. テスト方針

### 21.1 Python unit tests

- allowlist に基づく item 抽出
- 同じ parent object の複数 leaf が一 item にまとまること
- required/optional control の確認判定
- summary が item 単位で重複計数しないこと
- summary-only が本体配列を返さないこと
- `review_required: true` の抽出
- 未解決値の強制抽出
- 意図的な追加候補が promotion eligible にならないこと
- 未解決主ケースが promotion eligible になること
- `item_id` の並び替え耐性
- item locator 重複時の ambiguous 判定
- subject fingerprint の競合判定
- 部分保存
- 値変更時の確認解除
- 同一保存内での値変更と明示確認
- 確認済み未解決値の拒否
- C 式警告付き保存
- 候補ケースの昇格
- 変更済み実行ケースの安全な降格
- 非実行項目変更でケース位置が変わらないこと
- duplicate case ID の拒否
- revision 競合時に無変更であること
- stale source の拒否
- 禁止領域を更新できないこと
- formal review 情報が変わらないこと
- Markdown/CSV 再生成
- 複数変更の途中失敗で一部保存されないこと
- form input の件数上限と文字列長上限

### 21.2 VS Code unit tests

- `get-test-input-form` と `apply-test-input-form` の command builder
- `--test-spec` を使うハーネス生成
- `--previous-test-spec` を使う再解析
- Workflow パネルの件数表示
- summary cache の revision/SHA invalidation
- Workflow render 中に CLI を起動しないこと
- 実行阻害時の強調
- 編集タブの初期描画
- ケース選択と section 表示
- C 式候補の選択後も自由編集できること
- 値変更時の確認解除
- 部分保存 request
- Webview message validation
- HTML escape と CSP
- 保存成功後の revision、summary 更新
- 競合時の下書き維持
- fingerprint が同じ下書きだけを再適用すること
- 同一 workspace の editor singleton
- 一時 input JSON の削除

### 21.3 結合スモーク

fixture から未解決値を含む canonical spec を生成し、次を通す。

```text
get-test-input-form
apply-test-input-form
get-test-spec
generate-harness-skeleton --test-spec
build-probe --dry-run
```

確認項目:

- 入力値が canonical spec に保存される。
- revision が一回だけ進む。
- Markdown/CSV が同じ revision から生成される。
- 未解決主ケースが `test_cases` へ移る。
- 意図的な追加候補は候補側に残る。
- ハーネス生成物へ具体値が反映される。
- legacy `test_case_design.json` を編集していない。
- build probe が canonical 経路を使用する。

## 22. 受け入れ条件

1. 現在の関数を解析後、Workflow パネルに未確定件数が表示される。
2. ボタンから専用編集タブを開ける。
3. `TBD_VALID_VALUE` を `MODE_AUTO` に変更し、未確認のまま部分保存できる。
4. 同じ項目を確認済みにして保存すると `review_required` が false になる。
5. 確認済みにしたまま placeholder を保存しようとすると拒否される。
6. 必須項目をすべて具体値かつ確認済みにすると、昇格対象ケースが `test_cases` へ移る。
7. 意図的な追加候補は自動昇格しない。
8. 競合 revision では canonical spec の byte 内容が変わらない。
9. 保存後に Markdown と CSV が更新される。
10. 正式レビュー判断と review ID は不変である。
11. 再解析が `--previous-test-spec` を使用して入力値を引き継ぐ。
12. ハーネス生成が `--test-spec` を使用し、GUI 入力を生成 C へ反映する。
13. Python と VS Code の既存テストを含む全テストが成功する。

## 23. 採用しなかった案

### 23.1 Workflow サイドパネルへ全フォームを配置

項目数が多い関数で窮屈になり、ケース間移動と警告表示が難しいため採用しない。

### 23.2 Webview が canonical JSON を直接編集

revision、契約検証、昇格判定が TypeScript と Python に二重実装され、thin adapter 方針を壊すため採用しない。

### 23.3 値入力だけで自動確認

仮入力をレビュー完了と誤認するため採用しない。

### 23.4 全項目入力まで保存禁止

長いレビューを分割できず、部分保存の要件に反するため採用しない。

### 23.5 すべての C 式を厳格に構文解析

VC6/C90、プロジェクト固有マクロ、typedef、include context を完全に再現できない限り誤拒否が多いため、初期実装では警告方式とする。

## 24. 実装への引き継ぎ

実装計画では、次の順序を基本とする。

1. canonical consumer の VS Code command builder 修正
2. Python の form model、field locator、validation の unit tests
3. `get-test-input-form`
4. `apply-test-input-form` と昇格・降格
5. CLI 結合 tests
6. VS Code editor panel と message contract
7. Workflow パネル統合
8. 競合再読込
9. docs と end-to-end smoke
10. 全テストと配布ビルド確認

各段階はテスト駆動で進め、正本を直接編集する回避策は入れない。
