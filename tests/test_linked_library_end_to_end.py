import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from tests.coff_fixture import write_import_library


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


def _write_workspace(root: Path) -> tuple[Path, Path]:
    app = root / "App"
    app_src = app / "src"
    product = root / "ProductLib"
    product_debug = product / "Debug"
    libs = root / "libs"
    app_src.mkdir(parents=True)
    product_debug.mkdir(parents=True)
    libs.mkdir(parents=True)
    source = app_src / "app.c"
    source.write_text(
        "int ExplicitCall(int value);\n"
        "int DependencyCall(int value);\n"
        "int AppRun(int value)\n"
        "{\n"
        "    return ExplicitCall(value) + DependencyCall(value);\n"
        "}\n",
        encoding="ascii",
    )
    (app / "App.dsp").write_text(
        '# Microsoft Developer Studio Project File - Name="App" - Package Owner=<4>\n'
        '!IF  "$(CFG)" == "App - Win32 Debug"\n'
        '# ADD CPP /nologo /W3 /Od /D "WIN32" /c\n'
        '# ADD LINK32 ..\\libs\\Explicit.lib /libpath:"..\\libs"\n'
        '!ENDIF\n'
        '# Begin Group "Source Files"\n'
        'SOURCE=.\\src\\app.c\n'
        '# End Group\n',
        encoding="cp932",
    )
    (product / "ProductLib.dsp").write_text(
        '# Microsoft Developer Studio Project File - Name="ProductLib" - Package Owner=<4>\n'
        '!IF  "$(CFG)" == "ProductLib - Win32 Debug"\n'
        '# PROP Output_Dir "Debug"\n'
        '# ADD LINK32 /out:"Debug\\ProductLib.lib"\n'
        '!ENDIF\n',
        encoding="cp932",
    )
    dsw = root / "App.dsw"
    dsw.write_text(
        "Microsoft Developer Studio Workspace File, Format Version 6.00\n"
        'Project: "App"=App\\App.dsp - Package Owner=<4>\n'
        "    Begin Project Dependency\n"
        "    Project_Dep_Name ProductLib\n"
        "    End Project Dependency\n"
        'Project: "ProductLib"=ProductLib\\ProductLib.dsp - Package Owner=<4>\n'
        "Global:\n",
        encoding="cp932",
    )
    write_import_library(libs / "Explicit.lib", "_ExplicitCall@4")
    write_import_library(product_debug / "ProductLib.lib", "__imp__DependencyCall@4")
    return dsw, source


class LinkedLibraryEndToEndTests(unittest.TestCase):
    def test_quick_check_build_flow_uses_real_libraries_without_generating_stubs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            dsw, source = _write_workspace(workspace)
            out_dir = Path(temp_dir) / "result"

            completed = run_module(
                "--json",
                "quick-check",
                "--workspace",
                str(workspace),
                "--dsw",
                str(dsw),
                "--source",
                source.relative_to(workspace).as_posix(),
                "--function",
                "AppRun",
                "--configuration",
                "Win32 Debug",
                "--project",
                "App",
                "--profile",
                "build",
                "--out",
                str(out_dir),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            call_report = json.loads((out_dir / "reports" / "call_report.json").read_text(encoding="utf-8"))
            harness = json.loads((out_dir / "reports" / "harness_skeleton_report.json").read_text(encoding="utf-8"))
            build_context = json.loads((out_dir / "reports" / "build_context.json").read_text(encoding="utf-8"))
            build_workspace = json.loads((out_dir / "reports" / "build_workspace_report.json").read_text(encoding="utf-8"))
            quick_summary = json.loads((out_dir / "reports" / "quick_summary.json").read_text(encoding="utf-8"))
            makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")
            debug_dsp = next((out_dir / "build").glob("UTR_*.dsp")).read_text(encoding="cp932")

            linked = {item["name"] for item in call_report["calls"] if item["target_kind"] == "linked_library_function"}
            self.assertEqual({"ExplicitCall", "DependencyCall"}, linked)
            self.assertFalse(harness["stub_skeletons"])
            self.assertEqual(["Explicit.lib", "ProductLib.lib"], [Path(item["path"]).name for item in build_context["link_libraries"]])
            self.assertEqual(["Explicit.lib", "ProductLib.lib"], [Path(item["path"]).name for item in build_workspace["link_libraries"]])
            self.assertIn("Explicit.lib", makefile)
            self.assertIn("ProductLib.lib", makefile)
            self.assertIn("Explicit.lib", debug_dsp)
            self.assertIn("ProductLib.lib", debug_dsp)
            self.assertEqual(2, quick_summary["link_resolution"]["library_count"])
            self.assertEqual(2, quick_summary["link_resolution"]["linked_function_count"])


if __name__ == "__main__":
    unittest.main()
