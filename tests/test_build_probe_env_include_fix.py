import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_workspace_generator import generate_build_workspace
from unit_test_runner.c_analyzer.source_digest import build_source_digest
from unit_test_runner.harness.harness_skeleton_generator import generate_harness_skeleton
from unit_test_runner.vc6.dsp_options import parse_build_settings, tokenize_compiler_options


class BuildProbeEnvIncludeFixTests(unittest.TestCase):
    def test_compiler_options_handle_parenthesized_dollar_include_macros(self):
        tokens = tokenize_compiler_options('/I "($TEMP_MSVC)\\include" /I "$(LEGACY_SDK)\\inc" /I "%SDKROOT%\\inc"')
        settings = parse_build_settings(tokens, REPO_ROOT, REPO_ROOT)

        self.assertEqual(
            ["($TEMP_MSVC)/include", "$(LEGACY_SDK)/inc", "%SDKROOT%/inc"],
            [item.normalized for item in settings.include_dirs],
        )
        self.assertEqual([None, None, None], [item.absolute for item in settings.include_dirs])
        self.assertIn("TEMP_MSVC", settings.unresolved_macros)
        self.assertIn("LEGACY_SDK", settings.unresolved_macros)
        self.assertIn("SDKROOT", settings.unresolved_macros)

    def test_generator_preserves_macro_include_dirs_as_passthrough_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            source = project / "src" / "target.c"
            source.parent.mkdir(parents=True)
            source.write_text("int Target(void) { return 1; }\n", encoding="ascii")
            out_dir = Path(temp_dir) / "out"
            build_context = {
                "workspace_root": str(project),
                "include_dirs": ["($TEMP_MSVC)/include"],
                "defines": [],
                "compiler_options": [],
            }
            source_digest = {"source": {"path": str(source)}, "preprocessor": {"includes": []}}
            harness_report = {"function": {"name": "Target"}, "source": {"path": str(source)}, "output_root": str(out_dir), "generated_files": []}

            report, _probe = generate_build_workspace(build_context, source_digest, harness_report, out_dir, run_probe=False, dry_run=True)

            macro_include = next(item for item in report.include_dirs if item.raw == "($TEMP_MSVC)/include")
            self.assertIsNone(macro_include.workspace_path)
            self.assertIsNone(macro_include.original_path)

            makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")
            self.assertIn('/I"($TEMP_MSVC)\\include"', makefile)
            self.assertNotIn("extracted\\($TEMP_MSVC)", makefile)

            dsp = (out_dir / "build" / "UTR_Target.dsp").read_text(encoding="cp932")
            self.assertIn('/I "($TEMP_MSVC)\\include"', dsp)
            self.assertNotIn("extracted\\($TEMP_MSVC)", dsp)

    def test_extern_macro_data_declarations_from_headers_get_link_placeholders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            shared = project / "shared"
            source = shared / "shared.c"
            header = shared / "shared2.h"
            shared.mkdir(parents=True)
            source.write_text('#include "shared2.h"\nint Shared(void) { return g_com != 0; }\n', encoding="ascii")
            header.write_text(
                "#define EXTERN extern\n"
                "typedef struct _gbl1 { int test; } gbl1;\n"
                "typedef struct _gbl_com { gbl1* ptr; } gbl_com;\n"
                "EXTERN gbl_com *g_com;\n",
                encoding="ascii",
            )
            out_dir = Path(temp_dir) / "out"
            build_context = {"workspace_root": str(project), "include_dirs": ["shared"], "defines": [], "compiler_options": []}
            source_digest = {"source": {"path": str(source)}, "preprocessor": {"includes": [{"name": "shared2.h", "resolved_candidates": [str(header)]}]}}
            harness_report = {"function": {"name": "Shared"}, "source": {"path": str(source)}, "output_root": str(out_dir), "generated_files": []}

            report, _probe = generate_build_workspace(build_context, source_digest, harness_report, out_dir, run_probe=False, dry_run=True)

            placeholder = out_dir / "generated" / "stubs" / "utr_extern_globals.c"
            self.assertTrue(placeholder.exists())
            self.assertIn("gbl_com * g_com = {0};", placeholder.read_text(encoding="cp932"))
            self.assertIn("generated/stubs/utr_extern_globals.c", {unit.source_file.as_posix() for unit in report.compile_units})

    def test_function_level_source_removal_uses_character_offsets_for_cp932_crlf_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            shared = project / "shared"
            source = shared / "shared.c"
            shared.mkdir(parents=True)
            (shared / "shared0.h").write_text("typedef short DWORD;\n", encoding="ascii")
            (shared / "shared2.h").write_text("typedef struct gbl_input_tag { int value; } gbl_input;\n", encoding="ascii")
            source.write_bytes(
                (
                    "//テスト\r\n"
                    "#include \"shared0.h\"\r\n"
                    "#include \"shared2.h\"\r\n"
                    "\r\n"
                    "int g_count = 0;\r\n"
                    "\r\n"
                    "int Shared(void)\r\n"
                    "{\r\n"
                    "    g_count++;\r\n"
                    "    return g_count;\r\n"
                    "}\r\n"
                    "\r\n"
                    "int Shared2(void)\r\n"
                    "{\r\n"
                    "    g_count++;\r\n"
                    "    return g_count;\r\n"
                    "}\r\n"
                    "\r\n"
                    "DWORD Shared3(gbl_input* prm)\r\n"
                    "{\r\n"
                    "    g_count++;\r\n"
                    "    prm->value = g_count;\r\n"
                    "    return g_count;\r\n"
                    "}\r\n"
                ).encode("cp932")
            )
            out_dir = Path(temp_dir) / "out"
            build_context = {"workspace_root": str(project), "include_dirs": ["shared"], "defines": [], "compiler_options": []}
            source_digest = build_source_digest(source, build_context).to_dict()
            harness_report = {"function": {"name": "Shared3"}, "source": {"path": str(source)}, "output_root": str(out_dir), "generated_files": []}

            generate_build_workspace(build_context, source_digest, harness_report, out_dir, run_probe=False, dry_run=True)

            isolated = (out_dir / "extracted" / "shared" / "shared.c").read_text(encoding="cp932")
            normalized = isolated.replace("\r\n", "\n").replace("\r", "\n")
            self.assertIn("DWORD Shared3(gbl_input* prm)", isolated)
            self.assertNotIn("int Shared(void)", isolated)
            self.assertNotIn("int Shared2(void)", isolated)
            self.assertNotIn("\n;\n}", normalized)
            self.assertEqual(isolated.count("{"), isolated.count("}"))

    def test_target_invocation_includes_target_source_headers_for_typedef_return(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            source = project / "shared" / "shared.c"
            header = project / "shared" / "shared0.h"
            source.parent.mkdir(parents=True)
            source.write_text('#include "shared0.h"\nDWORD Shared3(void) { return 1; }\n', encoding="ascii")
            header.write_text("typedef short DWORD;\n", encoding="ascii")
            signature = {
                "source": {"path": str(source)},
                "function": {
                    "name": "Shared3",
                    "return_type": {"raw": "DWORD"},
                    "parameters": [],
                    "takes_no_parameters": True,
                },
            }
            design = {
                "function": {"name": "Shared3"},
                "test_cases": [{"test_case_id": "TC_Shared3_001", "input_assignments": [], "stub_setups": [], "expected_observations": []}],
            }

            generate_harness_skeleton(signature, {"global_accesses": [], "file_scope_declarations": []}, {"stub_candidates": []}, design, Path(temp_dir))

            target_header = (Path(temp_dir) / "generated" / "harness" / "target_invocation.h").read_text(encoding="cp932")
            target_source = (Path(temp_dir) / "generated" / "harness" / "target_invocation.c").read_text(encoding="cp932")
            test_source = (Path(temp_dir) / "generated" / "tests" / "test_Shared3.c").read_text(encoding="cp932")
            self.assertIn('#include "shared0.h"', target_header)
            self.assertIn("DWORD Target_Invoke_Shared3(void);", target_header)
            self.assertIn("DWORD Shared3(void);", target_source)
            self.assertNotIn('#include "shared.h"', target_source)
            self.assertIn("DWORD actual_return;", test_source)


if __name__ == "__main__":
    unittest.main()
