import hashlib
import json
import os
import shutil
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


def fixture_hashes():
    return {
        path.relative_to(FIXTURE_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file()
    }


@unittest.skipUnless(
    any(shutil.which(name) for name in ("gcc", "clang", "cc")),
    "host C compiler is required",
)
class Vc6FixtureBuildEndToEndTests(unittest.TestCase):
    def test_default_fixture_analysis_compiles_and_links_without_mutating_product_tree(self):
        before = fixture_hashes()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "Control_Update"
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
                "build",
                "--out",
                str(output),
            )
            self.assertEqual(0, analyzed.returncode, analyzed.stderr or analyzed.stdout)
            json.loads(analyzed.stdout)

            probe = run_cli(
                "build-probe",
                "--workspace",
                str(output),
                "--toolchain",
                "verification",
                "--run",
            )
            self.assertEqual(0, probe.returncode, probe.stderr or probe.stdout)
            probe_payload = json.loads(probe.stdout)
            self.assertEqual("passed", probe_payload["data"]["outcome"])
            self.assertEqual(0, probe_payload["data"]["exit_code"])
            self.assertEqual(
                "succeeded",
                probe_payload["data"]["details"]["build_probe"]["status"],
            )

            report = json.loads(
                (output / "reports" / "build_workspace_report.json").read_text(encoding="utf-8")
            )
            probe_report = json.loads(
                (output / "reports" / "build_probe_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual("succeeded", probe_report["function"]["status"])
            self.assertTrue(probe_report["executed"])
            self.assertEqual(0, probe_report["exit_code"])
            fixture = output / "generated" / "stubs" / "utr_extern_globals.c"
            self.assertTrue(fixture.is_file())
            self.assertEqual(
                1,
                fixture.read_text(encoding="cp932").count("int g_error_code = {0};"),
            )
            self.assertIn(
                "generated/stubs/utr_extern_globals.c",
                {item["source_file"] for item in report["compile_units"]},
            )
            self.assertTrue((output / "bin" / "utr_probe.exe").is_file())
            build_log = (output / "logs" / "build.log").read_text(encoding="utf-8")
            self.assertNotIn("undefined reference", build_log.lower())

        self.assertEqual(before, fixture_hashes())


if __name__ == "__main__":
    unittest.main()
