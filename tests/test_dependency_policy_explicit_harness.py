import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dossier.workflow import generate_harness_skeleton_from_reports


class DependencyPolicyExplicitHarnessTests(unittest.TestCase):
    def test_explicit_harness_generation_loads_sibling_dependency_policy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "target.c"
            source.write_text("int Target(void) { return Helper(); }\n", encoding="ascii")
            reports = root / "analysis" / "reports"
            reports.mkdir(parents=True)
            signature = {
                "source": {"path": str(source), "sha256": "abc"},
                "function": {"name": "Target", "return_type": {"raw": "int"}, "parameters": [], "storage_class": None},
            }
            global_access = {"global_accesses": [], "file_scope_declarations": []}
            call_report = {
                "calls": [{"call_id": "CALL_001", "name": "Helper", "target_kind": "external_function", "arguments": [], "return_usage": {"usage_kind": "returned"}}],
                "stub_candidates": [],
            }
            test_design = {
                "source": {"path": str(source), "sha256": "abc"},
                "function": {"name": "Target", "status": "generated"},
                "test_cases": [],
                "additional_case_candidates": [],
                "coverage_summary": {"total_coverage_items": 0, "covered_by_design_count": 0, "uncovered_coverage_ids": [], "coverage_to_test_cases": {}},
                "unresolved_items": [],
                "warnings": [],
            }
            policy = {
                "source": {"path": str(source)},
                "function": {"name": "Target", "status": "resolved"},
                "dependencies": [
                    {
                        "callee": "Helper",
                        "target_kind": "external_function",
                        "configured_mode": "stub",
                        "resolved_mode": "stub",
                        "review_status": "resolved",
                        "implementation_source": None,
                        "related_call_ids": ["CALL_001"],
                        "rewrite_sites": [{"call_id": "CALL_001", "start": {"line": 1, "column": 27}, "end": {"line": 1, "column": 33}}],
                        "signature": {
                            "resolution": "exact",
                            "return_type_raw": "int",
                            "calling_convention": None,
                            "parameters": [],
                            "prototype": "int Helper(void)",
                            "declaration_source": None,
                            "definition_source": None,
                            "conflicts": [],
                            "confidence": "high",
                        },
                    }
                ],
                "external_objects": [],
                "warnings": [],
            }
            for name, payload in (
                ("function_signature.json", signature),
                ("global_access.json", global_access),
                ("call_report.json", call_report),
                ("test_case_design.json", test_design),
                ("dependency_policy.json", policy),
            ):
                (reports / name).write_text(json.dumps(payload), encoding="utf-8")
            output = root / "explicit"

            report = generate_harness_skeleton_from_reports(
                reports / "function_signature.json",
                reports / "global_access.json",
                reports / "call_report.json",
                reports / "test_case_design.json",
                output,
                overwrite=True,
            )

            self.assertEqual(1, len(report.dependency_dispatches))
            self.assertTrue((output / "generated" / "dependencies" / "utr_dependency_dispatch.c").exists())


if __name__ == "__main__":
    unittest.main()
