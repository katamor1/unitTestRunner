import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.vc6.debug_workspace_response import _strip_include_options, vc6_cpp_options_path
from unit_test_runner.vc6.debug_workspace_writer import write_vc6_debug_project


class Vc6DspResponseFileTests(unittest.TestCase):
    def test_environment_macro_include_remains_in_dsp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            (workspace / "build").mkdir(parents=True)
            report = {
                "function": {"name": "MacroIncludes"},
                "include_dirs": [
                    {
                        "raw": "C:/product/include",
                        "workspace_path": None,
                        "exists": True,
                        "source": "referenced_header_dir",
                    },
                    {
                        "raw": "%LEGACY_SDK%/include",
                        "workspace_path": None,
                        "exists": False,
                        "source": "dsp_include",
                    },
                ],
                "defines": ["WIN32"],
                "compiler_options": ["/nologo", "/W3", "/Od", "/ZI"],
                "compile_units": [],
                "copied_files": [],
                "referenced_files": [],
                "generated_build_files": [],
            }

            dsp_path = write_vc6_debug_project(workspace, report)
            dsp_text = dsp_path.read_text(encoding="cp932")
            options_text = vc6_cpp_options_path(dsp_path).read_text(encoding="cp932")

            self.assertIn('# ADD CPP @"UTR_MacroIncludes.ini"', dsp_text)
            self.assertIn('/I "%LEGACY_SDK%\\include"', dsp_text)
            self.assertIn('/I "C:\\product\\include"', options_text)
            self.assertNotIn("%LEGACY_SDK%", options_text)

    def test_include_removal_does_not_treat_incremental_as_an_include_option(self):
        line = '# ADD CPP /nologo /incremental /I "C:\\product\\include" /c'

        rewritten = _strip_include_options(line, [])

        self.assertIn("/incremental", rewritten)
        self.assertNotIn('/I "C:\\product\\include"', rewritten)


if __name__ == "__main__":
    unittest.main()
