import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.contracts import ArtifactKind, ContractMode, load_artifact, validate_payload
from unit_test_runner.dossier.artifact_collector import collect_artifacts
from unit_test_runner.dossier.dossier_models import DossierArtifact
from unit_test_runner.dossier.dossier_validator import validate_artifacts
from unit_test_runner.dossier.finalizer import finalize_function_dossier
from tests.test_contract_validation import valid_function_dossier


SHA256 = "7b18e68b2afcf1b0f0a1b857c5d1fcb2cf9db4d1540d778a266dbeaa3aa176a8"


def valid_source_digest():
    return {
        "artifact_kind": "source_digest",
        "schema_version": "1.0.0",
        "producer": {
            "name": "unit-test-runner",
            "version": "0.1.0",
            "commit": "3aafd2b660b69f84be89a5797e1e66f8065bd80a",
        },
        "subject": {
            "function_id": "fn_control_update_7a32c11d",
            "source_path": "src/control.c",
            "source_sha256": SHA256,
        },
        "data": {
            "source": {
                "path": "src/control.c",
                "encoding": "utf-8",
                "newline": "lf",
                "sha256": SHA256,
                "line_count": 1,
                "warnings": [],
            },
            "masking": {"masked_source_path": None, "masked_ranges": []},
            "preprocessor": {"includes": [], "macros": [], "directives": []},
            "token_summary": {},
            "warnings": [],
            "tokens": [],
        },
        "extensions": {},
    }


