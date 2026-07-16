# 日本人ユーザー向けGUI文言見直し Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** VS Code拡張の可視GUI文言を、操作対象・処理結果・次の行動が分かる自然な日本語へ統一する。

**Architecture:** 既存の画面レンダラー、設定ビューモデル、コマンド定義、VS Code API呼び出しにある文字列だけを変更する。コマンドID、設定キー、状態遷移、データ形式は維持し、既存テストへ文言契約を追加して回帰を防ぐ。

**Tech Stack:** TypeScript 5、VS Code Webview API、Node.js built-in test runner、JSON、GitHub Actions

## Global Constraints

- スクリーンリーダー専用文言とARIA属性は変更しない。
- コマンドID、設定キー、JSONキー、ファイル名、CLI引数は変更しない。
- `Quick Check`、`Full Gate`、実ファイル名は固有名称として必要な箇所で保持する。
- 画面上の `workspace`、`manifest`、`status`、`dry-run` は自然な日本語へ置き換える。
- 実行確認のボタンは対象操作を明示する。
- 変更は `chore/japanese-gui-copy` ブランチで行う。

---

## File Structure

- `vscode/extension/src/config/settingsViewModel.ts`
  - 設定項目のラベル、説明、操作ボタンを定義する。
- `vscode/extension/src/workflow/settingsPanelRenderer.ts`
  - 設定セクションの状態文、保存値表示、HTMLを描画する。
- `vscode/extension/src/workflow/workflowState.ts`
  - 詳細ワークフローの工程名、説明、操作ラベルを定義する。
- `vscode/extension/src/workflow/workflowPanelBase.ts`
  - 簡易ワークフロー、実行状態、補助操作の文言を描画する。
- `vscode/extension/src/suite/suitePanel.ts`
  - サイドバー内のスイート表示文言を描画する。
- `vscode/extension/src/suite/suiteDashboard.ts`
  - スイート一覧画面の見出し、集計、列名、操作文言を描画する。
- `vscode/extension/src/extension.ts`
  - 入力欄、ファイル選択、確認ダイアログ、通知、エラー文を定義する。
- `vscode/extension/package.json`
  - コマンドパレット、ビュー、設定画面の表示文言を定義する。
- `vscode/extension/src/test/workflowPanel.test.ts`
  - ワークフローと設定の文言契約を検証する。
- `vscode/extension/src/test/adapter.test.ts`
  - 拡張マニフェストとスイート表示の文言契約を検証する。

---

### Task 1: 文言契約テストを先に追加する

**Files:**
- Modify: `vscode/extension/src/test/workflowPanel.test.ts`
- Modify: `vscode/extension/src/test/adapter.test.ts`

**Interfaces:**
- Consumes: `renderWorkflowHtml`、`buildSettingsViewModel`、拡張マニフェストJSON
- Produces: 日本語表示の期待値と旧混在表記の禁止条件

- [ ] **Step 1: ワークフローHTMLの期待文言テストを追加する**

`renderWorkflowHtml` の出力について、次を検証する。

```ts
assert.match(html, /出力ワークスペース/);
assert.match(html, /事前確認/);
assert.doesNotMatch(html, /出力workspace/);
assert.doesNotMatch(html, /dry-runを実行/);
```

- [ ] **Step 2: 設定ビューモデルの期待文言テストを追加する**

```ts
assert.equal(fieldById(model, 'sourceRoot').label, 'ソースのルートフォルダー');
assert.equal(fieldById(model, 'suiteManifestPath').label, 'スイート定義ファイル');
assert.match(fieldById(model, 'outputRoot').description, /出力先フォルダー/);
```

- [ ] **Step 3: マニフェストのコマンドタイトルテストを追加する**

```ts
assert.equal(commandTitle(pkg, 'unitTestRunner.quickCheckCurrentFunction'), 'UnitTestRunner: 現在の関数をクイックチェック');
assert.equal(commandTitle(pkg, 'unitTestRunner.runFullGateForCurrentFunction'), 'UnitTestRunner: 現在の関数でフルゲートを実行');
```

- [ ] **Step 4: CIでテストが文言差分により失敗することを確認する**

Run: GitHub Actions `ci` on the test-only commit

Expected: TypeScriptテストが、新しい期待文言が未実装であるため失敗する。

---

### Task 2: 設定とワークフローの表示文言を更新する

**Files:**
- Modify: `vscode/extension/src/config/settingsViewModel.ts`
- Modify: `vscode/extension/src/workflow/settingsPanelRenderer.ts`
- Modify: `vscode/extension/src/workflow/workflowState.ts`
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts`

**Interfaces:**
- Consumes: 既存 `SettingsViewModel`、`WorkflowStepDefinition`、`WorkflowAction`
- Produces: 自然な日本語の設定・ワークフローHTML

- [ ] **Step 1: 設定項目名と説明を更新する**

主な置換を次に統一する。

```text
プロジェクトルート -> ソースのルートフォルダー
VC6 .dsw -> VC6ワークスペースファイル（.dsw）
出力ルート -> 出力先フォルダー
スイートmanifest -> スイート定義ファイル
既定構成 -> 既定のビルド構成
VC6 vcvars32.bat -> VC6環境設定ファイル
```

- [ ] **Step 2: 設定セクションの状態文を更新する**

```text
設定確認は完了しています。 -> 必須項目はすべて設定されています。
未設定の必須項目があります。 -> 必須項目に未設定があります。各項目を確認してください。
設定値: -> 保存されている設定:
```

- [ ] **Step 3: 詳細ワークフローの英語混在を整理する**

`workspace` は `ワークスペース`、`dry-run` は `事前確認`、`dossier` は文脈に応じて `関数ドシエ` または実ファイル名へ置き換える。実ファイル名は変更しない。

- [ ] **Step 4: 簡易ワークフローの状態・補助操作文を更新する**

`Quick Summaryを開く` は `クイックチェックの概要を開く`、`Full Gateへ進む` は `フルゲートへ進む`、`出力workspaceを開く` は `出力ワークスペースを開く` とする。

- [ ] **Step 5: 対象テストを実行する**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
node --test dist/test/workflowPanel.test.js
```

