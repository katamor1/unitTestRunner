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
            wheel_dir = Path(temp_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    str(wheel_dir),
                    ".",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stdout)
            wheels = list(wheel_dir.glob("unit_test_runner-*.whl"))
            self.assertEqual(1, len(wheels), completed.stdout)
            with zipfile.ZipFile(wheels[0]) as archive:
                names = set(archive.namelist())

        expected = {
            "unit_test_runner/schemas/common.schema.json",
            *{
                f"unit_test_runner/schemas/{kind.value}.schema.json"
                for kind in ArtifactKind
            },
        }
        self.assertTrue(expected.issubset(names), sorted(expected - names))


if __name__ == "__main__":
    unittest.main()
