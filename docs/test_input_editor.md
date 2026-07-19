# テスト入力編集GUI 利用手順

## 1. 目的

テスト設計では、解析だけでは確定できない入力値、事前状態、スタブ戻り値、期待値が `TBD_VALID_VALUE` などの未確定値として残ることがあります。テスト入力編集GUIは、canonical正本である `reports/test_spec.json` をJSONエディターで直接変更せず、現在の関数に必要な項目をケース別フォームから入力・確認するための専用タブです。

VS Code拡張は画面表示、セッション内の下書き、CLI呼び出しだけを担当します。項目の検証、revision競合検出、subject fingerprint検証、部分保存、候補ケースの昇格・降格、正本の保存はPython CLI coreが実行します。

## 2. 前提と対象workspace

1. VS CodeでCプロジェクトを開き、UnitTestRunnerの設定を完了します。
2. 対象関数を解析し、テスト設計まで生成します。
3. Workflowパネルが保持する現在の関数workspaceに `reports/test_spec.json` があることを確認します。

初期版の編集対象は、現在の関数workspace一つです。別の関数やスイート全体を同じタブで一括編集する機能はありません。

## 3. 編集タブを開く

Workflowパネルに次のボタンが表示されます。

```text
未確定項目を入力（7件）
```

未確定項目が0件の場合は、次の控えめな表示になります。

```text
入力内容を確認（0件）
```

実行を阻害する未解決値がある場合は警告表示になります。タブは自動では開きません。ボタン、またはコマンドパレットの次のコマンドから明示的に開きます。

```text
UnitTestRunner: 未確定テスト項目を入力
```

## 4. 画面構成

ヘッダーには関数名、workspace、TestSpec revision、全体件数を表示します。左ペインには編集項目を持つテストケースだけを並べ、右ペインには選択ケースの項目を次の区分で表示します。

- 入力値
- 事前状態
- スタブ設定
- 期待値
- 前提条件
- 実行手順
- 依存関係
- その他のレビュー継続項目

各項目カードは次の状態を持ちます。

| 状態 | 意味 |
|---|---|
| 未入力 | 空欄、または `TBD`、`TODO`、`UNKNOWN`、`UNRESOLVED` で始まる値です。 |
| 入力済み・未確認 | 具体値はありますが、項目の「確認済み」が選択されていません。 |
| 確認済み | 必須値が具体値で、利用者が項目単位で確認済みにしています。 |
| 警告あり | 保存可能ですが、C式または型整合に疑いがあります。 |
| 保存不可 | 必須値不足、曖昧な項目ID、競合などにより保存できません。 |
| 競合 | 編集開始後に同じ対象の意味内容が変更されています。 |

## 5. 候補値とC式の自由入力

値はC式の文字列として保存します。候補が表示された場合も、候補選択後に入力欄を自由に編集できます。

```c
0
MODE_AUTO
NULL
&buffer[0]
sizeof(ControlState)
```

候補は解析根拠がある場合だけ表示します。主な候補元は、境界値候補、関数シグネチャから確認できるポインタ向け `NULL`、明確なフラグ向けの `0` / `1`、解析済みの列挙定数、同じtargetで既に使用されている具体値です。候補は確定値ではありません。根拠が弱い場合は自由入力だけを表示します。

## 6. 入力と「確認済み」の違い

値を入力しただけでは項目は確認済みになりません。項目内の値を変更すると、その項目の下書き上の「確認済み」は自動的に解除されます。内容を確認してから、項目カードの「確認済み」を明示的に選択します。

- 値を入力する: `value_expression` などの内容を変更します。
- 項目を確認済みにする: 対象親objectの `review_required` を `false` にします。
- 正式レビューを承認する: 既存のreview decision ledgerで別途判断します。

このGUIは `review_item_ids`、reviewer、resolution、rationale、正式なreadinessを変更しません。項目を「確認済み」にしても、正式レビュー項目が自動承認されることはありません。

## 7. 明示保存と部分保存

入力はタブ内の下書きとして保持されます。正本へ反映するのは、フッターの **保存して反映** を押したときだけです。自動保存は行いません。

変更した項目だけを保存できるため、すべての未確定項目を一度に完了する必要はありません。未変更項目や未入力項目はそのまま残り、次回も一覧に表示されます。

**変更を破棄** は確認後に、タブを最後に読み込んだ時点の値へ下書きを戻します。外部変更を取り込む場合は **最新状態を読み込む** を使用します。保存成功後もタブは閉じず、残りの項目を続けて編集できます。

