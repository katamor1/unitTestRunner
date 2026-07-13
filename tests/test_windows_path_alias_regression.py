from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import unit_test_runner.path_utils as path_utils
from tests import windows_path_alias_support as alias_support
from unit_test_runner.execution.executable_resolver import resolve_executable


class WindowsPathAliasPolicyTests(unittest.TestCase):
    def test_required_mode_fails_when_alias_is_unavailable(self):
        error = alias_support.WindowsPathAliasUnavailable("disabled")
        with (
            mock.patch.dict(
                os.environ,
                {alias_support.WINDOWS_8DOT3_REQUIRED_ENV: "1"},
            ),
            mock.patch.object(
                alias_support,
                "windows_path_alias_pair",
                side_effect=error,
            ),
            self.assertRaises(AssertionError),
        ):
            alias_support.require_windows_path_alias_pair(self, Path("."))

    def test_optional_mode_skips_when_alias_is_unavailable(self):
        error = alias_support.WindowsPathAliasUnavailable("disabled")
        with (
            mock.patch.dict(
                os.environ,
                {alias_support.WINDOWS_8DOT3_REQUIRED_ENV: ""},
            ),
            mock.patch.object(
                alias_support,
                "windows_path_alias_pair",
                side_effect=error,
            ),
            self.assertRaises(unittest.SkipTest),
        ):
            alias_support.require_windows_path_alias_pair(self, Path("."))


class ResolvedRelativePathContractTests(unittest.TestCase):
    def test_strict_relative_primitive_is_public_and_rejects_outside_root(self):
        self.assertTrue(
            hasattr(path_utils, "resolved_relative_to"),
            "path_utils must expose resolved_relative_to",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            root = parent / "root"
            outside = parent / "outside.txt"
            root.mkdir()
            with self.assertRaises(ValueError):
                path_utils.resolved_relative_to(outside, root)


@unittest.skipUnless(os.name == "nt", "Windows 8.3 aliases require Windows")
class WindowsPathAliasIntegrationTests(unittest.TestCase):
    def _resolved_relative_to(self, path: Path, root: Path) -> Path:
        self.assertTrue(
            hasattr(path_utils, "resolved_relative_to"),
            "path_utils must expose resolved_relative_to",
        )
        return path_utils.resolved_relative_to(path, root)

    def test_helper_returns_distinct_existing_aliases_for_same_directory(self):
        with tempfile.TemporaryDirectory(
            prefix=alias_support.WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = alias_support.require_windows_path_alias_pair(
                self, Path(temp_dir)
            )
            self.assertTrue(pair.long.is_dir())
            self.assertTrue(pair.short.is_dir())
            self.assertTrue(os.path.samefile(pair.long, pair.short))
            self.assertNotEqual(
                os.path.normcase(os.fspath(pair.long)),
                os.path.normcase(os.fspath(pair.short)),
            )

    def test_resolve_executable_relativizes_short_executable_under_long_workspace_alias(self):
        with tempfile.TemporaryDirectory(
            prefix=alias_support.WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = alias_support.require_windows_path_alias_pair(
                self, Path(temp_dir)
            )
            executable = pair.long / "bin" / "utr_probe.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"fixture executable")
            info = resolve_executable(
                pair.long,
                pair.short / "bin" / "utr_probe.exe",
                {"function": {"status": "succeeded"}},
            )
            self.assertTrue(info.exists)
            self.assertEqual("bin/utr_probe.exe", info.path.as_posix())

    def test_relative_path_accepts_long_child_under_short_root_alias(self):
        with tempfile.TemporaryDirectory(
            prefix=alias_support.WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = alias_support.require_windows_path_alias_pair(
                self, Path(temp_dir)
            )
            (pair.long / "reports").mkdir()
            relative = self._resolved_relative_to(
                pair.long / "reports" / "test_spec.json",
                pair.short,
            )
            self.assertEqual(Path("reports/test_spec.json"), relative)

    def test_relative_path_accepts_short_child_under_long_root_alias(self):
        with tempfile.TemporaryDirectory(
            prefix=alias_support.WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = alias_support.require_windows_path_alias_pair(
                self, Path(temp_dir)
            )
            (pair.long / "reports").mkdir()
            relative = self._resolved_relative_to(
                pair.short / "reports" / "test_spec.json",
                pair.long,
            )
            self.assertEqual(Path("reports/test_spec.json"), relative)
