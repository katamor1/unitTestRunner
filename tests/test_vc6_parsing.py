import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.vc6 import discover_workspace, map_source_to_projects


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "vc6_project"


class Vc6ParsingTests(unittest.TestCase):
    def test_discover_workspace_extracts_projects_and_build_context(self):
        workspace = discover_workspace(FIXTURE_ROOT, FIXTURE_ROOT / "Product.dsw")

        self.assertEqual("Product", workspace["workspace_name"])
        self.assertEqual(["Control", "FactoryTest"], [p["project_name"] for p in workspace["projects"]])

        control = workspace["projects"][0]
        self.assertEqual("Control/Control.dsp", control["dsp"])
        self.assertEqual(["Utils"], control["dependencies"])
        self.assertIn("src/control.c", control["sources"])
        self.assertIn("include/control.h", control["headers"])

        debug = control["configurations"]["Win32 Debug"]
        self.assertEqual("Control - Win32 Debug", debug["full_name"])
        self.assertIn("WIN32", debug["defines"])
        self.assertIn("_DEBUG", debug["defines"])
        self.assertIn("CONTROL_FEATURE=1", debug["defines"])
        self.assertIn("include", debug["include_dirs"])
        self.assertIn("$(LEGACY_SDK)/include", debug["include_dirs"])
        self.assertEqual(["forced.h"], debug["forced_includes"])
        self.assertEqual({"enabled": True, "header": "stdafx.h", "mode": "use"}, debug["precompiled_header"])
        self.assertIn("LEGACY_SDK", debug["unresolved_macros"])

        release = control["configurations"]["Win32 Release"]
        self.assertIn("NDEBUG", release["defines"])
        self.assertEqual({"enabled": True, "header": "stdafx.h", "mode": "create"}, release["precompiled_header"])

    def test_map_source_keeps_multiple_project_and_configuration_candidates(self):
        matches = map_source_to_projects(FIXTURE_ROOT, FIXTURE_ROOT / "Product.dsw", "src/control.c")

        keys = {(m["project_name"], m["configuration"]) for m in matches}
        self.assertEqual(
            {
                ("Control", "Win32 Debug"),
                ("Control", "Win32 Release"),
                ("FactoryTest", "Win32 Debug"),
            },
            keys,
        )


if __name__ == "__main__":
    unittest.main()
