import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.reanalysis.snapshot_builder import build_analysis_snapshot
from unit_test_runner.reanalysis import workflow as reanalysis_workflow
from unit_test_runner.contracts import (
    ArtifactKind,
    ConsumerContractError,
    load_consumer_data,
    normalize_consumer_data,
)
from unit_test_runner.reanalysis.reanalysis_models import (
    AnalysisSnapshot,
    SnapshotArtifact,
)
from unit_test_runner.reanalysis.workflow import (
    _payloads_from_previous_dossier,
    _snapshot_from_previous_dossier,
)
from unit_test_runner.test_spec import TestSpecContractError
from tests.spec_support import raw_v01_provenance_fixtures, valid_test_spec_payload


SOURCE_SHA256 = "1" * 64


def _competing_open(
    generations: dict[Path, tuple[bytes, bytes]],
    read_counts: dict[Path, int],
):
    original_open = Path.open

    def open_generation(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ):
        if path in generations and mode in {"r", "rb"}:
            count = read_counts.get(path, 0)
            read_counts[path] = count + 1
            raw_bytes = generations[path][0 if count == 0 else 1]
            if "b" in mode:
                return io.BytesIO(raw_bytes)
            return io.StringIO(raw_bytes.decode(encoding or "utf-8"))
        return original_open(path, mode, buffering, encoding, errors, newline)

    return open_generation


def strict_current_core_payloads() -> dict[str, dict]:
    legacy = raw_v01_provenance_fixtures(
        source_path="src/control.c",
        source_sha256=SOURCE_SHA256,
        function_name="Control_Update",
    )
    return {
        kind: {
            "artifact_kind": kind,
            "schema_version": "1.0.0",
            "producer": {
                "name": "unit-test-runner",
                "version": "0.1.0",
                "commit": "test-commit",
            },
            "subject": {
                "function_id": "fn-control-update",
                "source_path": "src/control.c",
                "source_sha256": SOURCE_SHA256,
            },
            "data": {
                key: value
                for key, value in legacy[kind].items()
                if key != "schema_version"
            },
            "extensions": {},
        }
        for kind in ("source_digest", "function_location", "function_signature")
    }


