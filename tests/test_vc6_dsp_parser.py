import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.vc6.dsp_options import parse_build_settings, tokenize_compiler_options
from unit_test_runner.vc6 import ProjectContextSelectionError, select_project_context
from unit_test_runner.cli.exit_codes import EXIT_TESTS_BLOCKED
from unit_test_runner.vc6.dsp_parser import parse_dsp
from unit_test_runner.vc6.source_membership import map_source_membership
from unit_test_runner.path_utils import resolve_vc6_path
from unit_test_runner.dsw_parser import parse_dsw as parse_dsw_workspace


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


class Vc6DspParserTests(unittest.TestCase):
    def test_vc6_path_resolution_keeps_absolute_drive_and_unc_inputs(self):
        base = Path(r"C:\workspace\project")

        self.assertEqual(
            Path(r"C:\product\src\control.c"),
            resolve_vc6_path(base, r"C:\product\src\control.c"),
        )
        self.assertEqual(
            Path(r"\\server\share\product\control.c"),
            resolve_vc6_path(base, r"\\server\share\product\control.c"),
        )

    def test_project_context_requires_one_exact_project_configuration_source_tuple(self):
        with self.assertRaises(ProjectContextSelectionError) as caught:
            select_project_context(
                WORKSPACE_FIXTURE,
                WORKSPACE_FIXTURE / "Product.dsw",
                "shared/shared.c",
                "Win32 Debug",
            )

        self.assertEqual("blocked", caught.exception.status)
        self.assertEqual(
            ["ProductA", "ProductB"],
            [item["project_name"] for item in caught.exception.candidates],
        )

        project, configuration, matches = select_project_context(
            WORKSPACE_FIXTURE,
            WORKSPACE_FIXTURE / "Product.dsw",
            "shared/shared.c",
            "ProductB - Win32 Debug",
            "ProductB",
        )
        self.assertEqual("ProductB", project["project_name"])
        self.assertEqual("ProductB - Win32 Debug", configuration["full_name"])
        self.assertEqual(1, len(matches))

    def test_effective_source_settings_apply_base_configuration_then_source_add_subtract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "target.c"
            source.write_text("int Target(void) { return 0; }\n", encoding="ascii")
            (root / "source include").mkdir()
            dsp = root / "Control.dsp"
            dsp.write_text(
                '# Microsoft Developer Studio Project File - Name="Control" - Package Owner=<4>\n'
                '# Microsoft Developer Studio Generated Build File, Format Version 6.00\n'
                '!IF "$(CFG)" == "Control - Win32 Debug"\n'
                '# ADD BASE CPP /D "BASE" /D "REMOVE_BASE" /W3 /YX\n'
                '# ADD CPP /D "CONFIG" /D "REMOVE_CONFIG" /W4 /Yu"stdafx.h"\n'
                '!ENDIF\n'
                '# Begin Source File\n'
                'SOURCE=.\\target.c\n'
                '!IF "$(CFG)" == "Control - Win32 Debug"\n'
                '# ADD CPP /D "SOURCE" /I ".\\source include" /Yc"source.h"\n'
                '# SUBTRACT CPP /D "REMOVE_BASE" /D "REMOVE_CONFIG" /W4 /Yu"stdafx.h"\n'
                '!ENDIF\n'
                '# End Source File\n',
                encoding="ascii",
            )
            dsw = root / "Product.dsw"
            dsw.write_text(
                'Microsoft Developer Studio Workspace File, Format Version 6.00\n'
                'Project: "Control"=.\\Control.dsp - Package Owner=<4>\n',
                encoding="ascii",
            )

            _project, configuration, _matches = select_project_context(
                root,
                dsw,
                source,
                "Control - Win32 Debug",
            )

        self.assertEqual(["BASE", "CONFIG", "SOURCE"], configuration["defines"])
        self.assertEqual("/W3", next(item for item in configuration["compiler_options"] if item.upper().startswith("/W")))
        self.assertNotIn("REMOVE_BASE", " ".join(configuration["compiler_options"]))
        self.assertNotIn("REMOVE_CONFIG", " ".join(configuration["compiler_options"]))
        self.assertEqual(
            {"enabled": True, "header": "source.h", "mode": "create"},
            configuration["precompiled_header"],
        )
        self.assertTrue(any(item.endswith("source include") for item in configuration["include_dirs"]))

    def test_parse_dsp_accepts_cp932_shift_jis_and_utf8_bom(self):
        cases = (("cp932", "cp932"), ("shift_jis", "cp932"), ("utf-8-sig", "utf-8-sig"))
        for encoding, detected_encoding in cases:
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as temp_dir:
                dsp = Path(temp_dir) / "Japanese.dsp"
                dsw = Path(temp_dir) / "Japanese.dsw"
                dsp.write_bytes(
                    (
                        '# Microsoft Developer Studio Project File - Name="制御" - Package Owner=<4>\n'
                        '# Microsoft Developer Studio Generated Build File, Format Version 6.00\n'
                    ).encode(encoding)
                )
                dsw.write_bytes(
                    (
                        "Microsoft Developer Studio Workspace File, Format Version 6.00\n"
                        'Project: "制御"=.\\Japanese.dsp - Package Owner=<4>\n'
                    ).encode(encoding)
                )

                project = parse_dsp(dsp)
                workspace = parse_dsw_workspace(dsw)

                self.assertEqual("制御", project.name)
                self.assertEqual(detected_encoding, project.encoding)
                self.assertEqual("制御", workspace.projects[0].name)
                self.assertEqual(detected_encoding, workspace.encoding)

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

        missing_config = map_source_membership(WORKSPACE_FIXTURE / "Product.dsw", "shared/shared.c", configuration="DoesNotExist")
        self.assertEqual("not_found", missing_config.status)
        self.assertEqual([], missing_config.matches)

    def test_map_source_cli_without_workspace_blocks_ambiguous_mapping_without_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "mapping.json"
            completed = run_module(
                "--json", "map-source",
                "--dsw", str(WORKSPACE_FIXTURE / "Product.dsw"),
                "--source", "shared/shared.c",
                "--configuration", "Win32 Debug", "--out", str(out),
            )

            self.assertEqual(EXIT_TESTS_BLOCKED, completed.returncode, completed.stderr)
            self.assertEqual("", completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("map-source", payload["command"])
            self.assertEqual("blocked", payload["outcome"])
            self.assertIn("ProductA", payload["diagnostics"][0]["message"])
            self.assertIn("ProductB", payload["diagnostics"][0]["message"])
            self.assertFalse(out.exists())

    def test_map_source_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "membership.md"
            completed = run_module(
                "map-source",
                "--dsw",
                str(WORKSPACE_FIXTURE / "Product.dsw"),
                "--source",
                "shared/shared.c",
                "--project",
                "ProductA",
                "--out",
                str(out),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            markdown = out.read_text(encoding="utf-8")
            self.assertIn("# ソース所属レポート", markdown)
            self.assertIn("| ProductA |", markdown)

    def test_discover_projects_with_dsp_details_adds_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "projects.json"
            completed = run_module(
                "--json", "discover-projects", "--workspace", str(WORKSPACE_FIXTURE),
                "--with-dsp-details", "--out", str(out),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("discover-projects", payload["command"])
            projects = json.loads(out.read_text(encoding="utf-8"))["workspaces"][0]["projects"]
            self.assertIn("dsp_summary", projects[0])
            self.assertEqual(1, projects[0]["dsp_summary"]["source_file_count"])
            self.assertEqual(["ProductA - Win32 Debug"], projects[0]["dsp_summary"]["configurations"])


if __name__ == "__main__":
    unittest.main()
