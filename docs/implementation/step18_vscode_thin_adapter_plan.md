# Step 18: VS Code Thin Adapter 実装計画

作成日: 2026-07-04  
状態: Draft v0.1  
対象リポジトリ: `katamor1/unitTestRunner`  
製造担当想定: CODEX  
前提文書:

- `docs/adr/0001-cli-layer-language-selection.md`
- `docs/function_level_vc6_unit_test_codex_design.md`
- `docs/review/current_assessment_and_future_outlook.md`
- `docs/implementation/step02_cli_entry_point_plan.md`
- `docs/implementation/step17_function_dossier_finalizer_review_workflow_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第18ステップとして **VS Code Thin Adapter** を実装するための計画である。

これまでの計画では、解析・生成・ビルド・実行・エビデンス生成の中心を Python CLI に置いてきた。
Step 18 では、その方針を維持したまま、ユーザーが普段利用している VS Code から以下を実行しやすくする。

- 現在開いている `.c` ファイルの関数を解析する
- カーソル位置または選択中の関数を対象にする
- `unit-test-runner analyze-function` を呼び出す
- `function_dossier.md` / `review_checklist.md` / `next_actions.md` を開く
- 生成済みレポートや外部ワークスペースを素早く確認する
- 必要に応じて `finalize-dossier` / `generate-test-design` / `build-probe` / `run-tests` を明示実行する

VS Code Thin Adapter は、解析ロジックを持たない。
あくまで CLI の起動、引数生成、結果表示、レポートを開くための薄いUI層である。

---

## 2. 目的

Step 18 の目的は、関数単位テスト支援パイプラインを、VS Code 上の自然な操作から開始・確認できるようにすることである。

具体的には、以下を実現する。

- VS Code で開いている `.c` ファイルから `analyze-function` を起動できる
- カーソル位置または選択文字列から対象関数名を推定できる
- 設定済みの `.dsw`、configuration、outputRoot、CLI path を使ってCLIを呼び出せる
- CLI の JSON 出力を解析し、成功・警告・失敗を VS Code 上に表示できる
- 生成された `function_dossier.md` を自動で開ける
- 生成された `review_checklist.md`、`unresolved_items.md`、`next_actions.md` を開ける
- 生成済みworkspaceを Explorer またはOSのファイルマネージャで開ける
- 実行を伴う危険度の高い操作、例: build probe実行、test実行は明示確認または明示コマンドに限定できる
- CLIコアを変更せず、VS Code拡張は薄いadapterとして保守できる

---

## 3. 基本方針

### 3.1 CLI First

VS Code extension は Python CLI を呼び出すだけにする。

VS Code extension に入れないもの:

- DSW / DSP parser
- C source lexer / masker
- Function locator
- Signature extractor
- Global / Call / Branch analyzer
- Boundary / Equivalence generator
- Test case design generator
- Stub / Harness generator
- Build probe runner
- Dossier finalizer

これらはすべて CLI 側に集約する。

### 3.2 Thin Adapter

VS Code extension が担当することは以下に限定する。

- 現在ファイル・選択範囲・カーソル位置の取得
- ユーザー設定の読み込み
- CLIコマンドラインの組み立て
- CLI実行
- JSON結果の読み取り
- Markdown / CSV / JSONレポートを開く
- Output Channel / Notification / Quick Pick で結果を見せる
- 明示実行が必要な危険操作を確認する

### 3.3 本番リポジトリ非侵襲

VS Code extension から実行しても、本番リポジトリには生成物を置かない。

方針:

- outputRoot は本番リポジトリ外を推奨する
- outputRoot が sourceRoot 配下の場合は warning を出す
- 本番 `.c` / `.h` / `.dsp` / `.dsw` を変更しない
- VS Code extension が本番ファイルへ自動編集を行わない

### 3.4 明示操作の原則

以下は勝手に実行しない。

- build probe 実行
- safe completion 適用
- test 実行
- evidence再生成
- 既存生成物の上書き

これらはコマンド名、確認ダイアログ、設定値で明示されている場合のみ行う。

---

## 4. スコープ

### 4.1 実装対象

Step 18 で実装するもの:

1. VS Code extension skeleton
   - TypeScript project
   - package.json
   - activation events
   - commands
   - configuration schema
   - extension tests

2. Settings reader
   - CLI path
   - DSW path
   - source root
   - output root
   - default configuration
   - default project
   - auto open dossier
   - JSON mode
   - run policy

3. Current function resolver
   - 選択文字列から関数名推定
   - カーソル位置から関数名推定
   - VS Code DocumentSymbol 利用候補
   - fallback regex候補
   - 失敗時のQuick Pick / input box

4. CLI command builder
   - `analyze-function`
   - `finalize-dossier`
   - `generate-test-design`
   - `build-probe`
   - `run-tests`
   - `prepare-evidence`
   - quote / Windows path handling

5. CLI process runner
   - child process起動
   - stdout / stderr capture
   - timeout
   - cancellation
   - output channel logging
   - JSON parse

6. Report opener
   - `function_dossier.md`
   - `review_checklist.md`
   - `unresolved_items.md`
   - `next_actions.md`
   - `test_spec.csv`
   - workspace folder

7. UI commands
   - Analyze Current Function
   - Analyze Selected Function
   - Finalize Dossier
   - Open Function Dossier
   - Open Review Checklist
   - Open Next Actions
   - Generate Test Design
   - Build Probe Dry Run
   - Run Build Probe, explicit
   - Run Tests, explicit
   - Prepare Evidence
   - Copy Last CLI Command

8. Status / diagnostics display
   - Output Channel
   - Notification
   - Quick Pick
   - status bar item, optional
   - problem matcherは初期では任意

9. Tests
   - command builder
   - settings reader
   - function resolver
   - CLI result parser
   - report path resolver
   - safety confirmation

### 4.2 対象外

Step 18 では以下を対象外とする。

- CLIコアの解析ロジック実装
- Python CLIの大幅変更
- VS Code内でのC parser実装
- VS Code内でのDSW/DSP解析
- 本番ソースの自動編集
- GitHub Issue / PR 自動作成
- GUI wizardの本格実装
- Webviewによるリッチdossierビュー
- 実測カバレッジ表示
- AIチャット統合
- モジュール単位dossierの可視化
- 疑似時間・疑似割込UI

Step 18 は、CLIを使いやすくする入口・閲覧・明示実行UIに限定する。

---

## 5. ユーザー体験

### 5.1 基本フロー: 現在関数を解析する

1. ユーザーが VS Code で対象 `.c` ファイルを開く
2. 対象関数内にカーソルを置く、または関数名を選択する
3. コマンドパレットから `UnitTestRunner: Analyze Current Function` を実行する
4. extension が関数名を推定する
5. `.dsw`、configuration、outputRoot を設定から取得する
6. `unit-test-runner analyze-function ... --finalize-dossier --json` を実行する
7. CLIの結果を Output Channel に表示する
8. 成功した場合、`function_dossier.md` を開く
9. review_required や warnings がある場合、通知と `review_checklist.md` へのリンクを出す

### 5.2 レポート確認フロー

1. コマンドパレットから `UnitTestRunner: Open Function Dossier` を実行する
2. extension が現在ファイル・関数名から出力workspaceを推定する
3. `reports/function_dossier.md` を開く
4. 見つからない場合は、workspace選択または `finalize-dossier` 実行を促す

### 5.3 明示ビルドフロー

1. ユーザーが `UnitTestRunner: Build Probe Dry Run` を実行する
2. build command と Makefile の生成状態を確認する
3. 必要に応じて `UnitTestRunner: Run Build Probe` を実行する
4. extension が確認ダイアログを出す
5. CLI `build-probe --run` を実行する
6. `build_probe_report.md` を開く

### 5.4 明示テスト実行フロー

1. ユーザーが `UnitTestRunner: Run Tests` を実行する
2. extension が build probe status と placeholder有無を確認する
3. placeholderがある場合は warning を表示する
4. ユーザーが明示承認した場合のみ `run-tests --run` を実行する
5. `test_execution_report.md` と `test_result.csv` を開く

---

## 6. 設定設計

VS Code settings.json に以下を定義する。

```json
{
  "unitTestRunner.cliPath": "D:/tools/unit-test-runner/unit-test-runner.exe",
  "unitTestRunner.sourceRoot": "D:/work/product",
  "unitTestRunner.dswPath": "D:/work/product/Product.dsw",
  "unitTestRunner.outputRoot": "D:/work/unit_test_workspace",
  "unitTestRunner.defaultConfiguration": "Control - Win32 Debug",
  "unitTestRunner.defaultProject": "Control",
  "unitTestRunner.autoOpenDossier": true,
  "unitTestRunner.finalizeDossierAfterAnalyze": true,
  "unitTestRunner.useJsonOutput": true,
  "unitTestRunner.showOutputChannel": true,
  "unitTestRunner.runBuildProbeRequiresConfirmation": true,
  "unitTestRunner.runTestsRequiresConfirmation": true,
  "unitTestRunner.commandTimeoutSeconds": 300
}
```

### 6.1 設定項目

| 設定 | 型 | 既定 | 内容 |
|---|---|---|---|
| `unitTestRunner.cliPath` | string | `unit-test-runner` | CLI実行ファイルpath |
| `unitTestRunner.sourceRoot` | string | workspace root | 本番ソースroot |
| `unitTestRunner.dswPath` | string | empty | VC6 `.dsw` path |
| `unitTestRunner.outputRoot` | string | empty | 外部出力workspace root |
| `unitTestRunner.defaultConfiguration` | string | empty | 既定VC6 configuration |
| `unitTestRunner.defaultProject` | string | empty | 既定DSP project |
| `unitTestRunner.autoOpenDossier` | boolean | true | 解析後にdossierを開く |
| `unitTestRunner.finalizeDossierAfterAnalyze` | boolean | true | analyze後にfinalize-dossierまで実行 |
| `unitTestRunner.useJsonOutput` | boolean | true | CLIへ `--json` を付ける |
| `unitTestRunner.showOutputChannel` | boolean | true | output channelを表示する |
| `unitTestRunner.runBuildProbeRequiresConfirmation` | boolean | true | build実行前に確認する |
| `unitTestRunner.runTestsRequiresConfirmation` | boolean | true | test実行前に確認する |
| `unitTestRunner.commandTimeoutSeconds` | number | 300 | CLI timeout |

### 6.2 設定検証

起動時またはコマンド実行前に以下を検証する。

- cliPath が存在する、またはPATHで解決可能
- dswPath が存在する
- outputRoot が空でない
- outputRoot が sourceRoot 配下の場合 warning
- defaultConfiguration が空の場合、CLI側の候補取得またはinput promptへ進む

---

## 7. コマンド設計

### 7.1 コマンド一覧

| Command ID | 表示名 | 内容 |
|---|---|---|
| `unitTestRunner.analyzeCurrentFunction` | UnitTestRunner: Analyze Current Function | カーソル位置関数を解析 |
| `unitTestRunner.analyzeSelectedFunction` | UnitTestRunner: Analyze Selected Function | 選択関数名を解析 |
| `unitTestRunner.finalizeDossier` | UnitTestRunner: Finalize Dossier | dossier最終化 |
| `unitTestRunner.openFunctionDossier` | UnitTestRunner: Open Function Dossier | dossier Markdownを開く |
| `unitTestRunner.openReviewChecklist` | UnitTestRunner: Open Review Checklist | review checklistを開く |
| `unitTestRunner.openNextActions` | UnitTestRunner: Open Next Actions | next actionsを開く |
| `unitTestRunner.generateTestDesign` | UnitTestRunner: Generate Test Design | test_case_design生成 |
| `unitTestRunner.buildProbeDryRun` | UnitTestRunner: Build Probe Dry Run | build probe dry-run |
| `unitTestRunner.runBuildProbe` | UnitTestRunner: Run Build Probe | 明示build probe実行 |
| `unitTestRunner.runTests` | UnitTestRunner: Run Tests | 明示test実行 |
| `unitTestRunner.prepareEvidence` | UnitTestRunner: Prepare Evidence | evidence再生成 |
| `unitTestRunner.openOutputWorkspace` | UnitTestRunner: Open Output Workspace | 出力workspaceを開く |
| `unitTestRunner.copyLastCommand` | UnitTestRunner: Copy Last CLI Command | 最後のCLIコマンドをコピー |

### 7.2 MVPコマンド

最初の実装では以下だけでもよい。

- `analyzeCurrentFunction`
- `analyzeSelectedFunction`
- `openFunctionDossier`
- `openReviewChecklist`
- `copyLastCommand`

Build / Test / Evidence 系は、CLIコアがMVP-3以降に進んでから有効化してもよい。

---

## 8. CLI呼び出し設計

### 8.1 analyze-function command line

```bat
unit-test-runner analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Control - Win32 Debug" ^
  --project Control ^
  --out D:\work\unit_test_workspace\Control_Update ^
  --finalize-dossier ^
  --json
