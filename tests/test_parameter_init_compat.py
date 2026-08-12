import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.harness.harness_skeleton_generator import _render_test_function


class ParameterInitializationTests(unittest.TestCase):
    def test_reviewed_null_pointer_assignment_remains_null(self):
        text = _render_test_function(
            "Test_TC_Shared3_001",
            {
                "input_assignments": [
                    {
                        "target_name": "prm",
                        "value_expression": "NULL",
                        "value_kind": "null_pointer",
                        "review_required": False,
                    }
                ],
                "stub_setups": [],
                "expected_observations": [
                    {
                        "observation_kind": "return_value",
                        "expected_expression": "0",
                        "review_required": False,
                    }
                ],
            },
            [
                {
                    "name": "prm",
                    "type_raw": "gbl_input *",
                    "base_type": "gbl_input",
                    "pointer_level": 1,
                }
            ],
            "int",
            "Shared3",
            [],
        )

        self.assertIn("static double prm_storage[512];", text)
        self.assertIn("void *prm;", text)
        self.assertNotIn("memset(", text)
        self.assertIn("prm = NULL;", text)
        self.assertNotIn("prm = (void *)prm_storage;", text)
        self.assertNotIn("gbl_input prm_storage", text)


if __name__ == "__main__":
    unittest.main()
