from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.spec_support import write_canonical_test_spec, write_test_input_form_fixture


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.test_input_form import build_test_input_form


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


def _resolved_value(control: dict) -> str:
    suggestions = control.get("suggestions") or []
    if suggestions:
        return str(suggestions[0]["value"])
    current = control.get("value")
    if isinstance(current, str) and current.strip() and not current.strip().upper().startswith(
        ("TBD", "TODO", "UNKNOWN", "UNRESOLVED")
    ):
        return current
    return "0"


def _change_request(form: dict) -> dict:
    changes = []
    for case in form["cases"]:
        for item in case["items"]:
            if not item["blocking"] or not item["editable"]:
                continue
            values = {
                control["name"]: _resolved_value(control)
                for control in item["controls"]
                if control["required_for_confirmation"]
            }
            changes.append(
                {
                    "item_id": item["item_id"],
                    "subject_fingerprint": item["subject_fingerprint"],
                    "values": values,
                    "confirmed": True,
                }
            )
    if not changes:
        raise AssertionError("fixture produced no editable blocking form items")
    return {"schema_version": "1.0", "changes": changes}


class TestSpecCliTests(unittest.TestCase):
    def test_get_and_revision_checked_apply_use_exact_envelopes_and_truthful_test_spec_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            fixture = write_test_input_form_fixture(workspace)
            form = build_test_input_form(workspace).to_dict()

            get_result = run_module(
                "--json", "get-test-input-form", "--workspace", str(workspace)
            )
            self.assertEqual(0, get_result.returncode, get_result.stderr)
            get_payload = json.loads(get_result.stdout)
            self.assertEqual("passed", get_payload["outcome"])
            self.assertEqual({"command", "outcome", "message", "artifacts", "diagnostics"}, set(get_payload))
            self.assertEqual(["test_spec"], [item["kind"] for item in get_payload["artifacts"]])
            form_path = workspace / "reports" / "test_input_form.json"
            self.assertTrue(form_path.is_file())
            self.assertEqual(
                form,
                json.loads(form_path.read_text(encoding="utf-8")),
            )
            self.assertIn("reports/test_input_form.json", get_payload["message"])

            request_path = workspace / "test-input-changes.json"
            request_path.write_text(json.dumps(_change_request(form)), encoding="utf-8")
            apply_result = run_module(
                "--json", "apply-test-input-form",
                "--workspace", str(workspace),
                "--input", str(request_path),
                "--expected-revision", str(form["revision"]),
            )

            self.assertEqual(0, apply_result.returncode, apply_result.stderr)
            apply_payload = json.loads(apply_result.stdout)
            self.assertEqual("passed", apply_payload["outcome"])
            self.assertEqual(["test_spec"], [item["kind"] for item in apply_payload["artifacts"]])
            artifact = apply_payload["artifacts"][0]
            self.assertEqual("reports/test_spec.json", artifact["path"])
            self.assertEqual(
                hashlib.sha256(fixture.canonical_path.read_bytes()).hexdigest(),
                artifact["sha256"],
            )
            self.assertEqual(form["revision"] + 1, json.loads(fixture.canonical_path.read_text(encoding="utf-8"))["data"]["revision"])

    def test_stale_revision_is_nonzero_and_never_partially_rewrites_test_spec(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            fixture = write_test_input_form_fixture(workspace)
            form = build_test_input_form(workspace).to_dict()
            request_path = workspace / "test-input-changes.json"
            request_path.write_text(json.dumps(_change_request(form)), encoding="utf-8")
            before = fixture.canonical_path.read_bytes()

            invalid = run_module(
                "--json", "apply-test-input-form",
                "--workspace", str(workspace),
                "--input", str(request_path),
                "--expected-revision", str(form["revision"] - 1),
            )

            self.assertNotEqual(0, invalid.returncode)
            payload = json.loads(invalid.stdout)
            self.assertEqual("error", payload["outcome"])
            self.assertEqual("apply-test-input-form", payload["command"])
            self.assertEqual(before, fixture.canonical_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
