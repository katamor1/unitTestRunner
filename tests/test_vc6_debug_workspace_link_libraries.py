import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.vc6.debug_workspace_writer import write_vc6_debug_project


class Vc6DebugWorkspaceLinkLibraryTests(unittest.TestCase):
    def test_debug_dsp_emits_library_paths_and_ordered_libraries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            build = workspace / "build"
            first_dir = Path(temp_dir) / "first libs"
            second_dir = Path(temp_dir) / "second libs"
            build.mkdir(parents=True)
            first_dir.mkdir()
            second_dir.mkdir()
            first_lib = first_dir / "First.lib"
            second_lib = second_dir / "Second.lib"
            first_lib.write_bytes(b"first")
            second_lib.write_bytes(b"second")
            report = {
                "function": {"name": "Linked"},
                "include_dirs": [],
                "defines": ["WIN32"],
                "compiler_options": ["/nologo", "/W3", "/Od", "/ZI"],
                "compile_units": [],
                "copied_files": [],
                "referenced_files": [],
                "generated_build_files": [],
                "link_libraries": [
                    {"path": str(second_lib.resolve()), "source": "direct_dependency_project", "link_order": 1},
                    {"path": str(first_lib.resolve()), "source": "explicit_link32", "link_order": 0},
                ],
                "library_dirs": [str(first_dir.resolve()), str(second_dir.resolve())],
            }

            dsp_path = write_vc6_debug_project(workspace, report)
            dsp_text = dsp_path.read_text(encoding="cp932")
            first = str(first_lib.resolve()).replace("/", "\\")
            second = str(second_lib.resolve()).replace("/", "\\")
            first_dir_windows = str(first_dir.resolve()).replace("/", "\\")
            second_dir_windows = str(second_dir.resolve()).replace("/", "\\")
            link_line = next(line for line in dsp_text.splitlines() if line.startswith("# ADD LINK32"))

            self.assertIn(f'/libpath:"{first_dir_windows}"', link_line)
            self.assertIn(f'/libpath:"{second_dir_windows}"', link_line)
            self.assertIn(f'"{first}"', link_line)
            self.assertIn(f'"{second}"', link_line)
            self.assertLess(link_line.index(first), link_line.index(second))
            self.assertLess(link_line.index(first_dir_windows), link_line.index(first))


if __name__ == "__main__":
    unittest.main()
