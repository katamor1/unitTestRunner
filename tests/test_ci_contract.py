from pathlib import Path
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
