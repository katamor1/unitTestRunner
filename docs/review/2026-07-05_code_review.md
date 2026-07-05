# unitTestRunner 全体コードレビュー

作成日: 2026-07-05  
対象リポジトリ: `katamor1/unitTestRunner`  
対象ブランチ: `main`  
レビュー種別: 静的コードレビュー  
実行テスト: 未実施。GitHub上のソース閲覧によるレビュー。

---

## 1. 総評

`unitTestRunner` は、計画文書だけでなく Python CLI、VC6 DSW/DSP解析、Cソース解析、dossier生成、build probe、build completion、test execution、VS Code Thin Adapter まで、かなり広い範囲の実装が入っている。

全体として、以下の方向性は良い。

- Python標準ライブラリ中心で実装されている
- `pyproject.toml` に console script が定義され、CLIとして使える
- READMEにfixtureを使ったsmoke flowが整理されている
- VC6 / C90 / CP932 / CRLF への配慮が入っている
- DSW/DSP解析、Cソース解析、テスト設計、ビルド、実行、エビデンスが段階的な成果物として出る
- 本番リポジトリ非侵襲という方針が多くの箇所で維持されている
- VS Code側はCLIを呼び出す薄いadapterに寄せられている

一方で、実コードは計画より先に多くのStepを一気に取り込んでおり、いくつかの箇所で **CLIオプションが効かない、実行結果の終了コードが不適切、VS Code extensionがコンパイルできない可能性、build probeがVCVARSを使う前に環境なし判定してしまう** など、実運用前に直すべき問題がある。

現時点の評価は次の通り。

| 観点 | 評価 | コメント |
|---|---|---|
| アーキテクチャ方針 | 良い | CLI中心、成果物分割、本番非侵襲は妥当 |
| 実装の到達度 | 高い | Step 17〜19相当までかなり実装が進んでいる |
| 安定性 | 要改善 | build/test/VS Code周辺に実行時不具合候補あり |
| 保守性 | 中 | `dossier.py` と `dossier/` packageの併存など構造負債あり |
| テスト容易性 | 中〜良 | fixtureは多いが、CLI policyやVS Code compileを捕まえるテストが不足 |
| 直近の推奨 | 高優先度バグ修正後、MVP-1〜MVP-2の安定化 | 広げるより固める段階 |

---

## 2. 良い点

### 2.1 CLIエントリポイントが整理されている

`pyproject.toml` で `unit-test-runner = "unit_test_runner.cli.main:main"` が定義されており、CLIツールとしての入口は明確である。

`cli/main.py` では、parse error、`CLIError`、想定外例外を `CLIResult` に変換し、JSON modeではstdoutへJSONを出す構成になっている。これはVS Code adapterとの接続に向いている。

### 2.2 VC6レガシー入力への配慮がある

`encoding.py` では `utf-8-sig`、`utf-8`、`cp932`、`shift_jis` の順で読み込みfallbackする。生成Cは `cp932` / CRLF を意識している。

これはVC6時代の日本語コメントやWindows環境に対して現実的である。

### 2.3 DSW/DSP解析は最小実用ラインを押さえている

`dsw_parser.py` はProject行、DSP path、dependency、missing DSP、unknown lineを扱っている。

`vc6/dsp_parser.py` はconfiguration、`# ADD CPP`、source file、group、custom build detectionを扱っており、Step 03/04のMVPとしては良い出発点である。

### 2.4 中間成果物モデルが多く、レビューしやすい

`source_digest`、`function_location`、`function_signature`、`global_access`、`call_report`、`coverage_design`、`boundary_equivalence_candidates`、`test_case_design`、`function_dossier` などが分かれている。

これにより、解析失敗時にどこで崩れたか追いやすい。

### 2.5 VS Code adapterの責務分離は良い

`vscode/extension/src/extension.ts` はCLIを呼び出し、レポートを開く薄いadapterとして作られている。DSW/DSP解析やC解析をVS Code側に持ち込んでいない点は、これまでの方針と合っている。

---

## 3. 重大度Highの指摘

### CR-001: VS Code extensionがTypeScript compileで失敗する可能性が高い

**対象:** `vscode/extension/src/extension.ts`

`openReport()` の中で `openPlainFile(reportPath)` を呼んでいるが、同ファイル内に `openPlainFile` の定義が見当たらない。

該当箇所:

```ts
async function openReport(reportPath: string): Promise<void> {
  if (path.extname(reportPath).toLowerCase() === '.md') {
    await openMarkdown(reportPath);
    return;
  }
  await openPlainFile(reportPath);
}
```

**影響:**

