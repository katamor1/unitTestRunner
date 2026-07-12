from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.test_spec import (
    ArtifactReference,
    CurrentArtifactContext,
    TestSpec,
    save_test_spec,
    signature_sha256,
    stable_function_id,
)

from tests.spec_support import copied_payload


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_module(*args: str):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def create_workspace(root: Path) -> Path:
    source = root / "src" / "control.c"
    source.parent.mkdir(parents=True)
    source.write_text("int Control_Update(int mode) { return mode; }\n", encoding="utf-8")
    reports = root / "reports"
    reports.mkdir()
    signature_payload = {
        "schema_version": "0.1",
        "source": {"path": "src/control.c", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "function": {"name": "Control_Update", "header_text_normalized": "int Control_Update(int mode)"},
        "warnings": [],
    }
    signature_path = reports / "function_signature.json"
    signature_path.write_text(json.dumps(signature_payload, indent=2) + "\n", encoding="utf-8")
    payload = copied_payload()
    function_id = stable_function_id("src/control.c", "Control_Update")
    payload["subject"] = {
        "function_id": function_id,
        "source_path": "src/control.c",
        "source_sha256": signature_payload["source"]["sha256"],
    }
    payload["data"]["source"] = dict(signature_payload["source"])
    payload["data"]["function"] = {
        "function_id": function_id,
        "name": "Control_Update",
        "signature_sha256": signature_sha256(signature_payload),
    }
    reference = ArtifactReference(
        artifact_kind="function_signature",
        path="reports/function_signature.json",
        sha256=hashlib.sha256(signature_path.read_bytes()).hexdigest(),
    )
    payload["data"]["generated_from"] = [reference.to_dict()]
    context = CurrentArtifactContext(
        source_path="src/control.c",
        source_sha256=signature_payload["source"]["sha256"],
        function_id=function_id,
        function_name="Control_Update",
        signature_sha256=signature_sha256(signature_payload),
        workspace_root=root,
        generated_from=(reference,),
    )
    save_test_spec(reports / "test_spec.json", TestSpec.from_payload(payload), expected_revision=None, current_context=context)
    return reports / "test_spec.json"


class TestSpecCliTests(unittest.TestCase):
    def test_get_and_revision_checked_update_use_cli_envelope_and_truthful_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            create_workspace(workspace)
            get_result = run_module("--json", "get-test-spec", "--workspace", str(workspace))

            self.assertEqual(0, get_result.returncode, get_result.stderr)
            get_payload = json.loads(get_result.stdout)
            self.assertEqual("passed", get_payload["data"]["outcome"])
            self.assertEqual(1, get_payload["data"]["details"]["revision"])
            self.assertEqual([], get_payload["data"]["artifacts"])

            patch_path = workspace / "patch.json"
            patch_path.write_text(
                json.dumps({"operations": [{"op": "replace", "case_id": "tc-control-update-001", "path": "/title", "value": "CLI updated"}]}),
                encoding="utf-8",
            )
            update_result = run_module(
                "--json", "update-test-spec", "--workspace", str(workspace),
                "--patch", str(patch_path), "--expected-revision", "1",
            )

            self.assertEqual(0, update_result.returncode, update_result.stderr)
            update_payload = json.loads(update_result.stdout)
            self.assertEqual("passed", update_payload["data"]["outcome"])
            self.assertEqual(2, update_payload["data"]["details"]["revision"])
            artifact = update_payload["data"]["artifacts"][0]
            self.assertEqual("test_spec", artifact["artifact_kind"])
            self.assertEqual("reports/test_spec.json", artifact["path"])
            self.assertEqual(hashlib.sha256((workspace / artifact["path"]).read_bytes()).hexdigest(), artifact["sha256"])

    def test_stale_revision_and_malformed_patch_are_explicit_nonzero_errors_without_partial_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            spec_path = create_workspace(workspace)
            patch_path = workspace / "patch.json"
            patch_path.write_text(json.dumps({"operations": [{"op": "replace", "case_id": "missing", "path": "/title", "value": "x"}]}), encoding="utf-8")
            before = spec_path.read_bytes()

            invalid = run_module(
                "--json", "update-test-spec", "--workspace", str(workspace),
                "--patch", str(patch_path), "--expected-revision", "1",
            )

            self.assertNotEqual(0, invalid.returncode)
            payload = json.loads(invalid.stdout)
            self.assertEqual("error", payload["data"]["outcome"])
            self.assertEqual("update-test-spec", payload["data"]["command"])
            self.assertEqual(before, spec_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