class ReanalysisSnapshotBuilderTests(unittest.TestCase):
    def test_contract_consumer_module_is_public(self):
        self.assertIsNotNone(find_spec("unit_test_runner.contracts.consumer"))

    def test_snapshot_hashing_keeps_missing_and_parse_warnings_separate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            legacy_source_digest = {
                "schema_version": "0.1",
                "source": {"path": "src/control.c", "sha256": "source123"},
            }
            (reports / "source_digest.json").write_text(
                json.dumps(legacy_source_digest),
                encoding="utf-8",
            )
            (reports / "function_signature.json").write_text("{not json", encoding="utf-8")

            snapshot, warnings, payloads = build_analysis_snapshot(
                "previous",
                root,
                "Control_Update",
                report_subdir=Path("reports"),
            )

        self.assertEqual("source123", snapshot.source_sha256)
        self.assertTrue(snapshot.artifacts["source_digest"].exists)
        self.assertTrue(snapshot.artifacts["function_signature"].exists)
        self.assertIn("source_digest", payloads)
        self.assertEqual(legacy_source_digest, payloads["source_digest"])
        codes = {warning.code for warning in warnings}
        self.assertIn("artifact_parse_failed", codes)
        self.assertIn("previous_artifact_missing", codes)

    def test_snapshot_invalid_utf8_is_parse_warning_and_excludes_payload(self):
        invalid_bytes = b'{"schema_version":"0.1","source":"\xff"}'
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            (reports / "source_digest.json").write_bytes(invalid_bytes)

            result = None
            caught = None
            try:
                result = build_analysis_snapshot(
                    "previous",
                    root,
                    "Control_Update",
                )
            except UnicodeDecodeError as error:
                caught = error

        self.assertIsNone(caught, f"invalid UTF-8 escaped the workflow: {caught}")
        snapshot, warnings, payloads = result
        self.assertNotIn("source_digest", payloads)
        parse_warnings = [
            warning
            for warning in warnings
            if warning.code == "artifact_parse_failed"
            and warning.related_artifact == "source_digest"
        ]
        self.assertEqual(1, len(parse_warnings))
        artifact = snapshot.artifacts["source_digest"]
        self.assertTrue(artifact.exists)
        self.assertIsNone(artifact.schema_version)
        self.assertEqual(hashlib.sha256(invalid_bytes).hexdigest(), artifact.sha256)

    def test_snapshot_normalizes_strict_current_core_envelopes(self):
        current_payloads = strict_current_core_payloads()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            for kind, payload in current_payloads.items():
                (reports / f"{kind}.json").write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )

            snapshot, _, payloads = build_analysis_snapshot(
                "previous",
                root,
                "Control_Update",
                report_subdir=Path("reports"),
            )

        for kind, envelope in current_payloads.items():
            self.assertEqual(envelope["data"], payloads[kind])
            self.assertEqual("1.0.0", snapshot.artifacts[kind].schema_version)
        self.assertEqual(Path("src/control.c"), snapshot.source_path)
        self.assertEqual(SOURCE_SHA256, snapshot.source_sha256)

    def test_snapshot_uses_one_saved_generation_for_payload_version_and_hash(self):
        current = strict_current_core_payloads()["source_digest"]
        legacy = raw_v01_provenance_fixtures(
            source_path="src/replacement.c",
            source_sha256="2" * 64,
            function_name="Replacement",
        )["source_digest"]
        saved_bytes = json.dumps(current, separators=(",", ":")).encode("utf-8")
        replacement_bytes = json.dumps(legacy).encode("utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            artifact_path = reports / "source_digest.json"
            artifact_path.write_bytes(saved_bytes)
            read_counts: dict[Path, int] = {}
            with mock.patch.object(
                Path,
                "open",
                new=_competing_open(
                    {artifact_path: (saved_bytes, replacement_bytes)},
                    read_counts,
                ),
            ):
                snapshot, _, payloads = build_analysis_snapshot(
                    "previous",
                    root,
                    "Control_Update",
                )

        self.assertEqual(1, read_counts[artifact_path])
        self.assertEqual(current["data"], payloads["source_digest"])
        artifact = snapshot.artifacts["source_digest"]
        self.assertEqual("1.0.0", artifact.schema_version)
        self.assertEqual(hashlib.sha256(saved_bytes).hexdigest(), artifact.sha256)

    def test_snapshot_raw_v01_payload_version_and_hash_share_saved_bytes(self):
        legacy = raw_v01_provenance_fixtures(
            source_path="src/control.c",
            source_sha256=SOURCE_SHA256,
            function_name="Control_Update",
        )["source_digest"]
        saved_bytes = json.dumps(legacy, indent=2).encode("utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            (reports / "source_digest.json").write_bytes(saved_bytes)

            snapshot, _, payloads = build_analysis_snapshot(
                "previous",
                root,
                "Control_Update",
            )

        self.assertEqual(legacy, payloads["source_digest"])
        artifact = snapshot.artifacts["source_digest"]
        self.assertEqual("0.1", artifact.schema_version)
        self.assertEqual(hashlib.sha256(saved_bytes).hexdigest(), artifact.sha256)

    def test_consumer_accepts_only_explicit_raw_v01_and_fails_closed_otherwise(self):
        legacy = raw_v01_provenance_fixtures(
            source_path="src/control.c",
            source_sha256=SOURCE_SHA256,
            function_name="Control_Update",
        )["source_digest"]
        self.assertEqual(
            legacy,
            normalize_consumer_data(
                legacy,
                expected_kind=ArtifactKind.SOURCE_DIGEST,
                allow_legacy_v01=True,
            ),
        )
        with self.assertRaises(ConsumerContractError):
            normalize_consumer_data(
                legacy,
                expected_kind=ArtifactKind.SOURCE_DIGEST,
                allow_legacy_v01=False,
            )

        current = strict_current_core_payloads()["source_digest"]
        invalid_cases = {
            "wrong_kind": (
                current,
                ArtifactKind.FUNCTION_LOCATION,
            ),
            "unsupported_version": (
                {**current, "schema_version": "9.0.0"},
                ArtifactKind.SOURCE_DIGEST,
            ),
            "current_shaped_v01": (
                {**copy.deepcopy(current), "schema_version": "0.1"},
                ArtifactKind.SOURCE_DIGEST,
            ),
            "invalid_current_data": (
                {**copy.deepcopy(current), "data": {}},
                ArtifactKind.SOURCE_DIGEST,
            ),
        }
        for label, (payload, expected_kind) in invalid_cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ConsumerContractError):
                    normalize_consumer_data(
                        payload,
                        expected_kind=expected_kind,
                        allow_legacy_v01=True,
                    )

    def test_consumer_rejects_numeric_legacy_schema_version(self):
        legacy = raw_v01_provenance_fixtures(
            source_path="src/control.c",
            source_sha256=SOURCE_SHA256,
            function_name="Control_Update",
        )["source_digest"]
        legacy["schema_version"] = 0.1

        with self.assertRaises(ConsumerContractError):
            normalize_consumer_data(
                legacy,
                expected_kind=ArtifactKind.SOURCE_DIGEST,
                allow_legacy_v01=True,
            )

    def test_consumer_recursively_isolates_current_and_raw_v01_mutations(self):
        current = strict_current_core_payloads()["source_digest"]
        current_data = normalize_consumer_data(
            current,
            expected_kind=ArtifactKind.SOURCE_DIGEST,
        )
        current["data"]["source"]["path"] = "src/mutated-input.c"
        self.assertEqual("src/control.c", current_data["source"]["path"])
        current_data["source"]["warnings"].append("mutated-output")
        self.assertEqual([], current["data"]["source"]["warnings"])

        legacy = raw_v01_provenance_fixtures(
            source_path="src/control.c",
            source_sha256=SOURCE_SHA256,
            function_name="Control_Update",
        )["source_digest"]
        legacy_data = normalize_consumer_data(
            legacy,
            expected_kind=ArtifactKind.SOURCE_DIGEST,
            allow_legacy_v01=True,
        )
        legacy["source"]["path"] = "src/mutated-input.c"
        self.assertEqual("src/control.c", legacy_data["source"]["path"])
        legacy_data["preprocessor"]["includes"].append("mutated-output")
        self.assertEqual([], legacy["preprocessor"]["includes"])

    def test_file_consumer_uses_the_same_current_and_legacy_policy(self):
        current = strict_current_core_payloads()["source_digest"]
        legacy = raw_v01_provenance_fixtures(
            source_path="src/control.c",
            source_sha256=SOURCE_SHA256,
            function_name="Control_Update",
        )["source_digest"]
        invalid_payloads = (
            {**copy.deepcopy(current), "artifact_kind": "function_location"},
            {**copy.deepcopy(current), "schema_version": "9.0.0"},
            {**copy.deepcopy(current), "schema_version": "0.1"},
            {**copy.deepcopy(current), "data": {}},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "source_digest.json"
            artifact.write_text(json.dumps(current), encoding="utf-8")
            self.assertEqual(
                current["data"],
                load_consumer_data(
                    artifact,
                    expected_kind=ArtifactKind.SOURCE_DIGEST,
                ),
            )

            artifact.write_text(json.dumps(legacy), encoding="utf-8")
            self.assertEqual(
                legacy,
                load_consumer_data(
                    artifact,
                    expected_kind=ArtifactKind.SOURCE_DIGEST,
                    allow_legacy_v01=True,
                ),
            )
            with self.assertRaises(ConsumerContractError):
                load_consumer_data(
                    artifact,
                    expected_kind=ArtifactKind.SOURCE_DIGEST,
                )

            for payload in invalid_payloads:
                artifact.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ConsumerContractError):
                    load_consumer_data(
                        artifact,
                        expected_kind=ArtifactKind.SOURCE_DIGEST,
                        allow_legacy_v01=True,
                    )

    def test_previous_dossier_workflow_normalizes_core_data_and_keeps_versions(self):
        current = strict_current_core_payloads()
        legacy = raw_v01_provenance_fixtures(
            source_path="src/replacement.c",
            source_sha256="2" * 64,
            function_name="Replacement",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = Path(temp_dir) / "reports"
            reports.mkdir()
            generations: dict[Path, tuple[bytes, bytes]] = {}
            for kind, payload in current.items():
                artifact_path = reports / f"{kind}.json"
                saved_bytes = json.dumps(
                    payload,
                    separators=(",", ":"),
                ).encode("utf-8")
                replacement_bytes = json.dumps(legacy[kind]).encode("utf-8")
                artifact_path.write_bytes(saved_bytes)
                generations[artifact_path.resolve()] = (
                    saved_bytes,
                    replacement_bytes,
                )
            dossier_path = reports / "function_dossier.json"
            dossier_path.write_text(
                json.dumps(
                    {
                        kind: {"json": f"{kind}.json"}
                        for kind in (
                            "source_digest",
                            "function_location",
                            "function_signature",
                        )
                    }
                ),
                encoding="utf-8",
            )

            read_counts: dict[Path, int] = {}
            with mock.patch.object(
                Path,
                "open",
                new=_competing_open(generations, read_counts),
            ):
                dossier, payloads, artifact_paths = _payloads_from_previous_dossier(
                    dossier_path
                )
                snapshot = _snapshot_from_previous_dossier(
                    "Control_Update",
                    dossier,
                    payloads,
                    artifact_paths,
                )

        for kind, envelope in current.items():
            artifact_path = artifact_paths[kind]
            saved_bytes = generations[artifact_path][0]
            self.assertEqual(1, read_counts[artifact_path])
            self.assertEqual(envelope["data"], payloads[kind])
            self.assertEqual("1.0.0", snapshot.artifacts[kind].schema_version)
            self.assertEqual(
                hashlib.sha256(saved_bytes).hexdigest(),
                snapshot.artifacts[kind].sha256,
            )

    def test_partial_dossier_snapshot_overlays_fallback_metadata_and_artifact_union(self):
        source_payload = raw_v01_provenance_fixtures(
            source_path="src/dossier.c",
            source_sha256="2" * 64,
            function_name="Control_Update",
        )["source_digest"]
        build_context = {
            "configuration": "Win32 Debug",
            "defines": ["DOSSIER=1"],
        }
        dossier_created_at = "2026-07-15T12:34:56+00:00"
        fallback_source = SnapshotArtifact(
            artifact_kind="source_digest",
            path=Path("reports/fallback_source_digest.json"),
            sha256="a" * 64,
            schema_version="0.1",
            exists=True,
        )
        fallback_global = SnapshotArtifact(
            artifact_kind="global_access",
            path=Path("reports/fallback_global_access.json"),
            sha256="b" * 64,
            schema_version="0.1",
            exists=True,
        )
        fallback = AnalysisSnapshot(
            snapshot_id="previous",
            function_name="Control_Update",
            source_path=Path("src/fallback.c"),
            source_sha256="f" * 64,
            build_context_hash="c" * 64,
            created_at="2026-07-14T00:00:00+00:00",
            artifacts={
                "source_digest": fallback_source,
                "global_access": fallback_global,
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            reports = Path(temp_dir) / "reports"
            reports.mkdir()
            source_path = (reports / "source_digest.json").resolve()
            source_bytes = json.dumps(source_payload).encode("utf-8")
            source_path.write_bytes(source_bytes)
            source_dossier_path = reports / "source_dossier.json"
            source_dossier_path.write_text(
                json.dumps(
                    {
                        "source_digest": {"json": "source_digest.json"},
                        "build_context": build_context,
                        "created_at": dossier_created_at,
                    }
                ),
                encoding="utf-8",
            )
            dossier, payloads, artifact_paths = _payloads_from_previous_dossier(
                source_dossier_path
            )
            overlaid = _snapshot_from_previous_dossier(
                "Control_Update",
                dossier,
                payloads,
                artifact_paths,
                fallback_snapshot=fallback,
            )

            global_path = (reports / "global_access.json").resolve()
            global_bytes = json.dumps(
                {"schema_version": "0.1", "globals": [{"name": "g_mode"}]}
            ).encode("utf-8")
            global_path.write_bytes(global_bytes)
            metadata_free_dossier_path = reports / "metadata_free_dossier.json"
            metadata_free_dossier_path.write_text(
                json.dumps({"global_access": {"json": "global_access.json"}}),
                encoding="utf-8",
            )
            (
                metadata_free_dossier,
                metadata_free_payloads,
                metadata_free_paths,
            ) = _payloads_from_previous_dossier(metadata_free_dossier_path)
            inherited = _snapshot_from_previous_dossier(
                "Control_Update",
                metadata_free_dossier,
                metadata_free_payloads,
                metadata_free_paths,
                fallback_snapshot=fallback,
            )

        self.assertEqual(
            {"source_digest", "global_access"},
            set(overlaid.artifacts),
        )
        self.assertEqual(fallback_global, overlaid.artifacts["global_access"])
        source_generation = artifact_paths.generations["source_digest"]
        self.assertEqual(source_path, overlaid.artifacts["source_digest"].path)
        self.assertEqual(
            source_generation.sha256,
            overlaid.artifacts["source_digest"].sha256,
        )
        self.assertEqual(
            source_generation.schema_version,
            overlaid.artifacts["source_digest"].schema_version,
        )
        self.assertEqual(Path("src/dossier.c"), overlaid.source_path)
        self.assertEqual("2" * 64, overlaid.source_sha256)
        self.assertEqual(
            hashlib.sha256(
                json.dumps(
                    build_context,
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest(),
            overlaid.build_context_hash,
        )
        self.assertEqual(dossier_created_at, overlaid.created_at)

        self.assertEqual(fallback.source_path, inherited.source_path)
        self.assertEqual(fallback.source_sha256, inherited.source_sha256)
        self.assertEqual(fallback.build_context_hash, inherited.build_context_hash)
        self.assertEqual(fallback.created_at, inherited.created_at)
        self.assertEqual(fallback_source, inherited.artifacts["source_digest"])
        self.assertEqual(global_path, inherited.artifacts["global_access"].path)
        self.assertEqual(
            metadata_free_paths.generations["global_access"].sha256,
            inherited.artifacts["global_access"].sha256,
        )

    def test_snapshot_exclusions_omit_provided_kinds_and_keep_other_warnings(self):
        source_payload = raw_v01_provenance_fixtures(
            source_path="src/control.c",
            source_sha256=SOURCE_SHA256,
            function_name="Control_Update",
        )["source_digest"]
        excluded_kinds = {"source_digest", "function_signature"}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            (reports / "source_digest.json").write_text(
                json.dumps(source_payload),
                encoding="utf-8",
            )
            (reports / "function_signature.json").write_text(
                "{not json",
                encoding="utf-8",
            )

            snapshot, warnings, payloads = build_analysis_snapshot(
                "previous",
                root,
                "Control_Update",
                exclude_kinds=excluded_kinds,
            )

        self.assertTrue(excluded_kinds.isdisjoint(snapshot.artifacts))
        self.assertTrue(excluded_kinds.isdisjoint(payloads))
        self.assertFalse(
            any(warning.related_artifact in excluded_kinds for warning in warnings),
            warnings,
        )
        self.assertIn("function_location", snapshot.artifacts)
        self.assertFalse(snapshot.artifacts["function_location"].exists)
        self.assertTrue(
            any(
                warning.code == "previous_artifact_missing"
                and warning.related_artifact == "function_location"
                for warning in warnings
            ),
            warnings,
        )

    def test_workflow_does_not_import_private_test_spec_snapshot_parser(self):
        self.assertFalse(hasattr(reanalysis_workflow, "_test_spec_snapshot_from_bytes"))

    def test_dossier_test_spec_cache_uses_one_public_snapshot_generation(self):
        payload = valid_test_spec_payload()
        saved_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = Path(temp_dir) / "reports"
            reports.mkdir()
            test_spec_path = (reports / "test_spec.json").resolve()
            test_spec_path.write_bytes(saved_bytes)
            dossier_path = reports / "function_dossier.json"
            dossier_path.write_text(
                json.dumps({"test_spec": {"json": "test_spec.json"}}),
                encoding="utf-8",
            )
            read_counts: dict[Path, int] = {}

            with mock.patch.object(
                Path,
                "open",
                new=_competing_open(
                    {test_spec_path: (saved_bytes, b"{not json")},
                    read_counts,
                ),
            ):
                _, dossier_payloads, artifact_paths = (
                    _payloads_from_previous_dossier(dossier_path)
                )
                spec = reanalysis_workflow._previous_test_spec(
                    test_spec_path,
                    artifact_paths,
                )

        self.assertEqual(1, read_counts[test_spec_path])
        self.assertEqual(payload["data"], dossier_payloads["test_case_design"])
        self.assertEqual(payload, spec.to_payload())
        generation = artifact_paths.generations["test_spec"]
        self.assertEqual(saved_bytes, generation.raw_bytes)
        self.assertEqual("1.1.0", generation.schema_version)
        self.assertEqual(hashlib.sha256(saved_bytes).hexdigest(), generation.sha256)

    def test_explicit_test_spec_missing_and_invalid_keep_contract_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            invalid_path = root / "invalid.json"
            invalid_path.write_bytes(b"{not json")
            for label, path in (
                ("missing", root / "missing.json"),
                ("invalid", invalid_path),
            ):
                with self.subTest(label=label):
                    caught = None
                    try:
                        reanalysis_workflow._previous_test_spec(path, {})
                    except Exception as error:  # noqa: BLE001 - assert public boundary
                        caught = error
                    self.assertIsInstance(caught, TestSpecContractError)
                    self.assertIn(
                        "parse_error",
                        {item.code for item in caught.violations},
                    )

    def test_partial_dossier_overlays_without_losing_fallbacks_or_warnings(self):
        fixture_root = REPO_ROOT / "tests" / "fixtures" / "vc6_project"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            product = temp / "product"
            shutil.copytree(fixture_root, product)
            out_dir = temp / "Control_Update"
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(REPO_ROOT / "src")
            analyzed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unit_test_runner",
                    "--json",
                    "analyze-function",
                    "--workspace",
                    str(product),
                    "--dsw",
                    str(product / "Product.dsw"),
                    "--source",
                    "src/control.c",
                    "--function",
                    "Control_Update",
                    "--configuration",
                    "Win32 Debug",
                    "--project",
                    "Control",
                    "--out",
                    str(out_dir),
                ],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, analyzed.returncode, analyzed.stdout)

            reports = out_dir / "reports"
            fallback_global = json.loads(
                (reports / "global_access.json").read_text(encoding="utf-8")
            )
            fallback_calls = json.loads(
                (reports / "call_report.json").read_text(encoding="utf-8")
            )
            (reports / "boundary_equivalence_candidates.json").write_text(
                "{not json",
                encoding="utf-8",
            )
            partial_dossier = reports / "partial_function_dossier.json"
            partial_dossier.write_text(
                json.dumps({"source_digest": {"json": "source_digest.json"}}),
                encoding="utf-8",
            )
            source_digest_path = (reports / "source_digest.json").resolve()
            saved_bytes = source_digest_path.read_bytes()
            replacement = raw_v01_provenance_fixtures(
                source_path="src/replacement.c",
                source_sha256="2" * 64,
                function_name="Replacement",
            )["source_digest"]
            replacement_bytes = json.dumps(replacement).encode("utf-8")
            read_counts: dict[Path, int] = {}

            with (
                mock.patch.object(
                    Path,
                    "open",
                    new=_competing_open(
                        {source_digest_path: (saved_bytes, replacement_bytes)},
                        read_counts,
                    ),
                ),
                mock.patch(
                    "unit_test_runner.reanalysis.workflow.compare_dependencies",
                    wraps=reanalysis_workflow.compare_dependencies,
                ) as compared_dependencies,
            ):
                reanalysis_workflow.reanalyze_function_workflow(
                    product,
                    product / "Product.dsw",
                    "src/control.c",
                    "Control_Update",
                    "Win32 Debug",
                    out_dir,
                    project_name="Control",
                    previous_dossier_path=partial_dossier,
                    previous_test_case_design_path=reports / "test_spec.json",
                )

            previous_global, _, previous_calls, _ = (
                compared_dependencies.call_args.args[:4]
            )
            impact = json.loads(
                (reports / "change_impact_report.json").read_text(encoding="utf-8")
            )

        self.assertEqual(1, read_counts[source_digest_path])
        self.assertEqual(fallback_global, previous_global)
        self.assertEqual(fallback_calls, previous_calls)
        self.assertTrue(
            any(
                warning["code"] == "artifact_parse_failed"
                and warning.get("related_artifact")
                == "boundary_equivalence_candidates"
                for warning in impact["warnings"]
            ),
            impact["warnings"],
        )


if __name__ == "__main__":
    unittest.main()