`package.json` では `npm test` が `npm run compile && node --test dist/test/*.test.js` を実行するため、TypeScript compile時に `Cannot find name 'openPlainFile'` で失敗する可能性が高い。

**推奨修正:**

以下を追加する。

```ts
async function openPlainFile(filePath: string): Promise<void> {
  await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(filePath));
}
```

また、VS Code extensionの `npm test` をCIまたはPython側のsmoke testからも実行できるようにする。

---

### CR-002: build-probeが`vcvars`指定を有効活用できない

**対象:** `src/unit_test_runner/build/build_workspace_generator.py`

`_render_build_bat()` は `vcvars` が指定されていれば `call VCVARS32.BAT` を入れる設計になっている。

しかし、実際にbuildを走らせる前の `_build_probe_report()` では、先に現在のPythonプロセスPATHだけを見て `nmake` / `cl` を探している。

```python
nmake = shutil.which("nmake")
cl = shutil.which("cl")
if not nmake and not cl:
    status="environment_missing"
```

そのため、VC6のbinがPATHにないが `--vcvars` を渡している通常ケースで、`build.bat` を実行する前に `environment_missing` で止まる。

**影響:**

VC6環境では、VCVARS32.BATでPATH/INCLUDE/LIBをセットしてからnmake/clを使う運用が普通である。現在の順序だと `--vcvars` が実質的に効かない。

**推奨修正:**

- `vcvars` が指定されている場合は、事前の `shutil.which()` 判定をskipして `build.bat` を実行する
- または `cmd /c "call vcvars32.bat && where nmake && where cl"` のように、vcvars適用後の環境で検出する
- `nmake` が必要なMakefile運用なので、少なくとも `nmake` の存在確認を重視する

---

### CR-003: build-probe失敗時もCLI終了コードが0になる

**対象:** `src/unit_test_runner/cli/commands.py`

`_build_probe_result()` は `probe_report.status` が `failed` でも常に `EXIT_OK` を返している。

```python
return CLIResult(
    status="build_workspace_generated" if not probe_report.executed else f"build_probe_{probe_report.status}",
    exit_code=EXIT_OK,
    ...
)
```

**影響:**

VS Code adapterやバッチ処理から見ると、build probeが失敗してもプロセスとして成功扱いになる。Step 02/14の計画では build-probe失敗は専用終了コードで扱う方針だったため、CLI contractとズレる。

**推奨修正:**

- `probe_report.executed and probe_report.status == "failed"` の場合は `EXIT_BUILD_PROBE_FAILED`、少なくとも非0終了コードにする
- ただし「診断抽出成功」をCLI成功扱いしたい場合は、`--json` payloadだけでなく明確な設計判断をADRまたはCLI仕様に追記する
- VS Code側は非0でも `build_probe_report.md` を開けるようにする

---

### CR-004: 追加スタブ補完がcall_reportの引数情報を使っていない

**対象:**

- `src/unit_test_runner/build_completion/stub_completion.py`
- `src/unit_test_runner/build_completion/completion_applier.py`

`stub_completion.py` では、未解決symbolが `call_report` に一致した場合、`parameter_strategy = "from_call_arguments"` として高confidenceのstub候補にしている。

しかし `completion_applier.py` の `_write_stub()` は、常に次の形のスタブを生成する。

```c
int FunctionName(void)
```

**影響:**

実際の呼び出しが `ReadAdValue(channel)` や `WritePort(port, value)` の場合、`int ReadAdValue(void)` ではコンパイル・リンク整合性が取れない。既知callであっても、追加スタブがビルドエラーを解消しない可能性がある。

**推奨修正:**

- `StubCompletionCandidate.parameter_strategy == "from_call_arguments"` の場合、call_reportの引数数から最低限の仮parameterを生成する
- 可能なら `call_report.calls[].arguments` から `int arg0`, `int arg1` のようなC90 placeholderを作る
- signature不明のunknown symbolは `auto_safe` ではなく `manual_review` に落とす
- 生成stubには `review required` を残すが、少なくとも呼び出し引数数には合わせる

---

### CR-005: `analyze-function` がデフォルトで後続Stepまで走りすぎる

**対象:** `src/unit_test_runner/dossier.py`

`analyze_function_workflow()` は、関数解析だけでなく、source digest、function location、signature、global access、call report、coverage、boundary、test case design、harness skeleton、build workspace、build completion、test execution evidenceまで、ほぼ全工程を無条件に進めている。

**影響:**

READMEでは「初期ゴールは完全な実行可能ハーネス生成ではなく、関数レベル解析成果物を外部に出す」と説明している。一方、実装では `analyze-function` が常にStep 13〜16相当のdry-run成果物まで作る。これは処理時間、生成物量、安全性、ユーザー期待の面でズレがある。

