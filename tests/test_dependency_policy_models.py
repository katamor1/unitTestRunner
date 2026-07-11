import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dependency_policy.models import (
    DependencyEvidence,
    DependencyPolicyEntry,
    DependencyPolicyReport,
    DependencyRewriteSite,
    ExternalObjectPolicyEntry,
    ResolvedParameter,
    ResolvedSignature,
)
from unit_test_runner.dependency_policy.writer import write_dependency_policy


class DependencyPolicyModelTests(unittest.TestCase):
    def test_report_serializes_dependency_signature_and_external_object_binding(self):
        signature = ResolvedSignature(
            resolution="exact",
            return_type_raw="long",
            calling_convention="__stdcall",
            parameters=[ResolvedParameter(0, "context", "DeviceContext *", 1, ["const"], False)],
            prototype="long __stdcall Device_Read(DeviceContext *context)",
            declaration_source=Path("include/device.h"),
            definition_source=Path("src/device.c"),
        )
        dependency = DependencyPolicyEntry(
            callee="Device_Read",
            target_kind="external_function",
            configured_mode="auto",
            resolved_mode="stub",
            review_status="resolved",
            signature=signature,
            implementation_source=Path("src/device.c"),
            related_call_ids=["CALL_001"],
            rewrite_sites=[DependencyRewriteSite("CALL_001", 10, 14, 10, 25)],
            evidence=[DependencyEvidence("return_only_boundary", "Only the return value is consumed.", "call_report", -2)],
        )
        external_object = ExternalObjectPolicyEntry(
            symbol="g_state",
            type_raw="struct State *",
            configured_mode="auto",
            resolved_mode="real",
            review_status="resolved",
            declaration_header=Path("include/state.h"),
            definition_source=Path("src/state.c"),
            definition_candidates=[Path("src/state.c")],
        )
        report = DependencyPolicyReport(
            source_path=Path("src/control.c"),
            target_function="Control_Update",
            status="resolved",
            dependencies=[dependency],
            external_objects=[external_object],
        )

        payload = report.to_dict()

        self.assertEqual("0.1", payload["schema_version"])
        self.assertEqual("stub", payload["dependencies"][0]["resolved_mode"])
        self.assertEqual("__stdcall", payload["dependencies"][0]["signature"]["calling_convention"])
        self.assertEqual("include/device.h", payload["dependencies"][0]["signature"]["declaration_source"])
        self.assertEqual("real", payload["external_objects"][0]["resolved_mode"])

    def test_writer_emits_json_and_markdown_with_resolution_reasons(self):
        report = DependencyPolicyReport(
            source_path=Path("src/control.c"),
            target_function="Control_Update",
            status="review_required",
            dependencies=[
                DependencyPolicyEntry(
                    callee="Helper",
                    target_kind="same_file_function",
                    configured_mode="auto",
                    resolved_mode="review_required",
                    review_status="review_required",
                    signature=ResolvedSignature(resolution="review_required", conflicts=["conflicting declarations"]),
                    evidence=[DependencyEvidence("shared_global", "Both functions write g_state.", "global_access", 3)],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_dependency_policy(Path(temp_dir), report)
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            markdown = paths["markdown"].read_text(encoding="utf-8")

        self.assertEqual("review_required", payload["function"]["status"])
        self.assertIn("Helper", markdown)
        self.assertIn("Both functions write g_state.", markdown)
        self.assertIn("conflicting declarations", markdown)


if __name__ == "__main__":
    unittest.main()
