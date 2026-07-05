import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_dsw"


def run_module(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class Vc6WorkspaceDiscoveryCliTests(unittest.TestCase):
    def test_discover_projects_workspace_file_writes_json_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "projects.json"

            completed = run_module(
                "--json",
                "discover-projects",
                "--workspace",
                str(FIXTURE_ROOT / "minimal" / "Product.dsw"),
                "--out",
                str(out),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("", completed.stderr)
            stdout_payload = json.loads(completed.stdout)
            file_payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(stdout_payload["data"], file_payload)
            self.assertEqual("ok", stdout_payload["status"])
            self.assertEqual("discover-projects", stdout_payload["command"])
            self.assertEqual(1, len(file_payload["workspaces"]))
            self.assertEqual("Control", file_payload["workspaces"][0]["projects"][0]["name"])

    def test_discover_projects_workspace_directory_single_dsw(self):
        completed = run_module("--json", "discover-projects", "--workspace", str(FIXTURE_ROOT / "minimal"))

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(1, len(payload["data"]["workspaces"]))

    def test_discover_projects_workspace_directory_multiple_dsw(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("A", "B"):
                project_dir = root / name
                (project_dir / "Control").mkdir(parents=True)
                (project_dir / "Control" / "Control.dsp").write_text("# dsp\n", encoding="utf-8")
                (project_dir / f"{name}.dsw").write_text(
                    'Microsoft Developer Studio Workspace File, Format Version 6.00\n'
                    'Project: "Control"=.\\Control\\Control.dsp - Package Owner=<4>\n',
                    encoding="utf-8",
                )

            completed = run_module("--json", "discover-projects", "--workspace", str(root))

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(2, len(payload["data"]["workspaces"]))

    def test_discover_projects_workspace_directory_without_dsw_exits_two(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = run_module("--json", "discover-projects", "--workspace", temp_dir)

        self.assertEqual(2, completed.returncode)
        self.assertEqual("", completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("error", payload["status"])
        self.assertIn(".dsw", payload["errors"][0])

    def test_discover_projects_out_markdown_writes_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "projects.md"

            completed = run_module(
                "discover-projects",
                "--workspace",
                str(FIXTURE_ROOT / "dependencies" / "Product.dsw"),
                "--out",
                str(out),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            markdown = out.read_text(encoding="utf-8")
            self.assertIn("# DSW Project Discovery Report", markdown)
            self.assertIn("| Control | Control/Control.dsp | yes |", markdown)
            self.assertIn("| Control | Common |", markdown)

    def test_discover_projects_human_mode_prints_short_summary(self):
        completed = run_module("discover-projects", "--workspace", str(FIXTURE_ROOT / "dependencies" / "Product.dsw"))

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("DSW parsed:", completed.stdout)
        self.assertIn("Projects: 2", completed.stdout)
        self.assertIn("Dependencies: 1", completed.stdout)
        self.assertIn("Warnings: 0", completed.stdout)
        self.assertNotIn('"workspaces"', completed.stdout)

    def test_map_source_without_workspace_keeps_candidate_projects_when_not_found(self):
        completed = run_module(
            "--json",
            "map-source",
            "--dsw",
            str(FIXTURE_ROOT / "dependencies" / "Product.dsw"),
            "--source",
            "src/control.c",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("not_found", payload["status"])
        self.assertEqual("src/control.c", payload["data"]["source"]["input"])
        self.assertEqual(["Control", "Common"], [item["name"] for item in payload["data"]["candidate_projects"]])

    def test_json_discover_projects_stdout_is_json_only(self):
        completed = run_module("--json", "discover-projects", "--workspace", str(FIXTURE_ROOT / "minimal"))

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        self.assertTrue(completed.stdout.lstrip().startswith("{"))
        self.assertTrue(completed.stdout.rstrip().endswith("}"))
        json.loads(completed.stdout)


if __name__ == "__main__":
    unittest.main()
