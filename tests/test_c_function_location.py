import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.c_analyzer.function_location_writer import write_function_location
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.source_digest import build_source_digest


REPO_ROOT = Path(__file__).resolve().parents[1]
FUNCTION_SOURCE = REPO_ROOT / "tests" / "fixtures" / "c_sources" / "functions" / "function_cases.c"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


def run_module(*args):
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


class CFunctionLocationTests(unittest.TestCase):
    def digest(self):
        return build_source_digest(FUNCTION_SOURCE, {"defines": []})

    def test_locates_static_function_with_ranges_and_signature_preview(self):
        location = locate_function(self.digest(), "StaticFunction")

        self.assertEqual("found", location.status)
        selected = location.selected_candidate
        self.assertIsNotNone(selected)
        self.assertEqual("definition", selected.kind)
        self.assertEqual("high", selected.confidence)
        self.assertEqual("static", selected.storage_class_hint)
        self.assertIn("static int StaticFunction", selected.signature_preview)
        self.assertLess(selected.header_range.start.line, selected.body_range.end.line)

    def test_ignores_prototype_function_pointer_call_and_masked_noise(self):
        digest = self.digest()

        prototype = locate_function(digest, "PrototypeOnly")
        pointer = locate_function(digest, "PointerLike")
        string_noise = locate_function(digest, "StringNoise")
        comment_noise = locate_function(digest, "CommentNoise")
        static_function = locate_function(digest, "StaticFunction")

        self.assertEqual("not_found", prototype.status)
        self.assertIn("prototype_only", [warning.code for warning in prototype.warnings])
        self.assertEqual("not_found", pointer.status)
        self.assertIn("function_pointer_candidate_ignored", [warning.code for warning in pointer.warnings])
        self.assertEqual("not_found", string_noise.status)
        self.assertEqual("not_found", comment_noise.status)
        self.assertEqual(1, len([candidate for candidate in static_function.candidates if candidate.kind == "definition"]))

    def test_locates_multiline_and_old_style_definitions(self):
        multiline = locate_function(self.digest(), "MultilineHeader")
        old_style = locate_function(self.digest(), "OldStyle")

        self.assertEqual("found", multiline.status)
        self.assertIn("MultilineHeader", multiline.selected_candidate.signature_preview)
        self.assertEqual("found", old_style.status)
        self.assertEqual("medium", old_style.selected_candidate.confidence)
        self.assertIn("old_style_definition_detected", [warning.code for warning in old_style.warnings])

    def test_duplicate_and_unmatched_brace_are_reported(self):
        duplicate = locate_function(self.digest(), "ConditionalDuplicate")
        broken = locate_function(self.digest(), "Broken")

        self.assertEqual("multiple_candidates", duplicate.status)
        self.assertIn("multiple_function_definitions", [warning.code for warning in duplicate.warnings])
        self.assertEqual("malformed", broken.status)
        self.assertIn("unmatched_opening_brace", [warning.code for warning in broken.warnings])

    def test_writer_emits_json_markdown_and_function_slice(self):
        digest = self.digest()
        location = locate_function(digest, "StaticFunction")
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_function_location(Path(temp_dir), digest, location)
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            markdown = paths["markdown"].read_text(encoding="utf-8")
            slice_text = paths["function_slice"].read_text(encoding="utf-8")

        self.assertEqual("0.1", payload["schema_version"])
        self.assertEqual("StaticFunction", payload["function"]["name"])
        self.assertIn("# 関数位置レポート", markdown)
        self.assertIn("StaticFunction", slice_text)

    def test_analyze_function_generates_function_location_artifacts(self):
        from unit_test_runner.dossier import analyze_function_workflow

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "Control_Update"
            analyze_function_workflow(
                FIXTURE_ROOT,
                FIXTURE_ROOT / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                out_dir,
                "Control",
            )

            self.assertTrue((out_dir / "reports" / "function_location.json").exists())
            self.assertTrue((out_dir / "reports" / "function_location.md").exists())
            self.assertTrue((out_dir / "intermediate" / "function_slice.c").exists())

    def test_analyze_function_json_cli_generates_location_without_stdout_noise(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "Control_Update"
            completed = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
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
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("", completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("analysis_completed", payload["status"])
            self.assertIn("function_location", payload["data"])
            self.assertTrue((out_dir / "reports" / "function_location.json").exists())


if __name__ == "__main__":
    unittest.main()
