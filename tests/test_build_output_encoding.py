import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_workspace_generator import generate_build_workspace
from unit_test_runner.build_probe import build_probe
from unit_test_runner.dossier import analyze_function_workflow
from unit_test_runner.encoding import decode_bytes_auto


class BuildOutputEncodingTests(unittest.TestCase):
    def prepare_analysis(self, temp_dir):
        out_dir = Path(temp_dir) / "Control_Update"
        analyze_function_workflow(
            VC6_FIXTURE_ROOT,
            VC6_FIXTURE_ROOT / "Product.dsw",
            "src/control.c",
            "Control_Update",
            "Win32 Debug",
            out_dir,
            "Control",
        )
        reports = out_dir / "reports"
        return out_dir, {
            "build_context": json.loads((reports / "build_context.json").read_text(encoding="utf-8")),
            "source_digest": json.loads((reports / "source_digest.json").read_text(encoding="utf-8")),
            "harness_report": json.loads((reports / "harness_skeleton_report.json").read_text(encoding="utf-8")),
        }

    def test_decode_bytes_auto_decodes_cp932_build_text_without_replacement(self):
        text = "control.c(4) : fatal error C1083: Cannot open include file: '設定.h': No such file or directory\n"

        decoded = decode_bytes_auto(text.encode("cp932"))

        self.assertIn("設定.h", decoded)
        self.assertNotIn("\ufffd", decoded)

    def test_workspace_build_probe_decodes_cp932_redirected_build_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir, reports = self.prepare_analysis(temp_dir)
            diagnostic_log = "control.c(4) : fatal error C1083: Cannot open include file: '設定.h': No such file or directory\n"

            def fake_run(*args, **kwargs):
                build_dir = Path(kwargs["cwd"])
                (build_dir.parent / "logs" / "build.log").write_bytes(diagnostic_log.encode("cp932"))
                return subprocess.CompletedProcess(args[0], 2, stdout=b"")

            with mock.patch("unit_test_runner.build.build_workspace_generator.shutil.which", return_value="tool.exe"):
                with mock.patch("unit_test_runner.build.build_workspace_generator.subprocess.run", side_effect=fake_run):
                    _report, probe = generate_build_workspace(
                        reports["build_context"],
                        reports["source_digest"],
                        reports["harness_report"],
                        out_dir,
                        run_probe=True,
                        dry_run=False,
                    )

            self.assertEqual("failed", probe.status)
            self.assertEqual(["設定.h"], [item.include_name for item in probe.missing_includes])
            report_payload = json.loads((out_dir / "reports" / "build_probe_report.json").read_text(encoding="utf-8"))
            self.assertIn("設定.h", report_payload["diagnostics"][0]["message"])
            self.assertNotIn("\ufffd", json.dumps(report_payload, ensure_ascii=False))

    def test_legacy_dossier_build_probe_decodes_cp932_stdout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            reports = workspace / "reports"
            source = workspace / "extracted" / "src" / "control.c"
            reports.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            source.write_text("int Control_Update(void) { return 0; }\n", encoding="utf-8")
            dossier = {
                "target": {"source": "src/control.c", "function": "Control_Update"},
                "build_context": {"include_dirs": [], "defines": []},
            }
            dossier_path = reports / "function_dossier.json"
            dossier_path.write_text(json.dumps(dossier), encoding="utf-8")
            diagnostic_log = "control.c(4) : fatal error C1083: Cannot open include file: '設定.h': No such file or directory\n"

            with mock.patch("unit_test_runner.build_probe.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(["build"], 2, stdout=diagnostic_log.encode("cp932"))
                payload = build_probe(dossier_path, vcvars="vcvars32.bat")

            self.assertEqual(2, payload["returncode"])
            self.assertEqual(["設定.h"], payload["diagnostics"]["missing_includes"])
            self.assertIn("設定.h", (reports / "build_probe.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
