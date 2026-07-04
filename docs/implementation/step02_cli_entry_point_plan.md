# Step 02: CLI Entry Point 実装計画

作成日: 2026-07-04  
状態: Draft v0.1  
対象リポジトリ: `katamor1/unitTestRunner`  
製造担当想定: CODEX  
前提ADR: `docs/adr/0001-cli-layer-language-selection.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第2ステップとして **CLI Entry Point** を実装するための計画である。

ADR-0001 の CODEX 向け製造指示では、製造順を以下としている。

1. Python package skeleton
2. CLI entry point
3. DSW parser
4. DSP parser
5. source-to-project mapper
6. build context collector

本書の対象は、このうち **2. CLI entry point** である。

なお、以前の関数単位設計書では `Task 2: DSW パーサ` と記載している箇所があるが、本実装計画では ADR-0001 の製造順を優先する。
混同を避けるため、以降は以下の呼び方に統一する。

| 呼称 | 内容 |
|---|---|
| Step 01 | Python package skeleton |
| Step 02 | CLI entry point |
| Step 03 | DSW parser |
| Step 04 | DSP parser |

---

## 2. 目的

Step 02 の目的は、以降の DSW/DSP 解析、C 関数解析、dossier 生成、build-probe をすべて呼び出せる **安定したCLIの入口** を先に作ることである。

この段階では、各解析機能の中身を完成させない。
代わりに、以下を固める。

- `unit-test-runner` コマンドとして起動できること
- サブコマンド体系が決まっていること
- 引数仕様が決まっていること
- 終了コードが決まっていること
- ログ出力方針が決まっていること
- JSON / Markdown / CSV 出力先の扱いが決まっていること
- 後続機能を stub 実装で接続できること
- CODEX が Step 03 以降を小さなPR/コミットで追加できること

---

## 3. ゴール

### 3.1 機能ゴール

Step 02 完了時点で、以下が動作する状態にする。

```bat
unit-test-runner --help
unit-test-runner --version
unit-test-runner doctor
unit-test-runner discover-projects --help
unit-test-runner map-source --help
unit-test-runner analyze-function --help
unit-test-runner build-probe --help
unit-test-runner generate-test-draft --help
```

また、未実装のサブコマンドを実行した場合でも、異常終了ではなく、以下を分かりやすく返す。

- そのサブコマンドが未実装であること
- 予定されている入力引数
- Step 03 以降で実装されること
- 終了コード `20` を返すこと

### 3.2 設計ゴール

- CLI層は解析ロジックを持ちすぎない
- CLI層は入出力の検証、パス解決、ログ初期化、コマンド振り分けに集中する
- 後続機能は service / usecase 関数として差し込む
- VS Code extension から呼び出しやすい stdout / stderr / 終了コードにする
- Windows バッチから呼び出しやすい引数形式にする
- 日本語パス、空白を含むパス、相対パスに配慮する

---

## 4. 対象範囲

### 4.1 実装対象

Step 02 で実装するもの:

1. CLI エントリポイント
   - `unit-test-runner`
   - `python -m unit_test_runner`

2. グローバルオプション
   - `--version`
   - `--verbose`
   - `--quiet`
   - `--log-file`
   - `--json`
   - `--no-color`

3. サブコマンド定義
   - `doctor`
   - `discover-projects`
   - `map-source`
   - `analyze-function`
   - `build-probe`
   - `generate-test-draft`

4. 共通処理
   - 引数解析
   - パス正規化
   - ログ初期化
   - エラー整形
   - 終了コード定義
   - JSON 出力モード
   - 未実装コマンドの stub 応答

5. テスト
   - `--help` が成功すること
   - `--version` が成功すること
   - `doctor` が成功すること
   - 必須引数不足で終了コード `1` になること
   - 未実装コマンドが終了コード `20` になること
   - JSON 出力モードが機械処理可能な JSON を返すこと

### 4.2 対象外

Step 02 では以下を実装しない。

- `.dsw` の実解析
- `.dsp` の実解析
- 対象 `.c` の所属判定
- C 関数ロケータ
- グローバル変数解析
- 分岐・条件解析
- 境界値・同値クラス候補生成
- `function_dossier.json` の本生成
- VC6 / nmake / cl.exe の実行
- VS Code extension 本体
- PyInstaller packaging

ただし、これらを呼び出すためのコマンド名、引数、戻り値の骨格は Step 02 で用意する。

---

## 5. CLI コマンド体系

### 5.1 全体

```text
unit-test-runner
  --help
  --version
  [--verbose]
  [--quiet]
  [--log-file PATH]
  [--json]
  [--no-color]
  <command> [command options]
