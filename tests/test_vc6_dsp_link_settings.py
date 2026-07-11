import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.vc6.dsp_parser import parse_dsp


class Vc6DspLinkSettingsTests(unittest.TestCase):
    def test_link32_libraries_paths_and_outputs_are_configuration_scoped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsp = root / "App.dsp"
            dsp.write_text(
                '# Microsoft Developer Studio Project File - Name="App" - Package Owner=<4>\n'
                '# TARGTYPE "Win32 (x86) Console Application" 0x0103\n'
                '!IF  "$(CFG)" == "App - Win32 Debug"\n'
                '# PROP Output_Dir "Debug"\n'
                '# PROP Intermediate_Dir "Debug\\obj"\n'
                '# ADD BASE LINK32 base.lib /libpath:"..\\base"\n'
                '# ADD LINK32 first.lib "..\\third party\\second.lib" /libpath:"..\\lib" '
                '/out:"Debug\\App.exe" /implib:"Debug\\AppImport.lib"\n'
                '!ENDIF\n'
                '!IF  "$(CFG)" == "App - Win32 Release"\n'
                '# PROP Output_Dir "Release"\n'
                '# ADD LINK32 release.lib /out:"Release\\App.exe"\n'
                '!ENDIF\n',
                encoding="cp932",
            )

            project = parse_dsp(dsp, root)
            debug = next(item for item in project.configurations if item.full_name.endswith("Win32 Debug"))
            release = next(item for item in project.configurations if item.full_name.endswith("Win32 Release"))

            self.assertEqual(["base.lib", "first.lib", "../third party/second.lib"], debug.link_settings.libraries)
            self.assertEqual(["../base", "../lib"], [item.normalized for item in debug.link_settings.library_dirs])
            self.assertEqual("Debug/App.exe", debug.link_settings.output_file.normalized)
            self.assertEqual("Debug/AppImport.lib", debug.link_settings.import_library.normalized)
            self.assertEqual("Debug", debug.link_settings.output_dir.normalized)
            self.assertEqual("Debug/obj", debug.link_settings.intermediate_dir.normalized)
            self.assertEqual(["release.lib"], release.link_settings.libraries)
            self.assertEqual("Release/App.exe", release.link_settings.output_file.normalized)

    def test_link_macros_are_preserved_for_the_resolver(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsp = root / "MacroLib.dsp"
            dsp.write_text(
                '# Microsoft Developer Studio Project File - Name="MacroLib" - Package Owner=<4>\n'
                '!IF  "$(CFG)" == "MacroLib - Win32 Debug"\n'
                '# PROP Output_Dir "$(CFG)\\out"\n'
                '# ADD LINK32 "%PRODUCT_LIB%\\Product.lib" /libpath:"($SDK_ROOT)\\lib"\n'
                '!ENDIF\n',
                encoding="cp932",
            )

            project = parse_dsp(dsp, root)
            settings = project.configurations[0].link_settings

            self.assertEqual(["%PRODUCT_LIB%/Product.lib"], settings.libraries)
            self.assertEqual(["SDK_ROOT"], settings.library_dirs[0].unresolved_macros)
            self.assertIn("CFG", settings.output_dir.unresolved_macros)
            self.assertIn("PRODUCT_LIB", settings.unresolved_macros)

    def test_linker_options_outside_configuration_emit_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsp = root / "Outside.dsp"
            dsp.write_text(
                '# Microsoft Developer Studio Project File - Name="Outside" - Package Owner=<4>\n'
                '# ADD LINK32 outside.lib\n',
                encoding="cp932",
            )

            project = parse_dsp(dsp, root)

            self.assertTrue(any(item.code == "linker_options_without_configuration" for item in project.warnings))


if __name__ == "__main__":
    unittest.main()
