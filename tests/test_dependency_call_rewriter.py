import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.dependency_rewriter import rewrite_dependency_calls


def _rewrite_site(source, token, call_id, occurrence=0):
    start = -1
    search_from = 0
    for _index in range(occurrence + 1):
        start = source.index(token, search_from)
        search_from = start + len(token)
    line = source.count("\n", 0, start) + 1
    line_start = source.rfind("\n", 0, start) + 1
    column = start - line_start + 1
    return {
        "call_id": call_id,
        "start": {"line": line, "column": column},
        "end": {"line": line, "column": column + len(token)},
    }


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
        self.assertEqual("CALL_001", issues[0].call_id)
        self.assertEqual("callee_mismatch", issues[0].code)
        self.assertEqual("error", issues[0].severity)

    def test_preserves_crlf_when_adding_dispatch_header(self):
        source = '#include "deps.h"\r\nint Target(void) { return Helper(); }\r\n'
        rewritten, issues = rewrite_dependency_calls(
            source,
            [
                {
                    "callee": "Helper",
                    "dispatcher_name": "Utr_Dep_Helper",
                    "rewrite_sites": [_rewrite_site(source, "Helper", "CALL_001")],
                }
            ],
        )

        self.assertEqual([], issues)
        self.assertIn("return Utr_Dep_Helper();", rewritten)
        self.assertEqual(1, rewritten.count('#include "utr_dependency_dispatch.h"'))
        self.assertNotIn("\n", rewritten.replace("\r\n", ""))

    def test_applies_two_same_line_edits_regardless_of_site_order(self):
        source = "int Target(void) { return First() + Second(); }\n"
        rewritten, issues = rewrite_dependency_calls(
            source,
            [
                {
                    "callee": "Second",
                    "dispatcher_name": "Utr_Dep_Second",
                    "rewrite_sites": [_rewrite_site(source, "Second", "CALL_002")],
                },
                {
                    "callee": "First",
                    "dispatcher_name": "Utr_Dep_First",
                    "rewrite_sites": [_rewrite_site(source, "First", "CALL_001")],
                },
            ],
        )

        self.assertEqual([], issues)
        self.assertIn("return Utr_Dep_First() + Utr_Dep_Second();", rewritten)

    def test_does_not_duplicate_existing_dispatch_header(self):
        source = (
            '#include "utr_dependency_dispatch.h"\n'
            "int Target(void) { return Helper(); }\n"
        )
        rewritten, issues = rewrite_dependency_calls(
            source,
            [
                {
                    "callee": "Helper",
                    "dispatcher_name": "Utr_Dep_Helper",
                    "rewrite_sites": [_rewrite_site(source, "Helper", "CALL_001")],
                }
            ],
        )

        self.assertEqual([], issues)
        self.assertEqual(1, rewritten.count('#include "utr_dependency_dispatch.h"'))

    def test_rejects_member_preprocessor_and_address_uses(self):
        source = (
            "#define INVOKE Helper()\n"
            "int Member(void) { return obj.Helper(); }\n"
            "int Address(void) { return (int)&Helper; }\n"
        )
        dispatches = []
        for occurrence, call_id in enumerate(("CALL_MACRO", "CALL_MEMBER", "CALL_ADDRESS")):
            dispatches.append(
                {
                    "callee": "Helper",
                    "dispatcher_name": "Utr_Dep_Helper",
                    "rewrite_sites": [_rewrite_site(source, "Helper", call_id, occurrence)],
                }
            )

        rewritten, issues = rewrite_dependency_calls(source, dispatches)

        self.assertEqual(source, rewritten)
        self.assertEqual(
            {"CALL_MACRO", "CALL_MEMBER", "CALL_ADDRESS"},
            {issue.call_id for issue in issues},
        )
        self.assertNotIn('utr_dependency_dispatch.h', rewritten)

    def test_rejects_overlapping_rewrite_sites(self):
        source = "int Target(void) { return Helper(); }\n"
        site = _rewrite_site(source, "Helper", "CALL_001")
        rewritten, issues = rewrite_dependency_calls(
            source,
            [
                {
                    "callee": "Helper",
                    "dispatcher_name": "Utr_Dep_First",
                    "rewrite_sites": [site],
                },
                {
                    "callee": "Helper",
                    "dispatcher_name": "Utr_Dep_Second",
                    "rewrite_sites": [dict(site, call_id="CALL_002")],
                },
            ],
        )

        self.assertEqual(source, rewritten)
        self.assertEqual({"CALL_001", "CALL_002"}, {issue.call_id for issue in issues})
        self.assertTrue(all(issue.code == "overlapping_rewrite" for issue in issues))


if __name__ == "__main__":
    unittest.main()