## 8. 保存不可エラーと保存可能な警告

次の例は操作全体を保存せずに拒否します。

- 「確認済み」なのに必須値が空欄または未確定値のまま
- revisionが編集開始時から変わっている
- subject fingerprintが一致しない
- item IDが存在しない、複数対象へ一致する、または編集不可
- enum値が許可集合外
- 現在の `review_required` がbooleanではない
- canonical TestSpecまたは関連成果物がstale
- 適用後のTestSpec契約に違反する

次の例は警告を表示しますが、利用者が確認したうえで保存できます。

- 括弧、角括弧、引用符の対応が不自然
- 数値型らしい対象へ文字列リテラルを入力
- ポインタ型らしい対象へ根拠のない数値を入力
- 未知の識別子またはマクロを使用
- C90では利用できない可能性がある構文
- 型情報または候補根拠が不足

保存処理はC式を実行しません。最終的な妥当性はハーネス生成とbuild probeで確認します。

## 9. 候補ケースの昇格と限定的な降格

未解決の実行必須値がある主ケースは `additional_case_candidates` に置かれる場合があります。次の条件をすべて満たすと、保存時に `test_cases` へ自動昇格します。

1. すべての実行必須値が具体値である。
2. すべての実行必須親objectが確認済みである。
3. case IDが一意である。
4. canonical契約検証を通る。

実行必須objectを持たない意図的な追加候補は自動昇格しません。

既に実行対象のケースで、今回変更した実行必須値を未解決または未確認へ戻した場合、そのケースだけを安全のため候補側へ降格します。無関係な保存で既存ケースを一括再分類することはありません。

## 10. revision競合とsubject fingerprint競合

編集開始後に別の処理が `test_spec.json` を更新した場合、保存は拒否され、下書きは保持されます。**最新状態を読み込む** を実行すると、同じitem IDかつ元のfingerprintが変わっていない下書きだけを再適用します。

fingerprintが変わった項目には次の選択肢を表示します。

- **最新値を使う**: 下書きを破棄し、最新のcanonical値を採用します。
- **下書きを採用**: 最新fingerprintへ明示的にrebaseし、再度保存対象にします。

削除済みまたは曖昧になった項目の下書きは参照用に残りますが、保存要求から除外されます。競合後に自動上書きや自動再送は行いません。

## 11. stale sourceと再解析

対象Cソース、関数シグネチャ、生成元成果物がTestSpec作成時から変化している場合、編集開始または保存を拒否します。

```text
このテスト仕様は現在のソースと一致しません。
先に「現在の関数を再解析」を実行してください。
```

再解析はcanonical `reports/test_spec.json` を前回仕様として使用します。通常経路でlegacy `test_case_design.json` を編集しません。旧ファイルと旧CLI引数は後方互換のaliasとしてのみ残ります。

## 12. CLIで同じ操作を再現する

フォーム取得:

```powershell
py -m unit_test_runner --json get-test-input-form --workspace $out
```

件数だけを取得:

```powershell
py -m unit_test_runner --json get-test-input-form --workspace $out --summary-only
```

取得結果の `item_id`、`subject_fingerprint`、`revision` を使用して変更ファイルを作成します。固定値を流用せず、必ず現在の出力から取得してください。

```json
{
  "schema_version": "1.0",
  "changes": [
    {
      "item_id": "item-<現在の64桁ID>",
      "subject_fingerprint": "<現在の64桁fingerprint>",
      "values": {
        "value_expression": "MODE_AUTO"
      },
      "confirmed": true
    }
  ]
}
```

変更を適用:

```powershell
py -m unit_test_runner --json apply-test-input-form `
  --workspace $out `
  --input $changes `
  --expected-revision 3
```

canonical仕様からハーネスを再生成:

```powershell
py -m unit_test_runner --json generate-harness-skeleton `
  --function-signature "$out\reports\function_signature.json" `
  --global-access "$out\reports\global_access.json" `
  --call-report "$out\reports\call_report.json" `
  --test-spec "$out\reports\test_spec.json" `
  --dependency-policy "$out\reports\dependency_policy.json" `
  --out $out `
  --overwrite
```

保存成功時はcanonical revisionが一度だけ進み、`test_spec.md` と `test_spec.csv` が同じsnapshotから再生成されます。派生ビューだけの生成に失敗した場合も、新しいcanonical JSONを古いrevisionへ巻き戻しません。候補ケースが実行対象へ昇格した場合、関連する履歴上の未解決項目は削除せず `blocking: false` として保持します。
