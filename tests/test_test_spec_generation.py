from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.c_analyzer.boundary_candidate_analyzer import generate_boundary_equivalence_candidates
from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.coverage_design_analyzer import analyze_coverage_design
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest
from unit_test_runner.test_design.test_case_design_generator import generate_test_case_design
from unit_test_runner.test_spec import (
    ArtifactReference,
    create_test_spec_from_design,
    test_spec_consumer_payload,
)
from unit_test_runner.dossier.workflow import analyze_function_workflow
from unit_test_runner.dossier.finalizer import finalize_function_dossier
from unit_test_runner.dossier.artifact_collector import collect_artifacts


REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE = REPO_ROOT / "tests" / "fixtures" / "c_sources" / "analysis_pipeline" / "pipeline.c"
VC6_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


class TestSpecGenerationTests(unittest.TestCase):
    def test_dossier_design_phase_saves_canonical_once_and_exports_views(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "Control_Update"

            dossier = analyze_function_workflow(
                VC6_FIXTURE,
                VC6_FIXTURE / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                out,
                "Control",
                phase="design",
            )

            canonical = out / "reports" / "test_spec.json"
            payload = json.loads(canonical.read_text(encoding="utf-8"))
            self.assertEqual("1.0.0", payload["schema_version"])
            self.assertEqual(1, payload["data"]["revision"])
            self.assertEqual(
                canonical.resolve(),
                Path(dossier["test_spec"]["json"]).resolve(),
            )
            self.assertTrue((out / "reports" / "test_spec.md").exists())
            self.assertTrue((out / "reports" / "test_spec.csv").exists())
            self.assertFalse((out / "reports" / "test_case_design.json").exists())
            artifacts, payloads, _warnings = collect_artifacts(out)
            canonical_artifact = next(item for item in artifacts if item.artifact_kind == "test_spec")
            self.assertTrue(canonical_artifact.exists)
            self.assertEqual("valid", canonical_artifact.contract_status)
            self.assertIn("test_spec", payloads)
            self.assertNotIn("test_case_design", {item.artifact_kind for item in artifacts})

            finalize_function_dossier(out, "Control_Update")
            self.assertEqual(1, json.loads(canonical.read_text(encoding="utf-8"))["data"]["revision"])

    def test_generated_design_requires_subject_binding_before_public_serialization(self):
        digest = build_source_digest(PIPELINE)
        location = locate_function(digest, "Control_Update")
        signature = extract_signature(digest, location)
        global_access = analyze_global_access(digest, location, signature)
        call_report = analyze_calls(digest, location, signature, global_access)
        coverage = analyze_coverage_design(digest, location, signature, global_access, call_report)
        boundary = generate_boundary_equivalence_candidates(signature, global_access, call_report, coverage)
        design = generate_test_case_design(signature, global_access, call_report, coverage, boundary)
        reference = ArtifactReference("function_signature", "reports/function_signature.json", "3" * 64)

        spec = create_test_spec_from_design(
            design,
            signature.to_dict(),
            source_path="src/pipeline.c",
            generated_from=[reference],
        )

        with self.assertRaisesRegex(ValueError, "unbound_subject"):
            spec.to_payload()
        spec = spec.with_subject_context(
            project="AnalysisPipeline",
            configuration="AnalysisPipeline - Win32 Debug",
        )
        payload = spec.to_payload()
        self.assertEqual("1.0.0", payload["schema_version"])
        self.assertNotIn("review_status", json.dumps(payload))
        self.assertFalse(spec.test_cases, "placeholder cases cannot be executable")
        self.assertTrue(spec.additional_case_candidates)
        self.assertTrue(spec.review_item_ids)
        for case in spec.additional_case_candidates:
            self.assertTrue(case["review_item_ids"])
        consumer = test_spec_consumer_payload(spec)
        self.assertEqual(spec.function.name, consumer["function"]["name"])
        self.assertEqual([], consumer["test_cases"])


if __name__ == "__main__":
    unittest.main()
