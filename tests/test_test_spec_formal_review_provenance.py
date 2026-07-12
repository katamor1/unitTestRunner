from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from unit_test_runner.dossier import (
    analyze_function_workflow,
    generate_harness_skeleton_from_reports,
)
from unit_test_runner.dossier.workflow import load_test_spec_for_consumer


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "vc6_project"
PROVENANCE_FILES = (
    "source_digest.json",
    "function_location.json",
    "function_signature.json",
    "global_access.json",
    "call_report.json",
    "coverage_design.json",
    "boundary_equivalence_candidates.json",
)


def analyze(out: Path, function_name: str = "Control_Update") -> Path:
    analyze_function_workflow(
        FIXTURE,
        FIXTURE / "Product.dsw",
        "src/control.c",
        function_name,
        "Win32 Debug",
        out,
        "Control",
        phase="design",
    )
    return out / "reports" / "test_spec.json"


def replace_reference_bytes(
    canonical: Path,
    *,
    artifact_kind: str,
    replacement: bytes,
) -> Path:
    payload = json.loads(canonical.read_text(encoding="utf-8"))
    reference = next(
        item
        for item in payload["data"]["generated_from"]
        if item["artifact_kind"] == artifact_kind
    )
    target = canonical.parent.parent / reference["path"]
    target.write_bytes(replacement)
    reference["sha256"] = hashlib.sha256(replacement).hexdigest()
    canonical.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


class TestSpecFormalReviewProvenanceTests(unittest.TestCase):
    def test_noop_reanalysis_files_do_not_override_saved_top_level_root_by_mtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            canonical = analyze(workspace)
            current = workspace / "reports" / "reanalysis" / "current"
            current.mkdir(parents=True)
            newer = time.time_ns() + 10_000_000_000
            for filename in PROVENANCE_FILES:
                destination = current / filename
                shutil.copyfile(workspace / "reports" / filename, destination)
                os.utime(destination, ns=(newer, newer))

            view = load_test_spec_for_consumer(canonical)

            self.assertEqual("Control_Update", view["function"]["name"])

    def test_invalid_json_call_report_is_rejected_even_when_reference_hash_matches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            canonical = analyze(Path(temp_dir))
            replace_reference_bytes(
                canonical,
                artifact_kind="call_report",
                replacement=b"{ broken json",
            )

            with self.assertRaises(ValueError):
                load_test_spec_for_consumer(canonical)

    def test_missing_and_duplicate_provenance_are_rejected(self):
        for mutation in ("missing", "duplicate"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                canonical = analyze(workspace)
                payload = json.loads(canonical.read_text(encoding="utf-8"))
                references = payload["data"]["generated_from"]
                if mutation == "missing":
                    removed = next(
                        item
                        for item in references
                        if item["artifact_kind"] == "call_report"
                    )
                    references.remove(removed)
                    (workspace / removed["path"]).unlink()
                else:
                    references.append(dict(references[0]))
                canonical.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

                with self.assertRaises(ValueError):
                    load_test_spec_for_consumer(canonical)

    def test_wrong_kind_and_function_provenance_are_rejected_with_matching_hash(self):
        for mutation in ("wrong-kind", "wrong-function"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                workspace = root / "update"
                canonical = analyze(workspace)
                if mutation == "wrong-kind":
                    replacement = (
                        workspace / "reports" / "global_access.json"
                    ).read_bytes()
                else:
                    reset = root / "reset"
                    analyze(reset, "Control_Reset")
                    replacement = (
                        reset / "reports" / "call_report.json"
                    ).read_bytes()
                replace_reference_bytes(
                    canonical,
                    artifact_kind="call_report",
                    replacement=replacement,
                )

                with self.assertRaises(ValueError):
                    load_test_spec_for_consumer(canonical)

    def test_cross_workspace_harness_inputs_are_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            update = root / "update"
            reset = root / "reset"
            update_spec = analyze(update)
            reset_spec = analyze(reset, "Control_Reset")
            self.assertTrue(update_spec.is_file())
            out = root / "mixed-harness"

            with self.assertRaises(ValueError):
                generate_harness_skeleton_from_reports(
                    update / "reports" / "function_signature.json",
                    update / "reports" / "global_access.json",
                    update / "reports" / "call_report.json",
                    reset_spec,
                    out,
                    dependency_policy_path=update
                    / "reports"
                    / "dependency_policy.json",
                )

            self.assertFalse(out.exists())

    def test_alternate_supplied_report_path_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            canonical = analyze(workspace)
            reports = workspace / "reports"
            alternate_call = reports / "call_report_copy.json"
            shutil.copyfile(reports / "call_report.json", alternate_call)
            out = Path(temp_dir) / "alternate-harness"

            with self.assertRaises(ValueError):
                generate_harness_skeleton_from_reports(
                    reports / "function_signature.json",
                    reports / "global_access.json",
                    alternate_call,
                    canonical,
                    out,
                    dependency_policy_path=reports / "dependency_policy.json",
                )

            self.assertFalse(out.exists())

    def test_supplied_report_hash_mismatch_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            canonical = analyze(workspace)
            reports = workspace / "reports"
            call_report = reports / "call_report.json"
            call_report.write_bytes(call_report.read_bytes() + b" \n")
            out = Path(temp_dir) / "stale-harness"

            with self.assertRaises(ValueError):
                generate_harness_skeleton_from_reports(
                    reports / "function_signature.json",
                    reports / "global_access.json",
                    call_report,
                    canonical,
                    out,
                    dependency_policy_path=reports / "dependency_policy.json",
                )

            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
