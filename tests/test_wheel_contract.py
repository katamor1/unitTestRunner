import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


from unit_test_runner.contracts import ArtifactKind


REPO_ROOT = Path(__file__).resolve().parents[1]


class WheelContractTests(unittest.TestCase):
    def test_fresh_venv_environment_removes_sensitive_names_case_insensitively(self):
        source = {
            "pythonpath": "remove",
            "PyThOnHoMe": "remove",
            "virtual_env": "remove",
            "__pyvenv_launcher__": "remove",
            "Unit_Test_Runner_Token": "remove",
            "Path": "preserve",
            "PYTHONUTF8": "preserve",
        }
        with mock.patch.object(os.environ, "copy", return_value=dict(source)):
            environment = _fresh_venv_environment()

        for name in (
            "pythonpath",
            "PyThOnHoMe",
            "virtual_env",
            "__pyvenv_launcher__",
            "Unit_Test_Runner_Token",
        ):
            self.assertNotIn(name, environment)
        self.assertEqual("preserve", environment["Path"])
        self.assertEqual("preserve", environment["PYTHONUTF8"])

    def test_fresh_venv_temp_root_guard_rejects_repository_containment(self):
        guard = globals().get("_assert_external_temp_root")
        self.assertIsNotNone(guard, "fresh-wheel temp containment guard is missing")
        for unsafe_root in (REPO_ROOT, REPO_ROOT / "build" / "fresh-wheel"):
            with self.subTest(unsafe_root=unsafe_root):
                with self.assertRaises(AssertionError):
                    guard(unsafe_root)

        with tempfile.TemporaryDirectory() as temp_dir:
            guard(Path(temp_dir))

    def test_wheel_contains_every_packaged_contract_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wheel = _build_wheel(Path(temp_dir), self)
            with zipfile.ZipFile(wheel) as archive:
                names = {
                    Path(name).name
                    for name in archive.namelist()
                    if name.startswith("unit_test_runner/schemas/")
                    and name.endswith(".json")
                }

        self.assertEqual(_source_schema_resources(), names)

    def test_wheel_metadata_declares_direct_referencing_dependency(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wheel = _build_wheel(Path(temp_dir), self)
            with zipfile.ZipFile(wheel) as archive:
                metadata_names = [
                    name
                    for name in archive.namelist()
                    if name.endswith(".dist-info/METADATA")
                ]
                self.assertEqual(1, len(metadata_names), metadata_names)
                metadata = archive.read(metadata_names[0]).decode("utf-8")

        requirements = [
            line.removeprefix("Requires-Dist:").strip()
            for line in metadata.splitlines()
            if line.startswith("Requires-Dist:")
        ]
        referencing = [
            requirement
            for requirement in requirements
            if _normalized_requirement_name(requirement) == "referencing"
        ]
        self.assertEqual(1, len(referencing), requirements)
        self.assertNotIn(";", referencing[0])
        name_match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", referencing[0])
        self.assertIsNotNone(name_match)
        specifier = referencing[0][name_match.end() :].strip()
        if specifier.startswith("(") and specifier.endswith(")"):
            specifier = specifier[1:-1]
        self.assertEqual(
            {">=0.28.4", "<1"},
            {item.strip() for item in specifier.split(",") if item.strip()},
        )
        self.assertFalse(
            [
                requirement
                for requirement in requirements
                if _normalized_requirement_name(requirement) == "typing-extensions"
            ],
            requirements,
        )

    def test_installed_wheel_validates_every_contract_schema_resource(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _assert_external_temp_root(root)
            wheel = _build_wheel(root / "dist", self)
            expected_resources = sorted(_source_schema_resources())
            venv_root = root / "venv"
            venv_env = _fresh_venv_environment()
            created = subprocess.run(
                [sys.executable, "-m", "venv", str(venv_root)],
                cwd=root,
                env=venv_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, created.returncode, created.stdout)
            venv_python = _venv_python(venv_root)
            installed = subprocess.run(
                [
                    str(venv_python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    str(wheel),
                ],
                cwd=root,
                env=venv_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, installed.returncode, installed.stdout)
            checked = subprocess.run(
                [str(venv_python), "-m", "pip", "check"],
                cwd=root,
                env=venv_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, checked.returncode, checked.stdout)
            script = """
import json
import sys
from importlib import resources
from pathlib import Path

import jsonschema
import referencing
import unit_test_runner
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.contracts.registry import (
    get_contract,
    iter_contracts,
    iter_contract_versions,
)
from unit_test_runner.contracts.validator import validate_payload_schema

expected_resources = json.loads(sys.argv[1])
prefix = Path(sys.prefix).resolve()
module_origins = {}
for module in (unit_test_runner, jsonschema, referencing):
    origin = Path(module.__file__).resolve()
    assert origin.is_relative_to(prefix), (module.__name__, origin, prefix)
    module_origins[module.__name__] = str(origin)

root = resources.files("unit_test_runner.schemas")
installed_resources = sorted(
    item.name for item in root.iterdir() if item.name.endswith(".json")
)
assert installed_resources == expected_resources, (
    installed_resources,
    expected_resources,
)
documents = {
    name: json.loads(root.joinpath(name).read_text(encoding="utf-8"))
    for name in installed_resources
}

registry = Registry()
for document in documents.values():
    Draft202012Validator.check_schema(document)
    registry = registry.with_resource(
        document["$id"],
        Resource.from_contents(document),
    )

def iter_refs(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            yield from iter_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_refs(child)

for resource_name, document in documents.items():
    resolver = registry.resolver(document["$id"])
    for reference in iter_refs(document):
        resolver.lookup(reference)

current_contracts = tuple(iter_contracts())
versioned_contracts = tuple(iter_contract_versions())
assert {contract.kind for contract in current_contracts} == set(ArtifactKind)
version_keys = {
    (contract.kind, contract.current_version)
    for contract in versioned_contracts
}
assert len(version_keys) == len(versioned_contracts)
assert set(current_contracts).issubset(versioned_contracts)
test_spec_versions = sorted(
    contract.current_version
    for contract in versioned_contracts
    if contract.kind is ArtifactKind.TEST_SPEC
)
assert test_spec_versions == ["1.0.0", "1.1.0"]
assert any(
    contract.schema_resource == "test_spec_v1_0.schema.json"
    for contract in versioned_contracts
)
future_common = "common_v1_0.schema.json"
if future_common in expected_resources:
    assert future_common in documents

for contract in versioned_contracts:
    document = documents[contract.schema_resource]
    validator = Draft202012Validator(document, registry=registry)
    tuple(validator.iter_errors({}))
for kind in ArtifactKind:
    assert get_contract(kind) in current_contracts
    assert validate_payload_schema(kind, {})

print(json.dumps({
    "schema_resources": installed_resources,
    "current_contracts": len(current_contracts),
    "versioned_contracts": len(versioned_contracts),
    "test_spec_versions": test_spec_versions,
    "module_origins": module_origins,
}, sort_keys=True))
"""
            loaded = subprocess.run(
                [
                    str(venv_python),
                    "-I",
                    "-c",
                    script,
                    json.dumps(expected_resources),
                ],
                cwd=root,
                env=venv_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        self.assertEqual(0, loaded.returncode, loaded.stdout)
        report = json.loads(loaded.stdout)
        self.assertEqual(expected_resources, report["schema_resources"])
        self.assertEqual(len(ArtifactKind), report["current_contracts"])
        self.assertGreaterEqual(
            report["versioned_contracts"],
            report["current_contracts"],
        )
        self.assertEqual(["1.0.0", "1.1.0"], report["test_spec_versions"])
        self.assertEqual(
            {"unit_test_runner", "jsonschema", "referencing"},
            set(report["module_origins"]),
        )


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


def _source_schema_resources() -> set[str]:
    return {
        path.name
        for path in (REPO_ROOT / "src" / "unit_test_runner" / "schemas").glob(
            "*.json"
        )
    }


def _venv_python(root: Path) -> Path:
    if sys.platform == "win32":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def _fresh_venv_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        normalized = name.casefold()
        if normalized in {
            "pythonhome",
            "pythonpath",
            "virtual_env",
            "__pyvenv_launcher__",
        } or normalized.startswith("unit_test_runner_"):
            environment.pop(name, None)
    return environment


def _assert_external_temp_root(root: Path) -> None:
    resolved_root = root.resolve()
    resolved_repo = REPO_ROOT.resolve()
    assert resolved_root != resolved_repo and not resolved_root.is_relative_to(
        resolved_repo
    ), f"Fresh-wheel temp root must be outside the repository: {resolved_root}"


def _normalized_requirement_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    if match is None:
        return ""
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


if __name__ == "__main__":
    unittest.main()
