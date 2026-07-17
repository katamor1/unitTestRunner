import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_large_vc6_fixture.py"

spec = importlib.util.spec_from_file_location("generate_large_vc6_fixture", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load generator: {SCRIPT_PATH}")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class LargeVc6FixtureGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp = Path(self.temp_dir.name)
        self.base = self.temp / "base"
        self.perf_root = self.temp / "perf"
        self._write_base_fixture()

    def _write_base_fixture(self):
        (self.base / "DeviceControl").mkdir(parents=True)
        (self.base / "src").mkdir()
        (self.base / "include").mkdir()
        (self.base / "Product.dsw").write_text(
            "\n".join(
                [
                    "Microsoft Developer Studio Workspace File, Format Version 6.00",
                    "# WARNING: DO NOT EDIT OR DELETE THIS WORKSPACE FILE!",
                    "",
                    'Project: "DeviceControl"=.\\DeviceControl\\DeviceControl.dsp - Package Owner=<4>',
                    "",
                    "Global:",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (self.base / "DeviceControl" / "DeviceControl.dsp").write_text(
            "\n".join(
                [
                    '# Microsoft Developer Studio Project File - Name="DeviceControl" - Package Owner=<4>',
                    "# Microsoft Developer Studio Generated Build File, Format Version 6.00",
                    "",
                    '!IF "$(CFG)" == "DeviceControl - Win32 Debug"',
                    '# ADD CPP /nologo /W3 /D "WIN32" /D "_DEBUG" /I "..\\include" /c',
                    "!ENDIF",
                    "",
                    "# Begin Target",
                    '# Name "DeviceControl - Win32 Debug"',
                    "",
                    '# Begin Group "Source Files"',
                    "",
                    "# Begin Source File",
                    "SOURCE=..\\src\\device_control.c",
                    "# End Source File",
                    "",
                    "# End Group",
                    "",
                    '# Begin Group "Header Files"',
                    "",
                    "# Begin Source File",
                    "SOURCE=..\\include\\device_control.h",
                    "# End Source File",
                    "",
                    "# End Group",
                    "",
                    "# End Target",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (self.base / "src" / "device_control.c").write_text(
            '#include "device_control.h"\nint DeviceControl_Update(int value)\n{\n    return value + 1;\n}\n',
            encoding="utf-8",
        )
        (self.base / "include" / "device_control.h").write_text(
            "#ifndef DEVICE_CONTROL_H\n#define DEVICE_CONTROL_H\nint DeviceControl_Update(int value);\n#endif\n",
            encoding="utf-8",
        )

    def test_parse_tier_entries_accepts_reference_scale_and_rejects_invalid_values(self):
        self.assertEqual((7000, 16000, 31000), generator.parse_tier_entries("7000,16000,31000"))
        with self.assertRaisesRegex(ValueError, "positive integer"):
            generator.parse_tier_entries("7000,0,31000")

    def test_tiers_flag_without_value_uses_reference_scale(self):
        args = generator.build_parser().parse_args(["--tiers"])

        self.assertEqual("7000,16000,31000", args.tiers)

    def test_empty_tiers_value_is_rejected_instead_of_using_default_entries(self):
        with mock.patch.dict("os.environ", {"UNIT_TEST_RUNNER_LARGE_ENTRIES": "1"}):
            with self.assertRaisesRegex(ValueError, "at least one positive integer"):
                generator.main(
                    [
                        "--base",
                        str(self.base),
                        "--root",
                        str(self.perf_root),
                        "--tiers",
                        "",
                    ]
                )

    def test_safe_output_requires_perf_root_and_expected_prefix(self):
        valid = self.perf_root / "unit-test-runner-large-8"
        generator.assert_safe_output(valid, self.perf_root)

        with self.assertRaisesRegex(ValueError, "outside performance root"):
            generator.assert_safe_output(self.temp / "unit-test-runner-large-8", self.perf_root)
        with self.assertRaisesRegex(ValueError, "expected prefix"):
            generator.assert_safe_output(self.perf_root / "unexpected", self.perf_root)

    def test_generate_fixture_copies_base_adds_sources_and_writes_manifest(self):
        output = self.perf_root / "unit-test-runner-large-4"

        base_source_before = (self.base / "src" / "device_control.c").read_text(encoding="utf-8")

        summary = generator.generate_fixture(
            base_root=self.base,
            output_root=output,
            source_entries=4,
            perf_root=self.perf_root,
        )

        self.assertEqual(4, summary["source_entries_in_target_project"])
        self.assertEqual(3, summary["generated_source_files"])
        self.assertEqual("DeviceControl_Update", summary["target"]["function"])
        self.assertEqual(
            base_source_before,
            (self.base / "src" / "device_control.c").read_text(encoding="utf-8"),
        )

        dsp = (output / "DeviceControl" / "DeviceControl.dsp").read_text(encoding="utf-8")
        self.assertIn(r"SOURCE=..\src\generated\large_module_00000.c", dsp)
        self.assertIn(r"SOURCE=..\src\generated\large_module_00002.c", dsp)
        self.assertEqual(3, len(list((output / "src" / "generated").glob("*.c"))))

        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(1, manifest["schema_version"])
        self.assertEqual("Product.dsw", manifest["workspace_file"])
        self.assertEqual("src/device_control.c", manifest["target"]["source"])
        self.assertEqual(4, manifest["source_entries_in_target_project"])
        self.assertEqual(
            sum(1 for path in output.rglob("*") if path.is_file()),
            manifest["total_files_on_disk"],
        )

    def test_generate_fixture_preserves_cp932_dsp_encoding(self):
        dsp_path = self.base / "DeviceControl" / "DeviceControl.dsp"
        dsp_text = dsp_path.read_text(encoding="utf-8").replace(
            '# Begin Group "Source Files"',
            '# Begin Group "Source Files"\n# 日本語のVC6プロジェクト',
        )
        dsp_path.write_bytes(dsp_text.encode("cp932"))
        output = self.perf_root / "unit-test-runner-large-2"

        generator.generate_fixture(self.base, output, 2, self.perf_root)

        output_bytes = (output / "DeviceControl" / "DeviceControl.dsp").read_bytes()
        output_text = output_bytes.decode("cp932")
        self.assertIn("# 日本語のVC6プロジェクト", output_text)
        self.assertIn(r"SOURCE=..\src\generated\large_module_00000.c", output_text)

    def test_regeneration_removes_stale_files_and_rebuilds_requested_scale(self):
        output = self.perf_root / "unit-test-runner-large-4"
        generator.generate_fixture(self.base, output, 4, self.perf_root)
        stale = output / "stale.tmp"
        stale.write_text("stale", encoding="utf-8")

        summary = generator.generate_fixture(self.base, output, 2, self.perf_root)

        self.assertFalse(stale.exists())
        self.assertEqual(1, summary["generated_source_files"])
        self.assertEqual(1, len(list((output / "src" / "generated").glob("*.c"))))


if __name__ == "__main__":
    unittest.main()