**推奨修正:**

- `analyze-function` に `--max-step` または `--phase analysis|design|harness|build|execution` を追加する
- 既定は MVP-1 または MVP-2 に絞る
- harness / build / completion / evidence は明示オプション時のみ生成する
- VS Code adapterも既定では `--finalize-dossier` までにし、build/test系は別コマンドに分ける

---

## 4. 重大度Mediumの指摘

### CR-006: CLI boolean optionが`or True`で常に有効化されている

**対象:** `src/unit_test_runner/cli/commands.py`

以下の2箇所で、CLI引数の値が常にtrueになる。

```python
generate_unknown_symbol_stubs=args.generate_unknown_symbol_stubs or True
```

```python
allow_placeholder_tests=args.allow_placeholder_tests or True
```

**影響:**

`--generate-unknown-symbol-stubs` や `--allow-placeholder-tests` が、実質的に無効なオプションになっている。将来「unknown symbol stubを生成しない」「placeholder testを許可しない」という安全側の運用ができない。

**推奨修正:**

- dataclass側のdefaultを使うなら、CLI引数を `None` にできる形へ変える
- または明示的なdisable optionを追加する
  - `--no-generate-unknown-symbol-stubs`
  - `--disallow-placeholder-tests`
- 少なくとも `or True` は削除する

---

### CR-007: build workspaceのinclude path配置が実プロジェクトで壊れやすい

**対象:** `src/unit_test_runner/build/build_workspace_generator.py`

`_copy_target_and_headers()` は、source digestに出てきた直接include候補を個別copyする。一方、`_include_dirs()` はDSP由来include dirを `extracted/<normalized>` のようなworkspace pathへ変換する。

しかし、DSP include directory全体をworkspaceへmirrorしているわけではない。

**影響:**

`../common/include` や `platform/include` のようなinclude dirがある実プロジェクトでは、Makefileの `/I"..\extracted\../common/include"` のようなpathが存在せず、C1083が多発する可能性がある。

**推奨修正:**

- copy modeの場合、DSP include dir配下をmirrorするか、直接copyしたheaderの配置に合わせてinclude pathを再構成する
- reference modeの場合、元のabsolute include dirをMakefileに渡す
- `BuildPathEntry` に `mode=copy|reference` を追加し、Makefile生成で使い分ける

---

### CR-008: `dossier.py` と `dossier/` packageの併存が保守性を下げている

**対象:**

- `src/unit_test_runner/dossier.py`
- `src/unit_test_runner/dossier/__init__.py`

`dossier/__init__.py` は `importlib.util.spec_from_file_location()` で sibling の `dossier.py` を legacy moduleとして読み込み、そこから `analyze_function_workflow` などをre-exportしている。

**影響:**

- import構造が分かりにくい
- IDEや型チェッカが追いづらい
- 将来の循環importや相対import問題を誘発しやすい
- `dossier.py` が大きなworkflow集約になっており、Stepごとの責務分離とズレている

**推奨修正:**

- `dossier.py` の中身を `dossier/workflow.py` などへ移す
- `dossier.py` を削除または互換shimにする
- dynamic importをやめ、通常importに戻す
- `analyze_function_workflow` は `workflow.py`、finalize系は `finalizer.py` に分ける

---

### CR-009: VS Code adapterの設定・計画・READMEで名称揺れがある

**対象:**

- `README.md`
- `docs/implementation/step18_vscode_thin_adapter_plan.md`
- `vscode/extension/src/cli/commandBuilder.ts`
- `vscode/extension/src/reports/reportPathResolver.ts`

計画では `test_case_draft` という名称を多く使っていたが、実装では `test_case_design` が使われている。READMEも `generate-test-design` と `test_case_design.csv` を案内している。

**影響:**

ユーザーやVS Code adapterが、どのファイル名を期待すべきか迷いやすい。Step 19の再利用・回帰選択では過去成果物名の安定性が重要になるため、ここは早めに揃えたほうがよい。

**推奨修正:**

- 公式名称を `test_case_design` に寄せるか、`test_case_draft` に戻すか決める
- 互換期間は両方を読めるようにする
- README、docs、CLI option、VS Code report resolverを合わせる

---

### CR-010: VS Code adapterのレポートpath parserがCLI payloadと密結合しすぎている

**対象:** `vscode/extension/src/cli/cliResultParser.ts`

`reportsFromParsed()` は `data.review.reports` または `data.reports` の特定キーを読みに行く。キー欠損時はfallbackする設計は良いが、CLIのpayload形がコマンドごとにかなり違うため、将来のreport追加時に漏れやすい。

**推奨修正:**

