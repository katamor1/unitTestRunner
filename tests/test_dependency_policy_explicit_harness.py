import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dossier.workflow import generate_harness_skeleton_from_reports
from tests.spec_support import write_canonical_test_spec


class DependencyPolicyExplicitHarnessTests(unittest.TestCase):
    def test_explicit_harness_generation_loads_sibling_dependency_policy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "analysis"
            source = analysis / "target.c"
            source.parent.mkdir(parents=True)
            source.write_text("int Target(void) { return Helper(); }\n", encoding="ascii")
            reports = analysis / "reports"
            reports.mkdir(parents=True)
            global_access = {"global_accesses": [], "file_scope_declarations": []}
            call_report = {
                "calls": [{"call_id": "CALL_001", "name": "Helper", "target_kind": "external_function", "arguments": [], "return_usage": {"usage_kind": "returned"}}],
                "stub_candidates": [],
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
                ("global_access.json", global_access),
                ("call_report.json", call_report),
                ("dependency_policy.json", policy),
            ):
                (reports / name).write_text(json.dumps(payload), encoding="utf-8")
            write_canonical_test_spec(
                analysis,
                source_path="target.c",
                function_name="Target",
                test_case_id="TC_Target_001",
                function_fields={
                    "return_type": {"raw": "int"},
                    "parameters": [],
                    "storage_class": None,
                },
            )
            output = root / "explicit"

            report = generate_harness_skeleton_from_reports(
                reports / "function_signature.json",
                reports / "global_access.json",
                reports / "call_report.json",
                reports / "test_spec.json",
                output,
                overwrite=True,
            )

            self.assertEqual(1, len(report.dependency_dispatches))
            self.assertTrue((output / "generated" / "dependencies" / "utr_dependency_dispatch.c").exists())


if __name__ == "__main__":
    unittest.main()
