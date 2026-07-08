import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.harness.state_setup_reflector import reflect_state_setups


class StateSetupReflectorTests(unittest.TestCase):
    def test_reflects_direct_and_fixture_state_setups_into_test_function(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            test_dir = workspace / "generated" / "tests"
            test_dir.mkdir(parents=True)
            source = test_dir / "test_Shared3.c"
            source.write_text(
                "/* generated test skeleton: review required */\n"
                "#include \"utr_assert.h\"\n"
                "#include \"utr_runner.h\"\n"
                "#include \"target_invocation.h\"\n"
                "\n"
                "extern int g_count;\n"
                "\n"
                "void Test_TC_Shared3_001(void)\n"
                "{\n"
                "    int actual_return;\n"
                "\n"
                "    actual_return = Target_Invoke_Shared3();\n"
                "    UTR_ASSERT_EQ_INT(TBD_EXPECTED_RETURN_INT, actual_return);\n"
                "}\n",
                encoding="cp932",
            )
            design = {
                "function": {"name": "Shared3"},
                "test_cases": [
                    {
                        "test_case_id": "TC_Shared3_001",
                        "state_setups": [
                            {
                                "variable_name": "g_com",
                                "scope": "extern",
                                "value_expression": "&fixture_g_com",
                                "setup_method_hint": "fixture_pointer",
                                "fixture_includes": ["../../extracted/shared/shared2.h"],
                                "fixture_declarations": ["static gbl1 fixture_gbl1", "static gbl_com fixture_g_com"],
                                "setup_statements": ["fixture_g_com.ptr = &fixture_gbl1", "fixture_gbl1.test = 0"],
                            },
                            {
                                "variable_name": "g_count",
                                "scope": "file",
                                "value_expression": "14",
                                "setup_method_hint": "direct_assignment",
                            },
                        ],
                    }
                ],
            }

            changed = reflect_state_setups(workspace, design, "Shared3")

            self.assertEqual([source], changed)
            text = source.read_text(encoding="cp932")
            self.assertIn('#include "../../extracted/shared/shared2.h"', text)
            self.assertIn("    static gbl1 fixture_gbl1;", text)
            self.assertIn("    static gbl_com fixture_g_com;", text)
            self.assertIn("    /* state_setups auto reflection */", text)
            self.assertIn("    fixture_g_com.ptr = &fixture_gbl1;", text)
            self.assertIn("    fixture_gbl1.test = 0;", text)
            self.assertIn("    g_com = &fixture_g_com;", text)
            self.assertIn("    g_count = 14;", text)
            self.assertLess(text.index("fixture_g_com.ptr"), text.index("Target_Invoke_Shared3"))


if __name__ == "__main__":
    unittest.main()
