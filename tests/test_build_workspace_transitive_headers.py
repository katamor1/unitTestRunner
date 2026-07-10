import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_workspace_generator import generate_build_workspace


class BuildWorkspaceTransitiveHeaderTests(unittest.TestCase):
    def test_declared_include_header_dependencies_are_referenced_not_copied(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            shared = project / "shared"
            source = shared / "shared.c"
            parent_header = shared / "shared2.h"
            transitive_header = shared / "shared.h"
            shared.mkdir(parents=True)
            source.write_text('#include "shared2.h"\nint Shared(void) { return SHARED_VALUE; }\n', encoding="ascii")
            parent_header.write_text('#include "shared.h"\nint Shared(void);\n', encoding="ascii")
            transitive_header.write_text('#define SHARED_VALUE 1\n', encoding="ascii")
            out_dir = Path(temp_dir) / "out"
            build_context = {
                "workspace_root": str(project),
                "include_dirs": ["shared"],
                "defines": [],
                "compiler_options": [],
            }
            source_digest = {
                "source": {"path": str(source)},
                "preprocessor": {
                    "includes": [
                        {
                            "name": "shared2.h",
                            "resolved_candidates": [str(parent_header)],
                        }
                    ]
                },
            }
            harness_report = {
                "function": {"name": "Shared"},
                "source": {"path": str(source)},
                "output_root": str(out_dir),
                "generated_files": [],
            }

            report, _probe = generate_build_workspace(
                build_context,
                source_digest,
                harness_report,
                out_dir,
                run_probe=False,
                dry_run=True,
            )

            header_refs = {item.source_path for item in report.copied_files if item.file_kind == "target_header"}
            self.assertIn(parent_header.resolve(), header_refs)
            self.assertIn(transitive_header.resolve(), header_refs)
            self.assertFalse((out_dir / "extracted" / "shared" / "shared2.h").exists())
            self.assertFalse((out_dir / "extracted" / "shared" / "shared.h").exists())
            include_dirs = {Path(item.raw) for item in report.include_dirs if item.source in {"referenced_header_dir", "dsp_include"}}
            self.assertIn(shared.resolve(), include_dirs)
            makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")
            self.assertIn(str(shared.resolve()).replace("/", "\\"), makefile)
            self.assertFalse(any(diagnostic.code == "missing_transitive_include" for diagnostic in report.diagnostics))


if __name__ == "__main__":
    unittest.main()
