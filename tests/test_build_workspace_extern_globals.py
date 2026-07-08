import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_workspace_generator import generate_build_workspace


class BuildWorkspaceExternGlobalsTests(unittest.TestCase):
    def test_extern_data_declarations_from_headers_get_link_placeholders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            shared = project / "shared"
            source = shared / "shared.c"
            header = shared / "shared2.h"
            shared.mkdir(parents=True)
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
                "defines": [],
                "compiler_options": [],
            }
            source_digest = {
                "source": {"path": str(source)},
                "preprocessor": {
                    "includes": [
                        {
                            "name": "shared2.h",
                            "resolved_candidates": [str(header)],
                        }
                    ]
                },
            }
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

            placeholder = out_dir / "generated" / "stubs" / "utr_extern_globals.c"
            self.assertTrue(placeholder.exists())
            text = placeholder.read_text(encoding="cp932")
            self.assertIn('#include "../../extracted/shared/shared2.h"', text)
            self.assertIn("gbl_com * g_com = {0};", text)
            compile_sources = {unit.source_file.as_posix() for unit in report.compile_units}
            self.assertIn("generated/stubs/utr_extern_globals.c", compile_sources)
            makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")
            self.assertIn("..\\generated\\stubs\\utr_extern_globals.c", makefile)
            self.assertIn("..\\obj\\utr_extern_globals.obj", makefile)

    def test_target_source_definitions_are_not_duplicated_as_placeholders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            source = project / "src" / "control.c"
            header = project / "src" / "control.h"
            source.parent.mkdir(parents=True)
            source.write_text('#include "control.h"\nint g_count = 0;\nint Control(void) { return g_count; }\n', encoding="ascii")
            header.write_text("extern int g_count;\n", encoding="ascii")
            out_dir = Path(temp_dir) / "out"
            build_context = {"workspace_root": str(project), "include_dirs": ["src"], "defines": [], "compiler_options": []}
            source_digest = {
                "source": {"path": str(source)},
                "preprocessor": {"includes": [{"name": "control.h", "resolved_candidates": [str(header)]}]},
            }
            harness_report = {"function": {"name": "Control"}, "source": {"path": str(source)}, "output_root": str(out_dir), "generated_files": []}

            report, _probe = generate_build_workspace(build_context, source_digest, harness_report, out_dir, run_probe=False, dry_run=True)

            self.assertFalse((out_dir / "generated" / "stubs" / "utr_extern_globals.c").exists())
            self.assertNotIn("generated/stubs/utr_extern_globals.c", {unit.source_file.as_posix() for unit in report.compile_units})


if __name__ == "__main__":
    unittest.main()
