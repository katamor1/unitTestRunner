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
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dossier import analyze_function_workflow
from unit_test_runner.dossier.finalizer import finalize_function_dossier, prepare_review_from_dossier


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


class DossierFinalizerStep17Tests(unittest.TestCase):
    def prepare_workspace(self, temp_dir):
        out_dir = Path(temp_dir) / "Control_Update"
        analyze_function_workflow(
            VC6_FIXTURE_ROOT,
            VC6_FIXTURE_ROOT / "Product.dsw",
            "src/control.c",
            "Control_Update",
            "Win32 Debug",
            out_dir,
            "Control",
        )
        return out_dir

    def test_finalize_workspace_generates_review_artifacts_and_traceability(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)

            dossier = finalize_function_dossier(workspace)
            payload = dossier.to_dict()

            self.assertEqual("Control_Update", payload["function"]["name"])
            self.assertIn(payload["function"]["status"], {"ready_for_review", "evidence_ready", "partial"})
            self.assertEqual("mvp4_execution_evidence", payload["readiness"]["mvp_level"])
            self.assertTrue(payload["readiness"]["ready_for_review"])
            self.assertTrue(payload["artifact_index"])
            self.assertTrue(payload["traceability"])
            self.assertTrue(payload["review_items"])
            self.assertTrue(payload["unresolved_items"])
            self.assertTrue(payload["next_actions"])
            self.assertIn("function_signature", {item["artifact_kind"] for item in payload["artifact_index"]})

            reports = workspace / "reports"
            for name in [
                "function_dossier.json",
                "function_dossier.md",
                "dossier_manifest.json",
                "traceability_matrix.csv",
                "review_checklist.md",
                "unresolved_items.md",
                "next_actions.md",
            ]:
                self.assertTrue((reports / name).exists(), name)

            markdown = (reports / "function_dossier.md").read_text(encoding="utf-8")
            self.assertIn("# Function Dossier: Control_Update", markdown)
            self.assertIn("## Traceability", markdown)
            traceability_csv = (reports / "traceability_matrix.csv").read_text(encoding="utf-8")
            self.assertIn("source_kind,source_id,relation,target_kind,target_id", traceability_csv)

    def test_finalize_handles_mvp1_partial_and_blocked_missing_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "mvp1"
            reports = workspace / "reports"
            reports.mkdir(parents=True)
            (reports / "source_digest.json").write_text(json.dumps({"schema_version": "0.1", "source": {"path": "src/control.c"}, "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_location.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update"}, "location": {"start_line": 10, "end_line": 20}}), encoding="utf-8")
            (reports / "function_signature.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update", "signature": "int Control_Update(void)"}}), encoding="utf-8")

            dossier = finalize_function_dossier(workspace, function_name="Control_Update")

            self.assertEqual("mvp1_analysis_only", dossier.readiness.mvp_level)
            self.assertTrue(dossier.readiness.ready_for_review)
            self.assertFalse(dossier.readiness.blocked)
            self.assertTrue(any(warning.code == "missing_artifact" for warning in dossier.warnings))

            blocked_workspace = Path(temp_dir) / "blocked"
            (blocked_workspace / "reports").mkdir(parents=True)
            blocked = finalize_function_dossier(blocked_workspace, function_name="Control_Update")
            self.assertTrue(blocked.readiness.blocked)
            self.assertEqual("blocked", blocked.status)
            self.assertTrue(blocked.readiness.blocked_reasons)

    def test_finalize_warns_on_function_name_mismatch_and_prepare_review_regenerates_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "mismatch"
            reports = workspace / "reports"
            reports.mkdir(parents=True)
            (reports / "source_digest.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_location.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_signature.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "test_case_draft.json").write_text(json.dumps({"schema_version": "0.1", "function": {"name": "Other_Function"}, "test_cases": []}), encoding="utf-8")

            dossier = finalize_function_dossier(workspace, function_name="Control_Update")
            self.assertTrue(any(warning.code == "function_name_mismatch" for warning in dossier.warnings))

            paths = prepare_review_from_dossier(reports / "function_dossier.json", reports)
            self.assertTrue(paths["review_checklist"].exists())
            self.assertTrue(paths["unresolved_items"].exists())
            self.assertTrue(paths["next_actions"].exists())
            self.assertTrue(paths["traceability_matrix"].exists())

    def test_finalize_marks_source_mismatch_and_old_artifacts_as_stale_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "stale"
            reports = workspace / "reports"
            inputs = workspace / "input"
            reports.mkdir(parents=True)
            inputs.mkdir(parents=True)
            (inputs / "request.json").write_text(json.dumps({"source": "src/control.c", "function": "Control_Update"}), encoding="utf-8")
            (reports / "source_digest.json").write_text(json.dumps({"schema_version": "0.1", "source": {"path": "src/control.c"}, "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_location.json").write_text(json.dumps({"schema_version": "0.1", "source": {"path": "src/control.c"}, "function": {"name": "Control_Update"}}), encoding="utf-8")
            (reports / "function_signature.json").write_text(json.dumps({"schema_version": "0.1", "source": {"path": "src/other.c"}, "function": {"name": "Control_Update"}}), encoding="utf-8")
            old_time = time.time() - 3600
            os.utime(reports / "source_digest.json", (old_time, old_time))

            dossier = finalize_function_dossier(workspace, function_name="Control_Update")
            payload = dossier.to_dict()

            stale = {item["artifact_kind"]: item for item in payload["artifact_index"] if item["stale_candidate"]}
            self.assertIn("function_signature", stale)
            self.assertIn("source_digest", stale)
            warning_codes = {warning["code"] for warning in payload["warnings"]}
            self.assertIn("source_path_mismatch", warning_codes)
            self.assertIn("artifact_older_than_request", warning_codes)
            self.assertIn("modified_at", stale["source_digest"])

    def test_cli_finalize_prepare_review_and_analyze_function_step17(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)

            finalize = run_module("--json", "finalize-dossier", "--workspace", str(workspace))
            self.assertEqual(0, finalize.returncode, finalize.stderr)
            finalize_payload = json.loads(finalize.stdout)
            self.assertEqual("dossier_finalized", finalize_payload["status"])
            self.assertTrue(Path(finalize_payload["data"]["reports"]["function_dossier_md"]).exists())

            prepare = run_module("--json", "prepare-review", "--dossier", str(workspace / "reports" / "function_dossier.json"))
            self.assertEqual(0, prepare.returncode, prepare.stderr)
            prepare_payload = json.loads(prepare.stdout)
            self.assertEqual("review_prepared", prepare_payload["status"])

            out_dir = Path(temp_dir) / "AnalyzeFunctionStep17"
            full = run_module(
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
                "--out",
                str(out_dir),
                "--finalize-dossier",
            )
            self.assertEqual(0, full.returncode, full.stderr)
            full_payload = json.loads(full.stdout)
            self.assertEqual("dossier_finalized", full_payload["status"])
            self.assertIn("review", full_payload["data"])
            self.assertTrue((out_dir / "reports" / "review_checklist.md").exists())

            final_dossier_path = out_dir / "reports" / "function_dossier.json"
            final_dossier = json.loads(final_dossier_path.read_text(encoding="utf-8"))
            required = set(json.loads((REPO_ROOT / "schemas" / "function_dossier.schema.json").read_text(encoding="utf-8"))["required"])
            self.assertLessEqual(required, set(final_dossier))
            self.assertEqual("src/control.c", final_dossier["target"]["source"])
            self.assertEqual("Control_Update", final_dossier["target"]["function"])
            self.assertIn("defines", final_dossier["build_context"])
            self.assertIn("branch_coverage_items", final_dossier["test_design"])

            probe = run_module("--json", "build-probe", "--dossier", str(final_dossier_path), "--dry-run")
            self.assertEqual(0, probe.returncode, probe.stderr)
            self.assertIn("extracted", json.loads(probe.stdout)["data"]["command"])

            draft = run_module("--json", "generate-test-draft", "--dossier", str(final_dossier_path))
            self.assertEqual(0, draft.returncode, draft.stderr)
            self.assertEqual("test_case_draft_generated", json.loads(draft.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
