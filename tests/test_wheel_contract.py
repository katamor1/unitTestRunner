import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


from unit_test_runner.contracts import ArtifactKind


REPO_ROOT = Path(__file__).resolve().parents[1]


class WheelContractTests(unittest.TestCase):
    def test_wheel_contains_every_packaged_contract_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wheel = _build_wheel(Path(temp_dir), self)
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())

        expected = {
            "unit_test_runner/schemas/common.schema.json",
            *{
                f"unit_test_runner/schemas/{kind.value}.schema.json"
                for kind in ArtifactKind
            },
        }
        self.assertTrue(expected.issubset(names), sorted(expected - names))

    def test_installed_wheel_loads_every_artifact_specific_schema_resource(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wheel = _build_wheel(root / "dist", self)
            site_packages = root / "site-packages"
            installed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-deps",
                    "--target",
                    str(site_packages),
                    str(wheel),
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, installed.returncode, installed.stdout)
            script = """
import json
import sys
from importlib import resources

sys.path.insert(0, sys.argv[1])
from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.contracts.registry import get_contract

root = resources.files("unit_test_runner.schemas")
common = json.loads(root.joinpath("common.schema.json").read_text(encoding="utf-8"))
assert common["additionalProperties"] is False
for kind in ArtifactKind:
    contract = get_contract(kind)
    assert contract.schema_resource != "common.schema.json"
    document = json.loads(
        root.joinpath(contract.schema_resource).read_text(encoding="utf-8")
    )
    overlay = document["allOf"][-1]
    assert "data" in overlay["properties"], contract.schema_resource
"""
            loaded = subprocess.run(
                [sys.executable, "-I", "-c", script, str(site_packages)],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        self.assertEqual(0, loaded.returncode, loaded.stdout)


def _build_wheel(directory: Path, test_case: unittest.TestCase) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(directory),
            ".",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    test_case.assertEqual(0, completed.returncode, completed.stdout)
    wheels = list(directory.glob("unit_test_runner-*.whl"))
    test_case.assertEqual(1, len(wheels), completed.stdout)
    return wheels[0]


if __name__ == "__main__":
    unittest.main()
