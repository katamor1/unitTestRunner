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
            "UnitTestRunner: Analyze Selected Function",
            commands["unitTestRunner.analyzeSelectedFunction"],
        )
        self.assertEqual(
            "UnitTestRunner: Open Last Function Dossier",
            commands["unitTestRunner.openLastFunctionDossier"],
        )

        properties = manifest["contributes"]["configuration"]["properties"]
        for key in (
            "unitTestRunner.cliPath",
            "unitTestRunner.dswPath",
            "unitTestRunner.outputRoot",
            "unitTestRunner.defaultConfiguration",
            "unitTestRunner.workspaceRoot",
        ):
            self.assertIn(key, properties)

    def test_extension_source_invokes_cli_and_opens_generated_markdown(self):
        source = (EXTENSION_ROOT / "src" / "extension.ts").read_text(encoding="utf-8")

        self.assertIn("child_process", source)
        self.assertIn("analyze-function", source)
        self.assertIn("unitTestRunner.analyzeSelectedFunction", source)
        self.assertIn("unitTestRunner.openLastFunctionDossier", source)
        self.assertIn("function_dossier.md", source)
        self.assertIn("vscode.commands.executeCommand('markdown.showPreview'", source)


if __name__ == "__main__":
    unittest.main()
