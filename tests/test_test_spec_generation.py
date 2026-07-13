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
from unit_test_runner.dossier.workflow import (
    generate_test_design_from_dossier,
    generate_test_design_from_reports,
)
from unit_test_runner.dossier.artifact_collector import collect_artifacts
from unit_test_runner.test_design.test_case_design_writer import write_test_case_design_payload_format


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
            self.assertEqual("1.1.0", payload["schema_version"])
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

            exported = generate_test_design_from_dossier(
                out / "reports" / "function_dossier.json",
                "all",
                out / "generated-views",
            )
            self.assertEqual(canonical.resolve(), Path(exported["json"]).resolve())
            self.assertEqual("test_spec.md", exported["markdown"].name)
            self.assertEqual("test_spec.csv", exported["csv"].name)
            self.assertEqual(1, json.loads(canonical.read_text(encoding="utf-8"))["data"]["revision"])

            regenerated = generate_test_design_from_reports(
                out / "reports" / "function_signature.json",
                out / "reports" / "global_access.json",
                out / "reports" / "call_report.json",
                out / "reports" / "coverage_design.json",
                out / "reports" / "boundary_equivalence_candidates.json",
                "all",
                out / "regenerated-views",
            )
            self.assertEqual(canonical.resolve(), Path(regenerated["json"]).resolve())
            self.assertEqual(2, json.loads(canonical.read_text(encoding="utf-8"))["data"]["revision"])

    def test_legacy_writer_cannot_create_an_alternate_editable_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                write_test_case_design_payload_format(
                    Path(temp_dir) / "test_case_design.json",
                    {"schema_version": "0.1", "test_cases": []},
                    "json",
                )

    def test_legacy_design_is_normalized_into_v1_1_without_review_authority(self):
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

        payload = spec.to_payload()
        self.assertEqual("1.1.0", payload["schema_version"])
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
