# ADR-0001: CLI層の実装言語選定

作成日: 2026-07-04  
状態: Accepted  
対象: `unitTestRunner` の CLI コア層  
関連文書: `docs/function_level_vc6_unit_test_codex_design.md`

---

## 1. 決定

`unitTestRunner` の CLI コア層は **Python** で実装する。

採用バージョン方針は以下とする。

- ソース互換の下限: Python 3.12
- 開発推奨: Python 3.13 以上
- リリース確認対象: Python 3.12 / 3.13 / 3.14
- エンドユーザー配布: 必要に応じて PyInstaller 等で Windows 向け exe 化する

ただし、層ごとの言語責務は分離する。

| 層 | 採用言語 | 理由 |
|---|---|---|
| CLI コア | Python | DSW/DSP/Cソース解析、レポート生成、CODEX による製造効率を優先 |
| VS Code アダプタ | TypeScript | VS Code extension の標準的な開発体験に合わせる |
| 生成されるテストコード | C90 互換 C | VC6 でコンパイル可能にするため |
| 将来のスタンドアロン GUI | 未決定 | CLI コアを呼び出す薄い UI として後続判断 |

---

## 2. 背景

本ツールの初期フェーズでは、リアルタイム性やハードウェア割込制御には踏み込まない。
まず、ユーザーが指定した `.c` ファイル内の関数について、以下を収集・生成する。

- `.dsw` / `.dsp` から所属 VC6 プロジェクトを特定する
- 構成別の define / include ディレクトリ / compiler option を収集する
- 対象 `.c` と関連ヘッダのファイル構成を選定する
- 指定関数のシグネチャ、引数、戻り値を解析する
- 参照・更新するグローバル変数候補を抽出する
- 外部呼び出し、スタブ候補を抽出する
- 分岐条件、条件網羅、境界値、同値クラス候補を出力する
- `function_dossier.json` / Markdown / CSV を生成する

このため、CLI層には「古いVC6プロジェクトファイルとC90相当のCソースを読み、テキスト・JSON・CSV・Markdownを安定して生成する」能力が求められる。

---

## 3. 評価基準

言語選定では、以下を重視した。

| 評価項目 | 重み | 内容 |
|---|---:|---|
| テキスト解析・レポート生成の容易さ | 25 | DSW/DSP/C/ログ/JSON/CSV/Markdown を扱いやすいこと |
| CODEX 製造効率 | 20 | 小さなタスク単位で実装・修正・テストしやすいこと |
| Windows 開発環境での扱いやすさ | 15 | VC6 開発環境から呼び出しやすく、パス・文字コード・プロセス実行を扱えること |
| 配布容易性 | 15 | Python 未導入環境でも exe 化などの逃げ道があること |
| 単体テスト容易性 | 10 | パーサ、解析器、レポート生成器を fixture で検証しやすいこと |
| VS Code 連携との分離 | 5 | VS Code extension と疎結合にできること |
| 性能 | 5 | 大規模ソースでも実用時間で解析できること |
| 長期保守性 | 5 | 担当者が増えても読みやすく保守しやすいこと |

---

## 4. 候補比較

### 4.1 比較結果

| 候補 | 総合評価 | 採否 | コメント |
|---|---:|---|---|
| Python | 92 | 採用 | テキスト解析、レポート生成、CODEX 製造効率、テスト容易性が最も高い |
| C# / .NET | 80 | 次点 | Windows 親和性は高いが、初期の解析・レポート実装速度は Python に劣る |
| Go | 76 | 保留 | 単体 exe 配布は強いが、C解析とレポート生成の試行錯誤では Python より重い |
| TypeScript / Node.js | 72 | VS Code 層のみ採用 | VS Code 連携には最適だが、CLI コアを Node に寄せる必然性は薄い |
| Rust | 64 | 不採用 | 品質は高いが、初期フェーズの製造速度と保守負荷に対して過剰 |
| C / C++ | 50 | 不採用 | VC6対象コードとの距離は近いが、ツール製造コストが高く、本件の価値に合わない |

### 4.2 Python

長所:

- DSW/DSP のような古いテキストフォーマットを段階的に解析しやすい
- `json` / `csv` / `argparse` / `pathlib` / `subprocess` など標準ライブラリだけでも MVP を作りやすい
- Markdown、CSV、JSON Schema、ログ解析との相性がよい
- fixture ベースの単体テストを書きやすい
- CODEX が小さなタスク単位で実装しやすい
- PyInstaller 等により、Python 未導入環境向けの exe 配布も検討できる
- 解析精度が足りない箇所を後からモジュール単位で差し替えやすい

短所:

- 実行には Python ランタイム、または exe 化された配布物が必要
- 動的型付けのため、型設計を怠ると保守性が落ちる
- 単体 exe 化した場合、ファイルサイズが大きくなりやすい
- 実行速度は Go / Rust / C# より不利な場面がある

対策:

- 型ヒントを必須化する
- `dataclasses` を活用する
- `mypy` または `pyright` の導入を検討する
- パーサ、解析器、レポート生成器を明確に分離する
- エンドユーザー向けには exe 化した配布物を用意できる構成にする

### 4.3 C# / .NET

長所:

- Windows との親和性が高い
- プロセス実行、ファイル監視、GUI 連携が強い
- 型安全性が高い
- 将来スタンドアロン GUI を作る場合に接続しやすい

短所:

- 初期 MVP のテキスト解析・レポート生成では Python より実装量が増えやすい
- .NET Runtime / SDK の配布・バージョン管理が必要になる
- CODEX による小刻みなパーサ改善では Python のほうが速い

判定:

- CLI コアの初期採用はしない
- Windows 専用 GUI や企業内配布要件が強くなった場合の移行候補とする

### 4.4 Go

長所:

- 単体 exe 配布がしやすい
- CLI ツールとしての起動が速い
- クロスプラットフォーム対応がしやすい
- 静的型付けで保守しやすい

短所:

- 試行錯誤が多いCソース軽量解析では Python より書き直しコストが高い
- Markdown / CSV / JSON 生成は可能だが、細かいテキスト整形は Python より重い
- CODEX 製造効率は Python に劣る

判定:

- Python 配布が運用上受け入れられない場合の再選定候補とする

### 4.5 TypeScript / Node.js

長所:

- VS Code extension との相性が最もよい
- JSON 処理と非同期処理に強い
- VS Code アダプタの製造に適している

短所:

- CLI コアとして使う場合、Node.js ランタイムまたはパッケージングが必要
- Windows の古い開発環境、VC6、バッチ、パス、文字コードとの付き合いでは Python のほうが素直
- C解析・ログ解析・レポート生成を CLI として安定運用する主言語にする強い理由がない

判定:

- VS Code アダプタ層には採用する
- CLI コアには採用しない

### 4.6 Rust

長所:

- 高速
- 単体バイナリ配布がしやすい
- 型安全性が高い

短所:

- 初期製造コストが高い
- CODEX による小刻みな仕様変更・解析ルール追加の速度が落ちやすい
- 本件のボトルネックは性能ではなく、解析ルールの発見とレポート設計である

判定:

- 初期採用しない

### 4.7 C / C++

長所:

- VC6 / C90 対象コードに近い
- 低レベル制御が可能

短所:

- ツール本体の製造コストが高い
- 文字コード、JSON、CSV、Markdown、CLI、テスト fixture の実装負荷が大きい
- 本番対象コードとテスト支援ツールの責務が混ざりやすい

判定:

- 採用しない

---

## 5. 公式情報から見た補足

Python のサポート状況は、Python Developer's Guide の status table を参照する。
2026-07-04 時点では、Python 3.12 は security、Python 3.13 と 3.14 は bugfix のステータスであるため、下限を 3.12 とし、開発推奨を 3.13 以上とする。

Python on Windows では、Python は Windows に標準搭載されないため、Python Install Manager、venv、または配布 exe のいずれかを前提にする必要がある。

PyInstaller は Windows 8 以降で動作するとされているため、Python 未導入環境向け配布の有力候補とする。

VS Code extension は TypeScript / JavaScript のプロジェクトとして scaffolding する流れが公式に案内されており、TypeScript が推奨されているため、VS Code アダプタ層は TypeScript とする。

---

## 6. アーキテクチャ上の決定

### 6.1 CLI コアを中心にする

VS Code extension や将来 GUI は、CLI を呼び出す薄いアダプタとする。

```text
[VS Code Extension: TypeScript]
        |
        | spawn CLI
        v
[unit-test-runner CLI: Python]
        |
        +-- DSW/DSP parser
        +-- build context collector
        +-- C function analyzer
        +-- dossier generator
        +-- report generator
        v
[generated artifacts]
        +-- function_dossier.json
        +-- function_dossier.md
        +-- test_case_design.csv
        +-- build_probe files
        +-- generated C90 test skeleton
```

### 6.2 Python パッケージ構成

```text
src/
  unit_test_runner/
    __init__.py
    cli/
      __init__.py
      main.py
      commands.py
    vc6/
      __init__.py
      dsw_parser.py
      dsp_parser.py
      build_context.py
      source_mapper.py
    c_analyzer/
      __init__.py
      lexer.py
      function_locator.py
      signature.py
      globals.py
      calls.py
      branches.py
      boundary.py
    dossier/
      __init__.py
      schema.py
      models.py
      writer.py
    reports/
      __init__.py
      markdown.py
      csv_writer.py
      json_writer.py
    workspace/
      __init__.py
      extractor.py
      build_probe.py
    utils/
      __init__.py
      paths.py
      encoding.py
      process.py
      logging.py
```

### 6.3 CLI エントリポイント

