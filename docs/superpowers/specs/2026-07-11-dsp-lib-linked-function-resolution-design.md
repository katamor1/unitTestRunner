# DSP/LIB解析によるリンク済み関数のスタブ除外設計

## 目的

UnitTestRunnerが生成する関数単体テストでは、対象関数から呼ばれる外部関数を原則スタブ候補として扱っている。しかし、選択中のVC6 DSP構成で実際にリンクされる静的ライブラリまたはDLL import libraryがその関数を提供している場合、スタブ生成は不要であり、実ライブラリと生成スタブの重複定義を招く可能性もある。

本機能は、DSP/DSWから実際のリンク対象ライブラリを解決し、Microsoft COFF archiveのシンボル表で関数提供を確認できた場合だけ、その呼び出しを `linked_library_function` と分類してスタブ生成対象から除外する。

## 非目標

- C++マングル名の解析とデマングル
- DSW依存の推移的探索
- workspace内の全 `.lib` の総当たり検索
- `.lib` の生成workspaceへのコピー
- 永続シンボルキャッシュ
- 対応DLLのビルド時存在検証
- COFF解析に失敗したライブラリを根拠とするスタブ除外
- `.lib` と `/libpath:` 以外のLINK32オプションを完全再現すること

## 確定した方針

- 実在する `.lib` のシンボル表に対象関数が存在すると確認できた場合だけスタブ除外する。
- COFF archiveはPython標準ライブラリだけで解析する。
- C関数の代表的なVC6装飾を正規化する。
- 選択中DSP構成の明示ライブラリと、DSWの直接依存プロジェクトだけを対象にする。
- 依存プロジェクトは対象と同じ platform/configuration の構成だけを使う。
- 依存ライブラリ出力は `/implib:`、`.lib` を指す `/out:`、`Output_Dir/ProjectName.lib` の順で解決する。
- 解決済みライブラリはコピーせず、絶対パスで生成DSP/Makefileへ追加する。
- COFF解析失敗時はライブラリをリンク入力には残すが、スタブ除外は行わない。
- 複数ライブラリが同じ関数を提供する場合はリンク順先頭を主提供元にする。
- 静的ライブラリとDLL import libraryの両方を提供元として認める。
- リンカーメンバーを優先し、必要な場合だけ通常COFF objectを走査する。
- シンボル索引は1回のCLIプロセス内だけキャッシュする。

## アーキテクチャ

### 1. DSPリンク設定モデル

`src/unit_test_runner/vc6/dsp_models.py` に、コンパイラ設定とは独立したリンク設定モデルを追加する。

```python
@dataclass
class DspLinkSettings:
    raw_options: list[str]
    libraries: list[str]
    library_dirs: list[PathLikeValue]
    output_file: PathLikeValue | None
    import_library: PathLikeValue | None
    output_dir: PathLikeValue | None
    intermediate_dir: PathLikeValue | None
    unresolved_macros: list[str]
```

`DspConfiguration` に `link_settings: DspLinkSettings` を持たせる。既存の `build_settings` はコンパイラ設定として維持する。

### 2. DSP parser拡張

`src/unit_test_runner/vc6/dsp_parser.py` は、構成ブロック内で以下を解析する。

```text
# ADD LINK32 foo.lib bar.lib /libpath:"..\lib" /out:"Debug\App.exe"
# ADD LINK32 /implib:"Debug\Product.lib"
# PROP Output_Dir "Debug"
# PROP Intermediate_Dir "Debug"
```

解析規則は次の通り。

- `.lib` トークンは記載順を保持する。
- `/libpath:`、`/out:`、`/implib:` は値を分離して保存する。
- `# ADD BASE LINK32` は基底設定として保持し、通常の `# ADD LINK32` を同じ構成へ順序を壊さずマージする。
- `Output_Dir` と `Intermediate_Dir` は構成単位で保持する。
- マクロを含むパスは未解決のまま記録し、後続resolverで解決する。

### 3. リンクライブラリ解決

新規モジュールを追加する。

```text
src/unit_test_runner/vc6/link_context.py
src/unit_test_runner/vc6/link_library_resolver.py
```

主な公開モデルは次を想定する。

```python
@dataclass
class ResolvedLinkLibrary:
    path: Path
    source: str
    link_order: int
    project_name: str | None
    configuration: str | None
    exists: bool

@dataclass
class LinkContext:
    libraries: list[ResolvedLinkLibrary]
    library_dirs: list[Path]
    warnings: list[LinkContextWarning]
```

