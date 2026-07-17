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

    def test_script_rejects_non_windows_hosts_and_stops_on_native_failures(self):
        self.assertIn('$env:OS -ne "Windows_NT"', self.text)
        self.assertIn('$ErrorActionPreference = "Stop"', self.text)
        self.assertRegex(self.text, r'if \(\$LASTEXITCODE -ne 0\)')

    def test_powershell_parser_accepts_script_when_available(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell is None:
            self.skipTest("PowerShell is not available")
        escaped = str(SCRIPT).replace("'", "''")
        command = (
            f"$text = Get-Content -LiteralPath '{escaped}' -Raw; "
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
