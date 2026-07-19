import importlib.util
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_large_vc6_fixture.py"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.c_analyzer.boundary_candidate_analyzer import (
    generate_boundary_equivalence_candidates,
)
from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.coverage_design_analyzer import analyze_coverage_design
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest
from unit_test_runner.test_design.candidate_selector import select_candidates_for_coverage
from unit_test_runner.test_design.test_case_design_generator import generate_test_case_design


def _load_large_fixture_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_large_vc6_fixture",
        GENERATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator: {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LargeGeneratedCandidateRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generator = _load_large_fixture_generator()
        source = generator.render_generated_source(
            index=6996,
            generated_count=6997,
            width=5,
        )
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp_dir.cleanup)
        source_path = Path(cls.temp_dir.name) / "large_module_06996.c"
        source_path.write_text(source, encoding="utf-8")

        digest = build_source_digest(source_path)
        location = locate_function(digest, "UtrLarge_Module_06996")
        signature = extract_signature(digest, location)
        global_access = analyze_global_access(digest, location, signature)
        call_report = analyze_calls(digest, location, signature, global_access)
        coverage = analyze_coverage_design(
            digest,
            location,
            signature,
            global_access,
            call_report,
        )
        boundary = generate_boundary_equivalence_candidates(
            signature,
            global_access,
            call_report,
            coverage,
        )

        cls.boundary = boundary.to_dict()
        cls.design = generate_test_case_design(
            signature,
            global_access,
            call_report,
            coverage,
            boundary,
        ).to_dict()

    def test_candidate_ids_are_unique_for_signed_and_condition_values(self):
        candidates = (
            self.boundary["input_candidates"]
            + self.boundary["state_candidates"]
            + self.boundary["stub_return_candidates"]
        )
        candidate_ids = [candidate["candidate_id"] for candidate in candidates]
        duplicates = {
            candidate_id: count
            for candidate_id, count in Counter(candidate_ids).items()
            if count > 1
        }

        self.assertEqual({}, duplicates)
        signed_type_candidates = {
            candidate["value_expression"]: candidate["candidate_id"]
            for candidate in self.boundary["input_candidates"]
            if candidate["target_name"] == "seed"
            and candidate["source"] == "type"
            and candidate["value_expression"] in {"-1", "0", "1"}
        }
        self.assertEqual({"-1", "0", "1"}, set(signed_type_candidates))
        self.assertEqual(3, len(set(signed_type_candidates.values())))

    def test_condition_candidates_link_only_to_their_own_branch(self):
        condition_coverage_ids = {
            coverage_id
            for candidate in self.boundary["input_candidates"]
            if candidate["related_condition_id"] == "COND_002"
            for coverage_id in candidate["related_coverage_ids"]
        }

        self.assertIn("BR_002_TRUE", condition_coverage_ids)
        self.assertIn("BR_002_FALSE", condition_coverage_ids)
        self.assertIn("COND_002_PART1_TRUE", condition_coverage_ids)
        self.assertNotIn("BR_001_TRUE", condition_coverage_ids)
        self.assertNotIn("BR_003_TRUE", condition_coverage_ids)

    def test_selector_preserves_alternatives_without_selecting_one_input_twice(self):
        boundary_payload = {
            "input_candidates": [
                {
                    "candidate_id": "A_seed_zero",
                    "target_name": "seed",
                    "target_kind": "parameter",
                    "value_expression": "0",
                    "value_kind": "boundary_at",
                    "confidence": "high",
                    "review_required": True,
                    "related_coverage_ids": ["BR_001_TRUE"],
                },
                {
                    "candidate_id": "B_seed_seventeen",
                    "target_name": "seed",
                    "target_kind": "parameter",
                    "value_expression": "17",
                    "value_kind": "boundary_at",
                    "confidence": "high",
                    "review_required": True,
                    "related_coverage_ids": ["BR_001_TRUE"],
                },
                {
                    "candidate_id": "Z_mode_auto",
                    "target_name": "mode",
                    "target_kind": "parameter",
                    "value_expression": "MODE_AUTO",
                    "value_kind": "boundary_at",
                    "confidence": "high",
                    "review_required": True,
                    "related_coverage_ids": ["BR_001_TRUE"],
                },
            ]
        }

        selected, additional = select_candidates_for_coverage(
            boundary_payload,
            "BR_001_TRUE",
            max_items=2,
        )

        self.assertEqual(
            {"seed", "mode"},
            {candidate["target_name"] for candidate in selected},
        )
        self.assertEqual(
            ["B_seed_seventeen"],
            [candidate["candidate_id"] for candidate in additional],
        )

    def test_each_case_assigns_at_most_one_value_to_each_input(self):
        ambiguous_cases = {}
        for case in self.design["test_cases"]:
            targets = [
                assignment["target_name"]
                for assignment in case["input_assignments"]
            ]
            duplicate_targets = {
                target
                for target, count in Counter(targets).items()
                if count > 1
            }
            if duplicate_targets:
                ambiguous_cases[case["test_case_id"]] = sorted(duplicate_targets)

        self.assertEqual({}, ambiguous_cases)


if __name__ == "__main__":
    unittest.main()
