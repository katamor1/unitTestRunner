import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.vc6.dsp_options import parse_build_settings, tokenize_compiler_options
from unit_test_runner.vc6.dsp_parser import parse_dsp
from unit_test_runner.vc6.source_membership import map_source_membership


REPO_ROOT = Path(__file__).resolve().parents[1]
DSP_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "vc6_dsp" / "comprehensive"
WORKSPACE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "vc6_workspace" / "multiple_membership"


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


class DspParserStep04Tests(unittest.TestCase):
    def test_parse_dsp_extracts_metadata_configurations_files_and_warnings(self):
        project = parse_dsp(DSP_FIXTURE / "Control.dsp")

        self.assertEqual("Control", project.name)
        self.assertEqual("6.00", project.format_version)
        self.assertEqual("Win32 (x86) Console Application", project.target_type)
        self.assertEqual(["Control - Win32 Release", "Control - Win32 Debug"], [cfg.full_name for cfg in project.configurations])
        self.assertEqual(["source", "source", "header", "resource", "source"], [entry.file_kind for entry in project.files])
        self.assertEqual("Source Files", project.files[0].group)
        self.assertEqual("src/control.c", project.files[0].source_path.as_posix())
        self.assertTrue(project.files[0].exists)
        self.assertIn("missing_source_file", [warning.code for warning in project.warnings])

    def test_compiler_options_handle_quoted_and_attached_values(self):
        tokens = tokenize_compiler_options(
            '/D "WIN32" /DDEBUG_FLAG /D "SIZE=10" /I ".\\include" /I"..\\shared include" '
            '/FI"config.h" /Yu"stdafx.h" /MDd /W3 /Od /ZI'
        )
        settings = parse_build_settings(tokens, DSP_FIXTURE, DSP_FIXTURE)

        self.assertIn("WIN32", settings.defines)
        self.assertIn("DEBUG_FLAG", settings.defines)
        self.assertIn("SIZE=10", settings.defines)
        self.assertEqual(["config.h"], settings.forced_includes)
        self.assertEqual("use", settings.pch_mode)
        self.assertEqual("stdafx.h", settings.pch_header)
        self.assertEqual("/MDd", settings.runtime_library)
        self.assertEqual("/W3", settings.warning_level)
        self.assertEqual("/Od", settings.optimization)
        self.assertEqual("/ZI", settings.debug_info)
        self.assertEqual([".\\include", "..\\shared include"], [item.raw for item in settings.include_dirs[:2]])

    def test_parse_dsp_build_settings_capture_unresolved_macros(self):
        project = parse_dsp(DSP_FIXTURE / "Control.dsp")
        debug = next(cfg for cfg in project.configurations if cfg.name == "Debug")

        self.assertIn("LEGACY_SDK", debug.build_settings.unresolved_macros)
        self.assertIn("unresolved_macro", [warning.code for warning in project.warnings])

    def test_source_membership_returns_multiple_project_matches_and_filters(self):
        result = map_source_membership(WORKSPACE_FIXTURE / "Product.dsw", "shared/shared.c")

        self.assertEqual("multiple_matches", result.status)
        self.assertEqual(["ProductA", "ProductB"], [match.project_name for match in result.matches])

        filtered = map_source_membership(WORKSPACE_FIXTURE / "Product.dsw", "shared/shared.c", project_name="ProductB")
        self.assertEqual("ok", filtered.status)
        self.assertEqual(["ProductB"], [match.project_name for match in filtered.matches])

    def test_map_source_cli_without_workspace_is_full_step04_mapping(self):
        completed = run_module(
            "--json",
            "map-source",
            "--dsw",
            str(WORKSPACE_FIXTURE / "Product.dsw"),
            "--source",
            "shared/shared.c",
            "--configuration",
            "Win32 Debug",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("multiple_matches", payload["status"])
        self.assertEqual(2, len(payload["data"]["matches"]))
        self.assertEqual(["Win32 Debug"], payload["data"]["matches"][0]["configurations"])

    def test_map_source_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "membership.md"
            completed = run_module(
                "map-source",
                "--dsw",
                str(WORKSPACE_FIXTURE / "Product.dsw"),
                "--source",
                "shared/shared.c",
                "--out",
                str(out),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            markdown = out.read_text(encoding="utf-8")
            self.assertIn("# Source Membership Report", markdown)
            self.assertIn("| ProductA |", markdown)

    def test_discover_projects_with_dsp_details_adds_summary(self):
        completed = run_module(
            "--json",
            "discover-projects",
            "--workspace",
            str(WORKSPACE_FIXTURE),
            "--with-dsp-details",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        projects = payload["data"]["workspaces"][0]["projects"]
        self.assertIn("dsp_summary", projects[0])
        self.assertEqual(1, projects[0]["dsp_summary"]["source_file_count"])
        self.assertEqual(["ProductA - Win32 Debug"], projects[0]["dsp_summary"]["configurations"])


if __name__ == "__main__":
    unittest.main()
