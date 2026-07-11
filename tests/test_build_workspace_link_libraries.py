import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build import generate_build_workspace


class BuildWorkspaceLinkLibraryTests(unittest.TestCase):
    def _fixture(self, temp_dir: str):
        root = Path(temp_dir)
        project = root / "project"
        source = project / "src" / "target.c"
        source.parent.mkdir(parents=True)
        source.write_text("int Target(void) { return 1; }\n", encoding="ascii")
        first_dir = root / "first libs"
        second_dir = root / "second libs"
        first_dir.mkdir()
        second_dir.mkdir()
        first_lib = first_dir / "First.lib"
        second_lib = second_dir / "Second.lib"
        first_lib.write_bytes(b"first")
        second_lib.write_bytes(b"second")
        out_dir = root / "out"
        source_digest = {"source": {"path": str(source)}, "preprocessor": {"includes": []}}
        harness_report = {
            "function": {"name": "Target"},
            "source": {"path": str(source)},
            "output_root": str(out_dir),
            "generated_files": [],
        }
        return project, first_lib, second_lib, out_dir, source_digest, harness_report

    def test_makefile_and_report_preserve_resolved_library_order_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project, first_lib, second_lib, out_dir, source_digest, harness_report = self._fixture(temp_dir)
            build_context = {
                "workspace_root": str(project),
                "include_dirs": [],
                "defines": [],
                "compiler_options": [],
                "link_libraries": [
                    {
                        "path": str(second_lib),
                        "source": "direct_dependency_project",
                        "link_order": 1,
                        "project_name": "Second",
                        "configuration": "Win32 Debug",
                        "exists": True,
                        "scan_status": "ok",
                    },
                    {
                        "path": str(first_lib),
                        "source": "explicit_link32",
                        "link_order": 0,
                        "project_name": None,
                        "configuration": "Win32 Debug",
                        "exists": True,
                        "scan_status": "ok",
                    },
                ],
                "library_dirs": [str(first_lib.parent), str(second_lib.parent)],
            }

            report, _probe = generate_build_workspace(
                build_context,
                source_digest,
                harness_report,
                out_dir,
                run_probe=False,
                dry_run=True,
            )
            makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")
            first_windows = str(first_lib.resolve()).replace("/", "\\")
            second_windows = str(second_lib.resolve()).replace("/", "\\")

            self.assertEqual([first_lib.resolve(), second_lib.resolve()], [item.path for item in report.link_libraries])
            self.assertEqual([first_lib.parent.resolve(), second_lib.parent.resolve()], report.library_dirs)
            self.assertLess(makefile.index(first_windows), makefile.index(second_windows))
            self.assertIn("LINK_LIBS=", makefile)
            self.assertIn("LIBPATHS=", makefile)
            self.assertIn("$(LINK) /nologo /OPT:REF /OUT:$@ $(OBJS) $(LIBPATHS) $(LINK_LIBS)", makefile)
            self.assertEqual(
                [first_lib.resolve(), second_lib.resolve()],
                report.link_units[-2:],
            )

    def test_unavailable_link_library_is_omitted_and_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project, first_lib, _second_lib, out_dir, source_digest, harness_report = self._fixture(temp_dir)
            missing = Path(temp_dir) / "missing" / "Missing.lib"
            build_context = {
                "workspace_root": str(project),
                "include_dirs": [],
                "defines": [],
                "compiler_options": [],
                "link_libraries": [
                    {
                        "path": str(missing),
                        "source": "explicit_link32",
                        "link_order": 0,
                        "exists": False,
                    },
                    {
                        "path": str(first_lib),
                        "source": "explicit_link32",
                        "link_order": 1,
                        "exists": True,
                    },
                ],
                "library_dirs": [str(first_lib.parent)],
            }

            report, _probe = generate_build_workspace(build_context, source_digest, harness_report, out_dir)
            makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")

            self.assertEqual([first_lib.resolve()], [item.path for item in report.link_libraries])
            self.assertNotIn(str(missing).replace("/", "\\"), makefile)
            self.assertTrue(any(item.code == "link_library_not_found" for item in report.diagnostics))


if __name__ == "__main__":
    unittest.main()
