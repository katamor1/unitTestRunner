from pathlib import Path
import re
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class CiContractTests(unittest.TestCase):
    def test_python_build_package_sources_are_not_ignored(self):
        completed = subprocess.run(
            [
                "git",
                "check-ignore",
                "--no-index",
                "-q",
                "src/unit_test_runner/build/dependency_rewriter.py",
            ],
            cwd=REPO_ROOT,
            check=False,
        )

        self.assertNotEqual(0, completed.returncode)

    def test_github_actions_runs_python_and_vscode_extension_gates(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        self.assertTrue(workflow.exists())
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("py -m unittest discover -s tests -p \"test_*.py\"", text)
        self.assertIn("npm.cmd test", text)
        self.assertIn("vscode/extension", text)

    def test_github_actions_uses_five_independent_required_jobs(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        text = workflow.read_text(encoding="utf-8")
        jobs_text = text.split("\njobs:\n", maxsplit=1)[1]
        job_ids = set(re.findall(r"^  ([a-z][a-z0-9-]+):\s*$", jobs_text, re.MULTILINE))
        self.assertEqual(
            {
                "source-integrity",
                "python-tests",
                "vscode-tests",
                "vscode-activation",
                "fixture-smoke",
            },
            job_ids,
        )
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("needs:", text)
        self.assertNotIn("continue-on-error", text)

    def test_github_actions_runs_activation_fixture_and_failure_log_contracts(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        text = workflow.read_text(encoding="utf-8")
        self.assertIn("npm.cmd run test:extension-host", text)
        self.assertIn(
            "py -m unittest tests.test_fixture_cli_smoke tests.test_vc6_fixture_build_e2e -v",
            text,
        )
        self.assertIn("uses: actions/upload-artifact@v4", text)
        self.assertIn("if: failure()", text)

    def test_github_actions_checks_rewriter_tracking_and_python_compilation(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        text = workflow.read_text(encoding="utf-8")
        tracking = (
            "git ls-files --error-unmatch "
            "src/unit_test_runner/build/dependency_rewriter.py"
        )
        self.assertIn(tracking, text)
        self.assertIn("py -m compileall -q src", text)
        self.assertLess(text.index(tracking), text.index("Run Python tests"))
        self.assertLess(text.index("py -m compileall -q src"), text.index("Run Python tests"))


if __name__ == "__main__":
    unittest.main()
