from __future__ import annotations

import ctypes
import os
import unittest
from dataclasses import dataclass
from pathlib import Path


WINDOWS_8DOT3_REQUIRED_ENV = "UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS"
WINDOWS_8DOT3_PREFIX = "unitTestRunner Windows 8dot3 alias "


class WindowsPathAliasUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WindowsPathAliasPair:
    original: Path
    long: Path
    short: Path


def _call_windows_path_api(function_name: str, path: Path) -> Path:
    if os.name != "nt":
        raise OSError("Windows path aliases require Windows.")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = getattr(kernel32, function_name)
    function.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    function.restype = ctypes.c_uint32
    path_text = os.path.abspath(os.fspath(path))
    capacity = max(260, len(path_text) + 1)
    while True:
        buffer = ctypes.create_unicode_buffer(capacity)
        written = function(path_text, buffer, capacity)
        if written == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        if written < capacity:
            return Path(buffer.value)
        capacity = written + 1


def windows_path_alias_pair(existing_dir: Path) -> WindowsPathAliasPair:
    original = Path(os.path.abspath(os.fspath(existing_dir)))
    if not original.is_dir():
        raise FileNotFoundError(original)
    long_path = _call_windows_path_api("GetLongPathNameW", original)
    short_path = _call_windows_path_api("GetShortPathNameW", long_path)
    if not long_path.is_dir() or not short_path.is_dir():
        raise AssertionError("Win32 path aliases must name existing directories.")
    if not os.path.samefile(long_path, short_path):
        raise AssertionError("Win32 long and short paths do not name the same directory.")
    long_key = os.path.normcase(os.path.normpath(os.fspath(long_path)))
    short_key = os.path.normcase(os.path.normpath(os.fspath(short_path)))
    if long_key == short_key:
        raise WindowsPathAliasUnavailable(
            f"No distinct Windows 8.3 alias exists for {long_path}"
        )
    return WindowsPathAliasPair(original, long_path, short_path)


def require_windows_path_alias_pair(
    test: unittest.TestCase,
    existing_dir: Path,
) -> WindowsPathAliasPair:
    try:
        return windows_path_alias_pair(existing_dir)
    except WindowsPathAliasUnavailable as error:
        if os.environ.get(WINDOWS_8DOT3_REQUIRED_ENV) == "1":
            test.fail(f"required Windows 8.3 alias unavailable: {error}")
        test.skipTest(str(error))
