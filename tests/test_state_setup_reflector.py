import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.harness.state_setup_reflector import reflect_state_setups


def write_invocation_files(workspace: Path) -> tuple[Path, Path]:
    harness_dir = workspace / "generated" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    header = harness_dir / "target_invocation.h"
    source = harness_dir / "target_invocation.c"
    header.write_text(
        "#ifndef TARGET_INVOCATION_H_\n"
        "#define TARGET_INVOCATION_H_\n"
        "int Target_Invoke_Shared3(void);\n"
        "#endif\n",
        encoding="cp932",
    )
    source.write_text(
        '#include "target_invocation.h"\n'
        '#include "../../extracted/shared/shared2.h"\n'
        "int Shared3(void);\n"
        "int Target_Invoke_Shared3(void) { return Shared3(); }\n",
        encoding="cp932",
    )
    return header, source


class StateSetupReflectorTests(unittest.TestCase):
    def test_reflects_direct_setups_in_test_and_fixture_setups_in_harness_helper(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            test_dir = workspace / "generated" / "tests"
            test_dir.mkdir(parents=True)
            header, helper_source = write_invocation_files(workspace)
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

            self.assertIn(source.resolve(), changed)
            self.assertIn(header.resolve(), changed)
            self.assertIn(helper_source.resolve(), changed)
            test_text = source.read_text(encoding="cp932")
            helper_text = helper_source.read_text(encoding="cp932")
            header_text = header.read_text(encoding="cp932")
            self.assertNotIn('#include "../../extracted/shared/shared2.h"', test_text)
            self.assertNotIn("static gbl1 fixture_gbl1", test_text)
            self.assertIn("    Utr_StateSetup_TC_Shared3_001();", test_text)
            self.assertIn("    g_count = 14;", test_text)
            self.assertLess(test_text.index("Utr_StateSetup_TC_Shared3_001"), test_text.index("Target_Invoke_Shared3"))
            self.assertIn("void Utr_StateSetup_TC_Shared3_001(void);", header_text)
            self.assertIn("void Utr_StateSetup_TC_Shared3_001(void)", helper_text)
            self.assertIn("    static gbl1 fixture_gbl1;", helper_text)
            self.assertIn("    static gbl_com fixture_g_com;", helper_text)
            self.assertIn("    fixture_g_com.ptr = &fixture_gbl1;", helper_text)
            self.assertIn("    fixture_gbl1.test = 0;", helper_text)
            self.assertIn("    g_com = &fixture_g_com;", helper_text)

    def test_infers_simple_pointer_fixture_from_extracted_source_and_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "generated" / "tests").mkdir(parents=True)
            (workspace / "reports").mkdir(parents=True)
            header, helper_source = write_invocation_files(workspace)
            extracted = workspace / "extracted" / "shared"
            extracted.mkdir(parents=True)
            (extracted / "shared.c").write_text(
                '#include "shared2.h"\n'
                "int g_count;\n"
                "int Shared3(void)\n"
                "{\n"
                "    g_com->ptr->test = g_count;\n"
                "    g_count++;\n"
                "    return g_count;\n"
                "}\n",
                encoding="cp932",
            )
            (extracted / "shared2.h").write_text(
                "typedef struct _gbl1 { int test; } gbl1;\n"
                "typedef struct _gbl_com { gbl1* ptr; } gbl_com;\n"
                "EXTERN gbl_com *g_com;\n",
                encoding="cp932",
            )
            test_source = workspace / "generated" / "tests" / "test_Shared3.c"
            test_source.write_text(
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
                "source": {"path": "shared/shared.c"},
                "function": {"name": "Shared3"},
                "test_cases": [{"test_case_id": "TC_Shared3_001", "state_setups": []}],
            }
            (workspace / "reports" / "test_case_design.json").write_text(json.dumps(design, indent=2), encoding="utf-8")

            design_path = workspace / "reports" / "test_case_design.json"
            before = design_path.read_bytes()

            reflect_state_setups(workspace, design, "Shared3")

            test_text = test_source.read_text(encoding="cp932")
            helper_text = helper_source.read_text(encoding="cp932")
            self.assertNotIn('#include "../../extracted/shared/shared2.h"', test_text)
            self.assertIn("    Utr_StateSetup_TC_Shared3_001();", test_text)
            self.assertIn("    static gbl1 fixture_g_com_ptr;", helper_text)
            self.assertIn("    static gbl_com fixture_g_com;", helper_text)
            self.assertIn("    fixture_g_com.ptr = &fixture_g_com_ptr;", helper_text)
            self.assertIn("    g_com = &fixture_g_com;", helper_text)
            self.assertEqual(before, design_path.read_bytes())
            self.assertEqual([], design["test_cases"][0]["state_setups"])

    def test_removes_stale_product_header_include_from_test_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            test_dir = workspace / "generated" / "tests"
            test_dir.mkdir(parents=True)
            write_invocation_files(workspace)
            source = test_dir / "test_Shared3.c"
            source.write_text(
                '#include "utr_assert.h"\n'
                '#include "target_invocation.h"\n'
                '#include "../../extracted/shared/shared2.h"\n'
                "\n"
                "void Test_TC_Shared3_001(void)\n"
                "{\n"
                "    int actual_return;\n"
                "    actual_return = Target_Invoke_Shared3();\n"
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
                                "value_expression": "&fixture_g_com",
                                "fixture_includes": ["../../extracted/shared/shared2.h"],
                                "fixture_declarations": ["static gbl1 fixture_g_com_ptr", "static gbl_com fixture_g_com"],
                                "setup_statements": ["fixture_g_com.ptr = &fixture_g_com_ptr"],
                            }
                        ],
                    }
                ],
            }

            reflect_state_setups(workspace, design, "Shared3")

            text = source.read_text(encoding="cp932")
            self.assertIn('#include "target_invocation.h"', text)
            self.assertNotIn('#include "../../extracted/shared/shared2.h"', text)
            self.assertIn("    Utr_StateSetup_TC_Shared3_001();", text)


if __name__ == "__main__":
    unittest.main()
