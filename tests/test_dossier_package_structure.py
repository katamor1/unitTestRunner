from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class DossierPackageStructureTests(unittest.TestCase):
    def test_dossier_workflow_lives_inside_package_without_dynamic_legacy_loader(self):
        self.assertFalse((REPO_ROOT / "src" / "unit_test_runner" / "dossier.py").exists())
        package_init = (REPO_ROOT / "src" / "unit_test_runner" / "dossier" / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("importlib.util", package_init)
        self.assertNotIn("_load_legacy_module", package_init)


if __name__ == "__main__":
    unittest.main()
