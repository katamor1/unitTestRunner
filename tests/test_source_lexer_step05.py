import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.c_analyzer.masker import mask_source_text
from unit_test_runner.c_analyzer.preprocessor import scan_preprocessor
from unit_test_runner.c_analyzer.source_digest import build_source_digest, write_source_digest
from unit_test_runner.c_analyzer.source_reader import read_source
from unit_test_runner.c_analyzer.tokens import extract_tokens


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "tests" / "fixtures" / "c_sources" / "integration" / "control_sample.c"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


class SourceLexerStep05Tests(unittest.TestCase):
    def test_masker_removes_comment_string_and_char_braces_without_changing_lines(self):
        text = "int f(void) {\n  char c = '}';\n  puts(\"}\"); // }\n  /* } */\n}\n"

        masked = mask_source_text(text, SOURCE)

        self.assertEqual(text.count("\n"), masked.masked_text.count("\n"))
        self.assertEqual(1, masked.masked_text.count("}"))
        self.assertIn("char_literal", [item.kind for item in masked.masked_ranges])
        self.assertIn("string_literal", [item.kind for item in masked.masked_ranges])
        self.assertIn("line_comment", [item.kind for item in masked.masked_ranges])
        self.assertIn("block_comment", [item.kind for item in masked.masked_ranges])

    def test_masker_reports_unterminated_constructs(self):
        masked = mask_source_text("int f(void) { /* unterminated\n", SOURCE)

        self.assertIn("unterminated_block_comment", [warning.code for warning in masked.warnings])

    def test_preprocessor_extracts_includes_macros_and_conditionals(self):
        digest = build_source_digest(SOURCE, {"defines": ["_DEBUG"], "include_dirs": [{"absolute": str(SOURCE.parent), "exists": True}]})

        self.assertEqual(["control_sample.h"], [item.target for item in digest.includes])
        self.assertTrue(digest.includes[0].exists)
        macros = {macro.name: macro for macro in digest.macros}
        self.assertFalse(macros["MAX_VALUE"].is_function_like)
        self.assertTrue(macros["IS_VALID"].is_function_like)
        ifdef = next(item for item in digest.directives if item.kind == "ifdef")
        self.assertEqual("active", ifdef.active_state)
        self.assertEqual(1, max(item.nesting_level for item in digest.directives))

    def test_tokens_skip_masked_noise_and_keep_line_column(self):
        digest = build_source_digest(SOURCE, {"defines": ["_DEBUG"]})
        tokens = extract_tokens(digest.masked_source.masked_text)
        values = [token.value for token in tokens]

        self.assertIn("Control_Update", values)
        self.assertNotIn("Fake", values)
        target = next(token for token in tokens if token.value == "Control_Update")
        self.assertGreater(target.line_number, 0)
        self.assertGreater(target.column, 0)

    def test_reader_supports_cp932_with_encoding_fallback_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cp932_comments.c"
            path.write_bytes("/* 日本語コメント */\nint f(void) { return 0; }\n".encode("cp932"))

            result = read_source(path)

        self.assertEqual("cp932", result.encoding)
        self.assertEqual(2, result.line_count)
        self.assertIn("encoding_fallback", [warning.code for warning in result.warnings])

    def test_source_digest_writer_emits_json_markdown_and_masked_source(self):
        digest = build_source_digest(SOURCE, {"defines": ["_DEBUG"]})
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            paths = write_source_digest(out_dir, digest)

            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            markdown = paths["markdown"].read_text(encoding="utf-8")

        self.assertEqual("0.1", payload["schema_version"])
        self.assertEqual(str(SOURCE).replace("\\", "/"), payload["source"]["path"])
        self.assertTrue(payload["token_summary"]["identifier_count"] > 0)
        self.assertIn("# Source Digest Report", markdown)
        self.assertIn("masked_source.c", str(paths["masked_source"]))

    def test_analyze_function_generates_source_digest_artifacts(self):
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

            self.assertTrue((out_dir / "reports" / "source_digest.json").exists())
            self.assertTrue((out_dir / "reports" / "source_digest.md").exists())
            self.assertTrue((out_dir / "intermediate" / "masked_source.c").exists())


if __name__ == "__main__":
    unittest.main()
