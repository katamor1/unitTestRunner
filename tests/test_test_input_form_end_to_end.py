from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
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


def details(completed: subprocess.CompletedProcess[str]) -> dict:
    if completed.returncode != 0:
        raise AssertionError(
            f"command failed with {completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    envelope = json.loads(completed.stdout)
    if envelope["data"]["outcome"] != "passed":
        raise AssertionError(completed.stdout)
    return envelope["data"]["details"]


def resolved_value(control: dict) -> str:
    suggestions = control.get("suggestions") or []
    if suggestions:
        return str(suggestions[0]["value"])
    current = control.get("value")
    if isinstance(current, str) and current.strip() and not current.strip().upper().startswith(
        ("TBD", "TODO", "UNKNOWN", "UNRESOLVED")
    ):
        return current
    return "0"


class TestInputFormEndToEndTests(unittest.TestCase):
    def test_canonical_form_apply_harness_and_build_probe_flow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "Control_Update"
            analyze = details(
                run_module(
                    "--json",
                    "analyze-function",
                    "--workspace",
                    str(VC6_FIXTURE_ROOT),
                    "--dsw",
                    str(VC6_FIXTURE_ROOT / "Product.dsw"),
                    "--source",
                    "src/control.c",
                    "--function",
                    "Control_Update",
                    "--configuration",
                    "Win32 Debug",
                    "--project",
                    "Control",
                    "--phase",
                    "design",
                    "--out",
                    str(workspace),
                )
            )
            self.assertIn("test_spec", analyze)

            form = details(
                run_module(
                    "--json",
                    "get-test-input-form",
                    "--workspace",
                    str(workspace),
                )
            )
            self.assertGreater(form["summary"]["execution_blocking_count"], 0)

            changes = []
            for case in form["cases"]:
                for item in case["items"]:
                    if not item["blocking"]:
                        continue
                    values = {
                        control["name"]: resolved_value(control)
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
            self.assertTrue(changes)
            request_path = workspace / "test-input-changes.json"
            request_path.write_text(
                json.dumps({"schema_version": "1.0", "changes": changes}),
                encoding="utf-8",
            )

            applied = details(
                run_module(
                    "--json",
                    "apply-test-input-form",
                    "--workspace",
                    str(workspace),
                    "--input",
                    str(request_path),
                    "--expected-revision",
                    str(form["revision"]),
                )
            )
            self.assertEqual(0, applied["summary"]["execution_blocking_count"])
            self.assertTrue(applied["promoted_case_ids"])

            spec = details(
                run_module(
                    "--json",
                    "get-test-spec",
                    "--workspace",
                    str(workspace),
                )
            )
            self.assertEqual(applied["revision"], spec["revision"])
            promoted = set(applied["promoted_case_ids"])
            for unresolved in spec["test_spec"]["data"]["unresolved_items"]:
                if promoted.intersection(unresolved.get("related_test_case_ids") or []):
                    self.assertIs(False, unresolved.get("blocking"))

            reports = workspace / "reports"
            harness = details(
                run_module(
                    "--json",
                    "generate-harness-skeleton",
                    "--function-signature",
                    str(reports / "function_signature.json"),
                    "--global-access",
                    str(reports / "global_access.json"),
                    "--call-report",
                    str(reports / "call_report.json"),
                    "--test-spec",
                    str(reports / "test_spec.json"),
                    "--dependency-policy",
                    str(reports / "dependency_policy.json"),
                    "--out",
                    str(workspace),
                    "--overwrite",
                )
            )
            self.assertIn("harness_skeleton", harness)
            self.assertTrue((workspace / "generated" / "tests" / "test_Control_Update.c").is_file())

            probe = details(
                run_module(
                    "--json",
                    "build-probe",
                    "--workspace",
                    str(workspace),
                    "--dry-run",
                    "--overwrite",
                )
            )
            self.assertIn("build_workspace", probe)
            self.assertTrue((workspace / "build" / "Makefile").is_file())


if __name__ == "__main__":
    unittest.main()
