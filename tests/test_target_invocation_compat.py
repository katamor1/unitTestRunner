import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.harness.target_invocation_compat import _write_target_invocation


class TargetInvocationCompatTests(unittest.TestCase):
    def test_target_invocation_header_uses_opaque_pointer_without_product_includes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "shared" / "shared.c"
            source.parent.mkdir(parents=True)
            source.write_text('#include "shared2.h"\nint Shared3(gbl_input *prm) { return 0; }\n', encoding="ascii")
            generated_files = []
            warnings = []

            _write_target_invocation(
                workspace,
                {
                    "source": {"path": str(source)},
                    "function": {
                        "name": "Shared3",
                        "return_type": {"raw": "int"},
                        "parameters": [
                            {
                                "name": "prm",
                                "type_raw": "gbl_input *",
                                "base_type": "gbl_input",
                                "pointer_level": 1,
                            }
                        ],
                    },
                },
                generated_files,
                warnings,
                True,
            )

            header = (workspace / "generated" / "harness" / "target_invocation.h").read_text(encoding="cp932")
            source_text = (workspace / "generated" / "harness" / "target_invocation.c").read_text(encoding="cp932")
            self.assertNotIn('#include "shared2.h"', header)
            self.assertIn("int Target_Invoke_Shared3(void * prm);", header)
            self.assertIn('#include "shared2.h"', source_text)
            self.assertIn("int Shared3(", source_text)
            self.assertIn("gbl_input *", source_text)
            self.assertIn("return Shared3((gbl_input *)prm);", source_text)


if __name__ == "__main__":
    unittest.main()