```

### 5.2 doctor

開発環境・実行環境の最低限の確認を行う。

```bat
unit-test-runner doctor
unit-test-runner --json doctor
```

Step 02 の `doctor` で確認するもの:

- Python バージョン
- OS 情報
- 現在の作業ディレクトリ
- 書き込み可能な一時ディレクトリ
- パッケージバージョン
- 標準ライブラリのみで動作していること

Step 02 では VC6 / nmake / cl.exe の検出は warning 扱いまたは未確認扱いでよい。
実検出は build-probe 実装時に強化する。

JSON 出力例:

```json
{
  "status": "ok",
  "command": "doctor",
  "version": "0.1.0",
  "python": {
    "version": "3.12.x",
    "supported": true
  },
  "checks": [
    {
      "id": "python_version",
      "status": "ok",
      "message": "Python version is supported."
    }
  ],
  "warnings": []
}
```

### 5.3 discover-projects

将来の DSW discovery 用コマンド。
Step 02 では引数受け取りと未実装応答のみ実装する。

```bat
unit-test-runner discover-projects ^
  --workspace D:\work\product ^
  --out D:\work\unit_test_workspace\reports\projects.json
```

引数:

| 引数 | 必須 | 内容 |
|---|---|---|
| `--workspace PATH` | 必須 | 探索対象の本番リポジトリまたは作業ツリー |
| `--out PATH` | 任意 | 結果JSONの出力先 |

### 5.4 map-source

対象 `.c` がどの `.dsw` / `.dsp` に属するかを調べるコマンド。
Step 02 では引数受け取りと未実装応答のみ実装する。

```bat
unit-test-runner map-source ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c
```

引数:

| 引数 | 必須 | 内容 |
|---|---|---|
| `--dsw PATH` | 必須 | VC6 workspace file |
| `--source PATH` | 必須 | 対象 `.c` ファイル |
| `--configuration NAME` | 任意 | 構成名。未指定時は候補を返す |
| `--project NAME` | 任意 | プロジェクト名。複数候補を絞るために使う |
| `--out PATH` | 任意 | 結果JSONまたはMarkdownの出力先 |

### 5.5 analyze-function

関数単位の dossier 生成に向けた中核コマンド。
Step 02 では引数受け取り、入力検証、未実装応答のみ実装する。

```bat
unit-test-runner analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Win32 Debug" ^
  --out D:\work\unit_test_workspace\Control_Update
```

引数:

| 引数 | 必須 | 内容 |
|---|---|---|
| `--dsw PATH` | 必須 | VC6 workspace file |
| `--source PATH` | 必須 | 対象 `.c` ファイル |
| `--function NAME` | 必須 | 対象関数名 |
| `--configuration NAME` | 任意 | VC6 構成名 |
| `--project NAME` | 任意 | 対象DSPプロジェクト名 |
| `--out PATH` | 必須 | ワークスペース出力先 |
| `--emit-json` | 任意 | `function_dossier.json` 生成を要求する |
| `--emit-md` | 任意 | Markdown レポート生成を要求する |
| `--emit-csv` | 任意 | CSV 草案生成を要求する |

### 5.6 build-probe

dossier に基づいてビルド試行するコマンド。
Step 02 では引数受け取りと未実装応答のみ実装する。

```bat
unit-test-runner build-probe ^
  --dossier D:\work\unit_test_workspace\Control_Update\reports\function_dossier.json
