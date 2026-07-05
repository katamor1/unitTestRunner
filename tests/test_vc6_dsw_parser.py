import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.dsw_parser import discover_dsw_workspaces, parse_dsw


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "vc6_dsw"


def warning_codes(workspace):
    return [warning.code for warning in workspace.warnings]


class Vc6DswParserTests(unittest.TestCase):
    def test_minimal_dsw_extracts_project_and_resolved_paths(self):
        workspace = parse_dsw(FIXTURE_ROOT / "minimal" / "Product.dsw")

        self.assertEqual("6.00", workspace.format_version)
        self.assertEqual(1, len(workspace.projects))
        project = workspace.projects[0]
        self.assertEqual("Control", project.name)
        self.assertEqual(r".\Control\Control.dsp", project.dsp_path_raw)
        self.assertEqual("Control/Control.dsp", project.dsp_path.as_posix())
        self.assertEqual((workspace.root_dir / "Control" / "Control.dsp").resolve(), project.dsp_path_absolute)
        self.assertTrue(project.exists)
        self.assertGreater(project.line_number, 0)

    def test_multiple_projects_and_uppercase_dsp_extension_are_extracted(self):
        workspace = parse_dsw(FIXTURE_ROOT / "multiple_projects" / "Product.dsw")

        self.assertEqual(["Control", "Common"], [project.name for project in workspace.projects])
        self.assertEqual("Common/Common.DSP", workspace.projects[1].dsp_path.as_posix())
        self.assertTrue(workspace.projects[1].exists)

    def test_dependency_block_uses_current_project_as_dependency_source(self):
        workspace = parse_dsw(FIXTURE_ROOT / "dependencies" / "Product.dsw")

        self.assertEqual(1, len(workspace.dependencies))
        dependency = workspace.dependencies[0]
        self.assertEqual("Control", dependency.from_project)
        self.assertEqual("Common", dependency.to_project)
        self.assertGreater(dependency.line_number, 0)

    def test_parent_relative_path_resolves_from_dsw_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            product = root / "Product"
            common = root / "Common"
            product.mkdir()
            common.mkdir()
            (common / "Common.dsp").write_text("# dsp\n", encoding="utf-8")
            dsw = product / "Product.dsw"
            dsw.write_text(
                'Microsoft Developer Studio Workspace File, Format Version 6.00\n'
                'Project: "Common"=..\\Common\\Common.dsp - Package Owner=<4>\n',
                encoding="utf-8",
            )

            workspace = parse_dsw(dsw)

        self.assertEqual("Common", workspace.projects[0].name)
        self.assertEqual("../Common/Common.dsp", workspace.projects[0].dsp_path.as_posix())
        self.assertTrue(workspace.projects[0].exists)

    def test_spaces_in_project_name_and_path_are_preserved(self):
        workspace = parse_dsw(FIXTURE_ROOT / "spaces_in_path" / "Product With Space.dsw")

        self.assertEqual("My Project", workspace.projects[0].name)
        self.assertEqual("My Project/My Project.dsp", workspace.projects[0].dsp_path.as_posix())

    def test_missing_dsp_file_is_a_warning_not_an_error(self):
        workspace = parse_dsw(FIXTURE_ROOT / "missing_dsp" / "Product.dsw")

        self.assertIn("missing_dsp_file", warning_codes(workspace))
        self.assertFalse(workspace.projects[0].exists)

    def test_malformed_project_and_unknown_lines_are_warnings(self):
        workspace = parse_dsw(FIXTURE_ROOT / "malformed" / "Broken.dsw")

        codes = warning_codes(workspace)
        self.assertIn("malformed_project_line", codes)
        self.assertIn("unknown_line", codes)
        self.assertEqual(["Control"], [project.name for project in workspace.projects])

    def test_unknown_dependency_target_is_a_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Control").mkdir()
            (root / "Control" / "Control.dsp").write_text("# dsp\n", encoding="utf-8")
            dsw = root / "Product.dsw"
            dsw.write_text(
                'Microsoft Developer Studio Workspace File, Format Version 6.00\n'
                'Project: "Control"=.\\Control\\Control.dsp - Package Owner=<4>\n'
                'Package=<4>\n'
                '{{{\n'
                '    Begin Project Dependency\n'
                '    Project_Dep_Name MissingDependency\n'
                '    End Project Dependency\n'
                '}}}\n',
                encoding="utf-8",
            )

            workspace = parse_dsw(dsw)

        self.assertIn("dependency_unknown_project", warning_codes(workspace))

    def test_cp932_encoded_workspace_uses_encoding_fallback_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Control").mkdir()
            (root / "Control" / "Control.dsp").write_text("# dsp\n", encoding="utf-8")
            dsw = root / "JapaneseProject.dsw"
            dsw.write_bytes(
                (
                    'Microsoft Developer Studio Workspace File, Format Version 6.00\n'
                    'Project: "制御"=.\\Control\\Control.dsp - Package Owner=<4>\n'
                ).encode("cp932")
            )

            workspace = parse_dsw(dsw)

        self.assertEqual("制御", workspace.projects[0].name)
        self.assertIn("encoding_fallback", warning_codes(workspace))

    def test_discover_dsw_workspaces_finds_multiple_dsw_files_under_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("A", "B"):
                project_dir = root / name
                (project_dir / "Control").mkdir(parents=True)
                (project_dir / "Control" / "Control.dsp").write_text("# dsp\n", encoding="utf-8")
                (project_dir / f"{name}.dsw").write_text(
                    'Microsoft Developer Studio Workspace File, Format Version 6.00\n'
                    'Project: "Control"=.\\Control\\Control.dsp - Package Owner=<4>\n',
                    encoding="utf-8",
                )

            result = discover_dsw_workspaces(root)

        self.assertEqual("ok", result.status)
        self.assertEqual(2, len(result.workspaces))
        self.assertEqual("discover-projects", result.command)


if __name__ == "__main__":
    unittest.main()
