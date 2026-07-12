from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.spec_support import write_canonical_test_spec


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
    source.write_text(
        "int Control_Update(int mode) { return mode; }\n",
        encoding="utf-8",
    )
    return write_canonical_test_spec(
        root,
        source_path="src/control.c",
        function_name="Control_Update",
        test_case_id="tc-control-update-001",
        expected_expression="OK",
        function_fields={
            "header_text_raw": "int Control_Update(int mode)",
            "header_text_normalized": "int Control_Update(int mode)",
        },
    )


class TestSpecCliTests(unittest.TestCase):
    def test_get_and_revision_checked_update_use_cli_envelope_and_truthful_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            create_workspace(workspace)
            get_result = run_module(
                "--json", "get-test-spec", "--workspace", str(workspace)
            )

            self.assertEqual(0, get_result.returncode, get_result.stderr)
            get_payload = json.loads(get_result.stdout)
            self.assertEqual("passed", get_payload["data"]["outcome"])
            self.assertEqual(1, get_payload["data"]["details"]["revision"])
            self.assertEqual([], get_payload["data"]["artifacts"])

            patch_path = workspace / "patch.json"
            patch_path.write_text(
                json.dumps(
                    {
                        "operations": [
                            {
                                "op": "replace",
                                "case_id": "tc-control-update-001",
                                "path": "/title",
                                "value": "CLI updated",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            update_result = run_module(
                "--json",
                "update-test-spec",
                "--workspace",
                str(workspace),
                "--patch",
                str(patch_path),
                "--expected-revision",
                "1",
            )

            self.assertEqual(0, update_result.returncode, update_result.stderr)
            update_payload = json.loads(update_result.stdout)
            self.assertEqual("passed", update_payload["data"]["outcome"])
            self.assertEqual(2, update_payload["data"]["details"]["revision"])
            self.assertTrue(
                update_payload["data"]["details"]["views_written_by_operation"]
            )
            artifacts = update_payload["data"]["artifacts"]
            self.assertEqual(
                {"test_spec", "test_spec_markdown", "test_spec_csv"},
                {item["artifact_kind"] for item in artifacts},
            )
            artifact = next(
                item for item in artifacts if item["artifact_kind"] == "test_spec"
            )
            self.assertEqual("reports/test_spec.json", artifact["path"])
            for produced in artifacts:
                self.assertEqual(
                    hashlib.sha256(
                        (workspace / produced["path"]).read_bytes()
                    ).hexdigest(),
                    produced["sha256"],
                )

    def test_stale_revision_and_malformed_patch_are_explicit_nonzero_errors_without_partial_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            spec_path = create_workspace(workspace)
            patch_path = workspace / "patch.json"
            patch_path.write_text(
                json.dumps(
                    {
                        "operations": [
                            {
                                "op": "replace",
                                "case_id": "missing",
                                "path": "/title",
                                "value": "x",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            before = spec_path.read_bytes()

            invalid = run_module(
                "--json",
                "update-test-spec",
                "--workspace",
                str(workspace),
                "--patch",
                str(patch_path),
                "--expected-revision",
                "1",
            )

            self.assertNotEqual(0, invalid.returncode)
            payload = json.loads(invalid.stdout)
            self.assertEqual("error", payload["data"]["outcome"])
            self.assertEqual("update-test-spec", payload["data"]["command"])
            self.assertEqual(before, spec_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