```

### 8.2 パス処理方針

- Windows pathの空白を安全にquoteする
- sourceは sourceRoot からの相対pathを優先する
- absolute pathしか取れない場合は CLI にabsolute pathを渡す
- output workspaceは `outputRoot/<function>` を既定にする
- 関数名にファイル名prefixを付けるかは後続検討。初期は関数名のみ

### 8.3 CLI結果JSON

CLIから期待する最小JSON例:

```json
{
  "status": "ok",
  "command": "analyze-function",
  "function": "Control_Update",
  "workspace": "D:/work/unit_test_workspace/Control_Update",
  "reports": {
    "function_dossier_md": "reports/function_dossier.md",
    "review_checklist_md": "reports/review_checklist.md",
    "next_actions_md": "reports/next_actions.md"
  },
  "warnings": []
}
```

extension は、このJSONから主要レポートpathを解決する。
JSONがない場合は、既定pathを推定する。

---

## 9. 関数名解決設計

### 9.1 優先順位

1. 選択中テキストがC識別子ならそれを関数名とする
2. VS Code DocumentSymbol からカーソル位置を含む function symbol を探す
3. 現在行周辺の簡易regexで関数定義らしき名前を探す
4. 見つからなければ input box で関数名を入力させる

### 9.2 制約

VS Code側の関数名解決は補助であり、最終判定はCLIのFunction Locatorが行う。

そのため、extensionが推定した関数名が誤っていても、CLI側が `function_not_found` を返す想定である。

### 9.3 変更関数候補

将来拡張として、Git diff から変更行を含む関数を候補表示する。

初期MVPでは必須ではない。

---

## 10. UI表示設計

### 10.1 Output Channel

Output Channel名:

```text
UnitTestRunner
```

表示するもの:

- 実行CLIコマンド
- 開始時刻
- stdout summary
- stderr summary
- JSON parse結果
- report path
- warnings

### 10.2 Notification

成功時:

```text
UnitTestRunner: Function dossier generated for Control_Update.
```

警告あり:

```text
UnitTestRunner: Analysis completed with warnings. Open review checklist?
```

失敗時:

```text
UnitTestRunner: analyze-function failed. See Output Channel.
```

### 10.3 Quick Pick

候補:

- 複数configurationがある場合の選択
- 複数project候補がある場合の選択
- 複数function candidateがある場合の選択
- 開くreportの選択

初期MVPでは、configuration / project はsettingsに固定でもよい。

### 10.4 Status Bar

任意機能として、直近の解析状態を表示する。

例:

```text
UTR: Control_Update ready_for_review
```

初期MVPでは必須ではない。

---

## 11. 安全設計

### 11.1 実行確認

以下のコマンドは確認ダイアログを出す。

- Run Build Probe
- Complete Build with Safe Completions
- Run Tests
- Overwrite Generated Files

確認例:

```text
This command may execute generated binaries or modify files in the output workspace. Continue?
```

### 11.2 本番リポジトリ保護

- outputRoot が sourceRoot 配下の場合、警告する
- 本番ファイルへの書き込みはしない
- extensionから本番 `.c` / `.h` を編集しない
- 生成物は outputRoot 配下のみ

### 11.3 コマンド表示

実行前または失敗時に、最後に実行したCLIコマンドをコピーできるようにする。

これにより、VS Code外のコマンドプロンプトで再現しやすくする。

---

## 12. データモデル設計

### 12.1 AdapterSettings

```typescript
interface AdapterSettings {
  cliPath: string;
  sourceRoot: string;
  dswPath: string;
  outputRoot: string;
  defaultConfiguration?: string;
  defaultProject?: string;
  autoOpenDossier: boolean;
  finalizeDossierAfterAnalyze: boolean;
  useJsonOutput: boolean;
  showOutputChannel: boolean;
  runBuildProbeRequiresConfirmation: boolean;
  runTestsRequiresConfirmation: boolean;
  commandTimeoutSeconds: number;
}
```

### 12.2 FunctionTarget

```typescript
interface FunctionTarget {
  sourcePath: string;
  sourceRelativePath?: string;
  functionName: string;
  project?: string;
  configuration?: string;
  outputWorkspace: string;
}
```

### 12.3 CliInvocation

```typescript
interface CliInvocation {
  command: string;
  args: string[];
  workingDirectory: string;
  displayCommand: string;
  timeoutSeconds: number;
  requiresConfirmation: boolean;
}
```

### 12.4 CliResult

```typescript
interface CliResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  parsedJson?: unknown;
  timedOut: boolean;
  commandLine: string;
}
```

### 12.5 ReportPaths

```typescript
interface ReportPaths {
  workspace: string;
  functionDossierMd?: string;
  reviewChecklistMd?: string;
  unresolvedItemsMd?: string;
  nextActionsMd?: string;
  testCaseDesignCsv?: string;
  buildProbeReportMd?: string;
  testExecutionReportMd?: string;
  evidencePackageMd?: string;
}
```

---

## 13. ディレクトリ構成

VS Code extensionはCLI本体と分離する。

```text
vscode/
  unit-test-runner-vscode/
    package.json
    tsconfig.json
    src/
      extension.ts
      commands/
        analyzeCurrentFunction.ts
        openReports.ts
        runBuildProbe.ts
        runTests.ts
      cli/
        commandBuilder.ts
        cliRunner.ts
        cliResultParser.ts
      config/
        settings.ts
        validation.ts
      functionTarget/
        currentFunctionResolver.ts
        documentSymbolResolver.ts
        regexFunctionResolver.ts
      reports/
        reportPathResolver.ts
        reportOpener.ts
      ui/
        outputChannel.ts
        notifications.ts
        quickPick.ts
      safety/
        confirmation.ts
        workspaceGuard.ts
    test/
      commandBuilder.test.ts
      settings.test.ts
      cliResultParser.test.ts
      reportPathResolver.test.ts
