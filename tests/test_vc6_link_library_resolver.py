import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from tests.coff_fixture import write_import_library
from unit_test_runner.vc6.link_library_resolver import expand_link_path, resolve_link_context


def _write_dsw(root: Path, dependency_release_only: bool = False) -> Path:
    dsw = root / "App.dsw"
    dsw.write_text(
        "Microsoft Developer Studio Workspace File, Format Version 6.00\n"
        'Project: "App"=App\\App.dsp - Package Owner=<4>\n'
        "    Project_Dep_Name ProductLib\n"
        'Project: "ProductLib"=ProductLib\\ProductLib.dsp - Package Owner=<4>\n'
        "    Project_Dep_Name TransitiveLib\n"
        'Project: "TransitiveLib"=TransitiveLib\\TransitiveLib.dsp - Package Owner=<4>\n'
        "Global:\n",
        encoding="cp932",
    )
    app_dir = root / "App"
    product_dir = root / "ProductLib"
    transitive_dir = root / "TransitiveLib"
    app_dir.mkdir()
    product_dir.mkdir()
    transitive_dir.mkdir()
    (app_dir / "App.dsp").write_text(
        '# Microsoft Developer Studio Project File - Name="App" - Package Owner=<4>\n'
        '!IF  "$(CFG)" == "App - Win32 Debug"\n'
        '# ADD LINK32 ..\\libs\\Explicit.lib /libpath:"..\\libs"\n'
        '!ENDIF\n',
        encoding="cp932",
    )
    product_config = "Release" if dependency_release_only else "Debug"
    (product_dir / "ProductLib.dsp").write_text(
        '# Microsoft Developer Studio Project File - Name="ProductLib" - Package Owner=<4>\n'
        f'!IF  "$(CFG)" == "ProductLib - Win32 {product_config}"\n'
        f'# PROP Output_Dir "{product_config}"\n'
        f'# ADD LINK32 /out:"{product_config}\\ProductLib.lib"\n'
        '!ENDIF\n',
        encoding="cp932",
    )
    (transitive_dir / "TransitiveLib.dsp").write_text(
        '# Microsoft Developer Studio Project File - Name="TransitiveLib" - Package Owner=<4>\n'
        '!IF  "$(CFG)" == "TransitiveLib - Win32 Debug"\n'
        '# PROP Output_Dir "Debug"\n'
        '# ADD LINK32 /out:"Debug\\TransitiveLib.lib"\n'
        '!ENDIF\n',
        encoding="cp932",
    )
    return dsw


