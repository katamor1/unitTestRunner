import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


def run_cli(*args, check=False):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def analyze(product: Path, output: Path):
    completed = run_cli(
        "--json", "analyze-function",
        "--workspace", str(product),
        "--dsw", str(product / "Product.dsw"),
        "--source", "src/control.c",
        "--function", "Control_Update",
        "--configuration", "Win32 Debug",
        "--project", "Control",
        "--out", str(output),
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout + completed.stderr)


def reanalyze(product: Path, output: Path):
    return run_cli(
        "--json", "reanalyze-function",
        "--workspace", str(product),
        "--dsw", str(product / "Product.dsw"),
        "--source", "src/control.c",
        "--function", "Control_Update",
        "--configuration", "Win32 Debug",
        "--project", "Control",
        "--out", str(output),
        "--previous-dossier", str(output / "reports" / "function_dossier.json"),
        "--previous-test-spec", str(output / "reports" / "test_spec.json"),
    )


class ReanalysisCliTests(unittest.TestCase):
    def test_reanalysis_writes_candidate_and_report_without_overwriting_canonical_test_spec(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            product = root / "product"
            shutil.copytree(FIXTURE_ROOT, product)
            output = root / "Control_Update"
            analyze(product, output)
            canonical = output / "reports" / "test_spec.json"
            before = canonical.read_bytes()
            source = product / "src" / "control.c"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    "sensor_value < SENSOR_MIN", "sensor_value <= SENSOR_MIN"
                ),
                encoding="utf-8",
            )

            completed = reanalyze(product, output)

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("passed", payload["outcome"])
            self.assertEqual(
                {"reanalysis_report", "test_spec"},
                {item["kind"] for item in payload["artifacts"]},
            )
            self.assertEqual(before, canonical.read_bytes())
            report = json.loads((output / "reports" / "reanalysis_report.json").read_text(encoding="utf-8"))
            self.assertEqual("reanalysis_report", report["artifact_kind"])
            self.assertTrue(report["data"]["change_impact"]["source_changes"])
            candidate = output / report["data"]["candidate"]["path"]
            self.assertTrue(candidate.is_file())
            self.assertEqual(
                hashlib.sha256(candidate.read_bytes()).hexdigest(),
                report["data"]["candidate"]["sha256"],
            )

    def test_apply_reanalysis_requires_exact_candidate_sha_and_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            product = root / "product"
            shutil.copytree(FIXTURE_ROOT, product)
            output = root / "Control_Update"
            analyze(product, output)
            source = product / "src" / "control.c"
            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            completed = reanalyze(product, output)
            self.assertEqual(0, completed.returncode, completed.stderr)
            report = json.loads((output / "reports" / "reanalysis_report.json").read_text(encoding="utf-8"))
            candidate_info = report["data"]["candidate"]
            candidate = output / candidate_info["path"]
            canonical = output / "reports" / "test_spec.json"
            before = canonical.read_bytes()
            revision = json.loads(before)["data"]["revision"]

            rejected = run_cli(
                "--json", "apply-reanalysis", "--workspace", str(output),
                "--candidate", str(candidate), "--candidate-sha256", "0" * 64,
                "--expected-revision", str(revision),
            )
            self.assertNotEqual(0, rejected.returncode)
            self.assertEqual(before, canonical.read_bytes())

            applied = run_cli(
                "--json", "apply-reanalysis", "--workspace", str(output),
                "--candidate", str(candidate),
                "--candidate-sha256", candidate_info["sha256"],
                "--expected-revision", str(revision),
            )
            self.assertEqual(0, applied.returncode, applied.stderr)
            envelope = json.loads(applied.stdout)
            self.assertEqual("passed", envelope["outcome"])
            self.assertEqual(["test_spec"], [item["kind"] for item in envelope["artifacts"]])
            self.assertEqual(revision + 1, json.loads(canonical.read_text(encoding="utf-8"))["data"]["revision"])


if __name__ == "__main__":
    unittest.main()
