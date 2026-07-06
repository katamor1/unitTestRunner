import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ROOT = REPO_ROOT / "vscode" / "extension"


class VscodeAdapterTests(unittest.TestCase):
    def test_extension_manifest_declares_thin_cli_adapter_commands_and_settings(self):
        package_json = EXTENSION_ROOT / "package.json"
        manifest = json.loads(package_json.read_text(encoding="utf-8"))

        self.assertEqual("unit-test-runner-vscode", manifest["name"])
        self.assertEqual("./dist/extension.js", manifest["main"])
        self.assertIn("onCommand:unitTestRunner.analyzeSelectedFunction", manifest["activationEvents"])
        self.assertIn("onCommand:unitTestRunner.openLastFunctionDossier", manifest["activationEvents"])

        commands = {
            command["command"]: command["title"]
            for command in manifest["contributes"]["commands"]
        }
        self.assertEqual(
            "UnitTestRunner: 選択関数を解析",
            commands["unitTestRunner.analyzeSelectedFunction"],
        )
        self.assertEqual(
            "UnitTestRunner: 最後の関数dossierを開く",
            commands["unitTestRunner.openLastFunctionDossier"],
        )
        self.assertFalse(any("Analyze Current Function" in title for title in commands.values()))
        self.assertFalse(any("Open Last Function Dossier" in title for title in commands.values()))

        properties = manifest["contributes"]["configuration"]["properties"]
        for key in (
            "unitTestRunner.cliPath",
            "unitTestRunner.dswPath",
            "unitTestRunner.outputRoot",
            "unitTestRunner.defaultConfiguration",
            "unitTestRunner.sourceRoot",
            "unitTestRunner.workspaceRoot",
            "unitTestRunner.finalizeDossierAfterAnalyze",
        ):
            self.assertIn(key, properties)

    def test_extension_source_invokes_cli_and_opens_generated_markdown(self):
        extension = (EXTENSION_ROOT / "src" / "extension.ts").read_text(encoding="utf-8")
        runner = (EXTENSION_ROOT / "src" / "cli" / "cliRunner.ts").read_text(encoding="utf-8")
        builder = (EXTENSION_ROOT / "src" / "cli" / "commandBuilder.ts").read_text(encoding="utf-8")
        opener = (EXTENSION_ROOT / "src" / "reports" / "reportOpener.ts").read_text(encoding="utf-8")

        self.assertIn("childProcess.spawn", runner)
        self.assertIn("shell: false", runner)
        self.assertIn("analyze-function", builder)
        self.assertIn("--finalize-dossier", builder)
        self.assertIn("unitTestRunner.analyzeSelectedFunction", extension)
        self.assertIn("unitTestRunner.openLastFunctionDossier", extension)
        self.assertIn("openMarkdown", extension)
        self.assertIn("markdown.showPreview", opener)

    def test_vscode_task_template_uses_json_and_finalized_review_flow(self):
        template = json.loads((REPO_ROOT / "templates" / "vscode" / "tasks.json").read_text(encoding="utf-8"))
        analyze_args = template["tasks"][0]["args"]

        self.assertIn("--json", analyze_args)
        self.assertIn("analyze-function", analyze_args)
        self.assertIn("--finalize-dossier", analyze_args)

    def test_vscode_plan_uses_current_test_case_design_names(self):
        plan = (REPO_ROOT / "docs" / "implementation" / "step18_vscode_thin_adapter_plan.md").read_text(encoding="utf-8")

        self.assertIn("generate-test-design", plan)
        self.assertIn("test_case_design.csv", plan)
        self.assertIn("unitTestRunner.generateTestDesign", plan)
        self.assertNotIn("generate-test-draft", plan)
        self.assertNotIn("test_case_draft", plan)
        self.assertNotIn("unitTestRunner.generateTestDraft", plan)


if __name__ == "__main__":
    unittest.main()
