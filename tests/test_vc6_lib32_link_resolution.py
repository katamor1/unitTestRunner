import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from tests.coff_fixture import write_object_library_without_linker
from unit_test_runner.vc6.dsp_parser import parse_dsp
from unit_test_runner.vc6.link_library_resolver import resolve_link_context


class Vc6Lib32LinkResolutionTests(unittest.TestCase):
    def test_static_library_lib32_output_is_parsed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsp = root / "ProductLib.dsp"
            dsp.write_text(
                '# Microsoft Developer Studio Project File - Name="ProductLib" - Package Owner=<4>\n'
                '# TARGTYPE "Win32 (x86) Static Library" 0x0104\n'
                '!IF  "$(CFG)" == "ProductLib - Win32 Debug"\n'
                '# PROP Output_Dir "Debug"\n'
                '# ADD BASE LIB32 /nologo\n'
                '# ADD LIB32 /nologo /out:"Debug\\ProductLib.lib"\n'
                '!ENDIF\n',
                encoding="cp932",
            )

            project = parse_dsp(dsp, root)
            configuration = project.configurations[0]

            self.assertEqual(["/nologo"], configuration.linker_base_options)
            self.assertEqual(["/nologo", '/out:"Debug\\ProductLib.lib"'], configuration.linker_options)
            self.assertEqual("Debug/ProductLib.lib", configuration.link_settings.output_file.normalized)

    def test_direct_static_library_dependency_is_resolved_from_lib32_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = root / "App"
            product = root / "ProductLib"
            output = product / "Debug"
            app.mkdir()
            output.mkdir(parents=True)
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
            (app / "App.dsp").write_text(
                '# Microsoft Developer Studio Project File - Name="App" - Package Owner=<4>\n'
                '!IF  "$(CFG)" == "App - Win32 Debug"\n'
                '# ADD LINK32 /nologo\n'
                '!ENDIF\n',
                encoding="cp932",
            )
            (product / "ProductLib.dsp").write_text(
                '# Microsoft Developer Studio Project File - Name="ProductLib" - Package Owner=<4>\n'
                '# TARGTYPE "Win32 (x86) Static Library" 0x0104\n'
                '!IF  "$(CFG)" == "ProductLib - Win32 Debug"\n'
                '# PROP Output_Dir "Debug"\n'
                '# ADD LIB32 /nologo /out:"Debug\\ProductLib.lib"\n'
                '!ENDIF\n',
                encoding="cp932",
            )
            library = output / "ProductLib.lib"
            write_object_library_without_linker(library, "_ProductCalc@4")

            context = resolve_link_context(root, dsw, "App", "Win32 Debug", environ={})

            self.assertEqual([library.resolve()], [item.path for item in context.libraries])
            self.assertEqual(["direct_dependency_project"], [item.source for item in context.libraries])
            self.assertIn("ProductCalc", context.providers_by_name)
            self.assertEqual("static_library", context.providers_by_name["ProductCalc"][0].provider_kind)


if __name__ == "__main__":
    unittest.main()
