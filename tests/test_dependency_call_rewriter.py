import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.dependency_rewriter import rewrite_dependency_calls


class DependencyCallRewriterTests(unittest.TestCase):
    def test_rewrites_only_exact_direct_call_sites_and_adds_dispatch_header(self):
        source = (
            '#include "deps.h"\n'
            "int Target(int value)\n"
            "{\n"
            "    int first = Helper(value);\n"
            "    int (*callback)(int) = Helper;\n"
            "    return first + callback(value);\n"
            "}\n"
        )
        dispatches = [
            {
                "callee": "Helper",
                "dispatcher_name": "Utr_Dep_Helper",
                "rewrite_sites": [
                    {"call_id": "CALL_001", "start": {"line": 4, "column": 17}, "end": {"line": 4, "column": 23}}
                ],
            }
        ]

        rewritten, issues = rewrite_dependency_calls(source, dispatches)

        self.assertIn('#include "utr_dependency_dispatch.h"', rewritten)
        self.assertIn("int first = Utr_Dep_Helper(value);", rewritten)
        self.assertIn("int (*callback)(int) = Helper;", rewritten)
        self.assertIn("return first + callback(value);", rewritten)
        self.assertEqual([], issues)

    def test_mismatched_source_position_is_not_rewritten(self):
        source = "int Target(void) { return Other(); }\n"
        rewritten, issues = rewrite_dependency_calls(
            source,
            [
                {
                    "callee": "Helper",
                    "dispatcher_name": "Utr_Dep_Helper",
                    "rewrite_sites": [
                        {"call_id": "CALL_001", "start": {"line": 1, "column": 27}, "end": {"line": 1, "column": 33}}
                    ],
                }
            ],
        )

        self.assertEqual(source, rewritten)
        self.assertEqual(1, len(issues))
        self.assertIn("CALL_001", issues[0])


if __name__ == "__main__":
    unittest.main()
