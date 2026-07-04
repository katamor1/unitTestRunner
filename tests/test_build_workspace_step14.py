import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_workspace_generator import generate_build_workspace
from unit_test_runner.build.log_parser import parse_build_log
from unit_test_runner.dossier import analyze_function_workflow


def run_module(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class BuildWorkspaceStep14Tests(unittest.TestCase):
    def prepare_analysis(self, temp_dir):
        out_dir = Path(temp_dir) / "Control_Update"
        analyze_function_workflow(
            VC6_FIXTURE_ROOT,
            VC6_FIXTURE_ROOT / "Product.dsw",
            "src/control.c",
            "Control_Update",
            "Win32 Debug",
            out_dir,
            "Control",
        )
        reports = out_dir / "reports"
        return out_dir, {
            "build_context": json.loads((reports / "build_context.json").read_text(encoding="utf-8")),
            "source_digest": json.loads((reports / "source_digest.json").read_text(encoding="utf-8")),
            "harness_report": json.loads((reports / "harness_skeleton_report.json").read_text(encoding="utf-8")),
        }

    def test_generator_creates_build_workspace_makefile_and_not_run_probe_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir, reports = self.prepare_analysis(temp_dir)
            report, probe = generate_build_workspace(
                reports["build_context"],
                reports["source_digest"],
                reports["harness_report"],
                out_dir,
                run_probe=False,
                dry_run=True,
            )
            payload = report.to_dict()
            probe_payload = probe.to_dict()

            for dirname in ["build", "obj", "bin", "logs", "extracted", "generated", "reports"]:
                self.assertTrue((out_dir / dirname).exists(), dirname)
            self.assertTrue((out_dir / "extracted" / "src" / "control.c").exists())
            self.assertTrue((out_dir / "build" / "Makefile").exists())
            self.assertTrue((out_dir / "build" / "build.bat").exists())
            self.assertTrue((out_dir / "build" / "clean.bat").exists())
            self.assertTrue((out_dir / "build" / "compile_commands.txt").exists())

            compile_sources = {Path(unit["source_file"]).as_posix() for unit in payload["compile_units"]}
            self.assertIn("extracted/src/control.c", compile_sources)
            self.assertIn("generated/tests/test_Control_Update.c", compile_sources)
            self.assertTrue(any(source.startswith("generated/stubs/") for source in compile_sources))
            self.assertTrue(any(item["raw"] == "generated/include" for item in payload["include_dirs"]))
            self.assertIn("build_workspace_report.json", [Path(item["workspace_path"]).name for item in payload["generated_build_files"]])

            self.assertEqual("not_run", probe_payload["function"]["status"])
            self.assertFalse(probe_payload["executed"])
            self.assertTrue((out_dir / "reports" / "build_workspace_report.json").exists())
            self.assertTrue((out_dir / "reports" / "build_probe_report.json").exists())

    def test_log_parser_extracts_include_unresolved_pch_and_vc6_compatibility(self):
        parsed = parse_build_log(
            """
control.c(4) : fatal error C1083: Cannot open include file: 'missing.h': No such file or directory
LINK : fatal error LNK2001: unresolved external symbol _ReadSensor
error LNK2019: unresolved external symbol _WriteOutput referenced in function _Control_Update
fatal error C1010: unexpected end of file while looking for precompiled header directive
generated\\tests\\test.c(7) : fatal error C1083: Cannot open include file: 'stdint.h': No such file or directory
"""
        )

        self.assertEqual(["missing.h", "stdint.h"], [item.include_name for item in parsed.missing_includes])
        self.assertEqual(["ReadSensor", "WriteOutput"], [item.symbol_name for item in parsed.unresolved_symbols])
        self.assertTrue(parsed.pch_issues)
        self.assertTrue(parsed.vc6_compatibility_issues)

    def test_build_probe_cli_and_analyze_function_connect_step14(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "Control_Update"
            analyze = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(VC6_FIXTURE_ROOT),
                "--dsw",
                str(VC6_FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(out_dir),
            )
            self.assertEqual(0, analyze.returncode, analyze.stderr)
            payload = json.loads(analyze.stdout)
            self.assertEqual("evidence_prepared", payload["status"])
            self.assertIn("Step 17", payload["message"])
            self.assertIn("build_workspace", payload["data"])
            self.assertIn("build_probe", payload["data"])

            probe = run_module("--json", "build-probe", "--workspace", str(out_dir), "--dry-run")
            self.assertEqual(0, probe.returncode, probe.stderr)
            probe_payload = json.loads(probe.stdout)
            self.assertEqual("build_workspace_generated", probe_payload["status"])
            self.assertTrue((out_dir / "build" / "Makefile").exists())

            explicit = run_module(
                "--json",
                "build-probe",
                "--build-context",
                str(out_dir / "reports" / "build_context.json"),
                "--source-digest",
                str(out_dir / "reports" / "source_digest.json"),
                "--harness-report",
                str(out_dir / "reports" / "harness_skeleton_report.json"),
                "--out",
                str(Path(temp_dir) / "explicit_build"),
                "--dry-run",
            )
            self.assertEqual(0, explicit.returncode, explicit.stderr)
            explicit_payload = json.loads(explicit.stdout)
            self.assertEqual("build_workspace_generated", explicit_payload["status"])
            self.assertTrue(Path(explicit_payload["data"]["build_workspace"]["json"]).exists())


if __name__ == "__main__":
    unittest.main()
