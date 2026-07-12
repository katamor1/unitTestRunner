from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.cli.parser import build_parser
from unit_test_runner.dossier.workflow import load_test_spec_for_consumer
from unit_test_runner.execution.test_execution import _read_canonical_test_spec

from tests.test_test_spec_cli import create_workspace


class TestSpecConsumerTests(unittest.TestCase):
    def test_harness_parser_prefers_test_spec_and_keeps_explicit_legacy_alias(self):
        parser = build_parser()
        common = [
            "generate-harness-skeleton",
            "--function-signature", "signature.json",
            "--global-access", "globals.json",
            "--call-report", "calls.json",
            "--out", "out",
        ]

        canonical = parser.parse_args(common + ["--test-spec", "test_spec.json"])
        legacy = parser.parse_args(common + ["--test-case-design", "test_case_design.json"])

        self.assertEqual("test_spec.json", canonical.test_spec)
        self.assertIsNone(canonical.test_case_design)
        self.assertEqual("test_case_design.json", legacy.test_case_design)

    def test_reanalysis_parser_exposes_canonical_spec_options_and_names_legacy_aliases(self):
        parser = build_parser()
        reconcile = parser.parse_args(
            [
                "reconcile-test-cases",
                "--previous-test-spec", "previous/test_spec.json",
                "--previous-coverage-design", "previous/coverage.json",
                "--current-test-spec", "current/test_spec.json",
                "--current-coverage-design", "current/coverage.json",
                "--current-boundary-candidates", "current/boundary.json",
                "--out", "reports/reconciliation.json",
            ]
        )

        self.assertEqual("previous/test_spec.json", reconcile.previous_test_spec)
        self.assertEqual("current/test_spec.json", reconcile.current_test_spec)
        self.assertIsNone(reconcile.previous_test_case_design)

    def test_canonical_envelope_is_normalized_to_consumer_data_and_views_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = create_workspace(workspace)

            payload = load_test_spec_for_consumer(path)

            self.assertEqual("spec-control-update", payload["spec_id"])
            self.assertEqual("tc-control-update-001", payload["test_cases"][0]["test_case_id"])
            markdown = workspace / "reports" / "test_spec.md"
            markdown.write_text("generated view; edits are not imported", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_test_spec_for_consumer(markdown)

    def test_canonical_consumers_fail_closed_after_source_becomes_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = create_workspace(workspace)
            (workspace / "src" / "control.c").write_text(
                "int Control_Update(int mode) { return mode + 1; }\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_test_spec_for_consumer(path)
            with self.assertRaises(ValueError):
                _read_canonical_test_spec(workspace / "reports")

    def test_v0_1_alias_uses_signature_context_and_never_rewrites_legacy_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            signature = {
                "schema_version": "0.1",
                "source": {"path": "src/control.c", "sha256": "1" * 64},
                "function": {"name": "Control_Update", "header_text_normalized": "int Control_Update(void)"},
                "warnings": [],
            }
            signature_path = root / "function_signature.json"
            signature_path.write_text(json.dumps(signature), encoding="utf-8")
            legacy = {
                "schema_version": "0.1",
                "source": dict(signature["source"]),
                "function": {"name": "Control_Update", "status": "generated"},
                "generation_policy": {},
                "test_cases": [{"test_case_id": "tc-1", "review_status": "review_required", "coverage_links": [{"coverage_id": "cov-1"}]}],
                "additional_case_candidates": [],
                "coverage_summary": {"total_coverage_items": 1, "covered_by_design_count": 1, "uncovered_coverage_ids": [], "coverage_to_test_cases": {"cov-1": ["tc-1"]}},
                "unresolved_items": [],
                "warnings": [],
            }
            legacy_path = root / "test_case_design.json"
            legacy_path.write_text(json.dumps(legacy, indent=2), encoding="utf-8")
            before = legacy_path.read_bytes()

            payload = load_test_spec_for_consumer(
                legacy_path,
                function_signature_path=signature_path,
                allow_legacy_alias=True,
            )

            self.assertEqual(before, legacy_path.read_bytes())
            self.assertNotIn("review_status", payload["test_cases"][0])
            self.assertTrue(payload["test_cases"][0]["review_item_ids"])

    def test_v0_1_alias_rejects_source_path_or_hash_mismatch_with_signature(self):
        for field, value in (("path", "src/other.c"), ("sha256", "9" * 64)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                signature = {
                    "schema_version": "0.1",
                    "source": {"path": "src/control.c", "sha256": "1" * 64},
                    "function": {"name": "Control_Update", "header_text_normalized": "int Control_Update(void)"},
                    "warnings": [],
                }
                signature_path = root / "function_signature.json"
                signature_path.write_text(json.dumps(signature), encoding="utf-8")
                legacy = {
                    "schema_version": "0.1",
                    "source": dict(signature["source"]),
                    "function": {"name": "Control_Update", "status": "generated"},
                    "generation_policy": {}, "test_cases": [], "additional_case_candidates": [],
                    "coverage_summary": {"total_coverage_items": 0, "covered_by_design_count": 0, "uncovered_coverage_ids": [], "coverage_to_test_cases": {}},
                    "unresolved_items": [], "warnings": [],
                }
                legacy["source"][field] = value
                legacy_path = root / "test_case_design.json"
                legacy_path.write_text(json.dumps(legacy), encoding="utf-8")

                with self.assertRaises(ValueError):
                    load_test_spec_for_consumer(
                        legacy_path,
                        function_signature_path=signature_path,
                        allow_legacy_alias=True,
                    )


if __name__ == "__main__":
    unittest.main()
