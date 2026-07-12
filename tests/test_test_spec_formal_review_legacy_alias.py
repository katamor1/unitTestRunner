from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.dossier.workflow import load_test_spec_for_consumer
from unit_test_runner.dossier import analyze_function_workflow
from unit_test_runner.test_spec import TestSpecContractError


REPO_ROOT = Path(__file__).resolve().parents[1]
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"
SOURCE_SHA = "1" * 64


def write_genuine_legacy_pair(root: Path, *, function_name: str = "Control_Update") -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    signature = {
        "schema_version": "0.1",
        "source": {"path": "src/control.c", "sha256": SOURCE_SHA},
        "function": {
            "name": function_name,
            "header_text_normalized": f"int {function_name}(void)",
        },
        "warnings": [],
    }
    signature_path = root / "function_signature.json"
    signature_path.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    legacy = {
        "schema_version": "0.1",
        "source": dict(signature["source"]),
        "function": {"name": function_name, "status": "generated"},
        "generation_policy": {},
        "test_cases": [
            {
                "test_case_id": "TC_Control_Update_001",
                "target_function": function_name,
                "review_status": "review_required",
                "expected_observations": [
                    {
                        "observation_kind": "return_value",
                        "expected_expression": "CONTROL_OK",
                    }
                ],
                "coverage_links": [{"coverage_id": "BR_001"}],
            }
        ],
        "additional_case_candidates": [],
        "coverage_summary": {
            "total_coverage_items": 1,
            "covered_by_design_count": 1,
            "uncovered_coverage_ids": [],
            "coverage_to_test_cases": {"BR_001": ["TC_Control_Update_001"]},
        },
        "unresolved_items": [],
        "warnings": [],
    }
    legacy_path = root / "test_case_design.json"
    legacy_path.write_text(json.dumps(legacy, indent=2), encoding="utf-8")
    return legacy_path, signature_path


def write_coverage(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "coverage_items": [
                    {
                        "coverage_id": "BR_001",
                        "coverage_type": "branch",
                        "target_id": "COND_001",
                        "purpose": "mode == 1",
                    }
                ],
                "condition_expressions": [
                    {"condition_id": "COND_001", "raw": "mode == 1"}
                ],
            }
        ),
        encoding="utf-8",
    )