```

---

## 14. テスト計画

### 14.1 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| VSC-001 | settings read | settings.json | AdapterSettings生成 |
| VSC-002 | missing cliPath | cliPathなし | warning |
| VSC-003 | outputRoot under sourceRoot | unsafe path | warning |
| VSC-004 | selected function | selection `Control_Update` | functionName取得 |
| VSC-005 | document symbol | symbolあり | functionName取得 |
| VSC-006 | regex fallback | C関数定義周辺 | functionName推定 |
| VSC-007 | function input fallback | 推定不可 | input promptへ進む |
| VSC-008 | analyze command build | target/settings | args生成 |
| VSC-009 | path quoting | 空白path | 正しくargs分離 |
| VSC-010 | json parse success | CLI stdout JSON | ReportPaths抽出 |
| VSC-011 | json parse failure | text stdout | default path推定 |
| VSC-012 | open dossier | file exists | markdown open |
| VSC-013 | missing report | fileなし | warning |
| VSC-014 | run build confirmation | command | confirmation required |
| VSC-015 | run tests confirmation | command | confirmation required |
| VSC-016 | timeout | long process mock | timedOut true |
| VSC-017 | copy last command | last commandあり | clipboardへコピー |

### 14.2 テスト方針

- CLI実体はmockする
- VS Code API依存箇所は薄くラップして単体テストしやすくする
- commandBuilderは純粋関数に近づける
- path quoteはWindows pathを重点的にテストする
- 実際のCLI統合テストは後続で少数だけ行う

---

## 15. 実装タスク分解

### Task 18-01: VS Code extension skeleton

成果物:

- `vscode/unit-test-runner-vscode/package.json`
- `tsconfig.json`
- `src/extension.ts`
- activate / deactivate
- command登録

完了条件:

- VS Code extensionとして読み込める
- 最小コマンドが実行できる

### Task 18-02: Settings reader / validator

成果物:

- `src/config/settings.ts`
- `src/config/validation.ts`
- configuration schema

完了条件:

- VSC-001 / VSC-002 / VSC-003 が通る

### Task 18-03: Function target resolver

成果物:

- `currentFunctionResolver.ts`
- `documentSymbolResolver.ts`
- `regexFunctionResolver.ts`
- input fallback

完了条件:

- VSC-004 から VSC-007 が通る

### Task 18-04: CLI command builder

成果物:

- `commandBuilder.ts`
- analyze-function args生成
- finalize-dossier args生成
- build/run系args生成
- Windows path対応

完了条件:

- VSC-008 / VSC-009 が通る

### Task 18-05: CLI runner / result parser

成果物:

- `cliRunner.ts`
- `cliResultParser.ts`
- timeout
- stdout/stderr capture
- JSON parse

完了条件:

- VSC-010 / VSC-011 / VSC-016 が通る

### Task 18-06: Report path resolver / opener

成果物:

- `reportPathResolver.ts`
- `reportOpener.ts`
- Markdown / CSV / workspace open

完了条件:

- VSC-012 / VSC-013 が通る

### Task 18-07: UI commands

成果物:

- `Analyze Current Function`
- `Analyze Selected Function`
- `Open Function Dossier`
- `Open Review Checklist`
- `Open Next Actions`
- `Copy Last CLI Command`

完了条件:

- MVPコマンドがCommand Paletteから実行できる

### Task 18-08: Safety confirmation

成果物:

- `confirmation.ts`
- build/run/test系確認
- outputRoot guard

完了条件:

- VSC-014 / VSC-015 が通る

### Task 18-09: Output Channel / notifications

成果物:

- `outputChannel.ts`
- `notifications.ts`
- 実行結果表示
- warning表示

完了条件:

- CLI成功/失敗/警告が表示される

### Task 18-10: Extension tests / fixtures

成果物:

- `test/*.test.ts`
- mock CLI runner
- path fixture
- JSON result fixture

完了条件:

- VSC-001 から VSC-017 が通る

---

## 16. 受け入れ基準

Step 18 は、以下をすべて満たしたら完了とする。

1. VS Code extensionとして起動できる
2. 設定からcliPath / dswPath / sourceRoot / outputRootを読み込める
3. outputRootがsourceRoot配下の場合にwarningを出せる
4. 選択文字列から関数名を取得できる
5. カーソル位置から関数名を推定できる
6. 推定できない場合にユーザー入力へfallbackできる
7. `analyze-function` のCLI引数を安全に生成できる
8. Windows空白pathを壊さずCLIへ渡せる
9. CLIを実行しstdout / stderrをOutput Channelに表示できる
10. CLI JSON出力をparseできる
11. JSONがない場合でも既定pathからreportを推定できる
12. `function_dossier.md` を開ける
13. `review_checklist.md` を開ける
14. `next_actions.md` を開ける
15. 最後に実行したCLIコマンドをコピーできる
16. build probe / test実行系コマンドは明示確認を要求できる
17. VS Code側に解析ロジックを持ち込んでいない
18. 本番リポジトリへファイルを書き込まない
19. CLIコアのMVP-1成果物だけでも利用できる
20. Step 19 のモジュール単位拡張や将来UI拡張を妨げない構造である

---

## 17. 成果物

Step 18 の成果物は以下とする。

```text
vscode/
  unit-test-runner-vscode/
    package.json
    tsconfig.json
    README.md
    src/
      extension.ts
      commands/
      cli/
      config/
      functionTarget/
      reports/
      ui/
      safety/
    test/
      commandBuilder.test.ts
      settings.test.ts
      cliResultParser.test.ts
      reportPathResolver.test.ts
```

既存ファイルの更新:

- `docs/implementation/step18_vscode_thin_adapter_plan.md`
- 必要に応じて `README.md`
- 必要に応じて `docs/review/current_assessment_and_future_outlook.md`

---

## 18. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| VS Code側が肥大化する | 解析ロジックをextensionに入れたくなる | CLI Firstを徹底し、extensionはadapterに限定する |
| 関数名推定ミス | カーソル位置推定が外れる | 最終判定はCLIに任せ、input fallbackを用意する |
| Windows path quoting | 空白pathや日本語pathで壊れる | args配列でspawnし、shell文字列結合を避ける |
| 意図しないbuild/test実行 | UIから危険操作が簡単に走る | build/testは確認必須、既定はdry-runにする |
| 本番リポジトリ汚染 | outputRoot設定ミス | sourceRoot配下ならwarningし、必要なら実行停止設定を追加する |
| CLI結果形式変更 | JSON schema変更でparserが壊れる | parsed JSONがなくても既定path推定へfallbackする |
| レポートが多く迷う | どれを開けばよいか分からない | function_dossier.mdを主入口にする |
| MVP未完成時のUI空振り | 後続Stepのreportがまだない | MVP levelに応じて利用可能コマンドを分ける |

---

## 19. Step 19 への接続

Step 18 完了後、Step 19 ではモジュール単位への拡張検討を行う。

VS Code Thin Adapter は、Step 19以降で以下へ拡張できる。

- 現在 `.c` ファイル内の関数一覧表示
- 複数関数の一括 dossier 生成
- モジュール単位dossierを開く
- 関数依存グラフを開く
- 複数function dossierの未解決項目を集約表示する

ただし、Step 18 の段階では関数単位の入口と成果物閲覧に集中する。

---

## 20. まとめ

Step 18 は、unitTestRunner のPython CLIを、普段使いのVS Codeから自然に呼び出すための薄いadapterである。

このステップにより、ユーザーは対象関数をVS Code上で選択し、`analyze-function` を実行し、生成された `function_dossier.md`、`review_checklist.md`、`next_actions.md` をすぐ確認できるようになる。

ただし、Step 18 は解析器やテスト生成器をVS Code側に移す段階ではない。
解析・生成・ビルド・実行・エビデンス化はCLIに残し、VS Code extensionは起動・表示・確認・安全な明示実行に責務を絞る。