Expected: PASS

---

### Task 3: スイート画面の表示文言を更新する

**Files:**
- Modify: `vscode/extension/src/suite/suitePanel.ts`
- Modify: `vscode/extension/src/suite/suiteDashboard.ts`
- Modify: `vscode/extension/src/test/adapter.test.ts`

**Interfaces:**
- Consumes: `SuiteViewModel`、`SuiteEntryView`
- Produces: 日本語化したサイドバーと一覧画面

- [ ] **Step 1: 操作ラベルを具体化する**

```text
現在関数を登録 -> 現在の関数をスイートに登録
広い一覧を開く -> スイート一覧を開く
選択を実行 -> 選択したテストを実行
タグ指定で実行 -> タグを指定して実行
全件GREEN確認 -> 全件テストを実行して合否を確認
manifestを開く -> スイート定義ファイルを開く
```

- [ ] **Step 2: 集計と列名を日本語化する**

```text
Total -> 合計
GREEN -> 合格
Not GREEN -> 不合格
Executed -> 実行済み
Failed -> 失敗
実行status -> 実行結果
workspace -> ワークスペース
```

- [ ] **Step 3: 空状態と実行中表示を更新する**

空状態には `［現在の関数をスイートに登録］から追加してください。` を含め、実行中表示は `〜を実行しています。` の文型にする。

- [ ] **Step 4: 対象テストを実行する**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
npm.cmd test
```

Expected: PASS

---

### Task 4: コマンド、設定説明、ダイアログ、通知を更新する

**Files:**
- Modify: `vscode/extension/package.json`
- Modify: `vscode/extension/src/extension.ts`
- Modify: `vscode/extension/src/test/adapter.test.ts`

**Interfaces:**
- Consumes: 既存コマンドIDと設定キー
- Produces: 日本語のコマンドパレット、設定UI、入力・確認・通知文

- [ ] **Step 1: コマンドパレットの英語タイトルを日本語化する**

```text
Quick Check Current Function -> 現在の関数をクイックチェック
Quick Check Selected Function -> 選択した関数をクイックチェック
Full Gate for Current Function -> 現在の関数でフルゲートを実行
```

既存の日本語タイトルも、`現在関数` を `現在の関数`、`選択関数` を `選択した関数` に統一する。

- [ ] **Step 2: 設定説明の英語混在を整理する**

`workspace folder`、`manifest`、`analyze-function`、`workspace名` を、日本語またはコード表記を伴う説明へ変更する。

- [ ] **Step 3: ファイル選択と入力欄を更新する**

`選択` は対象に応じて `このフォルダーを選択` または `このファイルを選択` とし、`TOPフォルダ` は `先頭のフォルダー` にする。

- [ ] **Step 4: 実行確認ダイアログを対象別にする**

ビルド、テスト、スイート全件実行で、それぞれ `ビルドを実行`、`テストを実行`、`全件テストを実行` を確認ボタンに使う。

- [ ] **Step 5: 完了・エラー通知を自然な日本語へ更新する**

スイート完了通知は `合計N件のうち、N件合格、N件不合格でした。` とする。パスを伴うエラーは、何が見つからないかを先に示す。

- [ ] **Step 6: 対象テストを実行する**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
npm.cmd test
```

Expected: PASS

---

### Task 5: 全体検証と差分確認を行う

**Files:**
- Verify: all modified files

**Interfaces:**
- Consumes: Tasks 1-4の実装
- Produces: CI成功とレビュー可能な差分

- [ ] **Step 1: 旧表記を検索する**

Run:

```powershell
rg -n "出力workspace|suite manifest|スイートmanifest|実行status|Not GREEN|dry-runを実行|Quick Check Current Function|Full Gate for Current Function" vscode/extension/src vscode/extension/package.json
```

Expected: 内部値・テストの否定検証・実ファイル名を除き、ユーザー向け文言にヒットしない。

- [ ] **Step 2: TypeScript拡張テストを実行する**

Run:

```powershell
cd vscode/extension
npm.cmd ci
npm.cmd run compile
npm.cmd test
```

Expected: PASS

- [ ] **Step 3: リポジトリ全体CIを実行する**

Run: GitHub Actions `ci`

Expected: 全ジョブ成功

- [ ] **Step 4: 差分を確認する**

コマンドID、設定キー、JSONキー、ファイル名、CLI引数、ARIA属性に意図しない変更がないことを確認する。
