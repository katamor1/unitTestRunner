import json
import os
import subprocess
import unittest
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.build_probe import parse_build_log
from unit_test_runner.build_probe import build_probe
from unit_test_runner.contracts import ConsumerContractError
from tests.windows_path_alias_support import require_windows_path_alias_pair


def _current_dossier_envelope() -> dict:
    return {
        "artifact_kind": "function_dossier",
        "schema_version": "1.1.0",
        "producer": {
            "name": "unit-test-runner",
            "version": "0.1.0",
            "commit": "test-commit",
        },
        "subject": {
            "function_id": "fn-target",
            "source_path": "src/control.c",
            "source_sha256": "1" * 64,
        },
        "data": {
            "target": {
                "source": "src/control.c",
                "function": "Target",
                "configuration": "Debug",
                "project": "Control",
            },
            "project_membership": [],
            "build_context": {"include_dirs": [], "defines": []},
            "function": {"name": "Target", "status": "ready"},
            "test_design": {},
            "diagnostics": [],
        },
        "extensions": {},
    }


def _assert_command_source_is_samefile(
    test: unittest.TestCase,
    expected: Path,
    command: str,
) -> None:
    _, separator, source_operand = command.rpartition(" /c ")
    test.assertEqual(
        " /c ",
        separator,
        f"missing source operand in command: {command}",
    )
    test.assertTrue(source_operand, f"empty source operand in command: {command}")
    has_quote_edge = (
        source_operand[0] in {"'", '"'} or source_operand[-1] in {"'", '"'}
    )
    if has_quote_edge:
        test.assertEqual(
            '"',
            source_operand[0],
            f"source operand must use paired double quotes: {source_operand}",
        )
        test.assertEqual(
            '"',
            source_operand[-1],
            f"source operand must use paired double quotes: {source_operand}",
        )
        source_path = source_operand[1:-1]
    else:
        test.assertFalse(
            any(character.isspace() for character in source_operand),
            f"source operand containing whitespace must be double-quoted: {source_operand}",
        )
        source_path = source_operand
    test.assertTrue(source_path, f"empty source path in command: {command}")
    actual = Path(source_path)
    test.assertTrue(expected.is_file(), f"expected source is not a file: {expected}")
    test.assertTrue(actual.is_file(), f"command source is not a file: {actual}")
    test.assertTrue(
        os.path.samefile(expected, actual),
        "command source does not name the expected physical file: "
        f"expected={expected}; actual={actual}",
    )