class TestSpecFormalReviewLegacyAliasTests(unittest.TestCase):
    def test_legacy_alias_leaf_and_parent_symlinks_are_rejected(self):
        for mutation in ("leaf", "parent"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                bundle = root / "bundle"
                legacy_path, signature_path = write_genuine_legacy_pair(bundle)
                try:
                    if mutation == "leaf":
                        real_legacy = bundle / "real_test_case_design.json"
                        legacy_path.replace(real_legacy)
                        os.symlink(real_legacy, legacy_path)
                    else:
                        real_bundle = root / "real-bundle"
                        bundle.rename(real_bundle)
                        os.symlink(real_bundle, bundle, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"symlink creation unavailable: {error}")

                with self.assertRaises(TestSpecContractError):
                    load_test_spec_for_consumer(
                        legacy_path,
                        function_signature_path=signature_path,
                        allow_legacy_alias=True,
                    )

    def test_harness_alias_returns_genuine_legacy_view_without_fabricated_canonical_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path, signature_path = write_genuine_legacy_pair(Path(temp_dir))
            before = legacy_path.read_bytes()

            view = load_test_spec_for_consumer(
                legacy_path,
                function_signature_path=signature_path,
                allow_legacy_alias=True,
            )

            self.assertEqual(before, legacy_path.read_bytes())
            self.assertNotIn("spec_id", view)
            self.assertNotIn("generated_from", view)
            self.assertNotIn("review_item_ids", view)
            self.assertNotIn("function_id", view["function"])
            self.assertNotIn("signature_sha256", view["function"])
            self.assertEqual(
                "review_required", view["test_cases"][0]["review_status"]
            )

    def test_harness_and_reconcile_aliases_accept_same_genuine_shape_without_rewrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            previous = root / "previous"
            current = root / "current"
            previous_legacy, _previous_signature = write_genuine_legacy_pair(previous)
            current_legacy, _current_signature = write_genuine_legacy_pair(current)
            previous_coverage = previous / "coverage_design.json"
            current_coverage = current / "coverage_design.json"
            boundary = current / "boundary_equivalence_candidates.json"
            write_coverage(previous_coverage)
            write_coverage(current_coverage)
            boundary.write_text(json.dumps({"schema_version": "0.1"}), encoding="utf-8")
            out = root / "reports" / "reconciliation.json"
            before = (previous_legacy.read_bytes(), current_legacy.read_bytes())
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unit_test_runner",
                    "--json",
                    "reconcile-test-cases",
                    "--previous-test-case-design",
                    str(previous_legacy),
                    "--previous-coverage-design",
                    str(previous_coverage),
                    "--current-test-case-design",
                    str(current_legacy),
                    "--current-coverage-design",
                    str(current_coverage),
                    "--current-boundary-candidates",
                    str(boundary),
                    "--out",
                    str(out),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertTrue(out.is_file())
            self.assertEqual(before, (previous_legacy.read_bytes(), current_legacy.read_bytes()))

    def test_shared_alias_adapter_returns_same_typed_blocking_identity_failure(self):
        try:
            adapter = importlib.import_module(
                "unit_test_runner.test_spec.legacy_adapter"
            ).load_legacy_test_case_design_view
        except (AttributeError, ModuleNotFoundError) as error:
            self.fail(f"shared legacy adapter is missing: {error}")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_path, signature_path = write_genuine_legacy_pair(root)
            signature = json.loads(signature_path.read_text(encoding="utf-8"))
            signature["function"]["name"] = "Other_Function"
            signature_path.write_text(json.dumps(signature), encoding="utf-8")

            with self.assertRaises(TestSpecContractError) as raised:
                adapter(legacy_path, function_signature_path=signature_path)

        self.assertIn(
            "legacy_identity_mismatch",
            {item.code for item in raised.exception.violations},
        )
        self.assertTrue(
            all(item.severity == "blocking" for item in raised.exception.violations)
        )

    def test_reanalyze_function_alias_accepts_genuine_legacy_view_without_rewrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            previous = root / "previous"
            current = root / "current"
            analyze_function_workflow(
                VC6_FIXTURE_ROOT,
                VC6_FIXTURE_ROOT / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                previous,
                "Control",
            )
            canonical = json.loads(
                (previous / "reports" / "test_spec.json").read_text(encoding="utf-8")
            )["data"]
            legacy_cases = []
            for source_case in canonical["test_cases"]:
                case = dict(source_case)
                if case.pop("review_item_ids", None):
                    case["review_status"] = "review_required"
                legacy_cases.append(case)
            legacy_candidates = []
            for source_case in canonical["additional_case_candidates"]:
                case = dict(source_case)
                case.pop("review_item_ids", None)
                case["review_status"] = "review_required"
                legacy_candidates.append(case)
            legacy = {
                "schema_version": "0.1",
                "source": canonical["source"],
                "function": {
                    "name": canonical["function"]["name"],
                    "status": "generated",
                },
                "generation_policy": canonical["generation_policy"],
                "test_cases": legacy_cases,
                "additional_case_candidates": legacy_candidates,
                "coverage_summary": canonical["coverage_summary"],
                "unresolved_items": canonical["unresolved_items"],
                "warnings": canonical["warnings"],
            }
            legacy_path = previous / "reports" / "legacy_test_case_design.json"
            legacy_path.write_text(json.dumps(legacy, indent=2), encoding="utf-8")
            before = legacy_path.read_bytes()
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unit_test_runner",
                    "--json",
                    "reanalyze-function",
                    "--workspace",
                    str(VC6_FIXTURE_ROOT),
                    "--dsw",
                    str(VC6_FIXTURE_ROOT / "Product.dsw"),
                    "--source",
                    "src/control.c",
                    "--function",
                    "Control_Update",
                    "--configuration",
                    "Win32 Debug",
                    "--project",
                    "Control",
                    "--out",
                    str(current),
                    "--previous-dossier",
                    str(previous / "reports" / "function_dossier.json"),
                    "--previous-test-case-design",
                    str(legacy_path),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertEqual(before, legacy_path.read_bytes())
            self.assertTrue((current / "reports" / "change_impact_report.json").is_file())


if __name__ == "__main__":
    unittest.main()