- CLI側で全コマンド共通の `reports` top-level conventionを定義する
- VS Code側は `reports` objectをgenericに扱い、既知キーだけをUIに表示する
- JSON schemaまたは軽量contract testを追加する

---

## 5. 重大度Low / 保守性の指摘

### CR-011: 実行系に重複・未使用らしき関数がある

**対象:** `src/unit_test_runner/execution/test_execution.py`

同ファイルでは `resolve_executable`、`run_test_executable`、`write_test_execution_reports` をimportして使っている一方、下部に `_resolve_executable()`、`_run_executable()`、`_write_test_reports()`、`_build_manifest()` など似た責務の関数が残っている。

**影響:**

どちらが正規実装なのか分かりにくく、将来の修正漏れにつながる。

**推奨修正:**

- 未使用関数を削除する
- 必要ならテストで参照されていないことを確認する
- `ruff` などのlintを導入し、未使用関数・importを検出する

---

### CR-012: C90互換チェックが文字列検査のみで弱い

**対象:** `src/unit_test_runner/harness/c90_writer.py`

`is_c90_compatible_text()` は `//`、`for (int `、`stdint.h`、`stdbool.h`、`inline ` の単純文字列検査で判定している。

**影響:**

- URL文字列やコメント内の `//` でfalse positiveになる
- `for(int i` のような空白差分を検出できない
- `inline` が識別子の一部の場合に誤判定し得る

**推奨修正:**

- C90 guardは簡易tokenizerベースに寄せる
- 生成ファイルに対する禁止構文テストを増やす
- まずは正規表現を改善する

---

### CR-013: CI定義が見当たらない

GitHub検索上、`.github/workflows` のCI定義は確認できなかった。

**推奨修正:**

最低限、以下をGitHub Actionsで実行する。

```powershell
py -m unittest discover -s tests -p "test_*.py"
cd vscode/extension
npm install
npm test
```

特にVS Code extensionはTypeScript compileを必ずCIに入れるべきである。

---

## 6. テスト観点の追加提案

### 6.1 CLI policy系

追加すべきテスト:

- `complete-build` で `--generate-unknown-symbol-stubs` 未指定時にpolicyが意図通りか
- `run-tests` でplaceholderを許可しない設定が可能か
- `build-probe --run` が失敗したときexit codeが非0になるか
- `analyze-function` が既定でどのStepまで実行するか

### 6.2 VS Code extension系

追加すべきテスト:

- `npm test` を実際に通す
- `openPlainFile` のような未定義関数をcompileで検出する
- `showOutputChannel=false` が機能するか
- `outputRoot` が `sourceRoot` 配下のとき警告または停止するか
- JSON payloadがないCLI出力でもfallback pathが正しいか

### 6.3 Build workspace系

追加すべきテスト:

- `--vcvars` 指定時、PATHにnmake/clがなくてもbuild.bat実行に進むか
- DSP include dirが外部パスの場合、Makefile include pathが正しいか
- C1083発生時、missing include候補がsourceRootから検索されるか
- PCH optionありのDSPでbuild hintが出るか

### 6.4 Stub completion系

追加すべきテスト:

- unresolved symbolがcall_reportの既知callと一致し、引数ありの場合にstub signatureが引数数に合うか
- unknown symbolの場合にauto_safeではなくreview/manual扱いになるか
- 既存stubがある場合に上書きしないか

---

## 7. 推奨修正順序

### 最優先

1. VS Code extensionの `openPlainFile` 未定義を修正し、`npm test` が通るようにする
2. `build-probe --run` のexit code方針を修正する
3. `--vcvars` 指定時のVC6環境検出順序を修正する
4. `or True` によるCLI policy無効化を修正する
5. 追加stub生成がcall_reportの引数情報を使うようにする

### 次点

6. `analyze-function` の既定実行範囲を整理する
7. build workspaceのinclude path/copy/reference方針を整理する
8. `dossier.py` と `dossier/` packageの構造を整理する
9. `test_case_design` / `test_case_draft` の名称を統一する
10. CIを追加する

---

## 8. 結論

`unitTestRunner` は、当初の計画よりかなり広い範囲まで実装が進んでいる。方向性は良く、特に本番非侵襲、VC6/C90配慮、成果物分割、VS Code thin adapter方針は維持できている。

ただし、現時点では **build/test/VS Code実行経路に実運用前に直すべき問題が複数ある**。とくに、VS Code extensionのcompileエラー候補、build-probeのexit code、vcvars無効化、CLI policyの `or True`、追加stub signatureの不整合は早めに修正したい。

次の開発アクションとしては、新機能追加よりも、まず上記High指摘を潰し、`py -m unittest` と `npm test` を通すCIを追加することを推奨する。
