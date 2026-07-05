from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class CiContractTests(unittest.TestCase):
    def test_github_actions_runs_python_and_vscode_extension_gates(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        self.assertTrue(workflow.exists())
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("py -m unittest discover -s tests -p \"test_*.py\"", text)
        self.assertIn("npm.cmd test", text)
        self.assertIn("vscode/extension", text)


if __name__ == "__main__":
    unittest.main()
