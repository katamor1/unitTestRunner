from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.spec_support import write_test_input_form_fixture

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


class TestInputFormCliTests(unittest.TestCase):
    def test_get_and_apply_form_use_canonical_test_spec(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            query = run_module(
                "--json",
                "get-test-input-form",
                "--workspace",
                str(fixture.workspace),
            )
            self.assertEqual(0, query.returncode, query.stderr)
            envelope = json.loads(query.stdout)
            self.assertEqual("passed", envelope["data"]["outcome"])
            form = envelope["data"]["details"]
            self.assertEqual("1.0", form["schema_version"])
            self.assertGreater(form["summary"]["attention_count"], 0)
            self.assertTrue(form["cases"])

            blocking = [
                item
                for case in form["cases"]
                for item in case["items"]
                if item["blocking"]
            ]
            self.assertTrue(blocking)
            changes = []
            for item in blocking:
                values = {}
                for control in item["controls"]:
                    if not control["required_for_confirmation"]:
                        continue
                    suggestions = control["suggestions"]
                    current = control["value"]
                    unresolved = (
                        not isinstance(current, str)
                        or not current.strip()
                        or current.strip().upper().startswith(("TBD", "TODO", "UNKNOWN", "UNRESOLVED"))
                    )
                    values[control["name"]] = (
                        suggestions[0]["value"] if suggestions else ("0" if unresolved else current)
                    )
                changes.append(
                    {
                        "item_id": item["item_id"],
                        "subject_fingerprint": item["subject_fingerprint"],
                        "values": values,
                        "confirmed": True,
                    }
                )
            request_path = fixture.workspace / "changes.json"
            request_path.write_text(
                json.dumps({"schema_version": "1.0", "changes": changes}),
                encoding="utf-8",
            )
            before = fixture.canonical_path.read_bytes()
            applied = run_module(
                "--json",
                "apply-test-input-form",
                "--workspace",
                str(fixture.workspace),
                "--input",
                str(request_path),
                "--expected-revision",
                str(form["revision"]),
            )
            self.assertEqual(0, applied.returncode, applied.stderr)
            result = json.loads(applied.stdout)
            details = result["data"]["details"]
            self.assertEqual(form["revision"] + 1, details["revision"])
            self.assertEqual(len(changes), details["updated_item_count"])
            self.assertIn(fixture.unresolved_case_id, details["promoted_case_ids"])
            self.assertNotEqual(before, fixture.canonical_path.read_bytes())
            self.assertEqual(
                {"test_spec", "test_spec_markdown", "test_spec_csv"},
                {item["artifact_kind"] for item in result["data"]["artifacts"]},
            )

    def test_summary_only_omits_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            completed = run_module(
                "--json",
                "get-test-input-form",
                "--workspace",
                str(fixture.workspace),
                "--summary-only",
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            details = json.loads(completed.stdout)["data"]["details"]
            self.assertNotIn("cases", details)

    def test_revision_conflict_preserves_error_code_and_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            form = json.loads(
                run_module(
                    "--json",
                    "get-test-input-form",
                    "--workspace",
                    str(fixture.workspace),
                ).stdout
            )["data"]["details"]
            item = form["cases"][0]["items"][0]
            request_path = fixture.workspace / "changes.json"
            request_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "changes": [
                            {
                                "item_id": item["item_id"],
                                "subject_fingerprint": item["subject_fingerprint"],
                                "values": {},
                                "confirmed": False,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            before = fixture.canonical_path.read_bytes()
            completed = run_module(
                "--json",
                "apply-test-input-form",
                "--workspace",
                str(fixture.workspace),
                "--input",
                str(request_path),
                "--expected-revision",
                str(form["revision"] + 1),
            )
            self.assertNotEqual(0, completed.returncode)
            payload = json.loads(completed.stdout)
            self.assertEqual(
                "test_input_revision_conflict",
                payload["data"]["errors"][0]["code"],
            )
            self.assertEqual(before, fixture.canonical_path.read_bytes())

    def test_oversized_request_is_rejected_before_json_parsing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = write_test_input_form_fixture(Path(temp_dir))
            request_path = fixture.workspace / "large.json"
            request_path.write_bytes(b"{" + b"x" * (4 * 1024 * 1024 + 1))
            completed = run_module(
                "--json",
                "apply-test-input-form",
                "--workspace",
                str(fixture.workspace),
                "--input",
                str(request_path),
                "--expected-revision",
                "1",
            )
            self.assertNotEqual(0, completed.returncode)
            payload = json.loads(completed.stdout)
            self.assertEqual("test_input_form_invalid", payload["data"]["errors"][0]["code"])


if __name__ == "__main__":
    unittest.main()
