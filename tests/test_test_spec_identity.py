from __future__ import annotations

import json
import os
import time
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.test_spec import (
    ArtifactReference,
    TestSpec,
    build_current_artifact_context,
)

from tests.test_test_spec_cli import create_workspace


class TestSpecIdentityTests(unittest.TestCase):
    def test_coexisting_roots_follow_saved_provenance_not_mtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            spec_path = create_workspace(workspace)
            spec = TestSpec.from_payload(json.loads(spec_path.read_text(encoding="utf-8")))
            top = workspace / "reports" / "function_signature.json"
            current_dir = workspace / "reports" / "reanalysis" / "current"
            current_dir.mkdir(parents=True)
            stale = json.loads(top.read_text(encoding="utf-8"))
            stale["source"]["sha256"] = "9" * 64
            reanalysis = current_dir / "function_signature.json"
            reanalysis.write_text(json.dumps(stale), encoding="utf-8")
            now = time.time()
            os.utime(top, (now - 20, now - 20))
            os.utime(reanalysis, (now, now))

            context = build_current_artifact_context(workspace, spec)
            signature_reference = next(
                item
                for item in context.generated_from
                if item.artifact_kind == "function_signature"
            )
            self.assertEqual("reports/function_signature.json", signature_reference.path)

            reanalysis.write_bytes(top.read_bytes())
            os.utime(reanalysis, (now + 10, now + 10))
            context = build_current_artifact_context(workspace, spec)
            signature_reference = next(
                item
                for item in context.generated_from
                if item.artifact_kind == "function_signature"
            )
            self.assertEqual("reports/function_signature.json", signature_reference.path)

            os.utime(top, (now + 20, now + 20))
            context = build_current_artifact_context(workspace, spec)
            signature_reference = next(
                item
                for item in context.generated_from
                if item.artifact_kind == "function_signature"
            )
            self.assertEqual("reports/function_signature.json", signature_reference.path)

    def test_context_does_not_trust_redirected_spec_provenance_path_or_kind(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            spec_path = create_workspace(workspace)
            canonical = json.loads(spec_path.read_text(encoding="utf-8"))
            redirected = workspace / "reports" / "redirected.json"
            redirected.write_bytes((workspace / "reports" / "function_signature.json").read_bytes())
            canonical["data"]["generated_from"] = [
                ArtifactReference(
                    "call_report",
                    "reports/redirected.json",
                    canonical["data"]["generated_from"][0]["sha256"],
                ).to_dict()
            ]
            spec = TestSpec.from_payload(canonical)

            with self.assertRaises(ValueError):
                build_current_artifact_context(workspace, spec)


if __name__ == "__main__":
    unittest.main()