```

引数:

| 引数 | 必須 | 内容 |
|---|---|---|
| `--dossier PATH` | 必須 | `function_dossier.json` |
| `--vcvars PATH` | 任意 | VC6 環境設定バッチ |
| `--out PATH` | 任意 | ビルドプローブ出力先 |

### 5.7 generate-test-draft

dossier からテストケース草案を生成するコマンド。
Step 02 では引数受け取りと未実装応答のみ実装する。

```bat
unit-test-runner generate-test-draft ^
  --dossier D:\work\unit_test_workspace\Control_Update\reports\function_dossier.json ^
  --out D:\work\unit_test_workspace\Control_Update\reports\test_case_draft.csv
```

引数:

| 引数 | 必須 | 内容 |
|---|---|---|
| `--dossier PATH` | 必須 | `function_dossier.json` |
| `--out PATH` | 任意 | CSV / Markdown 出力先 |
| `--format csv|md|json` | 任意 | 出力形式。既定は `csv` |

---

## 6. 終了コード

Step 02 で終了コードを先に固定する。

| 終了コード | 意味 | 使用例 |
|---:|---|---|
| 0 | 成功 | `--help`, `--version`, `doctor` 成功 |
| 1 | 入力不正 | 必須引数不足、不正なオプション |
| 2 | ファイルまたはディレクトリが見つからない | `--dsw` 指定先なし |
| 3 | 出力先作成失敗 | 権限不足、親ディレクトリ不在 |
| 10 | 内部エラー | 想定外例外 |
| 20 | 未実装 | Step 03 以降の stub コマンド実行 |
| 30 | 環境警告あり | `doctor` で致命的ではない警告 |

補足:

- `argparse` の標準エラー終了は `2` だが、本ツールでは入力不正を `1` に寄せる。
- `argparse.ArgumentParser.error()` を override するか、例外変換層を用意する。
- VS Code adapter から扱いやすいよう、終了コードと JSON の `status` を対応させる。

---

## 7. 標準出力・標準エラー方針

### 7.1 通常モード

通常モードでは、人間が読みやすいメッセージを stdout に出す。
エラー詳細は stderr に出す。

例:

```text
unitTestRunner 0.1.0
Command: analyze-function
Status: not implemented
This command will be implemented in Step 03 and later.
```

### 7.2 JSON モード

`--json` 指定時は、stdout に JSON のみを出す。
stderr にはログや余計な文字を出さない。

例:

```json
{
  "status": "not_implemented",
  "exit_code": 20,
  "command": "analyze-function",
  "message": "This command is defined but not implemented yet.",
  "planned_step": "Step 03+"
}
```

### 7.3 ログファイル

`--log-file PATH` 指定時は、ログをファイルへ出す。
JSON モードと併用しても stdout を汚さない。

---

## 8. 実装設計

### 8.1 推奨ファイル構成

```text
src/
  unit_test_runner/
    __init__.py
    __main__.py
    cli/
      __init__.py
      main.py
      parser.py
      commands.py
      exit_codes.py
      result.py
    utils/
      __init__.py
      paths.py
      logging.py
      platform.py
```

Step 02 では最小構成として以下を実装する。

| ファイル | 役割 |
|---|---|
| `__init__.py` | バージョン定義 |
| `__main__.py` | `python -m unit_test_runner` の入口 |
| `cli/main.py` | main関数、例外処理、終了コード返却 |
| `cli/parser.py` | argparse parser 構築 |
| `cli/commands.py` | 各サブコマンドの handler |
| `cli/exit_codes.py` | 終了コード定数 |
| `cli/result.py` | CLI結果モデル |
| `utils/logging.py` | ログ初期化 |
| `utils/paths.py` | パス正規化補助 |
| `utils/platform.py` | doctor 用環境情報 |

### 8.2 CLIResult モデル

すべてのコマンド handler は `CLIResult` を返す。

```python
@dataclass
class CLIResult:
    status: str
    exit_code: int
    command: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
