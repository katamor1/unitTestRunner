import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_practical_project"
SOURCE = FIXTURE_ROOT / "src" / "device_control.c"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.c_analyzer import list_functions
from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest


def run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


class PracticalVc6FixtureTests(unittest.TestCase):
    def setUp(self):
        self.digest = build_source_digest(
            SOURCE,
            {
                "workspace_root": str(FIXTURE_ROOT),
                "defines": ["WIN32", "_DEBUG", "DEVICE_CONTROL_FEATURE=1"],
                "include_dirs": [{"absolute": str(FIXTURE_ROOT / "include")}],
            },
        )
        self.location = locate_function(self.digest, "DeviceControl_Update")
        self.signature = extract_signature(self.digest, self.location)
        self.global_access = analyze_global_access(self.digest, self.location, self.signature)
        self.call_report = analyze_calls(self.digest, self.location, self.signature, self.global_access)

    def test_fixture_contains_practical_call_tree_functions(self):
        functions = {item["name"]: item for item in list_functions(SOURCE)}

        self.assertIn("DeviceControl_RunScheduler", functions)
        self.assertIn("DeviceControl_Update", functions)
        self.assertIn("ValidateInput", functions)
        self.assertIn("NormalizeSample", functions)
        self.assertIn("ComputeDuty", functions)
        self.assertIn("ApplyOutput", functions)
        self.assertIn("PushHistory", functions)
        self.assertTrue(functions["ValidateInput"]["static"])
        self.assertTrue(functions["NormalizeSample"]["static"])

    def test_source_digest_exposes_includes_and_macro_cases(self):
        include_targets = {item.target for item in self.digest.includes}
        macros = {item.name: item for item in self.digest.macros}

        self.assertIn("device_control.h", include_targets)
        self.assertIn("platform_io.h", include_targets)
        self.assertIn("DEVICE_HISTORY_SIZE", macros)
        self.assertIn("ACTIVE_DEVICE", macros)
        self.assertIn("RAW_SAMPLE", macros)
        self.assertIn("LIMIT_DUTY", macros)
        self.assertTrue(macros["RAW_SAMPLE"].is_function_like)
        self.assertTrue(macros["LIMIT_DUTY"].is_function_like)

    def test_signature_covers_struct_pointers_output_and_callback(self):
        payload = self.signature.to_dict()
        parameters = {item["name"]: item for item in payload["function"]["parameters"]}

        self.assertEqual("int", payload["function"]["return_type"]["base_type"])
        self.assertGreaterEqual(parameters["input"]["type"]["pointer_level"], 1)
        self.assertGreaterEqual(parameters["out"]["type"]["pointer_level"], 1)
        self.assertEqual("output_candidate", parameters["out"]["direction_hint"])
        self.assertTrue(parameters["callback"]["type"]["is_function_pointer"])

    def test_global_access_covers_static_extern_members_and_arrays(self):
        declarations = {item.name: item for item in self.global_access.file_scope_declarations}
        access_paths = {item.access_path for item in self.global_access.global_accesses}

        self.assertEqual("file_static", declarations["s_state"].scope)
        self.assertEqual("file_static", declarations["s_history"].scope)
        self.assertEqual("file_static", declarations["s_history_pos"].scope)
        self.assertEqual("file_static", declarations["s_fault_hook"].scope)
        self.assertEqual("extern", declarations["g_system_tick"].scope)
        self.assertEqual("extern", declarations["g_active_device"].scope)
        self.assertEqual("extern", declarations["g_device_table"].scope)
        self.assertEqual("extern", declarations["g_calibration"].scope)
        self.assertIn("s_state.filtered", access_paths)
        self.assertIn("s_history[s_history_pos]", access_paths)
        self.assertIn("g_device_table[ACTIVE_DEVICE]", access_paths)
        self.assertIn("g_active_device", access_paths)

    def test_call_report_classifies_static_external_function_pointer_and_macros(self):
        calls = {item.name: item for item in self.call_report.calls}
        stub_names = {item.name for item in self.call_report.stub_candidates}

        self.assertEqual("same_file_static_function", calls["ValidateInput"].target_kind)
        self.assertEqual("same_file_static_function", calls["NormalizeSample"].target_kind)
        self.assertEqual("same_file_static_function", calls["ComputeDuty"].target_kind)
        self.assertEqual("same_file_static_function", calls["ApplyOutput"].target_kind)
        self.assertEqual("same_file_static_function", calls["PushHistory"].target_kind)
        self.assertEqual("external_function", calls["Platform_ReadAdc"].target_kind)
        self.assertEqual("external_function", calls["Platform_WritePwm"].target_kind)
        self.assertEqual("external_function", calls["Audit_Record"].target_kind)
        self.assertEqual("function_pointer", calls["callback"].target_kind)
        self.assertEqual("macro_like", calls["RAW_SAMPLE"].target_kind)
        self.assertEqual("macro_like", calls["LIMIT_DUTY"].target_kind)
        self.assertIn("Platform_ReadAdc", stub_names)
        self.assertIn("Platform_WritePwm", stub_names)
        self.assertIn("Audit_Record", stub_names)

    def test_cli_smoke_generates_dossier_and_build_probe_for_practical_fixture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            projects_json = temp / "projects.json"

            run_cli(
                "discover-projects",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--out",
                str(projects_json),
            )
            projects = json.loads(projects_json.read_text(encoding="utf-8"))
            self.assertEqual("Product", projects["workspace_name"])

            mapped = run_cli(
                "map-source",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/device_control.c",
            )
            self.assertGreaterEqual(len(json.loads(mapped.stdout)["matches"]), 2)

            out_dir = temp / "DeviceControl_Update"
            run_cli(
                "analyze-function",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/device_control.c",
                "--function",
                "DeviceControl_Update",
                "--configuration",
                "DeviceControl - Win32 Debug",
                "--project",
                "DeviceControl",
                "--out",
                str(out_dir),
            )

            dossier_path = out_dir / "reports" / "function_dossier.json"
            self.assertTrue(dossier_path.exists())
            dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
            self.assertEqual("DeviceControl_Update", dossier["target"]["function"])
            self.assertEqual("DeviceControl - Win32 Debug", dossier["target"]["configuration"])
            self.assertTrue((out_dir / "reports" / "function_dossier.md").exists())
            self.assertTrue((out_dir / "reports" / "call_report.md").exists())
            self.assertTrue((out_dir / "reports" / "global_access_report.md").exists())

            probe = run_cli("build-probe", "--dossier", str(dossier_path), "--dry-run")
            probe_result = json.loads(probe.stdout)
            self.assertTrue(probe_result["dry_run"])
            self.assertTrue((out_dir / "generated" / "build" / "Makefile").exists())
            self.assertTrue((out_dir / "reports" / "build_probe.log").exists())


if __name__ == "__main__":
    unittest.main()
