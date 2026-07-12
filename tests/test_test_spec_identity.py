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
    validate_test_spec,
)

from tests.test_test_spec_cli import create_workspace


class TestSpecIdentityTests(unittest.TestCase):
    def test_coexisting_roots_select_newest_source_consistent_analysis_not_presence_only(self):
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
            self.assertEqual("reports/function_signature.json", context.generated_from[0].path)

            reanalysis.write_bytes(top.read_bytes())
            os.utime(reanalysis, (now + 10, now + 10))
            context = build_current_artifact_context(workspace, spec)
            self.assertEqual("reports/reanalysis/current/function_signature.json", context.generated_from[0].path)

            os.utime(top, (now + 20, now + 20))
            context = build_current_artifact_context(workspace, spec)
            self.assertEqual("reports/function_signature.json", context.generated_from[0].path)

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

            context = build_current_artifact_context(workspace, spec)
            codes = {item.code for item in validate_test_spec(spec, current_context=context)}

            self.assertIn("stale_generated_from", codes)
            self.assertEqual("function_signature", context.generated_from[0].artifact_kind)
            self.assertEqual("reports/function_signature.json", context.generated_from[0].path)


if __name__ == "__main__":
    unittest.main()
