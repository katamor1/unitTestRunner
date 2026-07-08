import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_workspace_generator import generate_build_workspace
from unit_test_runner.suite.manager import register_workspace


class Vc6DebugWorkspaceWriterTests(unittest.TestCase):
    def _workspace_reports(self, temp_dir):
        project = Path(temp_dir) / "project"
        source = project / "src" / "shared.c"
        source.parent.mkdir(parents=True)
        source.write_text("int Shared(void) { return 1; }\n", encoding="ascii")
        out_dir = Path(temp_dir) / "Shared"
        build_context = {
            "workspace_root": str(project),
            "include_dirs": [],
            "defines": ["WIN32", "_DEBUG"],
            "compiler_options": ["/nologo", "/W3", "/Od", "/ZI"],
        }
        source_digest = {
            "source": {"path": str(source)},
            "preprocessor": {"includes": []},
        }
        harness_root = out_dir
        (harness_root / "generated" / "include").mkdir(parents=True)
        (harness_root / "generated" / "harness").mkdir(parents=True)
        (harness_root / "generated" / "tests").mkdir(parents=True)
        (harness_root / "generated" / "include" / "utr_assert.h").write_text("void Utr_ResetFailureCount(void);\n", encoding="ascii")
        (harness_root / "generated" / "harness" / "utr_assert.c").write_text("void Utr_ResetFailureCount(void) {}\n", encoding="ascii")
        (harness_root / "generated" / "tests" / "test_Shared.c").write_text("void Test_Shared(void) {}\n", encoding="ascii")
        harness_report = {
            "function": {"name": "Shared"},
            "source": {"path": str(source)},
            "output_root": str(harness_root),
            "generated_files": [
                {"path": "generated/include/utr_assert.h", "file_kind": "assert_header"},
                {"path": "generated/harness/utr_assert.c", "file_kind": "assert_source"},
                {"path": "generated/tests/test_Shared.c", "file_kind": "test_source"},
            ],
        }
        return out_dir, build_context, source_digest, harness_report

    def test_build_workspace_generates_one_vc6_dsp_for_function_workflow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir, build_context, source_digest, harness_report = self._workspace_reports(temp_dir)

            report, _probe = generate_build_workspace(
                build_context,
                source_digest,
                harness_report,
                out_dir,
                run_probe=False,
                dry_run=True,
            )

            dsp_path = out_dir / "build" / "UTR_Shared.dsp"
            dsp_text = dsp_path.read_text(encoding="cp932")
            generated = {item.workspace_path.as_posix(): item.file_kind for item in report.generated_build_files}
            self.assertTrue(dsp_path.exists())
            self.assertEqual("vc6_debug_dsp", generated["build/UTR_Shared.dsp"])
            self.assertIn('Project File - Name="UTR_Shared"', dsp_text)
            self.assertIn('SOURCE=..\\extracted\\src\\shared.c', dsp_text)
            self.assertIn('/out:"..\\bin\\utr_probe.exe"', dsp_text)

    def test_suite_register_generates_dsw_referencing_entry_dsp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir, build_context, source_digest, harness_report = self._workspace_reports(temp_dir)
            generate_build_workspace(build_context, source_digest, harness_report, out_dir, run_probe=False, dry_run=True)
            reports = out_dir / "reports"
            dossier = {
                "schema_version": "0.1",
                "target": {"function": "Shared", "source": "src/shared.c", "project": "Shared", "configuration": "Win32 Debug"},
                "function": {"name": "Shared", "source_path": "src/shared.c"},
            }
            (reports / "function_dossier.json").write_text(json.dumps(dossier, indent=2) + "\n", encoding="utf-8")
            suite_path = Path(temp_dir) / "suites" / "default" / "suite_manifest.json"

            register_workspace(suite_path, out_dir, tags=["debug"])

            dsw_path = suite_path.parent / "vc6_debug_suite.dsw"
            dsw_text = dsw_path.read_text(encoding="cp932")
            self.assertTrue(dsw_path.exists())
            self.assertIn('Project: "UTR_Shared"=', dsw_text)
            self.assertIn('UTR_Shared.dsp', dsw_text)


if __name__ == "__main__":
    unittest.main()