```

Python 3.12 互換を保つため、必要に応じて `from __future__ import annotations` を使用する。

### 8.3 handler の責務

handler は以下のみを行う。

- 引数を受け取る
- パスを正規化する
- 必須パスの存在確認を行う
- 未実装機能は `not_implemented` を返す
- 実装済みの `doctor` は環境情報を返す

DSW/DSP の実解析は Step 03 以降の service に委譲する。

### 8.4 エラー処理

- 入力不正は `CLIResult(status="error", exit_code=1)` に変換する
- ファイルなしは `CLIResult(status="error", exit_code=2)` に変換する
- 未実装は `CLIResult(status="not_implemented", exit_code=20)` にする
- 想定外例外は `CLIResult(status="internal_error", exit_code=10)` に変換し、log に stack trace を残す
- JSON モードでは stack trace を stdout に出さない

---

## 9. pyproject.toml 方針

Step 02 では `pyproject.toml` に console script を定義する。

```toml
[project]
name = "unit-test-runner"
version = "0.1.0"
description = "Function-level unit test preparation tool for VC6/C90 projects"
requires-python = ">=3.12"

[project.scripts]
unit-test-runner = "unit_test_runner.cli.main:main"
```

依存ライブラリは原則なしとする。
pytest などの開発依存は Step 01 の骨格で導入済みの場合のみ利用する。
未導入の場合、Step 02 の中で最小導入してよい。

---

## 10. テスト計画

### 10.1 テスト対象

- CLI parser
- 各サブコマンドの help
- `doctor`
- 未実装サブコマンド
- JSON 出力
- 終了コード
- パス引数の受け取り

### 10.2 テストケース

| ID | 観点 | コマンド | 期待結果 |
|---|---|---|---|
| CLI-001 | help | `unit-test-runner --help` | exit 0 |
| CLI-002 | version | `unit-test-runner --version` | exit 0, version 表示 |
| CLI-003 | doctor | `unit-test-runner doctor` | exit 0 |
| CLI-004 | doctor json | `unit-test-runner --json doctor` | exit 0, JSON parse 可能 |
| CLI-005 | discover help | `unit-test-runner discover-projects --help` | exit 0 |
| CLI-006 | map-source help | `unit-test-runner map-source --help` | exit 0 |
| CLI-007 | analyze help | `unit-test-runner analyze-function --help` | exit 0 |
| CLI-008 | build-probe help | `unit-test-runner build-probe --help` | exit 0 |
| CLI-009 | draft help | `unit-test-runner generate-test-draft --help` | exit 0 |
| CLI-010 | missing required | `unit-test-runner analyze-function` | exit 1 |
| CLI-011 | not implemented | `unit-test-runner analyze-function --dsw a.dsw --source a.c --function f --out out` | exit 20 |
| CLI-012 | not implemented json | `unit-test-runner --json analyze-function ...` | exit 20, JSON parse 可能 |
| CLI-013 | log file | `unit-test-runner --log-file tmp.log doctor` | log file が作成される |

### 10.3 pytest 実装方針

- `subprocess` ではなく、まず `main(argv)` を直接呼ぶ単体テストを優先する
- console script の疎通は smoke test として少数にする
- stdout / stderr は `capsys` で検証する
- JSON は `json.loads()` で検証する
- Windows パス風文字列を fixture に含める

---

## 11. CODEX 向け作業分解

### Task 02-01: CLI result と終了コードの定義

成果物:

- `src/unit_test_runner/cli/exit_codes.py`
- `src/unit_test_runner/cli/result.py`
- 単体テスト

完了条件:

- 終了コード定数を import できる
- `CLIResult` を JSON 化できる

### Task 02-02: argparse parser の実装

成果物:

- `src/unit_test_runner/cli/parser.py`
- グローバルオプション
- サブコマンド定義
- 各サブコマンドの必須引数

完了条件:

- すべての `--help` が exit 0 になる

### Task 02-03: main 関数と例外処理

成果物:

- `src/unit_test_runner/cli/main.py`
- `src/unit_test_runner/__main__.py`
- console script 接続

完了条件:

- `unit-test-runner --help` が動く
- `python -m unit_test_runner --help` が動く

### Task 02-04: doctor コマンド

成果物:

- `doctor` handler
- Python version check
- OS / cwd / temp dir 情報
- JSON 出力対応

完了条件:

- `unit-test-runner doctor` が exit 0
- `unit-test-runner --json doctor` が parse 可能な JSON を返す

### Task 02-05: 未実装コマンド stub

成果物:

- `discover-projects` stub
- `map-source` stub
- `analyze-function` stub
- `build-probe` stub
- `generate-test-draft` stub

完了条件:

- 引数が妥当な場合は exit 20
- JSON モードでも機械処理可能な結果を返す

### Task 02-06: ログ初期化

成果物:

- `utils/logging.py`
- `--verbose`
- `--quiet`
- `--log-file`

完了条件:

- `--log-file` 指定時にログファイルが生成される
- JSON モードの stdout を汚さない

### Task 02-07: テスト整備

成果物:

- `tests/unit/test_cli_parser.py`
- `tests/unit/test_cli_main.py`
- `tests/unit/test_doctor.py`
- `tests/unit/test_not_implemented_commands.py`

完了条件:

- CLI-001 から CLI-013 が通る

---

## 12. 受け入れ基準

Step 02 は、以下をすべて満たしたら完了とする。

1. `unit-test-runner --help` が exit 0 で実行できる
2. `unit-test-runner --version` が exit 0 で実行できる
3. `python -m unit_test_runner --help` が exit 0 で実行できる
4. `doctor` が exit 0 で環境情報を表示できる
5. `--json doctor` が JSON として parse できる
6. 主要サブコマンドの `--help` がすべて exit 0 になる
7. 必須引数不足時に exit 1 になる
8. 未実装サブコマンドが妥当な引数で呼ばれた場合、exit 20 になる
9. `--json` 指定時、stdout が JSON のみになる
10. `--log-file` 指定時、ログファイルが生成される
11. CLI 層に DSW/DSP/C解析の実装が混ざっていない
12. Step 03 の DSW parser を handler へ差し込める構造になっている
13. テストが正常系・異常系を含んでいる

---

## 13. 成果物

Step 02 の成果物は以下とする。

```text
src/
  unit_test_runner/
    __init__.py
    __main__.py
    cli/
      __init__.py
      main.py
      parser.py
      commands.py
      exit_codes.py
      result.py
    utils/
      __init__.py
      logging.py
      paths.py
      platform.py