class BuildProbeTests(unittest.TestCase):
    def test_parse_build_log_extracts_actionable_diagnostics(self):
        diagnostics = parse_build_log(
            """
control.c(4) : fatal error C1083: Cannot open include file: 'missing.h': No such file or directory
cl : Command line warning D4024 : unrecognized source file type 'stdafx.h', object file assumed
LINK : fatal error LNK2001: unresolved external symbol _ReadSensor
LINK : fatal error LNK2019: unresolved external symbol _WriteOutput referenced in function _Control_Update
"""
        )

        self.assertEqual(["missing.h"], diagnostics["missing_includes"])
        self.assertTrue(diagnostics["pch_warnings"])
        self.assertEqual(["ReadSensor", "WriteOutput"], diagnostics["unresolved_symbols"])

    def test_current_dossier_envelope_uses_nested_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            (root / "extracted" / "src").mkdir(parents=True)
            (root / "extracted" / "src" / "control.c").write_text(
                "int Target(void) { return 0; }\n", encoding="ascii"
            )
            dossier = _current_dossier_envelope()
            dossier_path = reports / "function_dossier.json"
            dossier_path.write_text(json.dumps(dossier), encoding="utf-8")

            payload = build_probe(dossier_path, dry_run=True)

            self.assertTrue(payload["dry_run"])
            self.assertIn("control.c", payload["command"])

    def test_legacy_dossier_probe_uses_vcvars_without_requiring_vc6_bin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            (root / "extracted" / "src").mkdir(parents=True)
            (root / "extracted" / "src" / "control.c").write_text("int Target(void) { return 0; }\n", encoding="ascii")
            dossier = {
                "schema_version": "0.1",
                "target": {"source": "src/control.c", "function": "Target"},
                "build_context": {"include_dirs": [], "defines": []},
            }
            dossier_path = reports / "function_dossier.json"
            dossier_path.write_text(json.dumps(dossier), encoding="utf-8")
            vcvars = root / "vcvars32.bat"
            vcvars.write_text("@echo off\n", encoding="ascii")

            def fake_run(*args, **kwargs):
                return subprocess.CompletedProcess(args[0], 0, stdout="compiled\n")

            with mock.patch("unit_test_runner.build_probe.subprocess.run", side_effect=fake_run) as run:
                payload = build_probe(dossier_path, vcvars=vcvars, dry_run=False)

            self.assertFalse(payload["dry_run"])
            self.assertEqual(0, payload["returncode"])
            self.assertIn(str(vcvars), payload["command"])
            self.assertEqual(1, run.call_count)

    def test_current_dossier_envelope_reads_nested_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            source = root / "extracted" / "src" / "control.c"
            source.parent.mkdir(parents=True)
            source.write_text("int Target(void) { return 0; }\n", encoding="ascii")
            dossier = _current_dossier_envelope()
            dossier["target"] = {
                "source": "src/poisoned.c",
                "function": "Poisoned",
            }
            dossier["build_context"] = {
                "include_dirs": ["poisoned/include"],
                "defines": ["POISONED=1"],
            }
            dossier_path = reports / "function_dossier.json"
            dossier_path.write_text(json.dumps(dossier), encoding="utf-8")

            try:
                payload = build_probe(dossier_path, dry_run=True)
            except KeyError as error:
                self.fail(f"current dossier envelope did not use nested data: {error}")

            self.assertTrue(payload["dry_run"])
            _assert_command_source_is_samefile(self, source, payload["command"])
            self.assertNotIn("poisoned", payload["command"])
            self.assertNotIn("POISONED", payload["command"])

    @unittest.skipUnless(os.name == "nt", "Windows path aliases require Windows.")
    def test_command_source_assertion_accepts_equivalent_windows_aliases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            spaced_source_dir = Path(temp_dir) / "source files"
            spaced_source_dir.mkdir()
            pair = require_windows_path_alias_pair(self, spaced_source_dir)
            long_source = pair.long / "control.c"
            long_source.write_text(
                "int Target(void) { return 0; }\n",
                encoding="ascii",
            )
            short_source = pair.short / "control.c"
            self.assertTrue(any(character.isspace() for character in os.fspath(long_source)))
            self.assertFalse(
                any(character.isspace() for character in os.fspath(short_source))
            )

            for direction, expected, command_source in (
                ("long expected / short command operand", long_source, short_source),
                ("short expected / long command operand", short_source, long_source),
            ):
                with self.subTest(direction=direction):
                    _assert_command_source_is_samefile(
                        self,
                        expected,
                        f'cl /nologo /W3 /c "{command_source}"',
                    )

            _assert_command_source_is_samefile(
                self,
                short_source,
                f"cl /nologo /W3 /c {short_source}",
            )
            for description, invalid_operand in (
                ("unquoted spaced path", os.fspath(long_source)),
                ("single-quoted spaced path", f"'{long_source}'"),
                ("mismatched quote edges", f'"{long_source}\''),
                ("unmatched double quote", f'"{long_source}'),
            ):
                with self.subTest(description=description):
                    with self.assertRaises(AssertionError):
                        _assert_command_source_is_samefile(
                            self,
                            long_source,
                            f"cl /nologo /W3 /c {invalid_operand}",
                        )

    def test_invalid_current_dossier_fails_before_any_product_write(self):
        invalid_cases = {}

        wrong_kind = _current_dossier_envelope()
        wrong_kind["artifact_kind"] = "source_digest"
        invalid_cases["wrong_kind"] = wrong_kind

        unsupported_version = _current_dossier_envelope()
        unsupported_version["schema_version"] = "9.0.0"
        invalid_cases["unsupported_version"] = unsupported_version

        non_object_data = _current_dossier_envelope()
        non_object_data["data"] = []
        invalid_cases["non_object_data"] = non_object_data

        schema_invalid = _current_dossier_envelope()
        del schema_invalid["data"]["project_membership"]
        invalid_cases["schema_invalid"] = schema_invalid

        semantic_invalid = _current_dossier_envelope()
        semantic_invalid["subject"]["source_sha256"] = "0" * 64
        invalid_cases["semantic_invalid"] = semantic_invalid

        for label, dossier in invalid_cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                reports = root / "reports"
                reports.mkdir()
                log_path = reports / "build_probe.log"
                log_path.write_text("keep-existing-log\n", encoding="utf-8")
                dossier_path = reports / "function_dossier.json"
                dossier_path.write_text(json.dumps(dossier), encoding="utf-8")

                with self.assertRaises(ConsumerContractError):
                    build_probe(dossier_path, dry_run=True)

                self.assertFalse((root / "generated").exists())
                self.assertEqual(
                    "keep-existing-log\n",
                    log_path.read_text(encoding="utf-8"),
                )

    def test_legacy_dossier_rejects_unsafe_source_paths_before_write(self):
        unsafe_paths = (
            r"\outside.c",
            r"C:outside.c",
            r"C:\outside.c",
            r"\\server\share\outside.c",
            "/outside.c",
            r"src\..\outside.c",
        )
        for source_path in unsafe_paths:
            with (
                self.subTest(source_path=source_path),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                root = Path(temp_dir)
                reports = root / "reports"
                reports.mkdir()
                dossier_path = reports / "function_dossier.json"
                dossier_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "0.1",
                            "target": {
                                "source": source_path,
                                "function": "Target",
                            },
                            "build_context": {
                                "include_dirs": [],
                                "defines": [],
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                with self.assertRaises(ConsumerContractError):
                    build_probe(dossier_path, dry_run=True)

                self.assertFalse((root / "generated").exists())

    def test_legacy_dossier_accepts_relative_backslash_source_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            source = root / "extracted" / "src" / "control.c"
            source.parent.mkdir(parents=True)
            source.write_text("int Target(void) { return 0; }\n", encoding="ascii")
            dossier_path = reports / "function_dossier.json"
            dossier_path.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "target": {
                            "source": r"src\control.c",
                            "function": "Target",
                        },
                        "build_context": {"include_dirs": [], "defines": []},
                    }
                ),
                encoding="utf-8",
            )

            payload = build_probe(dossier_path, dry_run=True)
            _assert_command_source_is_samefile(self, source, payload["command"])


if __name__ == "__main__":
    unittest.main()
