import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.build_probe import parse_build_log


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


if __name__ == "__main__":
    unittest.main()
