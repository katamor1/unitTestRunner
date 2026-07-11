import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from tests.coff_fixture import write_import_library
from unit_test_runner.dossier import analyze_function_workflow


def _write_workspace(root: Path, library_bytes: bytes | None = None) -> tuple[Path, Path]:
    app = root / "App"
    libs = root / "libs"
    app.mkdir()
    libs.mkdir()
    source = app / "consumer.c"
    source.write_text(
        "int ProductCalc(int value);\n"
        "int Consumer(int value)\n"
        "{\n"
        "    return ProductCalc(value);\n"
        "}\n",
        encoding="ascii",
    )
    dsp = app / "App.dsp"
    dsp.write_text(
        '# Microsoft Developer Studio Project File - Name="App" - Package Owner=<4>\n'
        '!IF  "$(CFG)" == "App - Win32 Debug"\n'
        '# ADD CPP /nologo /W3 /Od /D "WIN32" /c\n'
        '# ADD LINK32 ..\\libs\\Product.lib /libpath:"..\\libs"\n'
        '!ENDIF\n'
        'SOURCE=.\\consumer.c\n',
        encoding="cp932",
    )
    dsw = root / "App.dsw"
    dsw.write_text(
        "Microsoft Developer Studio Workspace File, Format Version 6.00\n"
        'Project: "App"=App\\App.dsp - Package Owner=<4>\n'
        "Global:\n",
        encoding="cp932",
    )
    library = libs / "Product.lib"
    if library_bytes is None:
        write_import_library(library, "_ProductCalc@4")
    else:
        library.write_bytes(library_bytes)
    return dsw, source


class DossierLinkContextIntegrationTests(unittest.TestCase):
    def test_library_provider_removes_stub_before_harness_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            root.mkdir()
            dsw, source = _write_workspace(root)
            out_dir = Path(temp_dir) / "result"

            analyze_function_workflow(
                root,
                dsw,
                source.relative_to(root).as_posix(),
                "Consumer",
                "Win32 Debug",
                out_dir,
                project_name="App",
                phase="harness",
            )

            call_report = json.loads((out_dir / "reports" / "call_report.json").read_text(encoding="utf-8"))
            harness = json.loads((out_dir / "reports" / "harness_skeleton_report.json").read_text(encoding="utf-8"))
            build_context = json.loads((out_dir / "reports" / "build_context.json").read_text(encoding="utf-8"))
            call = next(item for item in call_report["calls"] if item["name"] == "ProductCalc")

            self.assertEqual("linked_library_function", call["target_kind"])
            self.assertNotIn("ProductCalc", {item["name"] for item in call_report["stub_candidates"]})
            self.assertNotIn("ProductCalc", {item["original_function_name"] for item in harness["stub_skeletons"]})
            self.assertEqual("Product.lib", Path(build_context["link_libraries"][0]["path"]).name)
            self.assertEqual([], build_context["link_context_warnings"])

    def test_failed_symbol_scan_keeps_external_stub_and_records_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            root.mkdir()
            dsw, source = _write_workspace(root, b"broken library")
            out_dir = Path(temp_dir) / "result"

            analyze_function_workflow(
                root,
                dsw,
                source.relative_to(root).as_posix(),
                "Consumer",
                "Win32 Debug",
                out_dir,
                project_name="App",
                phase="harness",
            )

            call_report = json.loads((out_dir / "reports" / "call_report.json").read_text(encoding="utf-8"))
            harness = json.loads((out_dir / "reports" / "harness_skeleton_report.json").read_text(encoding="utf-8"))
            build_context = json.loads((out_dir / "reports" / "build_context.json").read_text(encoding="utf-8"))
            call = next(item for item in call_report["calls"] if item["name"] == "ProductCalc")

            self.assertEqual("external_function", call["target_kind"])
            self.assertIn("ProductCalc", {item["name"] for item in call_report["stub_candidates"]})
            self.assertIn("ProductCalc", {item["original_function_name"] for item in harness["stub_skeletons"]})
            self.assertTrue(any(item["code"] == "library_symbol_scan_failed" for item in build_context["link_context_warnings"]))


if __name__ == "__main__":
    unittest.main()
