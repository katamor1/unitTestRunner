import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_workspace_generator import generate_build_workspace
from unit_test_runner.build.log_parser import parse_build_log
from unit_test_runner.c_analyzer.source_digest import build_source_digest
from unit_test_runner.dossier import analyze_function_workflow
from unit_test_runner.process_control import ProcessTreeRunResult


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


class BuildWorkspaceGenerationTests(unittest.TestCase):
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
            makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")
            self.assertIn('/I"..\\generated\\include"', makefile)
            self.assertNotIn('/I"generated/include"', makefile)
            self.assertIn("/Gy", payload["compiler_options"])
            self.assertIn("/OPT:REF", makefile)

            self.assertEqual("not_run", probe_payload["function"]["status"])
            self.assertFalse(probe_payload["executed"])
            self.assertTrue((out_dir / "reports" / "build_workspace_report.json").exists())
            self.assertTrue((out_dir / "reports" / "build_probe_report.json").exists())

    def test_generator_references_declared_include_dirs_without_copying_headers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            source = project / "src" / "control.c"
            header = project / "common" / "include" / "common.h"
            source.parent.mkdir(parents=True)
            header.parent.mkdir(parents=True)
            source.write_text('#include "common.h"\nint Target(void) { return COMMON_VALUE; }\n', encoding="ascii")
            header.write_text("#define COMMON_VALUE 1\n", encoding="ascii")
            out_dir = Path(temp_dir) / "out"
            build_context = {
                "workspace_root": str(project),
                "include_dirs": ["common/include"],
                "defines": [],
                "compiler_options": [],
            }
            source_digest = {
                "source": {"path": str(source)},
                "preprocessor": {
                    "includes": [
                        {
                            "name": "common.h",
                            "resolved_candidates": [str(header)],
                        }
                    ]
                },
            }
            harness_report = {
                "function": {"name": "Target"},
                "source": {"path": str(source)},
                "output_root": str(out_dir),
                "generated_files": [],
            }

            report, _probe = generate_build_workspace(
                build_context,
                source_digest,
                harness_report,
                out_dir,
                run_probe=False,
                dry_run=True,
            )

            self.assertFalse((out_dir / "extracted" / "common" / "include" / "common.h").exists())
            self.assertFalse((out_dir / "extracted" / "include" / "common.h").exists())
            header_refs = [item for item in report.copied_files if item.file_kind == "target_header"]
            self.assertEqual([header.resolve()], [item.source_path for item in header_refs])
            self.assertFalse(header_refs[0].copied)
            include_dirs = {Path(item.raw) for item in report.include_dirs if item.source in {"referenced_header_dir", "dsp_include"}}
            self.assertIn(header.parent.resolve(), include_dirs)
            makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")
            self.assertIn(str(header.parent.resolve()).replace("/", "\\"), makefile)

    def test_generator_enables_function_level_linking_for_unused_peer_functions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            source = project / "shared" / "shared.c"
            header = project / "shared" / "shared2.h"
            source.parent.mkdir(parents=True)
            source.write_text(
                '#include "shared2.h"\n\n'
                "int g_count = 0;\n\n"
                "int Shared(void)\n"
                "{\n"
                "    g_count++;\n"
                "    return g_count;\n"
                "}\n\n"
                "int Shared2(void)\n"
                "{\n"
                "    g_com->ptr->test = g_count;\n"
                "    return g_count;\n"
                "}\n",
                encoding="ascii",
            )
            header.write_text(
                "typedef struct _gbl1 { int test; } gbl1;\n"
                "typedef struct _gbl_com { gbl1* ptr; } gbl_com;\n"
                "extern gbl_com *g_com;\n",
                encoding="ascii",
            )
            out_dir = Path(temp_dir) / "out"
            build_context = {
                "workspace_root": str(project),
                "include_dirs": ["shared"],
                "defines": ["WIN32", "_DEBUG"],
                "compiler_options": ["/nologo", "/W3", "/MDd", "/Od", "/ZI"],
            }
            source_digest = build_source_digest(source, build_context).to_dict()
            harness_report = {
                "function": {"name": "Shared"},
                "source": {"path": str(source)},
                "output_root": str(out_dir),
                "generated_files": [],
            }

            report, _probe = generate_build_workspace(
                build_context,
                source_digest,
                harness_report,
                out_dir,
                run_probe=False,
                dry_run=True,
            )

            payload = report.to_dict()
            makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")
            compile_commands = (out_dir / "build" / "compile_commands.txt").read_text(encoding="cp932")
            isolated_source = (out_dir / "extracted" / "shared" / "shared.c").read_text(encoding="cp932")
            self.assertIn("/Gy", payload["compiler_options"])
            self.assertIn("/Gy", compile_commands)
            self.assertIn("/OPT:REF", makefile)
            self.assertIn("..\\extracted\\shared\\shared.c", makefile)
            self.assertIn("..\\obj\\shared.obj", makefile)
            self.assertIn('/Fo"..\\obj\\shared.obj"', makefile)
            self.assertNotIn('/Fo"obj\\shared.obj"', makefile)
            self.assertIn("int Shared(void)", isolated_source)
            self.assertNotIn("int Shared2(void)", isolated_source)
            self.assertNotIn("g_com->ptr->test", isolated_source)

    def test_run_probe_preserves_redirected_build_log_for_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir, reports = self.prepare_analysis(temp_dir)
            diagnostic_log = "control.c(4) : fatal error C1083: Cannot open include file: 'missing.h': No such file or directory\n"

            def fake_run(*args, **kwargs):
                build_dir = Path(kwargs["cwd"])
                (build_dir.parent / "logs" / "build.log").write_text(diagnostic_log, encoding="utf-8")
                return ProcessTreeRunResult(2, "", None, False)

            with mock.patch("unit_test_runner.build.build_workspace_generator.shutil.which", return_value="tool.exe"):
                with mock.patch("unit_test_runner.build.build_workspace_generator.run_process_tree", side_effect=fake_run):
                    _report, probe = generate_build_workspace(
                        reports["build_context"],
                        reports["source_digest"],
                        reports["harness_report"],
                        out_dir,
                        run_probe=True,
                        dry_run=False,
                    )

            self.assertEqual("failed", probe.status)
            self.assertEqual(["missing.h"], [item.include_name for item in probe.missing_includes])
            self.assertIn("missing.h", (out_dir / "logs" / "build.log").read_text(encoding="utf-8"))

    def test_run_probe_with_vcvars_runs_build_script_even_when_tools_are_not_on_initial_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir, reports = self.prepare_analysis(temp_dir)
            vcvars = Path(temp_dir) / "vcvars32.bat"
            vcvars.write_text("@echo off\n", encoding="utf-8")

            def fake_run(*args, **kwargs):
                build_dir = Path(kwargs["cwd"])
                (build_dir.parent / "logs" / "build.log").write_text("Build succeeded\n", encoding="utf-8")
                return ProcessTreeRunResult(0, "", None, False)

            with mock.patch("unit_test_runner.build.build_workspace_generator.shutil.which", return_value=None):
                with mock.patch("unit_test_runner.build.build_workspace_generator.run_process_tree", side_effect=fake_run) as run:
                    _report, probe = generate_build_workspace(
                        reports["build_context"],
                        reports["source_digest"],
                        reports["harness_report"],
                        out_dir,
                        run_probe=True,
                        dry_run=False,
                        vcvars=vcvars,
                    )

            self.assertEqual("succeeded", probe.status)
            self.assertTrue(probe.executed)
            self.assertEqual(0, probe.exit_code)
            self.assertEqual(1, run.call_count)
            self.assertIn(str(vcvars), (out_dir / "build" / "build.bat").read_text(encoding="cp932"))

    def test_log_parser_extracts_include_unresolved_pch_and_vc6_compatibility(self):
        parsed = parse_build_log(
            """
control.c(4) : fatal error C1083: Cannot open include file: 'missing.h': No such file or directory
LINK : fatal error LNK2001: unresolved external symbol _ReadSensor
error LNK2019: unresolved external symbol _WriteOutput referenced in function _Control_Update
fatal error C1010: unexpected end of file while looking for precompiled header directive
generated\tests\test.c(7) : fatal error C1083: Cannot open include file: 'stdint.h': No such file or directory
"""
        )

        self.assertEqual(["missing.h", "stdint.h"], [item.include_name for item in parsed.missing_includes])
        self.assertEqual(["ReadSensor", "WriteOutput"], [item.symbol_name for item in parsed.unresolved_symbols])
        self.assertTrue(parsed.pch_issues)
        self.assertTrue(parsed.vc6_compatibility_issues)

    def test_build_probe_cli_and_analyze_function_connect_build_workspace(self):
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
                "--phase",
                "execution",
                "--out",
                str(out_dir),
            )
            self.assertEqual(0, analyze.returncode, analyze.stderr)
            payload = json.loads(analyze.stdout)
            self.assertEqual("evidence_prepared", payload["status"])
            self.assertIn("dossier review", payload["message"])
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
            self.assertEqual("build_workspace_generated", json.loads(explicit.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
