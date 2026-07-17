# 大規模アプリケーション向けテスト環境 設計

作成日: 2026-07-17
状態: 実装済み
対象リポジトリ: `katamor1/unitTestRunner`

## 1. 目的

`unitTestRunner` の DSW/DSP 解析、source membership 判定、関数解析、build probe dry-run を、数千から数万の C/C++ source entry を含む VC6 風プロジェクトで手動検証できる環境を用意する。

本番ソースやリポジトリ内 fixture は書き換えず、生成物は外部の破棄可能なディレクトリへ作成する。

## 2. 参考実装から継承する原則

`vscodeTree/scripts/generate-sample2-scale.js` の次の考え方を採用する。

- 小さくレビュー可能な base fixture をコピーして規模だけを増やす
- 7,000 / 16,000 / 31,000 source entry の段階を用意する
- 出力先をリポジトリ外へ限定する
- 再生成前の削除対象を prefix と親ディレクトリの両方で検証する
- 生成数、対象プロジェクト、対象関数、パスを `manifest.json` に残す
- 生成器の境界条件を小さな単体テストで検証する

`unitTestRunner` の CLI core は Python であるため、JavaScript の直コピーではなく、同じ設計原則を Python 3.12 標準ライブラリへ移す。

## 3. 方式比較

### 案A: JavaScript を移植する

参考実装との差分は小さいが、ルートへ Node.js の責務を増やし、Python CLI core とテスト方式が分かれる。

### 案B: Python 生成器で既存の実用 fixture を拡張する

既存の Python 3.12、`unittest`、Windows CI に統合でき、`tests/fixtures/vc6_practical_project` の既知の解析対象を維持できる。追加依存も不要である。

### 案C: 大規模 fixture 自体を Git 管理する

生成なしで利用できる一方、数千から数万ファイルが clone、検索、レビュー、CI を重くする。

### 決定

案Bを採用する。

## 4. base fixture と解析対象

既定の base は `tests/fixtures/vc6_practical_project` とする。

- workspace: `Product.dsw`
- project: `DeviceControl`
- configuration: `DeviceControl - Win32 Debug`
- source: `src/device_control.c`
- function: `DeviceControl_Update`

## 5. 生成器

`scripts/generate_large_vc6_fixture.py` を追加する。

公開引数:

- `--base`: base fixture。既定は実用 fixture
- `--root`: 性能 fixture の親ディレクトリ
- `--output`: 単一規模の明示出力先
- `--entries`: `DeviceControl.dsp` に含める C/C++ source entry 総数
- `--tiers [LIST]`: 複数規模。値省略時は `7000,16000,31000`

環境変数:

- `UNIT_TEST_RUNNER_PERF_ROOT`: `--root` の既定値
- `UNIT_TEST_RUNNER_LARGE_ENTRIES`: `--entries` の既定値

生成処理:

1. base DSP を UTF-8 BOM、UTF-8、CP932、Shift-JIS の順で判定する。
2. 安全境界を検証して出力先だけを初期化する。
3. base fixture をコピーする。
4. `src/generated/large_module_XXXXX.c` を必要数生成する。
5. `DeviceControl/DeviceControl.dsp` の `Source Files` group へ source entry を追加する。
6. 元の DSP エンコーディングで byte 出力する。
7. 実在ファイル総数を含む `manifest.json` と標準出力 JSON summary を生成する。

生成 C は C90/VC6 で扱える構文に限定し、一意な関数、隣接関数呼び出し、分岐、`g_system_tick` への外部 global access を含める。

## 6. 安全性

再生成の削除前に次をすべて検証する。

- 出力先が `--root` 配下である
- 出力先が `unitTestRunner` リポジトリの外側である
- basename が `unit-test-runner-large-` で始まる
- `--root` 自体ではない
- base と output が同一、親子、包含関係にない

違反時は削除前に中止する。明示的な `--root` または `--output` でも、リポジトリ内の出力は許可しない。

## 7. manifest 契約

`manifest.json` は少なくとも次を持つ。

- `schema_version`
- `generator`
- `generated_at`
- `base_root`
- `root`
- `workspace_file`
- `target_project_file`
- `base_source_entries`
- `source_entries_in_target_project`
- `generated_source_files`
- `total_files_on_disk`
- `target.project`
- `target.configuration`
- `target.source`
- `target.function`

## 8. テスト

`tests/test_large_vc6_fixture_generator.py` は production 規模を生成せず、小さな一時 fixture で次を検証する。

- tier 解析、空指定、不正値拒否
- `--tiers` 値省略時の既定段階
- 性能 root、リポジトリ外、prefix による削除境界
- base の非破壊コピー
- DSP source entry 追加
- manifest 件数と実在ファイル数の一致
- CP932 DSP の維持
- 再生成時の stale file 除去

大規模 tier 自体は手動性能確認用であり、通常 CI では生成しない。

## 9. 非目標

- 31,000ファイルを通常 CI で生成すること
- VC6 のコンパイル時間やメモリ上限を保証すること
- 複数 project を自動生成すること
- 本番プロジェクトを直接変更すること
- ベンチマーク合否の固定閾値を導入すること

## 10. 受け入れ条件

- Python 3.12 互換構文で生成器が起動する
- 小規模単体テストが全件通る
- 出力境界外とリポジトリ内の削除を拒否する
- 既存実用 fixture を変更しない
- 7,000 / 16,000 / 31,000 の各出力先を生成できる
- 生成後の CLI smoke 手順が文書化されている
