from __future__ import annotations

import json
from pathlib import Path

ROOT = Path.cwd()


def replace_exact(relative_path: str, old: str, new: str, expected: int = 1) -> None:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != expected:
        raise AssertionError(
            f"{relative_path}: expected {expected} occurrence(s) of {old!r}, found {actual}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


def update_package_json() -> None:
    path = ROOT / "vscode/extension/package.json"
    package = json.loads(path.read_text(encoding="utf-8"))

    titles = {
        "unitTestRunner.quickCheckCurrentFunction": "UnitTestRunner: 現在の関数をクイックチェック",
        "unitTestRunner.quickCheckSelectedFunction": "UnitTestRunner: 選択した関数をクイックチェック",
        "unitTestRunner.openGeneratedTestSource": "UnitTestRunner: 生成したテストソースを開く",
        "unitTestRunner.openQuickSummary": "UnitTestRunner: クイックチェックの概要を開く",
        "unitTestRunner.runFullGateForCurrentFunction": "UnitTestRunner: 現在の関数でフルゲートを実行",
        "unitTestRunner.analyzeCurrentFunction": "UnitTestRunner: 現在の関数を解析",
        "unitTestRunner.analyzeSelectedFunction": "UnitTestRunner: 選択した関数を解析",
        "unitTestRunner.reanalyzeCurrentFunction": "UnitTestRunner: 現在の関数を再解析",
        "unitTestRunner.finalizeDossier": "UnitTestRunner: 関数分析レポートを確定",
        "unitTestRunner.openFunctionDossier": "UnitTestRunner: 関数分析レポートを開く",
        "unitTestRunner.openReviewChecklist": "UnitTestRunner: レビュー確認リストを開く",
        "unitTestRunner.openNextActions": "UnitTestRunner: 次に行う操作を開く",
        "unitTestRunner.openChangeImpactReport": "UnitTestRunner: 変更影響レポートを開く",
        "unitTestRunner.openRegressionSelection": "UnitTestRunner: 回帰テストの選定結果を開く",
        "unitTestRunner.generateTestDesign": "UnitTestRunner: テスト設計を生成",
        "unitTestRunner.generateHarnessSkeleton": "UnitTestRunner: テストハーネスを生成",
        "unitTestRunner.buildProbeDryRun": "UnitTestRunner: ビルドの事前確認を実行",
        "unitTestRunner.runBuildProbe": "UnitTestRunner: ビルドを実行",
        "unitTestRunner.runTests": "UnitTestRunner: テストを実行",
        "unitTestRunner.prepareEvidence": "UnitTestRunner: 検証資料を作成",
        "unitTestRunner.registerCurrentFunctionInSuite": "UnitTestRunner: 現在の関数をテストスイートに登録",
        "unitTestRunner.openSuite": "UnitTestRunner: テストスイートを開く",
        "unitTestRunner.openSuiteDashboard": "UnitTestRunner: テストスイート一覧を開く",
        "unitTestRunner.openSuiteManifest": "UnitTestRunner: スイート定義ファイルを開く",
        "unitTestRunner.runSelectedSuiteTests": "UnitTestRunner: 選択したテストを実行",
        "unitTestRunner.runSuiteByTag": "UnitTestRunner: タグを指定してテストを実行",
        "unitTestRunner.runAllSuiteTestsRequireGreen": "UnitTestRunner: 全件テストを実行して合否を確認",
        "unitTestRunner.openSuiteRunReport": "UnitTestRunner: テストスイートの実行レポートを開く",
        "unitTestRunner.openOutputWorkspace": "UnitTestRunner: 出力ワークスペースを開く",
        "unitTestRunner.copyLastCommand": "UnitTestRunner: 最後に実行したCLIコマンドをコピー",
        "unitTestRunner.openLastFunctionDossier": "UnitTestRunner: 最後の関数分析レポートを開く",
    }
    commands = package["contributes"]["commands"]
    seen = set()
    for command in commands:
        command_id = command["command"]
        if command_id in titles:
            command["title"] = titles[command_id]
            seen.add(command_id)
    missing = set(titles) - seen
    if missing:
        raise AssertionError(f"package.json commands not found: {sorted(missing)}")

    views = package["contributes"]["views"]["unitTestRunner"]
    for view in views:
        if view["id"] == "unitTestRunner.workflow":
            view["name"] = "関数テスト"
        elif view["id"] == "unitTestRunner.suite":
            view["name"] = "テストスイート"

    package["description"] = "UnitTestRunner CLIをVS Codeから操作するための拡張機能です。"

    properties = package["contributes"]["configuration"]["properties"]
    descriptions = {
        "unitTestRunner.cliPath": "UnitTestRunnerのCLIまたは実行ファイルのパスです。空欄または既定値の場合は、同梱のWindows x64実行ファイルを優先します。",
        "unitTestRunner.sourceRoot": "テスト対象のソースコードがあるルートフォルダーです。未設定の場合は、VS Codeで最初に開いたフォルダーを使用します。",
        "unitTestRunner.workspaceRoot": "unitTestRunner.sourceRootの旧設定名です。新規設定ではsourceRootを使用してください。",
        "unitTestRunner.dswPath": "テスト対象のVisual C++ 6.0ワークスペースファイル（.dsw）のパスです。",
        "unitTestRunner.outputRoot": "関数分析レポートやテスト設計などの生成物を保存する出力先フォルダーです。",
        "unitTestRunner.suiteManifestPath": "複数の関数をまとめて実行するテストスイートの定義ファイルです。未設定の場合は、出力先フォルダー配下のsuites/default/suite_manifest.jsonを使用します。",
        "unitTestRunner.defaultConfiguration": "関数解析とビルドで既定として使用するVisual C++ 6.0のビルド構成名です。",
        "unitTestRunner.defaultProject": "ソースファイルが複数のVisual C++ 6.0プロジェクトに含まれる場合に使用する既定のプロジェクト名です。",
        "unitTestRunner.vcvarsPath": "ビルド前に実行するVisual C++ 6.0の環境設定バッチファイルです。nmakeまたはclがPATHにない場合に指定します。",
        "unitTestRunner.projectName": "unitTestRunner.defaultProjectの旧設定名です。新規設定ではdefaultProjectを使用してください。",
        "unitTestRunner.autoOpenDossier": "解析成功後に関数分析レポート（function_dossier.md）を自動で開きます。",
        "unitTestRunner.finalizeDossierAfterAnalyze": "関数解析時に関数分析レポートを確定するオプション（--finalize-dossier）を使用します。",
        "unitTestRunner.quickProfile": "クイックチェックで実行する範囲です。通常はテスト設計まで、必要に応じてテストハーネス生成またはビルドの事前確認まで実行できます。",
        "unitTestRunner.quickOutputRoot": "クイックチェック専用の出力先フォルダーです。未設定の場合は、出力先フォルダー配下の_quickを使用します。",
        "unitTestRunner.quickReusePreviousWorkspace": "クイックチェックで同じ関数の出力ワークスペース名を固定し、繰り返し実行しやすくします。",
        "unitTestRunner.quickAutoOpenSummary": "クイックチェック成功後に概要レポート（quick_summary.md）を自動で開きます。",
        "unitTestRunner.quickAllowExecution": "将来、クイックチェックから実行を伴うプロファイルを許可するための安全設定です。現在の既定プロファイルでは、ビルドやテストを実行しません。",
        "unitTestRunner.useJsonOutput": "CLIコマンドに--jsonを渡し、生成されたレポートのパスを機械可読形式で受け取ります。",
        "unitTestRunner.showOutputChannel": "コマンド実行時に［Unit Test Runner］出力チャンネルを表示します。",
        "unitTestRunner.runBuildProbeRequiresConfirmation": "ビルドを実行する前に確認ダイアログを表示します。",
        "unitTestRunner.runTestsRequiresConfirmation": "生成したテストを実行する前に確認ダイアログを表示します。",
        "unitTestRunner.commandTimeoutSeconds": "CLIコマンドがタイムアウトするまでの秒数です。",
    }
    for key, description in descriptions.items():
        if key not in properties:
            raise AssertionError(f"package.json property not found: {key}")
        properties[key]["description"] = description

    quick_profile = properties["unitTestRunner.quickProfile"]
    quick_profile["enumDescriptions"] = [
        "関数解析とテスト設計まで実行します。",
        "テストハーネスの生成まで実行します。",
        "ビルドの事前確認まで実行します。",
    ]

    path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    # Settings model and renderer
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """      label: 'プロジェクトルート',
      settingKey: 'unitTestRunner.sourceRoot',
      description: '本番ソースを読むルートフォルダです。未設定時はVS Codeで開いた先頭フォルダを使います。',
""",
        """      label: 'ソースのルートフォルダー',
      settingKey: 'unitTestRunner.sourceRoot',
      description: 'テスト対象のソースコードを読み込むルートフォルダーです。未設定の場合は、VS Codeで最初に開いたフォルダーを使用します。',
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """        { id: 'pickSourceRoot', kind: 'pickFolder', label: 'フォルダを選択', primary: true },
        { id: 'inputSourceRoot', kind: 'inputText', label: 'パスを入力' },
""",
        """        { id: 'pickSourceRoot', kind: 'pickFolder', label: 'フォルダーを選択', primary: true },
        { id: 'inputSourceRoot', kind: 'inputText', label: 'フォルダーのパスを入力' },
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """      label: 'VC6 .dsw',
      settingKey: 'unitTestRunner.dswPath',
      description: '対象プロジェクトのVisual C++ 6.0 workspaceファイルです。',
""",
        """      label: 'VC6ワークスペースファイル（.dsw）',
      settingKey: 'unitTestRunner.dswPath',
      description: 'テスト対象プロジェクトのVisual C++ 6.0ワークスペースファイルです。',
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """        { id: 'pickDswPath', kind: 'pickFile', label: '.dswを選択', primary: true },
        { id: 'inputDswPath', kind: 'inputText', label: 'パスを入力' },
""",
        """        { id: 'pickDswPath', kind: 'pickFile', label: '.dswファイルを選択', primary: true },
        { id: 'inputDswPath', kind: 'inputText', label: 'ファイルのパスを入力' },
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """      label: '出力ルート',
      settingKey: 'unitTestRunner.outputRoot',
      description: 'dossierやテスト設計などの生成物を書き出す外部フォルダです。',
""",
        """      label: '出力先フォルダー',
      settingKey: 'unitTestRunner.outputRoot',
      description: '関数分析レポートやテスト設計などの生成物を保存する出力先フォルダーです。ソースのルートフォルダーとは別の場所を指定してください。',
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """        { id: 'pickOutputRoot', kind: 'pickFolder', label: '出力フォルダを選択', primary: true },
        { id: 'inputOutputRoot', kind: 'inputText', label: 'パスを入力' },
""",
        """        { id: 'pickOutputRoot', kind: 'pickFolder', label: '出力先フォルダーを選択', primary: true },
        { id: 'inputOutputRoot', kind: 'inputText', label: 'フォルダーのパスを入力' },
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """      label: 'スイートmanifest',
      settingKey: 'unitTestRunner.suiteManifestPath',
      description: '複数関数回帰スイートのmanifestです。未設定時は出力ルート配下の suites/default を使います。',
""",
        """      label: 'スイート定義ファイル',
      settingKey: 'unitTestRunner.suiteManifestPath',
      description: '複数の関数をまとめて実行するテストスイートの定義ファイルです。未設定の場合は、出力先フォルダー配下のsuites\\\\default\\\\suite_manifest.jsonを使用します。',
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """        { id: 'pickSuiteManifestPath', kind: 'pickFile', label: 'manifestを選択' },
        { id: 'inputSuiteManifestPath', kind: 'inputText', label: 'パスを入力' },
""",
        """        { id: 'pickSuiteManifestPath', kind: 'pickFile', label: '定義ファイルを選択' },
        { id: 'inputSuiteManifestPath', kind: 'inputText', label: 'ファイルのパスを入力' },
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """      label: '既定構成',
      settingKey: 'unitTestRunner.defaultConfiguration',
      description: '解析時に既定で渡すVC6構成名です。',
""",
        """      label: '既定のビルド構成',
      settingKey: 'unitTestRunner.defaultConfiguration',
      description: '関数解析とビルドで既定として使用するVisual C++ 6.0のビルド構成名です。',
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        "{ id: 'inputDefaultConfiguration', kind: 'inputText', label: '構成名を入力', primary: true }",
        "{ id: 'inputDefaultConfiguration', kind: 'inputText', label: 'ビルド構成名を入力', primary: true }",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """      label: '既定プロジェクト',
      settingKey: 'unitTestRunner.defaultProject',
      description: 'ソースが複数プロジェクトに属する場合の既定プロジェクト名です。',
""",
        """      label: '既定のVC6プロジェクト',
      settingKey: 'unitTestRunner.defaultProject',
      description: 'ソースファイルが複数のVisual C++ 6.0プロジェクトに含まれる場合に使用する既定のプロジェクト名です。',
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        "{ id: 'resetDefaultProject', kind: 'reset', label: 'クリア' }",
        "{ id: 'resetDefaultProject', kind: 'reset', label: '設定をクリア' }",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """      label: 'VC6 vcvars32.bat',
      settingKey: 'unitTestRunner.vcvarsPath',
      description: 'ビルドプローブ実行前に呼び出すVC6環境設定バッチです。nmake/clがPATHに無い場合に指定します。',
""",
        """      label: 'VC6環境設定ファイル',
      settingKey: 'unitTestRunner.vcvarsPath',
      description: 'ビルド前に実行するVisual C++ 6.0の環境設定バッチファイルです。nmakeまたはclがPATHにない場合に指定します。',
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """        { id: 'pickVcvarsPath', kind: 'pickFile', label: 'batを選択', primary: true },
        { id: 'inputVcvarsPath', kind: 'inputText', label: 'パスを入力' },
        { id: 'resetVcvarsPath', kind: 'reset', label: 'クリア' },
""",
        """        { id: 'pickVcvarsPath', kind: 'pickFile', label: 'バッチファイルを選択', primary: true },
        { id: 'inputVcvarsPath', kind: 'inputText', label: 'ファイルのパスを入力' },
        { id: 'resetVcvarsPath', kind: 'reset', label: '設定をクリア' },
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """      label: 'CLI実行ファイル',
      settingKey: 'unitTestRunner.cliPath',
      description: '通常は同梱CLIを使います。外部exeを使う場合だけ指定します。',
""",
        """      label: 'UnitTestRunnerの実行ファイル',
      settingKey: 'unitTestRunner.cliPath',
      description: '通常は同梱のCLIを使用します。外部の実行ファイルを使用する場合だけ指定してください。',
""",
    )
    replace_exact(
        "vscode/extension/src/config/settingsViewModel.ts",
        """        { id: 'pickCliPath', kind: 'pickFile', label: 'exeを選択' },
        { id: 'inputCliPath', kind: 'inputText', label: 'パスを入力' },
""",
        """        { id: 'pickCliPath', kind: 'pickFile', label: '実行ファイルを選択' },
        { id: 'inputCliPath', kind: 'inputText', label: '実行ファイルのパスを入力' },
""",
    )

    replace_exact(
        "vscode/extension/src/workflow/settingsPanelRenderer.ts",
        "const readyLabel = settings.ready ? '設定確認は完了しています。' : '未設定の必須項目があります。';",
        "const readyLabel = settings.ready ? '必須項目はすべて設定されています。' : '必須項目に未設定があります。各項目を確認してください。';",
    )
    replace_exact(
        "vscode/extension/src/workflow/settingsPanelRenderer.ts",
        '<span class="settings-toggle settings-expanded-label">設定を隠す</span>',
        '<span class="settings-toggle settings-expanded-label">設定を閉じる</span>',
    )
    replace_exact(
        "vscode/extension/src/workflow/settingsPanelRenderer.ts",
        "設定値: ${escapeHtml(field.configuredValue)}",
        "保存されている設定: ${escapeHtml(field.configuredValue)}",
    )

    # Validation messages shown in the GUI
    replace_exact(
        "vscode/extension/src/config/validation.ts",
        "warnings.push({ code: 'missing_cli_path', message: 'unitTestRunner.cliPath が未設定です。' });",
        "warnings.push({ code: 'missing_cli_path', message: 'UnitTestRunnerの実行ファイルが設定されていません。' });",
    )
    replace_exact(
        "vscode/extension/src/config/validation.ts",
        "warnings.push({ code: 'missing_source_root', message: 'unitTestRunner.sourceRoot が未設定です。' });",
        "warnings.push({ code: 'missing_source_root', message: 'ソースのルートフォルダーが設定されていません。' });",
    )
    replace_exact(
        "vscode/extension/src/config/validation.ts",
        "warnings.push({ code: 'missing_dsw_path', message: 'unitTestRunner.dswPath が未設定です。' });",
        "warnings.push({ code: 'missing_dsw_path', message: 'VC6ワークスペースファイル（.dsw）が設定されていません。' });",
    )
    replace_exact(
        "vscode/extension/src/config/validation.ts",
        "warnings.push({ code: 'missing_output_root', message: 'unitTestRunner.outputRoot が未設定です。' });",
        "warnings.push({ code: 'missing_output_root', message: '出力先フォルダーが設定されていません。' });",
    )
    replace_exact(
        "vscode/extension/src/config/validation.ts",
        "warnings.push({ code: 'output_root_inside_source_root', message: 'unitTestRunner.outputRoot が sourceRoot 配下です。本番リポジトリへ生成物が混入する可能性があります。' });",
        "warnings.push({ code: 'output_root_inside_source_root', message: '出力先フォルダーがソースのルートフォルダー内にあります。生成物が本番ソースへ混在する可能性があります。別のフォルダーを指定してください。' });",
    )
    replace_exact(
        "vscode/extension/src/config/validation.ts",
        "warnings.push({ code: 'quick_output_root_inside_source_root', message: 'unitTestRunner.quickOutputRoot が sourceRoot 配下です。Quick Check生成物が本番リポジトリへ混入する可能性があります。' });",
        "warnings.push({ code: 'quick_output_root_inside_source_root', message: 'クイックチェックの出力先がソースのルートフォルダー内にあります。生成物が本番ソースへ混在する可能性があります。別のフォルダーを指定してください。' });",
    )

    # Detailed workflow copy
    state_replacements = [
        ("purpose: 'sourceRoot、dswPath、outputRoot、CLIの利用準備を確認します。'", "purpose: 'ソースのルートフォルダー、VC6ワークスペースファイル、出力先フォルダー、UnitTestRunnerの実行ファイルを確認します。'"),
        ("requiredAction: 'VS Code設定で対象プロジェクトと外部出力workspaceを指定します。'", "requiredAction: '［設定］でテスト対象プロジェクトと出力先を指定します。'"),
        ("label: '最後のCLIをコピー'", "label: '最後に実行したCLIコマンドをコピー'"),
        ("title: '2. 関数解析'", "title: '2. 関数を解析'"),
        ("purpose: '現在のCファイルと関数を対象にdossierを生成します。'", "purpose: '現在のCソースファイルと対象関数を解析し、関数分析レポートを生成します。'"),
        ("requiredAction: '関数内にカーソルを置くか関数名を選択して解析します。'", "requiredAction: '関数内にカーソルを置くか関数名を選択して、解析を実行します。'"),
        ("label: '現在関数を解析', repeatLabel: '現在関数の解析を再実行'", "label: '現在の関数を解析', repeatLabel: '現在の関数を再解析'"),
        ("label: '選択関数を解析', repeatLabel: '選択関数の解析を再実行'", "label: '選択した関数を解析', repeatLabel: '選択した関数を再解析'"),
        ("title: '3. function_dossier.md 確認'", "title: '3. 関数分析レポート（function_dossier.md）を確認'"),
        ("purpose: '関数概要、依存、カバレッジ、未解決事項の入口を確認します。'", "purpose: '関数の概要、依存関係、カバレッジ、未解決事項を確認します。'"),
        ("requiredAction: 'dossierを開き、必要なレビューを行って保存または確定します。'", "requiredAction: 'function_dossier.mdを開いて内容を確認し、必要に応じて修正して保存します。'"),
        ("label: 'dossierを開く'", "label: '関数分析レポートを開く'"),
        ("title: '4. レビュー項目確認'", "title: '4. レビュー項目を確認'"),
        ("purpose: 'review checklist、unresolved items、next actionsを確認します。'", "purpose: 'レビュー確認リスト、未解決項目、次に行う操作を確認します。'"),
        ("requiredAction: '未解決項目と次アクションを確認し、必要なら編集して保存します。'", "requiredAction: '未解決項目と次に行う操作を確認し、必要に応じて編集して保存します。'"),
        ("label: '次のアクションを開く'", "label: '次に行う操作を開く'"),
        ("title: '5. テスト設計生成'", "title: '5. テスト設計を生成'"),
        ("purpose: 'dossierからtest_case_designを生成します。'", "purpose: '関数分析レポートからテストケース設計を生成します。'"),
        ("requiredAction: 'テスト設計生成コマンドを実行します。'", "requiredAction: '［テスト設計を生成］を実行します。'"),
        ("title: '6. test_case_design.csv 確認'", "title: '6. テストケース設計を確認'"),
        ("purpose: '生成されたテストケース設計を確認します。CSVは一覧確認、Markdownはレビュー、JSONはハーネス生成の入力です。'", "purpose: '生成されたテストケース設計を確認します。CSVは一覧確認、Markdownはレビュー、JSONはテストハーネス生成に使用します。'"),
        ("requiredAction: 'CSV/Markdown/JSONを開き、TBD_EXPECTED_RETURNやreview_required項目を埋めて保存または確定します。'", "requiredAction: 'CSV、Markdown、JSONを開き、TBD_EXPECTED_RETURNやreview_requiredの項目を入力して保存します。'"),
        ("label: 'CSVを開く'", "label: 'テスト設計（CSV）を開く'"),
        ("label: 'Markdownを開く'", "label: 'レビュー用Markdownを開く'"),
        ("label: 'JSONを開く'", "label: '生成用JSONを開く'"),
        ("title: '7. ハーネス生成'", "title: '7. テストハーネスを生成'"),
        ("purpose: 'レビュー済みtest_case_design.jsonを使い、Build Probeの前提になるharness_skeleton_reportを生成します。'", "purpose: 'レビュー済みのtest_case_design.jsonから、ビルドの事前確認に使用するテストハーネスを生成します。'"),
        ("requiredAction: 'test_case_design.jsonの期待値とレビュー項目を保存した後に、ハーネス生成を実行します。'", "requiredAction: 'test_case_design.jsonの期待値とレビュー項目を保存してから、テストハーネスを生成します。'"),
        ("label: 'ハーネスを生成', repeatLabel: 'ハーネスを再生成'", "label: 'テストハーネスを生成', repeatLabel: 'テストハーネスを再生成'"),
        ("title: '8. ビルドプローブ dry-run'", "title: '8. ビルドの事前確認'"),
        ("purpose: 'harness_skeleton_report.jsonを使い、実ビルド前に生成workspaceとbuild準備を確認します。'", "purpose: 'harness_skeleton_report.jsonを使用し、実際にビルドする前に生成ワークスペースとビルド手順を確認します。'"),
        ("requiredAction: 'ハーネス生成が完了してから、dry-runでBuild Probeを実行します。'", "requiredAction: 'テストハーネスの生成後に、ビルドの事前確認を実行します。'"),
        ("label: 'dry-runを実行', repeatLabel: 'dry-runを再実行'", "label: '事前確認を実行', repeatLabel: '事前確認を再実行'"),
        ("title: '9. ビルドプローブレポート確認'", "title: '9. ビルド結果を確認'"),
        ("purpose: 'ビルドプローブ結果と未解決のビルド項目を確認します。'", "purpose: 'ビルドの事前確認結果と、未解決のビルド項目を確認します。'"),
        ("label: 'ビルドレポートを開く'", "label: 'ビルド結果レポートを開く'"),
        ("title: '10. ビルドプローブ実行'", "title: '10. ビルドを実行'"),
        ("purpose: '生成されたビルド手順を明示確認のうえ実行します。'", "purpose: '生成されたテストを、確認後にビルドします。'"),
        ("requiredAction: '確認ダイアログを承認してビルドプローブを実行します。'", "requiredAction: '確認ダイアログで内容を確認し、ビルドを実行します。'"),
        ("label: 'ビルドプローブを実行', repeatLabel: 'ビルドプローブを再実行'", "label: 'ビルドを実行', repeatLabel: 'ビルドを再実行'"),
        ("title: '11. 生成テスト実行'", "title: '11. テストを実行'"),
        ("purpose: '生成テストを明示確認のうえ実行します。'", "purpose: '生成されたテストを、確認後に実行します。'"),
        ("requiredAction: '確認ダイアログを承認してテストを実行します。'", "requiredAction: '確認ダイアログで内容を確認し、テストを実行します。'"),
        ("title: '12. エビデンス準備'", "title: '12. 検証資料を作成'"),
        ("purpose: '実行結果とmanifestをレビュー用エビデンスへ整理します。'", "purpose: '実行結果と定義ファイルを、レビュー用の検証資料として整理します。'"),
        ("requiredAction: 'エビデンス準備コマンドを実行します。'", "requiredAction: '［検証資料を作成］を実行します。'"),
        ("label: 'エビデンスを準備', repeatLabel: 'エビデンスを再生成'", "label: '検証資料を作成', repeatLabel: '検証資料を再作成'"),
        ("title: '13. 実行結果・エビデンス確認'", "title: '13. 実行結果と検証資料を確認'"),
        ("purpose: 'test_execution_reportとevidence_packageを確認します。'", "purpose: 'テスト実行レポートと検証資料を確認します。'"),
        ("requiredAction: '実行結果とエビデンスを開き、保存または確定します。'", "requiredAction: '実行結果と検証資料を開き、内容を確認して保存します。'"),
        ("label: 'エビデンスを開く'", "label: '検証資料を開く'"),
        ("purpose: 'dossier、テスト実行、エビデンス確認が完了しています。'", "purpose: '関数分析レポート、テスト実行、検証資料の確認が完了しています。'"),
        ("requiredAction: '必要に応じて出力workspaceを開くか、次の関数へ進みます。'", "requiredAction: '必要に応じて出力ワークスペースを開くか、次の関数のテストへ進みます。'"),
        ("label: '出力workspaceを開く'", "label: '出力ワークスペースを開く'"),
        ("label: '変更後に再解析'", "label: '変更後の関数を再解析'"),
        ("label: '回帰選定を開く'", "label: '回帰テストの選定結果を開く'"),
    ]
    for old, new in state_replacements:
        expected = 2 if old == "label: '最後のCLIをコピー'" else 1
        if old == "label: '出力workspaceを開く'":
            expected = 2
        replace_exact("vscode/extension/src/workflow/workflowState.ts", old, new, expected)

    # Workflow panel copy
    panel_replacements = [
        ("label: 'Quick Checkを実行'", "label: 'クイックチェックを実行'"),
        ("repeatLabel: 'Quick Checkを再実行'", "repeatLabel: 'クイックチェックを再実行'"),
        ("label: 'Quick Summaryを開く'", "label: 'クイックチェックの概要を開く'"),
        ("label: '出力workspaceを開く'", "label: '出力ワークスペースを開く'"),
        ("label: 'Full Gateへ進む'", "label: 'フルゲートへ進む'"),
        ("`UnitTestRunner: ${this.runningLabel}を実行中です。完了するまでお待ちください。`", "`UnitTestRunner: 「${this.runningLabel}」を実行しています。完了するまでほかの操作はできません。`"),
        ("'UnitTestRunner: 対象レポートがまだ記録されていません。'", "'UnitTestRunner: 対象のレポートはまだ作成されていません。先に該当する処理を実行してください。'"),
        ("`UnitTestRunner: レポートが見つかりません: ${reportPath}`", "`UnitTestRunner: レポートが見つかりません。確認先: ${reportPath}`"),
        ("const functionName = state.functionName || '対象関数未選択';", "const functionName = state.functionName || '対象の関数が選択されていません';"),
        ("const workspace = state.outputWorkspace || state.reports?.workspace || '出力workspace未選択';", "const workspace = state.outputWorkspace || state.reports?.workspace || '出力ワークスペースが選択されていません';"),
        ("`<div class=\"notice\">保存待ち: ${escapeHtml(state.awaitingSave.filePath)}</div>`", "`<div class=\"notice\">保存を待っています: ${escapeHtml(state.awaitingSave.filePath)}</div>`"),
        ("`<div class=\"error\">直近エラー: ${escapeHtml(state.lastError)}</div>`", "`<div class=\"error\">前回のエラー: ${escapeHtml(state.lastError)}</div>`"),
        ("`<div class=\"busy\" role=\"status\">実行中: ${escapeHtml(runningLabel)}<br><span>大きいプロジェクトでは時間がかかります。完了までボタンは無効です。</span></div>`", "`<div class=\"busy\" role=\"status\">「${escapeHtml(runningLabel)}」を実行しています。<br><span>大きなプロジェクトでは時間がかかる場合があります。完了するまでほかの操作はできません。</span></div>`"),
        ("<span>完了ステップ</span>", "<span>完了したステップ</span>"),
        ("<span>簡易ステップ</span>", "<span>全ステップ</span>"),
        ("<h2>結果・補助</h2>", "<h2>結果と補助操作</h2>"),
        ("正式レビューや証跡確認の全工程を見る場合は詳細表示に切り替えます。", "レビュー項目や検証資料を含むすべてのステップを確認する場合は、詳細表示に切り替えてください。"),
        ("title: '1. Quick Check', description: '解析とテスト生成を行います。'", "title: '1. クイックチェック', description: '関数を解析し、テスト設計とテストソースを生成します。'"),
        ("title: '2. テストソース確認'", "title: '2. テストソースを確認'"),
        ("title: '4. テスト実行'", "title: '4. テストを実行'"),
        ("<h2>任意操作</h2>", "<h2>その他の操作</h2>"),
        ("return '設定操作';", "return '設定を変更';"),
        ("return '工程を更新';", "return 'ステップを完了';"),
        ("return '出力workspaceを開く';", "return '出力ワークスペースを開く';"),
        ("return '最後のCLIコマンドをコピー';", "return '最後に実行したCLIコマンドをコピー';"),
        ("'unitTestRunner.quickCheckCurrentFunction': 'Quick Check'", "'unitTestRunner.quickCheckCurrentFunction': 'クイックチェック'"),
        ("'unitTestRunner.quickCheckSelectedFunction': 'Quick Check'", "'unitTestRunner.quickCheckSelectedFunction': 'クイックチェック'"),
        ("'unitTestRunner.openQuickSummary': 'Quick Summaryを開く'", "'unitTestRunner.openQuickSummary': 'クイックチェックの概要を開く'"),
        ("'unitTestRunner.runFullGateForCurrentFunction': 'Full Gateへ進む'", "'unitTestRunner.runFullGateForCurrentFunction': 'フルゲートへ進む'"),
        ("'unitTestRunner.analyzeCurrentFunction': '現在関数を解析'", "'unitTestRunner.analyzeCurrentFunction': '現在の関数を解析'"),
        ("'unitTestRunner.analyzeSelectedFunction': '選択関数を解析'", "'unitTestRunner.analyzeSelectedFunction': '選択した関数を解析'"),
        ("'unitTestRunner.reanalyzeCurrentFunction': '現在関数を再解析'", "'unitTestRunner.reanalyzeCurrentFunction': '現在の関数を再解析'"),
        ("'unitTestRunner.finalizeDossier': 'dossierを確定'", "'unitTestRunner.finalizeDossier': '関数分析レポートを確定'"),
        ("'unitTestRunner.generateHarnessSkeleton': 'ハーネスを生成'", "'unitTestRunner.generateHarnessSkeleton': 'テストハーネスを生成'"),
        ("'unitTestRunner.buildProbeDryRun': 'ビルドプローブをdry-run'", "'unitTestRunner.buildProbeDryRun': 'ビルドの事前確認を実行'"),
        ("'unitTestRunner.runBuildProbe': 'ビルド実行'", "'unitTestRunner.runBuildProbe': 'ビルドを実行'"),
        ("'unitTestRunner.runTests': 'テスト実行'", "'unitTestRunner.runTests': 'テストを実行'"),
        ("'unitTestRunner.prepareEvidence': 'エビデンスを準備'", "'unitTestRunner.prepareEvidence': '検証資料を作成'"),
        ("return commandId ? labels[commandId] ?? commandId : 'コマンド実行';", "return commandId ? labels[commandId] ?? commandId : 'コマンドを実行';"),
    ]
    for old, new in panel_replacements:
        replace_exact("vscode/extension/src/workflow/workflowPanelBase.ts", old, new)

    # Suite side panel
    suite_panel_replacements = [
        ("`UnitTestRunner: ${this.runningLabel}を実行中です。完了するまでお待ちください。`", "`UnitTestRunner: 「${this.runningLabel}」を実行しています。完了するまでほかの操作はできません。`"),
        ("? `<div class=\"summary\">GREEN ${model.summary.green} / Not GREEN ${model.summary.notGreen} / Total ${model.summary.total}</div>`", "? `<div class=\"summary\">合計 ${model.summary.total}件 / 合格 ${model.summary.green}件 / 不合格 ${model.summary.notGreen}件</div>`"),
        ("`<div class=\"busy\" role=\"status\">実行中: ${escapeHtml(runningLabel)}<br><span>処理が完了するまでボタンと選択は無効です。</span></div>`", "`<div class=\"busy\" role=\"status\">「${escapeHtml(runningLabel)}」を実行しています。<br><span>処理が完了するまでボタンと選択は変更できません。</span></div>`"),
        ("model.suitePath || 'suite manifest未設定'", "model.suitePath || 'スイート定義ファイルが設定されていません'"),
        (">現在関数を登録</button>", ">現在の関数をスイートに登録</button>"),
        (">広い一覧を開く</button>", ">スイート一覧を開く</button>"),
        (">選択を実行</button>", ">選択したテストを実行</button>"),
        (">タグ指定で実行</button>", ">タグを指定して実行</button>"),
        (">全件GREEN確認</button>", ">全件テストを実行して合否を確認</button>"),
        (">manifestを開く</button>", ">スイート定義ファイルを開く</button>"),
        ("'<p class=\"empty\">登録済み関数はありません。</p>'", "'<p class=\"empty\">登録済みの関数はありません。［現在の関数をスイートに登録］から追加してください。</p>'"),
        ("entry.greenStatus === 'green' ? 'GREEN' : entry.greenStatus === 'not_green' ? 'Not GREEN' : '未実行'", "entry.greenStatus === 'green' ? '合格' : entry.greenStatus === 'not_green' ? '不合格' : '未実行'"),
        ("${escapeHtml(entry.lastRunStatus)}", "${escapeHtml(suiteExecutionStatusLabel(entry.lastRunStatus))}"),
        ("register: '現在関数を登録'", "register: '現在の関数をスイートに登録'"),
        ("runSelected: '選択を実行'", "runSelected: '選択したテストを実行'"),
        ("runTag: 'タグ指定で実行'", "runTag: 'タグを指定して実行'"),
        ("runAllGreen: '全件GREEN確認'", "runAllGreen: '全件テストを実行して合否を確認'"),
        ("openSuite: '広い一覧を開く'", "openSuite: 'スイート一覧を開く'"),
        ("openManifest: 'manifestを開く'", "openManifest: 'スイート定義ファイルを開く'"),
        ("toggleEntry: '選択を更新'", "toggleEntry: '選択状態を更新'"),
    ]
    for old, new in suite_panel_replacements:
        replace_exact("vscode/extension/src/suite/suitePanel.ts", old, new)
    replace_exact(
        "vscode/extension/src/suite/suitePanel.ts",
        """function suiteActionLabel(kind: SuiteActionMessage['kind']): string {
""",
        """function suiteExecutionStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    passed: '成功',
    failed: '失敗',
    error: 'エラー',
    skipped: 'スキップ',
    not_run: '未実行',
    suite_run_completed: '完了',
    suite_run_failed: '失敗',
  };
  return labels[status] ?? (status || '未実行');
}

function suiteActionLabel(kind: SuiteActionMessage['kind']): string {
""",
    )

    # Suite dashboard
    suite_dashboard_replacements = [
        ("'UnitTestRunner スイート'", "'UnitTestRunner テストスイート'"),
        ("`UnitTestRunner: ${this.runningLabel}を実行中です。完了するまでお待ちください。`", "`UnitTestRunner: 「${this.runningLabel}」を実行しています。完了するまでほかの操作はできません。`"),
        ("const reportState = model.reportExists ? escapeHtml(model.lastRunStatus) : '実行結果なし';", "const reportState = model.reportExists ? escapeHtml(suiteExecutionStatusLabel(model.lastRunStatus)) : '実行結果はありません';"),
        ("`<div class=\"error\">直近エラー: ${escapeHtml(model.lastError)}</div>`", "`<div class=\"error\">前回のエラー: ${escapeHtml(model.lastError)}</div>`"),
        ("`<div class=\"busy\" role=\"status\">実行中: ${escapeHtml(runningLabel)}<br><span>処理が完了するまでボタンと選択は無効です。</span></div>`", "`<div class=\"busy\" role=\"status\">「${escapeHtml(runningLabel)}」を実行しています。<br><span>処理が完了するまでボタンと選択は変更できません。</span></div>`"),
        ("<h1>スイート</h1>", "<h1>テストスイート</h1>"),
        ("model.suitePath || 'suite manifest未設定'", "model.suitePath || 'スイート定義ファイルが設定されていません'"),
        ("直近レポート:", "最新の実行レポート:"),
        ("renderMetric('Total'", "renderMetric('合計'"),
        ("renderMetric('GREEN'", "renderMetric('合格'"),
        ("renderMetric('Not GREEN'", "renderMetric('不合格'"),
        ("renderMetric('Executed'", "renderMetric('実行済み'"),
        ("renderMetric('Failed'", "renderMetric('失敗'"),
        (">現在関数を登録</button>", ">現在の関数をスイートに登録</button>"),
        (">選択を実行</button>", ">選択したテストを実行</button>"),
        (">タグ指定で実行</button>", ">タグを指定して実行</button>"),
        (">全件GREEN確認</button>", ">全件テストを実行して合否を確認</button>"),
        (">manifestを開く</button>", ">スイート定義ファイルを開く</button>"),
        ("'<div class=\"empty\">登録済み関数はありません。</div>'", "'<div class=\"empty\">登録済みの関数はありません。［現在の関数をスイートに登録］から追加してください。</div>'"),
        ("<th>ソース</th>", "<th>ソースファイル</th>"),
        ("<th>GREEN</th>", "<th>合否</th>"),
        ("<th>実行status</th>", "<th>実行結果</th>"),
        ("<th>テスト</th>", "<th>テスト結果</th>"),
        ("<th>未解決</th>", "<th>未解決項目</th>"),
        ("<th>workspace</th>", "<th>ワークスペース</th>"),
        ("entry.greenStatus === 'green' ? 'GREEN' : entry.greenStatus === 'not_green' ? 'Not GREEN' : '未実行'", "entry.greenStatus === 'green' ? '合格' : entry.greenStatus === 'not_green' ? '不合格' : '未実行'"),
        ("${escapeHtml(entry.lastRunStatus)}", "${escapeHtml(suiteExecutionStatusLabel(entry.lastRunStatus))}"),
        ("register: '現在関数を登録'", "register: '現在の関数をスイートに登録'"),
        ("runSelected: '選択を実行'", "runSelected: '選択したテストを実行'"),
        ("runTag: 'タグ指定で実行'", "runTag: 'タグを指定して実行'"),
        ("runAllGreen: '全件GREEN確認'", "runAllGreen: '全件テストを実行して合否を確認'"),
        ("openManifest: 'manifestを開く'", "openManifest: 'スイート定義ファイルを開く'"),
        ("toggleEntry: '選択を更新'", "toggleEntry: '選択状態を更新'"),
    ]
    for old, new in suite_dashboard_replacements:
        replace_exact("vscode/extension/src/suite/suiteDashboard.ts", old, new)
    replace_exact(
        "vscode/extension/src/suite/suiteDashboard.ts",
        """function suiteDashboardActionLabel(kind: SuiteDashboardMessage['kind']): string {
""",
        """function suiteExecutionStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    passed: '成功',
    failed: '失敗',
    error: 'エラー',
    skipped: 'スキップ',
    not_run: '未実行',
    suite_run_completed: '完了',
    suite_run_failed: '失敗',
  };
  return labels[status] ?? (status || '未実行');
}

function suiteDashboardActionLabel(kind: SuiteDashboardMessage['kind']): string {
""",
    )

    # Extension prompts, dialogs, notifications, and errors
    extension_replacements = [
        ("'UnitTestRunner: 保存を検知し、次の工程へ進めました。'", "'UnitTestRunner: ファイルの保存を確認しました。次のステップへ進めます。'"),
        ("placeHolder: '開くテストソースを選択してください。'", "placeHolder: '開くテストソースを選んでください。'"),
        ("`生成テストソースが見つかりません: ${candidates[0]}`", "`生成したテストソースが見つかりません。確認先: ${candidates[0]}`"),
        ("prompt: '生成テストソースを開く関数名を入力してください。'", "prompt: 'テストソースを開く対象の関数名を入力してください。'"),
        ("'Cの関数識別子を入力してください。'", "'C言語の関数名として有効な識別子を入力してください。'"),
        ("'関数名の指定が必要です。'", "'関数名を入力してください。'"),
        ("'UnitTestRunnerを実行する前にCソースファイルを開いてください。'", "'Cソースファイルを開き、対象の関数内にカーソルを置いてから実行してください。'"),
        ("'UnitTestRunner: 現在関数をスイートに登録しました。'", "'UnitTestRunner: 現在の関数をテストスイートに登録しました。'"),
        ("prompt: '実行するスイートタグを入力してください。'", "prompt: '実行するテストに付けられたタグを入力してください。'"),
        ("'スイートタグの指定が必要です。'", "'実行するタグを入力してください。'"),
        ("'スイートで実行する関数を選択してください。'", "'テストスイートで実行する関数を選択してください。'"),
        ("throw new Error(`UnitTestRunnerの設定が不足しています: ${validation.warnings.map((warning) => warning.message).join(' ')}`);", "throw new Error(`UnitTestRunnerの必須設定が不足しています。ワークフローパネルの［設定］を確認してください。${validation.warnings.map((warning) => ` ${warning.message}`).join('')}`);"),
        ("throw new Error(`Unknown settings field: ${fieldId}`);", "throw new Error(`設定項目を認識できません: ${fieldId}`);"),
        ("if (kind === 'pickFolder') {\n    const selected = await vscode.window.showOpenDialog({\n      canSelectFiles: false,\n      canSelectFolders: true,\n      canSelectMany: false,\n      defaultUri: defaultUriForField(field.effectiveValue, false),\n      openLabel: '選択',\n      title: `${field.label}を選択`,", "if (kind === 'pickFolder') {\n    const selected = await vscode.window.showOpenDialog({\n      canSelectFiles: false,\n      canSelectFolders: true,\n      canSelectMany: false,\n      defaultUri: defaultUriForField(field.effectiveValue, false),\n      openLabel: 'このフォルダーを選択',\n      title: `${field.label}を選択`,"),
        ("if (kind === 'pickFile') {\n    const selected = await vscode.window.showOpenDialog({\n      canSelectFiles: true,\n      canSelectFolders: false,\n      canSelectMany: false,\n      defaultUri: defaultUriForField(field.configuredValue || field.effectiveValue, true),\n      filters: filePickerFilters(fieldId),\n      openLabel: '選択',\n      title: `${field.label}を選択`,", "if (kind === 'pickFile') {\n    const selected = await vscode.window.showOpenDialog({\n      canSelectFiles: true,\n      canSelectFolders: false,\n      canSelectMany: false,\n      defaultUri: defaultUriForField(field.configuredValue || field.effectiveValue, true),\n      filters: filePickerFilters(fieldId),\n      openLabel: 'このファイルを選択',\n      title: `${field.label}を選択`,"),
        ("'UnitTestRunnerの設定を保存するには、フォルダまたはworkspaceを開いてください。'", "'設定を保存するには、VS Codeでフォルダーまたはワークスペースを開いてください。'"),
        ("return { 'Visual C++ workspace': ['dsw'], 'すべてのファイル': ['*'] };", "return { 'Visual C++ワークスペース': ['dsw'], 'すべてのファイル': ['*'] };"),
        ("return { 'Batch files': ['bat', 'cmd'], 'すべてのファイル': ['*'] };", "return { 'バッチファイル': ['bat', 'cmd'], 'すべてのファイル': ['*'] };"),
        ("'プロジェクトルートのフォルダパスを入力してください。空にするとVS Codeで開いたTOPフォルダを使います。'", "'ソースのルートフォルダーのパスを入力してください。空欄の場合は、VS Codeで最初に開いたフォルダーを使用します。'"),
        ("'VC6 .dsw ファイルの絶対パスを入力してください。'", "'VC6ワークスペースファイル（.dsw）の絶対パスを入力してください。'"),
        ("'生成物の出力ルートフォルダを入力してください。関数名フォルダはこの下に自動作成されます。'", "'生成物を保存する出力先フォルダーを入力してください。関数ごとのフォルダーは、この中に自動で作成されます。'"),
        ("'複数関数回帰スイートmanifestのパスを入力してください。空にすると outputRoot\\\\suites\\\\default\\\\suite_manifest.json を使います。'", "'テストスイートの定義ファイルのパスを入力してください。空欄の場合は、出力先フォルダー配下のsuites\\\\default\\\\suite_manifest.jsonを使用します。'"),
        ("'VC6構成名を入力してください。'", "'Visual C++ 6.0のビルド構成名を入力してください。'"),
        ("'既定プロジェクト名を入力してください。空にすると指定なしになります。'", "'既定として使用するVisual C++ 6.0のプロジェクト名を入力してください。空欄の場合は指定しません。'"),
        ("'VC6環境設定バッチの絶対パスを入力してください。例: C:\\\\Program Files\\\\Microsoft Visual Studio\\\\VC98\\\\Bin\\\\VCVARS32.BAT'", "'Visual C++ 6.0の環境設定バッチファイルの絶対パスを入力してください。例: C:\\\\Program Files\\\\Microsoft Visual Studio\\\\VC98\\\\Bin\\\\VCVARS32.BAT'"),
        ("'外部CLI exeの絶対パスを入力してください。同梱CLIを使う場合は unit-test-runner または空にします。'", "'外部のUnitTestRunner実行ファイルの絶対パスを入力してください。同梱のCLIを使用する場合は、unit-test-runnerまたは空欄にします。'"),
        ("'関数解析をキャンセルしました。'", "'関数名が入力されなかったため、解析を中止しました。'"),
        ("'unit-test-runnerがタイムアウトしました。'", "'UnitTestRunner CLIの処理がタイムアウトしました。'"),
        ("await showSuiteError(context, `unit-test-runnerを起動できませんでした。${message}`);", "await showSuiteError(context, `UnitTestRunner CLIを起動できませんでした。 ${message}`);"),
        ("`UnitTestRunner: スイート実行完了。GREEN ${summary.green} / Not GREEN ${summary.notGreen} / Total ${summary.total}`", "`UnitTestRunner: テストスイートの実行が完了しました。合計${summary.total}件のうち、${summary.green}件合格、${summary.notGreen}件不合格でした。`"),
        ("prompt: '出力workspaceのパスを入力してください。'", "prompt: '出力ワークスペースのフォルダーパスを入力してください。'"),
        ("'出力workspaceの指定が必要です。'", "'出力ワークスペースのフォルダーパスを入力してください。'"),
        ("'記録済みの出力workspaceがありません。'", "'記録された出力ワークスペースがありません。先に関数解析またはクイックチェックを実行してください。'"),
        ("`スイートmanifestがまだありません: ${suitePath}`", "`スイート定義ファイルが見つかりません。確認先: ${suitePath}`"),
        ("`スイート実行レポートがまだありません: ${reportPath}`", "`テストスイートの実行レポートが見つかりません。先にテストスイートを実行してください。確認先: ${reportPath}`"),
        ("'記録済みのUnitTestRunnerコマンドがありません。'", "'記録されたCLIコマンドがありません。先にいずれかの処理を実行してください。'"),
    ]
    # C identifier validation appears twice.
    for old, new in extension_replacements:
        expected = 2 if old == "'Cの関数識別子を入力してください。'" else 1
        if old == "'UnitTestRunnerを実行する前にCソースファイルを開いてください。'":
            expected = 3
        if old == "'unit-test-runnerがタイムアウトしました。'":
            expected = 3
        replace_exact("vscode/extension/src/extension.ts", old, new, expected)

    replace_exact(
        "vscode/extension/src/extension.ts",
        """  if (invocation.requiresConfirmation) {
    const selected = await vscode.window.showWarningMessage('このコマンドは生成されたツールまたはテストを実行する可能性があります。続行しますか？', { modal: true }, '続行');
    if (selected !== '続行') {
      throw new Error('UnitTestRunnerコマンドをキャンセルしました。');
    }
  }
""",
        """  if (invocation.requiresConfirmation) {
    const confirmation = executionConfirmation(invocation);
    const selected = await vscode.window.showWarningMessage(
      confirmation.message,
      { modal: true },
      confirmation.action,
    );
    if (selected !== confirmation.action) {
      throw new Error(`${confirmation.operation}を中止しました。`);
    }
  }
""",
    )
    replace_exact(
        "vscode/extension/src/extension.ts",
        """  if (invocation.requiresConfirmation) {
    const selected = await vscode.window.showWarningMessage('このコマンドは登録済みスイートのテストを実行する可能性があります。続行しますか？', { modal: true }, '続行');
    if (selected !== '続行') {
      return false;
    }
  }
""",
        """  if (invocation.requiresConfirmation) {
    const runAll = invocation.args.includes('--all');
    const action = runAll ? '全件テストを実行' : 'テストスイートを実行';
    const message = runAll
      ? '登録されているすべてのテストを実行し、合否を確認します。実行してもよろしいですか？'
      : '選択したテストスイートを実行します。実行してもよろしいですか？';
    const selected = await vscode.window.showWarningMessage(message, { modal: true }, action);
    if (selected !== action) {
      return false;
    }
  }
""",
    )
    replace_exact(
        "vscode/extension/src/extension.ts",
        """async function executeInvocation(context: vscode.ExtensionContext, output: vscode.OutputChannel, invocation: CliInvocation, outputWorkspace: string, workflowPanel: WorkflowPanelProvider): Promise<ReportPaths> {
""",
        """interface ExecutionConfirmation {
  operation: string;
  message: string;
  action: string;
}

function executionConfirmation(invocation: CliInvocation): ExecutionConfirmation {
  if (invocation.args.includes('build-probe')) {
    return {
      operation: 'ビルド',
      message: '生成したテストをビルドします。ビルドを実行してもよろしいですか？',
      action: 'ビルドを実行',
    };
  }
  if (invocation.args.includes('run-tests')) {
    return {
      operation: 'テスト実行',
      message: '生成したテストを実行します。テストを実行してもよろしいですか？',
      action: 'テストを実行',
    };
  }
  return {
    operation: '処理',
    message: '生成したツールまたはテストを実行します。実行してもよろしいですか？',
    action: '実行する',
  };
}

async function executeInvocation(context: vscode.ExtensionContext, output: vscode.OutputChannel, invocation: CliInvocation, outputWorkspace: string, workflowPanel: WorkflowPanelProvider): Promise<ReportPaths> {
""",
    )

    # CLI failure text that surfaces in error dialogs.
    replace_exact(
        "vscode/extension/src/cli/cliResultParser.ts",
        "const exitText = `unit-test-runnerが終了コード ${exitCode ?? 'unknown'} で終了しました。`;",
        "const exitText = `UnitTestRunner CLIが終了コード${exitCode ?? '不明'}で終了しました。`;",
    )
    replace_exact(
        "vscode/extension/src/cli/cliResultParser.ts",
        "const parts = [`全件GREENではありません。GREEN ${green} / Not GREEN ${notGreen} / Total ${total}`];",
        "const parts = [`全件の合格条件を満たしていません。合計${total}件 / 合格${green}件 / 不合格${notGreen}件`];",
    )
    replace_exact(
        "vscode/extension/src/cli/cliResultParser.ts",
        "const warnings = ['CLI output is not a JSON envelope; produced report paths are unavailable.'];",
        "const warnings = ['CLIの出力がJSON形式ではないため、生成されたレポートのパスを取得できませんでした。'];",
    )

    update_package_json()

    # Existing tests: update assertions to the new copy.
    workflow_test_replacements = [
        ("/<h3>1\\. Quick Check<\\/h3>/", "/<h3>1\\. クイックチェック<\\/h3>/"),
        ("/<h3>2\\. テストソース確認<\\/h3>/", "/<h3>2\\. テストソースを確認<\\/h3>/"),
        ("/<h3>4\\. テスト実行<\\/h3>/", "/<h3>4\\. テストを実行<\\/h3>/"),
        (">Quick Checkを再実行<\\/button>", ">クイックチェックを再実行<\\/button>"),
        ("(?:Quick Check|テストソース|ビルド|テスト実行)", "(?:クイックチェック|テストソース|ビルド|テスト)"),
        ("data-label=\"Quick Checkを再実行\"", "data-label=\"クイックチェックを再実行\""),
        (">Quick Checkを実行<\\/button>", ">クイックチェックを実行<\\/button>"),
        ("/現在関数の解析を再実行/", "/現在の関数を再解析/"),
        ("/data-label=\"現在関数の解析を再実行\"/", "/data-label=\"現在の関数を再解析\"/"),
        ("<h3>3\\. function_dossier\\.md 確認<\\/h3>", "<h3>3\\. 関数分析レポート（function_dossier\\.md）を確認<\\/h3>"),
    ]
    for old, new in workflow_test_replacements:
        replace_exact("vscode/extension/src/test/workflowPanel.test.ts", old, new)

    adapter_test_replacements = [
        ("message.includes('本番リポジトリへ生成物が混入')", "message.includes('生成物が本番ソースへ混在')"),
        ("/未設定の必須項目があります。/", "/必須項目に未設定があります。各項目を確認してください。/"),
        ("'UnitTestRunner: 現在関数を解析'", "'UnitTestRunner: 現在の関数を解析'"),
        ("'UnitTestRunner: 最後の関数dossierを開く'", "'UnitTestRunner: 最後の関数分析レポートを開く'"),
        ("'UnitTestRunner: スイートを開く'", "'UnitTestRunner: テストスイートを開く'"),
        ("'UnitTestRunner: スイートmanifestを開く'", "'UnitTestRunner: スイート定義ファイルを開く'"),
        ("'UnitTestRunner: スイート全件GREEN確認'", "'UnitTestRunner: 全件テストを実行して合否を確認'"),
        ("item.id === 'unitTestRunner.workflow' && item.name === 'ワークフロー'", "item.id === 'unitTestRunner.workflow' && item.name === '関数テスト'"),
        ("item.id === 'unitTestRunner.suite' && item.name === 'スイート'", "item.id === 'unitTestRunner.suite' && item.name === 'テストスイート'"),
        ("assert.match(harnessStep.purpose, /Build Probe/);", "assert.match(harnessStep.purpose, /ビルドの事前確認/);"),
        ("actions.get('CSVを開く')", "actions.get('テスト設計（CSV）を開く')"),
        ("actions.get('Markdownを開く')", "actions.get('レビュー用Markdownを開く')"),
        ("actions.get('JSONを開く')", "actions.get('生成用JSONを開く')"),
        ("assert.match(message, /全件GREENではありません/);", "assert.match(message, /全件の合格条件を満たしていません/);"),
        ("assert.match(message, /GREEN 1 \\/ Not GREEN 1 \\/ Total 2/);", "assert.match(message, /合計2件 \\/ 合格1件 \\/ 不合格1件/);"),
    ]
    for old, new in adapter_test_replacements:
        replace_exact("vscode/extension/src/test/adapter.test.ts", old, new)

    # The file name is intentionally preserved in the setting description.
    replace_exact(
        "vscode/extension/src/test/uiCopy.test.ts",
        "assert.doesNotMatch(properties['unitTestRunner.suiteManifestPath'].description, /manifest/);",
        "assert.doesNotMatch(properties['unitTestRunner.suiteManifestPath'].description, /スイートmanifest|manifestのパス/);",
    )


if __name__ == "__main__":
    main()
