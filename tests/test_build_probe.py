import json
import subprocess
import unittest
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.build_probe import parse_build_log
from unit_test_runner.build_probe import build_probe


class BuildProbeTests(unittest.TestCase):
    def test_parse_build_log_extracts_actionable_diagnostics(self):
        diagnostics = parse_build_log(
            """
control.c(4) : fatal error C1083: Cannot open include file: 'missing.h': No such file or directory
cl : Command line warning D4024 : unrecognized source file type 'stdafx.h', object file assumed
LINK : fatal error LNK2001: unresolved external symbol _ReadSensor
LINK : fatal error LNK2019: unresolved external symbol _WriteOutput referenced in function _Control_Update
"""
        )

        self.assertEqual(["missing.h"], diagnostics["missing_includes"])
        self.assertTrue(diagnostics["pch_warnings"])
        self.assertEqual(["ReadSensor", "WriteOutput"], diagnostics["unresolved_symbols"])

    def test_legacy_dossier_probe_uses_vcvars_without_requiring_vc6_bin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            (root / "extracted" / "src").mkdir(parents=True)
            (root / "extracted" / "src" / "control.c").write_text("int Target(void) { return 0; }\n", encoding="ascii")
            dossier = {
                "target": {"source": "src/control.c", "function": "Target"},
                "build_context": {"include_dirs": [], "defines": []},
            }
            dossier_path = reports / "function_dossier.json"
            dossier_path.write_text(json.dumps(dossier), encoding="utf-8")
            vcvars = root / "vcvars32.bat"
            vcvars.write_text("@echo off\n", encoding="ascii")

            def fake_run(*args, **kwargs):
                return subprocess.CompletedProcess(args[0], 0, stdout="compiled\n")

            with mock.patch("unit_test_runner.build_probe.subprocess.run", side_effect=fake_run) as run:
                payload = build_probe(dossier_path, vcvars=vcvars, dry_run=False)

            self.assertFalse(payload["dry_run"])
            self.assertEqual(0, payload["returncode"])
            self.assertIn(str(vcvars), payload["command"])
            self.assertEqual(1, run.call_count)


if __name__ == "__main__":
    unittest.main()
