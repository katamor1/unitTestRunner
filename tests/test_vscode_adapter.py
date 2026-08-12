import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ROOT = REPO_ROOT / "vscode" / "extension"


class VscodeAdapterTests(unittest.TestCase):
    def test_manifest_exposes_only_the_thin_v01_surface(self):
        manifest = json.loads(
            (EXTENSION_ROOT / "package.json").read_text(encoding="utf-8")
        )
        command_ids = {
            item["command"] for item in manifest["contributes"]["commands"]
        }
        self.assertEqual(16, len(command_ids))
        self.assertIn("unitTestRunner.analyzeCurrentFunction", command_ids)
        self.assertIn("unitTestRunner.openTestInputEditor", command_ids)
        self.assertIn("unitTestRunner.runSelectedSuiteTests", command_ids)
        self.assertFalse(
            any(
                token in command_id
                for command_id in command_ids
                for token in (
                    "quick",
                    "Evidence",
                    "generateTestDesign",
                    "generateHarnessSkeleton",
                    "Dashboard",
                )
            )
        )

        properties = manifest["contributes"]["configuration"]["properties"]
        self.assertEqual(12, len(properties))
        self.assertTrue(
            all(value.get("scope") == "resource" for value in properties.values())
        )
        self.assertNotIn("unitTestRunner.workspaceRoot", properties)
        self.assertNotIn("unitTestRunner.projectName", properties)

    def test_adapter_uses_active_resource_scope_and_shared_process_gate(self):
        extension = (EXTENSION_ROOT / "src" / "extension.ts").read_text(
            encoding="utf-8"
        )
        runner = (EXTENSION_ROOT / "src" / "cli" / "cliRunner.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn("getWorkspaceFolder", extension)
        self.assertIn("getConfiguration('unitTestRunner', resource)", extension)
        self.assertIn("let invocationActive = false", runner)
        self.assertIn("CliInvocationBusyError", runner)
        self.assertIn("childProcess.spawn", runner)
        self.assertIn("shell: false", runner)
        self.assertIn("terminateProcessTree", runner)

    def test_command_builder_uses_only_formal_cli_commands(self):
        builder = (EXTENSION_ROOT / "src" / "cli" / "commandBuilder.ts").read_text(
            encoding="utf-8"
        )
        for command in (
            "analyze-function",
            "finalize-dossier",
            "review-set",
            "build-probe",
            "run-tests",
            "reanalyze-function",
            "suite-register",
            "suite-update",
            "suite-run",
        ):
            self.assertIn(command, builder)
        for removed in (
            "generate-test-design",
            "generate-harness-skeleton",
            "prepare-evidence",
            "quick-check",
            "full-gate",
        ):
            self.assertNotIn(removed, builder)

    def test_vscode_task_template_stops_at_design_phase(self):
        template = json.loads(
            (REPO_ROOT / "templates" / "vscode" / "tasks.json").read_text(
                encoding="utf-8"
            )
        )
        analyze_args = template["tasks"][0]["args"]
        self.assertIn("--json", analyze_args)
        self.assertIn("analyze-function", analyze_args)
        self.assertIn("--phase", analyze_args)
        self.assertIn("design", analyze_args)
        self.assertNotIn("--finalize-dossier", analyze_args)


if __name__ == "__main__":
    unittest.main()
