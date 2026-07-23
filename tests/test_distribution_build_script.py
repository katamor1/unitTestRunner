import re
import shutil
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_distribution.ps1"


class DistributionBuildScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_pyinstaller_collects_schema_package_and_data(self):
        self.assertRegex(
            self.text,
            r'"--hidden-import"\s*,\s*"unit_test_runner\.schemas"',
        )
        self.assertRegex(
            self.text,
            r'"--collect-data"\s*,\s*"unit_test_runner\.schemas"',
        )

    def test_exe_smoke_finalizes_dossier_before_vsix_packaging(self):
        build_index = self.text.index('"-m", "PyInstaller"')
        finalize_index = self.text.index('"--finalize-dossier"')
        copy_index = self.text.index('Copy-Item -LiteralPath $exePath')
        package_index = self.text.index('"vsce", "package"')

        self.assertLess(build_index, finalize_index)
        self.assertLess(finalize_index, copy_index)
        self.assertLess(copy_index, package_index)
        self.assertIn('reports\\function_dossier.json', self.text)
        self.assertIn('"prepare-review"', self.text)

    def test_script_builds_and_verifies_bundled_vsix(self):
        required_fragments = (
            'npm.cmd',
            '"ci"',
            '"test"',
            'extension/bin/win32-x64/unit-test-runner.exe',
            '[System.IO.Compression.ZipFile]::OpenRead',
            'ConvertTo-Json',
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.text)

    def test_packaged_vsix_keeps_bundled_cli_as_the_default_runtime(self):
        for fragment in (
            "$cliPathDefault = $manifest.contributes.configuration.properties.'unitTestRunner.cliPath'.default",
            '$cliPathDefault -ne "unit-test-runner"',
            'VSIX package.json no longer selects the bundled CLI by default',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.text)

    def test_vsix_verification_requires_the_exact_cli_built_in_dist(self):
        for fragment in (
            '[string]$ExpectedCliPath',
            'Get-FileHash -LiteralPath $ExpectedCliPath -Algorithm SHA256',
            '[System.Security.Cryptography.SHA256]::Create()',
            'Bundled CLI hash does not match the freshly built distribution CLI',
            'Test-VsixContainsBundledCli -VsixPath $vsixPath -ExpectedCliPath $exePath',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.text)

    def test_packaged_smoke_verifies_blocked_exit_and_reports(self):
        for fragment in (
            '"--phase", "execution"',
            '"run-tests"',
            '-ExpectedExitCode 35',
            'reports\\test_execution_blockers.json',
            'reports\\test_execution_blockers.md',
            'extension/dist/testExecutionBlockers/contracts.js',
            'extension/dist/testExecutionBlockers/verification.js',
            'extension/dist/testExecutionBlockers/workflowIntegration.js',
            'unitTestRunner.resolveExecutionBlocker',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.text)

    def test_blocked_smoke_uses_workspace_relative_default_executable(self):
        smoke_start = self.text.index('Invoke-NativeExpectedExit -FilePath $exePath -ExpectedExitCode 35')
        smoke_end = self.text.index('$blockerJson =', smoke_start)
        blocked_smoke = self.text[smoke_start:smoke_end]

        self.assertNotIn('"--executable"', blocked_smoke)
        self.assertIn('"--run-id", "release-blocked-smoke"', blocked_smoke)

    def test_script_rejects_non_windows_hosts_and_stops_on_native_failures(self):
        self.assertIn('$env:OS -ne "Windows_NT"', self.text)
        self.assertIn('$ErrorActionPreference = "Stop"', self.text)
        self.assertRegex(self.text, r'if \(\$LASTEXITCODE -ne 0\)')

    def test_native_failure_message_delimits_last_exit_code_before_colon(self):
        self.assertNotIn("$LASTEXITCODE:", self.text)
        self.assertIn("${LASTEXITCODE}:", self.text)

    def test_extension_manifest_is_read_as_utf8_before_json_parsing(self):
        self.assertRegex(
            self.text,
            re.compile(
                r'Get-Content\s+-LiteralPath\s+'
                r'\(Join-Path \$extensionRoot "package\.json"\)\s+'
                r'-Raw\s+-Encoding\s+UTF8\s+\|\s+ConvertFrom-Json'
            ),
        )

    def test_powershell_parser_accepts_script_when_available(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell is None:
            self.skipTest("PowerShell is not available")
        escaped = str(SCRIPT).replace("'", "''")
        command = (
            f"$text = Get-Content -LiteralPath '{escaped}' -Raw -Encoding UTF8; "
            "[void][scriptblock]::Create($text)"
        )
        completed = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command", command],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)


if __name__ == "__main__":
    unittest.main()