tests/
  unit/
    test_cli_parser.py
    test_cli_main.py
    test_doctor.py
    test_not_implemented_commands.py
```

必要に応じて Step 01 の `pyproject.toml` に console script を追加する。

---

## 14. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| CLI仕様が後続で頻繁に変わる | DSW/DSP実装時に引数不足が判明する | Step 02 では基本形を固定し、追加引数は後方互換で増やす |
| argparse の exit code が想定とずれる | 標準では parser error が exit 2 になりやすい | parser error を捕捉し exit 1 に変換する |
| JSON mode の stdout がログで汚れる | VS Code extension から parse できない | JSON mode では stdout を JSON 専用にし、ログは file または stderr に制御する |
| Windows パスの空白で壊れる | VC6環境では空白パスが多い | pathlib と quoted path のテストを追加する |
| CLI層に実装が膨らむ | 後続の解析ロジックが main に入り込む | handler は usecase 呼び出しだけに制限する |
| 未実装コマンドの扱いが曖昧 | ユーザーが失敗と誤解する | exit 20 と `not_implemented` status を明確に返す |

---

## 15. 次ステップへの接続

Step 02 完了後、Step 03 の DSW parser は以下の形で接続する。

現在の stub:

```python
def handle_discover_projects(args: argparse.Namespace) -> CLIResult:
    return not_implemented("discover-projects", planned_step="Step 03")
```

Step 03 後:

```python
def handle_discover_projects(args: argparse.Namespace) -> CLIResult:
    request = DiscoverProjectsRequest(
        workspace=args.workspace,
        out=args.out,
    )
    result = discover_projects(request)
    return CLIResult(
        status="ok",
        exit_code=EXIT_OK,
        command="discover-projects",
        message="Projects discovered.",
        data=result.to_dict(),
    )
```

この差し替えが小さく済む構造であることを、Step 02 の設計完了条件とする。

---

## 16. まとめ

Step 02 は、解析機能そのものではなく、今後の解析機能を安全に増設するための CLI 基盤である。

ここで `unit-test-runner` の起動方法、サブコマンド、終了コード、JSON出力、ログ、未実装応答、テスト方針を固定することで、Step 03 以降の DSW parser / DSP parser / 関数解析 / dossier 生成を CODEX が迷わず製造できる状態にする。
