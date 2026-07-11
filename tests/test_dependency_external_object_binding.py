import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build import generate_build_workspace


class DependencyExternalObjectBindingTests(unittest.TestCase):
    def _generate(self, root: Path, *, external_object: dict, definition_text: str | None = None):
        project = root / "project"
        output = root / "out"
        project.mkdir()
        target = project / "target.c"
        header = project / "state.h"
        target.write_text('#include "state.h"\nint Target(void) { return g_state; }\n', encoding="ascii")
        header.write_text("extern int g_state;\n", encoding="ascii")
        if definition_text is not None:
            (project / "state.c").write_text(definition_text, encoding="ascii")
        (output / "reports").mkdir(parents=True)
        policy = {
            "source": {"path": "target.c"},
            "function": {"name": "Target", "status": external_object.get("review_status", "resolved")},
            "dependencies": [],
            "external_objects": [external_object],
            "warnings": [],
        }
        (output / "reports" / "dependency_policy.json").write_text(json.dumps(policy), encoding="utf-8")
        source_digest = {
            "source": {"path": str(target)},
            "preprocessor": {"includes": [{"name": "state.h", "resolved_candidates": [str(header)]}]},
        }
        build_context = {"workspace_root": str(project), "include_dirs": [str(project)], "defines": [], "compiler_options": []}
        harness_report = {"function": {"name": "Target"}, "source": {"path": str(target)}, "output_root": str(output), "generated_files": [], "dependency_dispatches": []}
        report, _probe = generate_build_workspace(build_context, source_digest, harness_report, output, run_probe=False, dry_run=True)
        return project, output, report

    def test_real_external_object_uses_product_definition_and_no_fixture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project, output, report = self._generate(
                root,
                external_object={
                    "symbol": "g_state",
                    "type_raw": "int",
                    "configured_mode": "auto",
                    "resolved_mode": "real",
                    "review_status": "resolved",
                    "declaration_header": "state.h",
                    "definition_source": "state.c",
                    "definition_candidates": ["state.c"],
                    "evidence": [],
                    "warnings": [],
                },
                definition_text='#include "state.h"\nint g_state = 3;\n',
            )

            self.assertFalse((output / "generated" / "stubs" / "utr_extern_globals.c").exists())
            real_sources = [item for item in report.copied_files if item.file_kind == "external_object_source"]
            self.assertEqual(1, len(real_sources))
            self.assertEqual((project / "state.c").resolve(), real_sources[0].source_path)
            self.assertIn(real_sources[0].workspace_path, [unit.source_file for unit in report.compile_units])
            self.assertFalse(any(item.code.startswith("external_object_") for item in report.diagnostics))

    def test_fixture_external_object_is_defined_once_from_real_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _project, output, report = self._generate(
                Path(temp_dir),
                external_object={
                    "symbol": "g_state",
                    "type_raw": "int",
                    "configured_mode": "fixture",
                    "resolved_mode": "fixture",
                    "review_status": "resolved",
                    "declaration_header": "state.h",
                    "definition_source": None,
                    "definition_candidates": [],
                    "evidence": [],
                    "warnings": [],
                },
            )

            fixture = output / "generated" / "stubs" / "utr_extern_globals.c"
            text = fixture.read_text(encoding="cp932")
            self.assertEqual(1, text.count("int g_state = {0};"))
            self.assertIn('#include "state.h"', text)
            self.assertIn(Path("generated/stubs/utr_extern_globals.c"), [unit.source_file for unit in report.compile_units])

    def test_review_required_external_object_is_not_defined_automatically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _project, output, report = self._generate(
                Path(temp_dir),
                external_object={
                    "symbol": "g_state",
                    "type_raw": "int",
                    "configured_mode": "auto",
                    "resolved_mode": "review_required",
                    "review_status": "review_required",
                    "declaration_header": "state.h",
                    "definition_source": None,
                    "definition_candidates": ["state_a.c", "state_b.c"],
                    "evidence": [],
                    "warnings": ["Multiple product definitions were found."],
                },
            )

            self.assertFalse((output / "generated" / "stubs" / "utr_extern_globals.c").exists())
            diagnostics = [item for item in report.diagnostics if item.code == "external_object_binding_review_required"]
            self.assertEqual(1, len(diagnostics))
            self.assertEqual("error", diagnostics[0].severity)


if __name__ == "__main__":
    unittest.main()
