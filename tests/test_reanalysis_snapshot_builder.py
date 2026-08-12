import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.reanalysis.snapshot_builder import (
    STANDARD_ARTIFACTS,
    build_analysis_snapshot,
)


class ReanalysisSnapshotBuilderTests(unittest.TestCase):
    def test_snapshot_records_missing_artifacts_without_inventing_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot, warnings, payloads = build_analysis_snapshot(
                "previous",
                temp_dir,
                "Control_Update",
            )

        self.assertEqual({}, payloads)
        self.assertEqual(set(STANDARD_ARTIFACTS), set(snapshot.artifacts))
        self.assertTrue(all(not item.exists for item in snapshot.artifacts.values()))
        self.assertEqual(len(STANDARD_ARTIFACTS), len(warnings))

    def test_snapshot_hashes_the_same_bytes_that_it_parses(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            reports.mkdir()
            raw = b'{"schema_version":"0.1","source":{"path":"src/control.c","sha256":"' + b"a" * 64 + b'"}}'
            (reports / "source_digest.json").write_bytes(raw)

            snapshot, warnings, payloads = build_analysis_snapshot(
                "current",
                workspace,
                "Control_Update",
                exclude_kinds=set(STANDARD_ARTIFACTS) - {"source_digest"},
            )

        self.assertEqual([], warnings)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), snapshot.artifacts["source_digest"].sha256)
        self.assertEqual("src/control.c", snapshot.source_path.as_posix())
        self.assertEqual("a" * 64, snapshot.source_sha256)
        self.assertEqual("0.1", payloads["source_digest"]["schema_version"])

    def test_invalid_utf8_is_a_parse_warning_and_not_a_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            reports.mkdir()
            raw = b'{"schema_version":"0.1","source":"\xff"}'
            (reports / "source_digest.json").write_bytes(raw)

            snapshot, warnings, payloads = build_analysis_snapshot(
                "current",
                workspace,
                "Control_Update",
                exclude_kinds=set(STANDARD_ARTIFACTS) - {"source_digest"},
            )

        self.assertEqual({}, payloads)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), snapshot.artifacts["source_digest"].sha256)
        self.assertEqual(["artifact_parse_failed"], [item.code for item in warnings])

    def test_build_context_hash_is_canonical_over_parsed_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            reports.mkdir()
            payload = {"schema_version": "0.1", "defines": ["DEBUG=1"]}
            (reports / "build_context.json").write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )

            snapshot, warnings, _ = build_analysis_snapshot(
                "current",
                workspace,
                "Control_Update",
                exclude_kinds=set(STANDARD_ARTIFACTS) - {"build_context"},
            )

        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        self.assertEqual([], warnings)
        self.assertEqual(expected, snapshot.build_context_hash)

    def test_exclusions_remove_artifact_rows_and_warnings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot, warnings, _ = build_analysis_snapshot(
                "current",
                temp_dir,
                "Control_Update",
                exclude_kinds={"test_spec", "build_context"},
            )

        self.assertNotIn("test_spec", snapshot.artifacts)
        self.assertNotIn("build_context", snapshot.artifacts)
        self.assertTrue(
            all(item.related_artifact not in {"test_spec", "build_context"} for item in warnings)
        )


if __name__ == "__main__":
    unittest.main()