def run_module(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class DossierContractStatusTests(unittest.TestCase):
    def test_v1_dossier_artifact_requires_contract_status_and_machine_severity(self):
        payload = valid_function_dossier()
        artifact = payload["data"]["artifact_index"][0]
        artifact["contract_status"] = "schema_error"
        artifact["contract_violations"] = [
            {
                "code": "required_property",
                "json_path": "$.data",
                "message": "A required property is missing.",
                "severity": "error",
            }
        ]
        self.assertEqual((), validate_payload(ArtifactKind.FUNCTION_DOSSIER, payload))

        for field in ("contract_status", "contract_violations"):
            with self.subTest(field=field):
                missing = copy.deepcopy(payload)
                missing["data"]["artifact_index"][0].pop(field)
                violations = validate_payload(ArtifactKind.FUNCTION_DOSSIER, missing)
                self.assertTrue(
                    any(
                        item.code == "required_property"
                        and item.json_path == "$.data.artifact_index[0]"
                        and field in item.message
                        for item in violations
                    )
                )

        localized = copy.deepcopy(payload)
        localized["data"]["artifact_index"][0]["contract_violations"][0][
            "severity"
        ] = "エラー"
        self.assertIn(
            ("invalid_enum", "$.data.artifact_index[0].contract_violations[0].severity"),
            {(item.code, item.json_path) for item in validate_payload(ArtifactKind.FUNCTION_DOSSIER, localized)},
        )

    def test_nested_array_instead_of_object_is_classified_without_consuming_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            reports.mkdir(parents=True)
            (reports / "function_signature.json").write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "function": [],
                    }
                ),
                encoding="utf-8",
            )

            try:
                dossier = finalize_function_dossier(
                    workspace,
                    function_name="Control_Update",
                )
            except Exception as error:  # pragma: no cover - regression guard
                self.fail(
                    "A schema-invalid nested shape must not reach dossier "
                    f"consumers: {error!r}"
                )

            signature = next(
                item
                for item in dossier.artifact_index
                if item.artifact_kind == "function_signature"
            )
            self.assertEqual("schema_error", signature.contract_status)
            self.assertTrue(
                any(
                    item.json_path == "$.data.function"
                    for item in signature.contract_violations
                )
            )

    def test_cross_artifact_mismatch_marks_valid_artifact_contract_stale(self):
        artifacts = [
            DossierArtifact(
                artifact_id=f"ART_{index:03d}_{kind}",
                artifact_kind=kind,
                path=Path(f"reports/{kind}.json"),
                exists=True,
                sha256=None,
                schema_version="1.0.0",
                produced_by_item="analysis",
                required_level="mvp1_required",
                contract_status="valid",
                contract_violations=[],
            )
            for index, kind in enumerate(
                ["source_digest", "function_location", "function_signature"],
                start=1,
            )
        ]
        payloads = {
            "source_digest": {
                "source": {"path": "src/control.c"},
                "function": {"name": "Control_Update"},
            },
            "function_location": {
                "source": {"path": "src/control.c"},
                "function": {"name": "Control_Update"},
            },
            "function_signature": {
                "source": {"path": "src/other.c"},
                "function": {"name": "Other_Function"},
            },
        }

        _name, _path, warnings, _blocked = validate_artifacts(
            artifacts,
            payloads,
            function_name="Control_Update",
        )

        signature = next(
            item
            for item in artifacts
            if item.artifact_kind == "function_signature"
        )
        self.assertTrue(signature.stale_candidate)
        self.assertEqual("stale", signature.contract_status)
        self.assertEqual(
            {"function_name_mismatch", "source_path_mismatch"},
            {warning.code for warning in warnings},
        )

    def test_valid_readable_artifact_is_stale_when_older_than_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            inputs = workspace / "input"
            reports.mkdir(parents=True)
            inputs.mkdir(parents=True)
            artifact_path = reports / "source_digest.json"
            artifact_path.write_text(
                json.dumps(valid_source_digest()),
                encoding="utf-8",
            )
            old_time = time.time() - 3600
            os.utime(artifact_path, (old_time, old_time))
            (inputs / "request.json").write_text("{}", encoding="utf-8")

            artifacts, payloads, _warnings = collect_artifacts(workspace)

            artifact = next(
                item
                for item in artifacts
                if item.artifact_kind == "source_digest"
            )
            self.assertEqual([], artifact.contract_violations)
            self.assertEqual("stale", artifact.contract_status)
            self.assertEqual("src/control.c", payloads["source_digest"]["source"]["path"])

    def test_strict_collection_reports_unsupported_artifact_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            reports.mkdir(parents=True)
            (reports / "source_digest.json").write_text(
                json.dumps({"schema_version": "0.1"}),
                encoding="utf-8",
            )

            artifacts, _payloads, _warnings = collect_artifacts(
                workspace,
                strict_schema_version=True,
            )

            artifact = next(
                item
                for item in artifacts
                if item.artifact_kind == "source_digest"
            )
            self.assertEqual("unsupported_version", artifact.contract_status)
            self.assertEqual(
                ["unsupported_version"],
                [item.code for item in artifact.contract_violations],
            )

    def test_parse_error_takes_precedence_over_staleness(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            inputs = workspace / "input"
            reports.mkdir(parents=True)
            inputs.mkdir(parents=True)
            artifact_path = reports / "source_digest.json"
            artifact_path.write_text("{", encoding="utf-8")
            old_time = time.time() - 3600
            os.utime(artifact_path, (old_time, old_time))
            (inputs / "request.json").write_text("{}", encoding="utf-8")

            artifacts, _payloads, _warnings = collect_artifacts(workspace)

            artifact = next(
                item
                for item in artifacts
                if item.artifact_kind == "source_digest"
            )
            self.assertTrue(artifact.stale_candidate)
            self.assertEqual("parse_error", artifact.contract_status)
            self.assertEqual(
                ["parse_error"],
                [item.code for item in artifact.contract_violations],
            )

    def test_strict_mode_accepts_each_artifact_kinds_current_version(self):
        artifacts = [
            DossierArtifact(
                artifact_id=f"ART_{index:03d}_{kind}",
                artifact_kind=kind,
                path=Path(f"reports/{kind}.json"),
                exists=True,
                sha256=None,
                schema_version=version,
                produced_by_item="analysis",
                required_level="mvp1_required",
                contract_status="valid",
                contract_violations=[],
            )
            for index, (kind, version) in enumerate(
                [
                    ("source_digest", "1.0.0"),
                    ("function_location", "2.0.0"),
                    ("function_signature", "3.1.0"),
                ],
                start=1,
            )
        ]

        _function_name, _source_path, warnings, blocked_reasons = (
            validate_artifacts(
                artifacts,
                payloads={},
                function_name="Control_Update",
                strict_schema_version=True,
            )
        )

        self.assertEqual([], blocked_reasons)
        self.assertNotIn(
            "schema_version_mismatch",
            {warning.code for warning in warnings},
        )

    def test_malformed_object_shape_becomes_schema_error_and_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            reports.mkdir(parents=True)
            (reports / "source_digest.json").write_text(
                json.dumps([]),
                encoding="utf-8",
            )

            result = run_module(
                "--json",
                "finalize-dossier",
                "--workspace",
                str(workspace),
                "--function",
                "Control_Update",
            )
            self.assertNotEqual(10, result.returncode, result.stderr)
            self.assertEqual(0, result.returncode, result.stderr)

            try:
                dossier = finalize_function_dossier(
                    workspace,
                    function_name="Control_Update",
                )
            except Exception as error:  # pragma: no cover - regression guard
                self.fail(
                    "Malformed artifact shape must be classified, not raised as an "
                    f"internal error: {error!r}"
                )

            artifact = next(
                item
                for item in dossier.artifact_index
                if item.artifact_kind == "source_digest"
            )
            self.assertEqual("schema_error", artifact.contract_status)
            self.assertEqual(
                [
                    {
                        "code": "schema_error",
                        "json_path": "$",
                        "message": "Artifact root must be a JSON object.",
                        "severity": "error",
                    }
                ],
                [
                    {
                        "code": item.code,
                        "json_path": item.json_path,
                        "message": item.message,
                        "severity": item.severity,
                    }
                    for item in artifact.contract_violations
                ],
            )
            self.assertTrue(dossier.readiness.blocked)
            self.assertTrue(
                any(
                    "source_digest" in reason
                    and "schema_error" in reason
                    and "$" in reason
                    for reason in dossier.readiness.blocked_reasons
                )
            )
            self.assertTrue(
                any(
                    warning.code == "schema_error"
                    and warning.related_artifact_id == artifact.artifact_id
                    for warning in dossier.warnings
                )
            )

            payload = json.loads(
                (reports / "function_dossier.json").read_text(encoding="utf-8")
            )
            indexed = next(
                item
                for item in payload["artifact_index"]
                if item["artifact_kind"] == "source_digest"
            )
            self.assertEqual("schema_error", indexed["contract_status"])
            self.assertEqual("$", indexed["contract_violations"][0]["json_path"])

            loaded = load_artifact(
                reports / "function_dossier.json",
                expected_kind=ArtifactKind.FUNCTION_DOSSIER,
                mode=ContractMode.COMPATIBLE,
            )
            self.assertNotIn(
                "unknown_property",
                {item.code for item in loaded.violations},
            )


if __name__ == "__main__":
    unittest.main()
