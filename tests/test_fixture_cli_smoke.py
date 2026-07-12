import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


def run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", "--json", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class FixtureCliSmokeTests(unittest.TestCase):
    def test_discover_map_and_design_phase_emit_valid_envelopes(self):
        discover = run_cli("discover-projects", "--workspace", str(FIXTURE_ROOT))
        self.assertEqual(0, discover.returncode, discover.stderr)
        discover_payload = json.loads(discover.stdout)
        self.assertEqual("cli_result", discover_payload["artifact_kind"])
        self.assertEqual("passed", discover_payload["data"]["outcome"])
        self.assertTrue(discover_payload["data"]["details"]["workspaces"])

        mapped = run_cli(
            "map-source",
            "--workspace",
            str(FIXTURE_ROOT),
            "--dsw",
            str(FIXTURE_ROOT / "Product.dsw"),
            "--source",
            "src/control.c",
        )
        self.assertEqual(0, mapped.returncode, mapped.stderr)
        mapped_payload = json.loads(mapped.stdout)
        self.assertEqual("passed", mapped_payload["data"]["outcome"])
        self.assertTrue(mapped_payload["data"]["details"]["matches"])

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "design-smoke"
            analyzed = run_cli(
                "analyze-function",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--phase",
                "design",
                "--out",
                str(output),
            )
            self.assertEqual(0, analyzed.returncode, analyzed.stderr)
            analyzed_payload = json.loads(analyzed.stdout)
            self.assertEqual("passed", analyzed_payload["data"]["outcome"])
            self.assertEqual("design", analyzed_payload["data"]["details"]["phase"])
            self.assertTrue((output / "reports" / "function_signature.json").is_file())
            self.assertTrue((output / "reports" / "test_spec.json").is_file())


if __name__ == "__main__":
    unittest.main()
