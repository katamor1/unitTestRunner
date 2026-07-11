import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.harness.type_bridge import classify_bridge_type


class TypeBridgeTests(unittest.TestCase):
    def test_classifies_scalar_and_complete_aggregate_typedefs_from_definitions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            header = Path(temp_dir) / "types.h"
            header.write_text(
                "typedef unsigned long DWORD;\n"
                "typedef struct InputTag { int value; } gbl_input;\n",
                encoding="ascii",
            )

            scalar = classify_bridge_type("DWORD", [header])
            aggregate = classify_bridge_type("gbl_input", [header])

            self.assertEqual("scalar", scalar.kind)
            self.assertEqual("aggregate", aggregate.kind)
            self.assertEqual((header,), aggregate.defining_headers)

    def test_classifies_pointer_without_requiring_a_complete_pointee(self):
        result = classify_bridge_type("UnknownTag *", [])

        self.assertEqual("pointer", result.kind)
        self.assertEqual("UnknownTag *", result.type_text)

    def test_keeps_unknown_value_type_unresolved_instead_of_mapping_to_int(self):
        result = classify_bridge_type("UnknownValue", [])

        self.assertEqual("unresolved", result.kind)
        self.assertNotEqual("int", result.type_text)


if __name__ == "__main__":
    unittest.main()
