import ast
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "unit_test_runner"


class RepositorySourceTrackingTests(unittest.TestCase):
    def test_all_python_package_sources_are_tracked_and_not_ignored(self):
        completed = subprocess.run(
            ["git", "ls-files", "src/unit_test_runner"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        tracked = {line.strip() for line in completed.stdout.splitlines() if line.strip()}

        for source in PACKAGE_ROOT.rglob("*.py"):
            relative = source.relative_to(REPO_ROOT).as_posix()
            self.assertIn(relative, tracked, relative)
            ignored = subprocess.run(
                ["git", "check-ignore", "--no-index", "-q", relative],
                cwd=REPO_ROOT,
                check=False,
            )
            self.assertNotEqual(0, ignored.returncode, relative)

    def test_static_local_import_targets_exist_and_are_tracked(self):
        tracked = set(
            subprocess.run(
                ["git", "ls-files", "src/unit_test_runner"],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            ).stdout.splitlines()
        )
        failures = []
        for source in PACKAGE_ROOT.rglob("*.py"):
            module_name = _module_name(source)
            package_name = module_name if source.name == "__init__.py" else module_name.rpartition(".")[0]
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for imported in _local_imports(tree, package_name):
                target = _module_file(imported)
                if target is None:
                    failures.append(f"{source.relative_to(REPO_ROOT)} imports missing {imported}")
                    continue
                relative = target.relative_to(REPO_ROOT).as_posix()
                if relative not in tracked:
                    failures.append(f"{source.relative_to(REPO_ROOT)} imports untracked {relative}")
        self.assertEqual([], failures)


def _module_name(source: Path) -> str:
    relative = source.relative_to(SRC_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _local_imports(tree: ast.AST, package_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "unit_test_runner" or alias.name.startswith("unit_test_runner."):
                    yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative = "." * node.level + (node.module or "")
                try:
                    name = importlib.util.resolve_name(relative, package_name)
                except (ImportError, ValueError):
                    continue
            else:
                name = node.module or ""
            if name == "unit_test_runner" or name.startswith("unit_test_runner."):
                yield name


def _module_file(module_name: str):
    relative = Path(*module_name.split("."))
    module_file = SRC_ROOT / relative.with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = SRC_ROOT / relative / "__init__.py"
    return package_file if package_file.is_file() else None


if __name__ == "__main__":
    unittest.main()
