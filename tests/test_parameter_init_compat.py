import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.harness.parameter_init_compat import _render_test_function


class ParameterInitCompatTests(unittest.TestCase):
    def test_null_pointer_candidate_uses_valid_storage_by_default(self):
        text = _render_test_function(
            "Test_TC_Shared3_001",
            {
                "input_assignments": [
                    {
                        "target_name": "prm",
                        "value_expression": "NULL",
                        "value_kind": "null_pointer",
                        "review_required": True,
                    }
                ],
                "stub_setups": [],
                "expected_observations": [],
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

        self.assertIn("gbl_input prm_storage = {0};", text)
        self.assertIn("prm = &prm_storage;", text)
        self.assertIn("NULL candidate for prm is not used", text)
        self.assertNotIn("prm = NULL;", text)


if __name__ == "__main__":
    unittest.main()
