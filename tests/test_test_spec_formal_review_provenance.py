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
from unit_test_runner.test_spec import signature_sha256


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
    def test_all_raw_v01_provenance_kinds_reject_wrong_nested_field_types(self):
        mutations = {
            "source_digest": (
                "source_digest.json",
                lambda payload: payload["masking"]["masked_ranges"][0].__setitem__(
                    "start_line", "BROKEN"
                ),
            ),
            "function_location": (
                "function_location.json",
                lambda payload: payload["function"]["selected_candidate"].__setitem__(
                    "name", 42
                ),
            ),
            "function_signature": (
                "function_signature.json",
                lambda payload: payload["function"]["parameters"][0].__setitem__(
                    "index", "BROKEN"
                ),
            ),
            "global_access": (
                "global_access.json",
                lambda payload: payload["global_accesses"][0].__setitem__(
                    "name", 42
                ),
            ),
            "call_report": (
                "call_report.json",
                lambda payload: payload["calls"][0].__setitem__("call_id", 42),
            ),
            "dependency_policy": (
                "dependency_policy.json",
                lambda payload: payload["dependencies"][0].__setitem__(
                    "callee", 42
                ),
            ),
            "coverage_design": (
                "coverage_design.json",
                lambda payload: payload["coverage_items"][0].__setitem__(
                    "coverage_id", 42
                ),
            ),
            "boundary_candidates": (
                "boundary_equivalence_candidates.json",
                lambda payload: payload["input_candidates"][0].__setitem__(
                    "candidate_id", 42
                ),
            ),
        }
        for artifact_kind, (filename, mutate) in mutations.items():
            with self.subTest(artifact_kind=artifact_kind), tempfile.TemporaryDirectory() as temp_dir:
                canonical = analyze(Path(temp_dir))
                artifact_path = canonical.parent / filename
                payload = json.loads(artifact_path.read_text(encoding="utf-8"))
                mutate(payload)
                replacement = (
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
                ).encode("utf-8")
                replace_reference_bytes(
                    canonical,
                    artifact_kind=artifact_kind,
                    replacement=replacement,
                )
                if artifact_kind == "function_signature":
                    spec_payload = json.loads(canonical.read_text(encoding="utf-8"))
                    spec_payload["data"]["function"]["signature_sha256"] = (
                        signature_sha256(payload)
                    )
                    canonical.write_text(
                        json.dumps(spec_payload, indent=2, ensure_ascii=False)
                        + "\n",
                        encoding="utf-8",
                    )

                with self.assertRaises(ValueError):
                    load_test_spec_for_consumer(canonical)

    def test_all_raw_v01_provenance_kinds_reject_malformed_nested_data(self):
        mutations = {
            "source_digest": (
                "source_digest.json",
                lambda payload: payload["masking"].__setitem__(
                    "masked_ranges", "BROKEN"
                ),
            ),
            "function_location": (
                "function_location.json",
                lambda payload: payload["function"].__setitem__(
                    "selected_candidate", "BROKEN"
                ),
            ),
            "function_signature": (
                "function_signature.json",
                lambda payload: payload["function"].__setitem__(
                    "parameters", [42]
                ),
            ),
            "global_access": (
                "global_access.json",
                lambda payload: payload.__setitem__("global_accesses", [42]),
            ),
            "call_report": (
                "call_report.json",
                lambda payload: payload.__setitem__("calls", [42]),
            ),
            "dependency_policy": (
                "dependency_policy.json",
                lambda payload: payload.__setitem__("dependencies", [42]),
            ),
            "coverage_design": (
                "coverage_design.json",
                lambda payload: payload.__setitem__("coverage_items", [42]),
            ),
            "boundary_candidates": (
                "boundary_equivalence_candidates.json",
                lambda payload: payload.__setitem__("input_candidates", [42]),
            ),
        }
        for artifact_kind, (filename, mutate) in mutations.items():
            with self.subTest(artifact_kind=artifact_kind), tempfile.TemporaryDirectory() as temp_dir:
                canonical = analyze(Path(temp_dir))
                artifact_path = canonical.parent / filename
                payload = json.loads(artifact_path.read_text(encoding="utf-8"))
                mutate(payload)
                replacement = (
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
                ).encode("utf-8")
                replace_reference_bytes(
                    canonical,
                    artifact_kind=artifact_kind,
                    replacement=replacement,
                )
                if artifact_kind == "function_signature":
                    spec_payload = json.loads(canonical.read_text(encoding="utf-8"))
                    spec_payload["data"]["function"]["signature_sha256"] = (
                        signature_sha256(payload)
                    )
                    canonical.write_text(
                        json.dumps(spec_payload, indent=2, ensure_ascii=False)
                        + "\n",
                        encoding="utf-8",
                    )

                with self.assertRaises(ValueError):
                    load_test_spec_for_consumer(canonical)

    def test_nested_review_authority_in_raw_provenance_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            canonical = analyze(Path(temp_dir))
            call_report = canonical.parent / "call_report.json"
            payload = json.loads(call_report.read_text(encoding="utf-8"))
            self.assertTrue(payload["calls"])
            payload["calls"][0]["approval_status"] = "approved"
            replacement = (
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            replace_reference_bytes(
                canonical,
                artifact_kind="call_report",
                replacement=replacement,
            )

            with self.assertRaises(ValueError):
                load_test_spec_for_consumer(canonical)

    def test_canonical_leaf_and_reports_parent_symlinks_are_rejected(self):
        for mutation in ("leaf", "parent"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir) / "analysis"
                canonical = analyze(workspace)
                try:
                    if mutation == "leaf":
                        real_canonical = workspace / "real_test_spec.json"
                        canonical.replace(real_canonical)
                        os.symlink(real_canonical, canonical)
                    else:
                        reports = workspace / "reports"
                        real_reports = workspace / "real_reports"
                        reports.rename(real_reports)
                        os.symlink(real_reports, reports, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"symlink creation unavailable: {error}")

                with self.assertRaises(ValueError):
                    load_test_spec_for_consumer(
                        workspace / "reports" / "test_spec.json"
                    )

    def test_source_parent_symlink_is_rejected_before_harness_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "analysis"
            canonical = analyze(workspace)
            linked_project = root / "linked-project"
            linked_project.mkdir()
            try:
                os.symlink(
                    FIXTURE / "src",
                    linked_project / "src",
                    target_is_directory=True,
                )
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            request_path = workspace / "input" / "request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["workspace"] = linked_project.as_posix()
            request_path.write_text(
                json.dumps(request, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            reports = workspace / "reports"
            out = root / "unsafe-source-harness"

            with self.assertRaises(ValueError):
                generate_harness_skeleton_from_reports(
                    reports / "function_signature.json",
                    reports / "global_access.json",
                    reports / "call_report.json",
                    canonical,
                    out,
                    dependency_policy_path=reports / "dependency_policy.json",
                )

            self.assertFalse(out.exists())

    def test_reanalysis_provenance_parent_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "analysis"
            canonical = analyze(workspace)
            reports = workspace / "reports"
            real_current = workspace / "real-current"
            real_current.mkdir()
            reanalysis = reports / "reanalysis"
            reanalysis.mkdir()
            try:
                os.symlink(
                    real_current,
                    reanalysis / "current",
                    target_is_directory=True,
                )
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            payload = json.loads(canonical.read_text(encoding="utf-8"))
            references = []
            for reference in payload["data"]["generated_from"]:
                if reference["artifact_kind"] == "dependency_policy":
                    continue
                filename = Path(reference["path"]).name
                shutil.copyfile(reports / filename, real_current / filename)
                updated = dict(reference)
                updated["path"] = f"reports/reanalysis/current/{filename}"
                references.append(updated)
            payload["data"]["generated_from"] = references
            canonical.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_test_spec_for_consumer(canonical)

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

    def test_non_object_call_record_is_rejected_even_when_reference_hash_matches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            canonical = analyze(Path(temp_dir))
            call_report = canonical.parent / "call_report.json"
            payload = json.loads(call_report.read_text(encoding="utf-8"))
            payload["calls"] = [42]
            replacement = (
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            replace_reference_bytes(
                canonical,
                artifact_kind="call_report",
                replacement=replacement,
            )

            with self.assertRaises(ValueError):
                load_test_spec_for_consumer(canonical)

    def test_foreign_absolute_same_suffix_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canonical = analyze(root / "analysis")
            foreign_source = root / "foreign" / "src" / "control.c"
            foreign_source.parent.mkdir(parents=True)
            shutil.copyfile(FIXTURE / "src" / "control.c", foreign_source)
            call_report = canonical.parent / "call_report.json"
            payload = json.loads(call_report.read_text(encoding="utf-8"))
            payload["source"]["path"] = foreign_source.as_posix()
            replacement = (
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            replace_reference_bytes(
                canonical,
                artifact_kind="call_report",
                replacement=replacement,
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