class Vc6LinkLibraryResolverTests(unittest.TestCase):
    def test_explicit_and_direct_dependency_libraries_are_ordered_and_transitive_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsw = _write_dsw(root)
            (root / "libs").mkdir()
            (root / "ProductLib" / "Debug").mkdir()
            (root / "TransitiveLib" / "Debug").mkdir()
            write_import_library(root / "libs" / "Explicit.lib", "_ExplicitCall@4")
            write_import_library(root / "ProductLib" / "Debug" / "ProductLib.lib", "_DependencyCall@4")
            write_import_library(root / "TransitiveLib" / "Debug" / "TransitiveLib.lib", "_TransitiveCall@4")

            context = resolve_link_context(root, dsw, "App", "Win32 Debug", environ={})

            self.assertEqual(["Explicit.lib", "ProductLib.lib"], [item.path.name for item in context.libraries])
            self.assertEqual(["explicit_link32", "direct_dependency_project"], [item.source for item in context.libraries])
            self.assertNotIn("TransitiveLib.lib", {item.path.name for item in context.libraries})
            self.assertIn("ExplicitCall", context.providers_by_name)
            self.assertIn("DependencyCall", context.providers_by_name)
            self.assertNotIn("TransitiveCall", context.providers_by_name)
            self.assertEqual([0, 1], [item.link_order for item in context.libraries])

    def test_dependency_requires_matching_platform_and_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsw = _write_dsw(root, dependency_release_only=True)
            (root / "libs").mkdir()
            write_import_library(root / "libs" / "Explicit.lib", "_ExplicitCall")

            context = resolve_link_context(root, dsw, "App", "Win32 Debug", environ={})

            self.assertEqual(["Explicit.lib"], [item.path.name for item in context.libraries])
            self.assertTrue(any(item.code == "dependency_configuration_not_found" for item in context.warnings))

    def test_import_library_output_has_priority_over_out_and_default_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsw = _write_dsw(root)
            (root / "libs").mkdir()
            write_import_library(root / "libs" / "Explicit.lib", "_ExplicitCall")
            product = root / "ProductLib"
            (product / "Debug").mkdir()
            (product / "ProductLib.dsp").write_text(
                '# Microsoft Developer Studio Project File - Name="ProductLib" - Package Owner=<4>\n'
                '!IF  "$(CFG)" == "ProductLib - Win32 Debug"\n'
                '# PROP Output_Dir "Debug"\n'
                '# ADD LINK32 /implib:"Debug\\Preferred.lib" /out:"Debug\\Fallback.lib"\n'
                '!ENDIF\n',
                encoding="cp932",
            )
            write_import_library(product / "Debug" / "Preferred.lib", "_PreferredCall")
            write_import_library(product / "Debug" / "Fallback.lib", "_FallbackCall")
            write_import_library(product / "Debug" / "ProductLib.lib", "_DefaultCall")

            context = resolve_link_context(root, dsw, "App", "Win32 Debug", environ={})

            self.assertEqual("Preferred.lib", context.libraries[1].path.name)
            self.assertIn("PreferredCall", context.providers_by_name)
            self.assertNotIn("FallbackCall", context.providers_by_name)
            self.assertNotIn("DefaultCall", context.providers_by_name)

    def test_existing_broken_library_remains_link_input_but_does_not_resolve_calls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsw = _write_dsw(root, dependency_release_only=True)
            (root / "libs").mkdir()
            broken = root / "libs" / "Explicit.lib"
            broken.write_bytes(b"broken")

            context = resolve_link_context(root, dsw, "App", "Win32 Debug", environ={})

            self.assertEqual([broken.resolve()], [item.path for item in context.libraries])
            self.assertEqual("failed", context.libraries[0].scan_status)
            self.assertFalse(context.providers_by_name)
            self.assertTrue(any(item.code == "library_symbol_scan_failed" for item in context.warnings))

    def test_environment_lib_directory_resolves_explicit_library(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsw = _write_dsw(root, dependency_release_only=True)
            app_dsp = root / "App" / "App.dsp"
            app_dsp.write_text(
                '# Microsoft Developer Studio Project File - Name="App" - Package Owner=<4>\n'
                '!IF  "$(CFG)" == "App - Win32 Debug"\n'
                '# ADD LINK32 Environment.lib\n'
                '!ENDIF\n',
                encoding="cp932",
            )
            envlib = root / "envlib"
            envlib.mkdir()
            write_import_library(envlib / "Environment.lib", "_EnvironmentCall")

            context = resolve_link_context(root, dsw, "App", "Win32 Debug", environ={"LIB": str(envlib)})

            self.assertEqual("Environment.lib", context.libraries[0].path.name)
            self.assertIn("EnvironmentCall", context.providers_by_name)

    def test_supported_macros_expand_deterministically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            value, unresolved = expand_link_path(
                "$(OUTDIR)/$(INTDIR)/$(CFG)/$(NAME)/%PRODUCT%/${SDK}/($LEGACY)",
                output_dir="Debug",
                intermediate_dir="Obj",
                configuration="App - Win32 Debug",
                project_name="App",
                environ={"PRODUCT": str(root / "product"), "SDK": "sdk", "LEGACY": "legacy"},
            )

            self.assertEqual("Debug/Obj/App - Win32 Debug/App/" + str(root / "product").replace("\\", "/") + "/sdk/legacy", value)
            self.assertEqual([], unresolved)

    def test_duplicate_absolute_library_paths_keep_first_link_position(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsw = _write_dsw(root, dependency_release_only=True)
            (root / "libs").mkdir()
            library = root / "libs" / "Explicit.lib"
            write_import_library(library, "_ExplicitCall")
            (root / "App" / "App.dsp").write_text(
                '# Microsoft Developer Studio Project File - Name="App" - Package Owner=<4>\n'
                '!IF  "$(CFG)" == "App - Win32 Debug"\n'
                '# ADD LINK32 ..\\libs\\Explicit.lib ..\\libs\\Explicit.lib\n'
                '!ENDIF\n',
                encoding="cp932",
            )

            context = resolve_link_context(root, dsw, "App", "Win32 Debug", environ={})

            self.assertEqual(1, len(context.libraries))
            self.assertEqual(0, context.libraries[0].link_order)


if __name__ == "__main__":
    unittest.main()
