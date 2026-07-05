import dataclasses
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.c_analyzer import list_functions
from unit_test_runner.encoding import write_generated_c_text
from unit_test_runner.models import BuildConfiguration, Project
from unit_test_runner.vc6 import discover_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]


class AdrLanguageRequirementTests(unittest.TestCase):
    def test_package_declares_python_312_minimum(self):
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(">=3.12", pyproject["project"]["requires-python"])

    def test_vc6_project_files_can_be_read_as_cp932(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "App").mkdir()
            (root / "src").mkdir()
            dsw = root / "Product.dsw"
            dsp = root / "App" / "App.dsp"
            source = root / "src" / "main.c"
            dsw.write_bytes(
                (
                    'Project: "制御"=.\\App\\App.dsp - Package Owner=<4>\n'
                    "Package=<4>\n"
                    "{{{\n"
                    "}}}\n"
                ).encode("cp932")
            )
            dsp.write_bytes(
                (
                    '# Microsoft Developer Studio Project File - Name="制御" - Package Owner=<4>\n'
                    '!IF "$(CFG)" == "制御 - Win32 Debug"\n'
                    '# ADD CPP /nologo /D "WIN32" /I "..\\include"\n'
                    "!ENDIF\n"
                    '# Name "制御 - Win32 Debug"\n'
                    "# Begin Source File\n"
                    "SOURCE=..\\src\\main.c\n"
                    "# End Source File\n"
                ).encode("cp932")
            )
            source.write_text("int main_func(void) { return 0; }\n", encoding="utf-8")

            workspace = discover_workspace(root, dsw)

            self.assertEqual("制御", workspace["projects"][0]["project_name"])
            self.assertIn("Win32 Debug", workspace["projects"][0]["configurations"])

    def test_c_analyzer_handles_utf8_bom_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "bom.c"
            source.write_bytes("int BomFunction(void) { return 0; }\n".encode("utf-8-sig"))

            functions = list_functions(source)

            self.assertEqual(["BomFunction"], [function["name"] for function in functions])

    def test_c_analyzer_treats_shift_jis_japanese_comments_as_normal_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sjis.c"
            source.write_bytes(
                (
                    "/* 日本語コメント: 条件 { } を含む */\n"
                    "int JapaneseCommentedFunction(void)\n"
                    "{\n"
                    "    return 0;\n"
                    "}\n"
                ).encode("shift_jis")
            )

            functions = list_functions(source)

            self.assertEqual(["JapaneseCommentedFunction"], [function["name"] for function in functions])

    def test_generated_c_style_files_are_written_as_cp932_crlf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "runner.c"

            write_generated_c_text(target, "/* 生成ランナー */\nint Runner(void)\n{\n    return 0;\n}\n")

            raw = target.read_bytes()
            self.assertIn(b"\r\n", raw)
            self.assertNotIn(b"\nint Runner", raw.replace(b"\r\n", b""))
            self.assertEqual(
                "/* 生成ランナー */\r\nint Runner(void)\r\n{\r\n    return 0;\r\n}\r\n",
                raw.decode("cp932"),
            )

    def test_core_structures_are_dataclass_models(self):
        self.assertTrue(dataclasses.is_dataclass(BuildConfiguration))
        self.assertTrue(dataclasses.is_dataclass(Project))
        self.assertEqual({}, BuildConfiguration(full_name="Debug").to_dict()["precompiled_header"])


if __name__ == "__main__":
    unittest.main()