#### 3.1 明示LINK32ライブラリ

選択中プロジェクト・構成の `LINK32` に記載された `.lib` を先に解決する。解決順は以下。

1. 絶対パス
2. DSPディレクトリ相対
3. `/libpath:` ディレクトリ
4. 環境変数 `LIB` の各ディレクトリ

環境変数 `LIB` はWindows形式のセミコロン区切りとして扱う。`/libpath:` 自体もマクロ展開し、実在ディレクトリだけを生成リンク設定へ引き継ぐ。

#### 3.2 直接依存プロジェクト

DSWの依存関係から、選択中プロジェクトの直接依存だけを記載順に取得する。依存先の依存先は探索しない。

依存プロジェクトでは、対象プロジェクトと同じ platform と短いconfiguration名を大文字小文字を区別せず比較し、一致する構成だけを選択する。対応構成がない場合は `dependency_configuration_not_found` を記録し、その依存プロジェクトをリンク提供元に使わない。

依存プロジェクト出力 `.lib` は次の優先順位で解決する。

1. `/implib:"...lib"`
2. `/out:"...lib"` が `.lib` を指す場合
3. `Output_Dir/ProjectName.lib`

優先順位は候補集合ではなく段階的フォールバックとして扱う。上位段階で実在する候補が一意に解決できたら、下位段階は評価しない。各段階で実在候補が複数ある場合は `dependency_library_output_ambiguous` を記録して採用しない。全段階で候補が0件なら `link_library_not_found` を記録する。

#### 3.3 マクロ展開

次をサポートする。

```text
$(OUTDIR)
$(INTDIR)
$(CFG)
$(NAME)
$(ENV_VAR)
${ENV_VAR}
%ENV_VAR%
($ENV_VAR)
```

`OUTDIR` と `INTDIR` はDSP構成値、`CFG` は構成名、`NAME` はプロジェクト名を使う。それ以外はプロセス環境変数から解決する。未解決マクロを含む候補は採用せず警告を残す。

#### 3.4 最終リンク順

```text
明示LINK32ライブラリ（DSP記載順）
→ 直接依存プロジェクト出力（DSW依存記載順）
```

同じ実体パスは、最初に現れたものを残して重複排除する。

## COFF archive解析

新規モジュール `src/unit_test_runner/vc6/coff_archive.py` を追加する。

### 1. 対応範囲

- Microsoft COFF archiveシグネチャ `!<arch>\n`
- 第1リンカーメンバー
- 第2リンカーメンバー
- 長いファイル名テーブル `//`
- 通常COFF objectメンバー
- Microsoft import object

### 2. 解析順

1. 第1リンカーメンバーから公開シンボルを読む。
2. 第2リンカーメンバーが有効なら追加情報を読む。
3. リンカーメンバーが指すメンバーのヘッダーを確認し、通常COFF objectかimport objectかを判定する。
4. import objectメンバーを解析する。
5. リンカーメンバーが欠落または破損している場合だけ、通常COFF objectのシンボル表を走査する。
6. どの方法でも信頼できる索引を作れなければ `scan_status = failed` とする。

通常の大規模ライブラリで全object走査を避け、Quick Checkの応答時間を維持する。

### 3. 結果モデル

```python
@dataclass
class LibrarySymbol:
    raw_name: str
    normalized_name: str | None
    provider_kind: str
    member_name: str | None

@dataclass
class LibrarySymbolIndex:
    library_path: Path
    scan_status: str
    symbols_by_normalized_name: dict[str, list[LibrarySymbol]]
    warnings: list[LibraryScanWarning]
```

`provider_kind` は `static_library` または `import_library` とする。

### 4. Cシンボル正規化

以下を同じ関数 `Foo` とみなす。

```text
Foo
_Foo
_Foo@8
Foo@8
__imp__Foo
__imp__Foo@8
```

正規化規則。

1. `__imp__` または `__imp_` 接頭辞を除去する。
2. 先頭 `_` を1つ除去する。
3. 末尾 `@<decimal>` を除去する。
4. C識別子として有効なら正規化名とする。
5. `?Foo@@...` のようなC++マングル名は正規化対象外とする。

### 5. CLI実行内キャッシュ

キャッシュキーは次とする。

```python
(
    resolved_absolute_path,
    file_size,
    mtime_ns,
)
```

同じCLI実行内で同一ライブラリを複数経路から参照しても1回だけ解析する。キャッシュは永続化しない。