```bat
unit-test-runner discover-projects --workspace D:\work\product --out reports\projects.json
unit-test-runner map-source --dsw D:\work\product\Product.dsw --source src\control.c
unit-test-runner analyze-function --dsw D:\work\product\Product.dsw --source src\control.c --function Control_Update --configuration "Win32 Debug" --out D:\work\unit_test_workspace\Control_Update
unit-test-runner build-probe --dossier D:\work\unit_test_workspace\Control_Update\reports\function_dossier.json
```

---

## 7. 実装ルール

### 7.1 Python コーディングルール

- Python 3.12 互換構文を使う
- すべての公開関数に型ヒントを付与する
- データ構造は `dataclasses` を優先する
- パーサ戻り値は `dict` 乱用ではなく model class にまとめる
- ファイル読み込みは文字コードを明示する
- 文字コードは `utf-8-sig`、`cp932`、`shift_jis` の候補を扱えるようにする
- 改行コードは可能な限り保持する
- Windows パスと相対パス解決は `pathlib` に集約する
- VC6 / nmake / cl.exe の実行は `subprocess` ラッパに集約する
- 例外を握りつぶさず、dossier と log に警告として残す

### 7.2 依存ライブラリ方針

MVP は標準ライブラリ中心とする。

MVP で使ってよい標準ライブラリ例:

- `argparse`
- `json`
- `csv`
- `re`
- `pathlib`
- `subprocess`
- `dataclasses`
- `typing`
- `logging`
- `hashlib`
- `shutil`
- `tempfile`

外部依存は、必要性が明確になってから追加する。
候補:

- `jsonschema`: `function_dossier.json` の schema 検証
- `pytest`: fixture ベースの単体テスト
- `pyinstaller`: Windows exe 配布
- `mypy` または `pyright`: 型チェック
- `ruff`: lint / format

### 7.3 生成コードの言語制約

CLI 本体が Python でも、生成されるテストコードは VC6 / C90 互換を守る。

生成 C コードでは以下を避ける。

- C99 以降の構文
- `stdint.h`
- `stdbool.h`
- 変数宣言の途中配置
- `for (int i = 0; ... )`
- `inline`
- 可変長配列
- `snprintf` 前提
- C++ 専用構文

---

## 8. 配布方針

### 8.1 開発者向け

開発者は Python 仮想環境で実行する。

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e .
unit-test-runner --help
```

### 8.2 ユーザー向け

ユーザー向けには、以下のどちらかを用意する。

1. Python インストール前提の zip 配布
2. PyInstaller 等で固めた Windows exe 配布

初期は 1 を優先し、運用で Python 導入が難しいことが分かった時点で 2 を正式化する。

### 8.3 VS Code 連携

VS Code extension は TypeScript で実装し、設定値から CLI パスを取得する。

設定例:

```json
{
  "unitTestRunner.cliPath": "D:/tools/unit-test-runner/unit-test-runner.exe",
  "unitTestRunner.dswPath": "D:/work/product/Product.dsw",
  "unitTestRunner.outputRoot": "D:/work/unit_test_workspace",
  "unitTestRunner.defaultConfiguration": "Win32 Debug"
}
```

---

## 9. CODEX 向け製造指示

CODEX は、Python CLI コアを以下の順で製造する。

1. Python package skeleton
2. CLI entry point
3. DSW parser
4. DSP parser
5. source-to-project mapper
6. build context collector
7. C source lexer / masker
8. function locator
9. signature extractor
10. global access candidate analyzer
11. call candidate analyzer
12. branch / condition candidate analyzer
13. boundary / equivalence candidate generator
14. function dossier writer
15. Markdown / CSV report writer
16. build-probe runner
17. PyInstaller packaging prototype
18. TypeScript VS Code thin adapter

各タスクでは fixture を必ず追加し、少なくとも正常系 1 件と異常系 1 件をテストする。

---

## 10. 再選定条件

以下の条件が発生した場合、CLI コア言語の再選定を行う。

| 条件 | 再選定候補 |
|---|---|
| Python 導入・exe 配布が運用上認められない | Go / C# |
| Windows GUI が主目的になり、CLI が従になる | C# |
| 解析対象が数百万行規模になり、Python 実装で実用速度を満たせない | Go / Rust |
| VS Code extension 内だけで完結させる要求が強くなる | TypeScript / Node.js |
| 企業標準で .NET が必須になる | C# |

---

## 11. 結論

初期フェーズの価値は、VC6/C90 の巨大な既存コードに対して、関数単位の単体テスト準備情報を素早く、反復的に、レビュー可能な形で生成することである。

この目的では、実行速度や単体バイナリ配布よりも、テキスト解析の柔軟性、レポート生成の容易さ、CODEX による製造効率、fixture ベースの改善速度が重要になる。

そのため、CLI コア層は Python を採用する。
VS Code 連携は TypeScript の薄いアダプタとし、生成されるテストコードは VC6 / C90 互換 C に限定する。