## 呼び出し解析への統合

### 1. データフロー

`analyze_function_workflow` は、プロジェクト選択後に `LinkContext` と全ライブラリの `LibrarySymbolIndex` を構築し、`analyze_calls` へ渡す。

```text
DSW/DSP解析
→ LinkContext構築
→ COFF symbol index構築
→ call analyzer
→ test design
→ harness generation
→ build workspace
```

リンク判定をハーネス生成直前やリンク失敗後に遅延させない。`call_report.json`、テスト設計、生成スタブを最初から一貫させる。

既存呼び出し元との互換性を保つため、`analyze_calls` のリンクコンテキスト引数は省略可能とし、省略時は従来どおりライブラリ照合なしで解析する。

### 2. 判定順

呼び出し先分類は次の順とする。

```text
macro_like
→ function_pointer
→ same_file_static_function / same_file_function
→ standard_library
→ linked_library_function
→ external_function
```

標準ライブラリ判定をライブラリ判定より先に置き、既存のCRT分類を維持する。

### 3. 提供元モデル

`FunctionCall` にデフォルト値付きで以下を追加する。

```python
link_provider: LinkProvider | None = None
link_providers: list[LinkProvider] = field(default_factory=list)
```

```python
@dataclass
class LinkProvider:
    library: Path
    symbol: str
    provider_kind: str
    source: str
    link_order: int
    project_name: str | None
```

JSON例。

```json
{
  "name": "ProductCalc",
  "target_kind": "linked_library_function",
  "link_provider": {
    "library": "C:/product/lib/ProductCore.lib",
    "symbol": "_ProductCalc@8",
    "provider_kind": "static_library",
    "source": "explicit_link32",
    "link_order": 0,
    "project_name": "ProductCore"
  },
  "link_providers": [
    {
      "library": "C:/product/lib/ProductCore.lib",
      "symbol": "_ProductCalc@8",
      "provider_kind": "static_library",
      "source": "explicit_link32",
      "link_order": 0,
      "project_name": "ProductCore"
    }
  ]
}
```

### 4. 複数提供元

同じ正規化関数名が複数ライブラリに存在する場合は、最終リンク順で最初の提供元を `link_provider` にする。`link_providers` は主提供元を含む全提供元をリンク順で保持し、`multiple_library_symbol_providers` 警告を記録する。

1つ以上の提供元を確認できれば `linked_library_function` とし、スタブ候補から除外する。archiveの遅延取り込みを考慮し、複数提供元だけを根拠に重複定義エラーとは判定しない。

### 5. スタブ候補

`_stub_candidates` は `linked_library_function` を候補に含めない。これにより、テストケース設計の `stub_setups` と `generated/stubs` の両方から除外される。

## 解析失敗時の保守的挙動

実在する `.lib` の解析に失敗した場合は次の通り。

- ライブラリは生成DSP/Makefileのリンク入力へ追加する。
- そのライブラリを根拠に関数を `linked_library_function` にしない。
- 呼び出しは `external_function` のまま残す。
- スタブ候補は残す。
- `library_symbol_scan_failed` を記録する。
- 生成スタブは既存どおり `review_required` とする。

この挙動は、誤ってスタブを除外して未解決リンクを作るより、リンク時の重複や競合を診断可能な形で残すことを優先する。

## ビルドworkspaceへの反映

### 1. build_context

`build_context.json` に以下を追加する。

```json
{
  "link_libraries": [
    {
      "path": "C:/product/lib/ProductCore.lib",
      "source": "explicit_link32",
      "link_order": 0,
      "project_name": "ProductCore",
      "exists": true
    }
  ],
  "library_dirs": [
    "C:/product/lib"
  ],
  "link_context_warnings": []
}
```

### 2. Makefile

解決済みライブラリを元の絶対パスのままリンクコマンドへ追加する。コピーはしない。

```text
LINK_LIBS="C:\product\lib\ProductCore.lib" ...
```

リンク順を維持する。必要な実在 `/libpath:` も引き継ぐ。

### 3. VC6 debug DSP

生成DSPの `LINK32` に解決済みライブラリを絶対パスで追加する。明示ライブラリと依存プロジェクト出力の順序を維持する。

## 警告コード

最低限、以下を実装する。

```text
link_library_not_found
link_library_macro_unresolved
dependency_configuration_not_found
dependency_library_output_ambiguous
library_symbol_scan_failed
unsupported_coff_member
multiple_library_symbol_providers
```

各警告は、対象プロジェクト、構成、ライブラリ候補、原因を可能な範囲で含める。

## レポート

新規の独立レポートは初期実装では追加しない。既存成果物へ情報を統合する。

- `build_context.json`
  - 解決済みライブラリ
  - library path
  - 解決警告
- `call_report.json` / `.md`
  - `linked_library_function`
  - `link_provider`
  - `link_providers`
  - 複数提供元警告
- `build_workspace_report.json` / `.md`
  - 実際のリンクライブラリ一覧
  - 実際のlibrary path
- `quick_summary.json` / `.md`
  - 解決済みライブラリ数
  - ライブラリによりスタブ除外された関数数
  - ライブラリ解決・解析警告数

## エラー処理

- DSPのLINK32解析が部分的でも、既存の解析・ハーネス生成は継続する。
- 実在しないライブラリはリンク入力へ追加しない。
- 解析不能ライブラリはリンク入力へ追加するが、スタブ除外には使わない。
- COFFメンバー範囲や整数フィールドが不正なら、そのライブラリの解析を安全に中止する。
- 巨大または不正なサイズ値でファイル外参照を行わない。
- 同一関数に複数提供元がある場合は警告のみで処理を継続する。

## セキュリティと堅牢性

COFF parserは信頼できないバイナリを扱う前提で実装する。

- すべてのoffset/lengthをファイルサイズに対して検証する。
- メンバー数、シンボル数、名前長に現実的な上限を設ける。
- 再帰解析を行わない。
- mmapを必須にせず、範囲を限定して読み取る。
- 解析エラーでCLI全体をクラッシュさせず、F1の警告経路へ落とす。

## テスト計画

### DSP parser

1. `LINK32` の `.lib` 順序を保持する。
2. `/libpath:`、`/out:`、`/implib:` を解析する。
3. `Output_Dir` と `Intermediate_Dir` を構成ごとに保持する。
4. BASEと非BASE設定を正しくマージする。
5. マクロを含むパスを保持する。

### ライブラリ解決

6. 明示ライブラリを絶対、DSP相対、`/libpath:`、`LIB` の順で解決する。
7. 直接依存だけを対象にし、推移依存は使わない。
8. 同じplatform/configurationだけを使う。
9. `/implib:` を最優先する。
10. `.lib` の `/out:` を次に使う。
11. `Output_Dir/ProjectName.lib` を既定候補にする。
12. 複数候補ではスタブ除外しない。
13. 実在しない候補をリンク入力に追加しない。
14. リンク順と重複排除を確認する。

### COFF archive

15. 第1リンカーメンバーを解析する。
16. 第2リンカーメンバーを解析する。
17. import objectを解析する。
18. リンカーメンバー破損時に通常objectへフォールバックする。
19. 不正offset/lengthを安全に拒否する。
20. `_Foo@8`、`__imp__Foo@8` を `Foo` に正規化する。
21. C++マングル名を対象外にする。
22. 同一CLI実行内キャッシュが再解析を防ぐ。

### 統合

23. 明示ライブラリ提供関数が `linked_library_function` になる。
24. 直接依存ライブラリ提供関数が `linked_library_function` になる。
25. `link_provider` がリンク順先頭になる。
26. 複数提供元警告が出る。
27. ライブラリ提供関数が `stub_candidates` に入らない。
28. テスト設計に該当関数のstub setupが出ない。
29. `generated/stubs/stub_<name>.c` が生成されない。
30. 解析失敗時はスタブ候補が残る。
31. 生成MakefileとDSPへ絶対ライブラリパスが追加される。
32. quick summaryに件数と警告が反映される。

## 受け入れ条件

- 選択中DSP構成の実リンク対象 `.lib` だけが解析対象になる。
- 直接依存プロジェクトは同じplatform/configurationの実在出力だけを使う。
- シンボル確認済み関数だけが `linked_library_function` になる。
- `linked_library_function` のスタブファイルは生成されない。
- 解決済み `.lib` はコピーされず、生成DSP/Makefileへ絶対パスで追加される。
- COFF解析失敗時にスタブが誤って除外されない。
- import libraryの関数も正しく検出できる。
- 複数提供元ではリンク順先頭を主提供元として記録する。
- 既存の同一ファイル関数、標準ライブラリ、外部関数の分類を壊さない。
- Quick Checkの既存4ステップ導線を維持し、不要スタブによるリンク競合を減らす。
