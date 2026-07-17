#!/usr/bin/env python3
"""Generate an external VC6-style fixture for large-application smoke tests."""

from __future__ import annotations

import argparse
import codecs
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_SOURCE_ENTRIES = 7000
DEFAULT_TIER_ENTRIES = (7000, 16000, 31000)
OUTPUT_PREFIX = "unit-test-runner-large-"
WORKSPACE_FILE = "Product.dsw"
TARGET_DSP = Path("DeviceControl") / "DeviceControl.dsp"
TARGET = {
    "project": "DeviceControl",
    "configuration": "DeviceControl - Win32 Debug",
    "source": "src/device_control.c",
    "function": "DeviceControl_Update",
}


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_base_root() -> Path:
    return repository_root() / "tests" / "fixtures" / "vc6_practical_project"


def default_perf_root() -> Path:
    configured = os.environ.get("UNIT_TEST_RUNNER_PERF_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(tempfile.gettempdir()) / "unitTestRunner_perf_samples").resolve()


def output_root_for_entries(perf_root: Path | str, entries: int) -> Path:
    return Path(perf_root) / f"{OUTPUT_PREFIX}{entries}"


def parse_tier_entries(value: str) -> tuple[int, ...]:
    entries: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            parsed = int(item)
        except ValueError as exc:
            raise ValueError(f"tier entries must be positive integers: {value}") from exc
        if parsed <= 0:
            raise ValueError(f"tier entries must be positive integers: {value}")
        entries.append(parsed)
    if not entries:
        raise ValueError(f"tier entries must contain at least one positive integer: {value}")
    return tuple(entries)


def assert_safe_output(output_root: Path | str, perf_root: Path | str) -> None:
    output = Path(output_root).expanduser().resolve()
    boundary = Path(perf_root).expanduser().resolve()
    try:
        relative = output.relative_to(boundary)
    except ValueError as exc:
        raise ValueError(f"refusing output outside performance root: {output}") from exc
    if not relative.parts:
        raise ValueError(f"refusing to use performance root itself as output: {output}")
    if not output.name.startswith(OUTPUT_PREFIX):
        raise ValueError(f"output directory must use expected prefix {OUTPUT_PREFIX!r}: {output}")


def reset_output(output_root: Path | str, perf_root: Path | str) -> None:
    output = Path(output_root).expanduser().resolve()
    assert_safe_output(output, perf_root)
    if output.exists():
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)


def generate_fixture(
    base_root: Path | str,
    output_root: Path | str,
    source_entries: int,
    perf_root: Path | str,
) -> dict[str, object]:
    base = Path(base_root).expanduser().resolve()
    output = Path(output_root).expanduser().resolve()
    boundary = Path(perf_root).expanduser().resolve()

    if not base.is_dir():
        raise FileNotFoundError(f"base fixture directory does not exist: {base}")
    if not (base / WORKSPACE_FILE).is_file():
        raise FileNotFoundError(f"base workspace file is missing: {base / WORKSPACE_FILE}")
    if not (base / TARGET_DSP).is_file():
        raise FileNotFoundError(f"base target project is missing: {base / TARGET_DSP}")
    if output == base or output in base.parents or base in output.parents:
        raise ValueError("base fixture and output directory must not contain one another")

    base_dsp, dsp_encoding = read_legacy_text(base / TARGET_DSP)
    base_source_entries = count_dsp_source_entries(base_dsp)
    if source_entries < base_source_entries:
        raise ValueError(
            f"source_entries must be at least {base_source_entries} because all base project sources are retained"
        )

    reset_output(output, boundary)
    shutil.copytree(base, output)

    generated_count = source_entries - base_source_entries
    generated_dir = output / "src" / "generated"
    generated_paths: list[str] = []
    if generated_count:
        generated_dir.mkdir(parents=True, exist_ok=True)
        width = max(5, len(str(generated_count - 1)))
        for index in range(generated_count):
            file_name = f"large_module_{index:0{width}d}.c"
            generated_paths.append(f"..\\src\\generated\\{file_name}")
            (generated_dir / file_name).write_text(
                render_generated_source(index, generated_count, width),
                encoding="utf-8",
            )

    output_dsp = output / TARGET_DSP
    output_dsp.write_bytes(append_dsp_sources(base_dsp, generated_paths).encode(dsp_encoding))

    manifest_path = output / "manifest.json"
    manifest = {
        "schema_version": 1,
        "generator": "scripts/generate_large_vc6_fixture.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_root": slash(base),
        "root": slash(output),
        "workspace_file": WORKSPACE_FILE,
        "target_project_file": slash(TARGET_DSP),
        "base_source_entries": base_source_entries,
        "source_entries_in_target_project": source_entries,
        "generated_source_files": generated_count,
        "total_files_on_disk": count_files(output) + (0 if manifest_path.exists() else 1),
        "target": dict(TARGET),
        "note": "Generated outside the repository as a disposable, read-only large-application fixture.",
    }
    manifest_path.write_text(
        f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    return manifest


def read_legacy_text(path: Path | str) -> tuple[str, str]:
    data = Path(path).read_bytes()
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "utf-8-sig"
    for encoding in ("utf-8", "cp932", "shift_jis"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"cannot decode VC6 project file: {path}")


def count_dsp_source_entries(text: str) -> int:
    return sum(
        1
        for line in text.splitlines()
        if line.strip().upper().startswith("SOURCE=") and _is_c_source(line)
    )


def _is_c_source(source_line: str) -> bool:
    value = source_line.split("=", 1)[-1].strip().strip('"').lower()
    return value.endswith((".c", ".cc", ".cpp", ".cxx"))


def append_dsp_sources(text: str, source_paths: Sequence[str]) -> str:
    if not source_paths:
        return text
    newline = "\r\n" if "\r\n" in text else "\n"
    marker = '# Begin Group "Source Files"'
    group_start = text.find(marker)
    if group_start < 0:
        raise ValueError('target DSP does not contain a "Source Files" group')
    group_end = text.find("# End Group", group_start)
    if group_end < 0:
        raise ValueError('target DSP "Source Files" group is not terminated')

    block_lines: list[str] = []
    for source_path in source_paths:
        block_lines.extend(
            [
                "# Begin Source File",
                f"SOURCE={source_path}",
                "# End Source File",
                "",
            ]
        )
    block = newline.join(block_lines)
    before = text[:group_end].rstrip("\r\n")
    after = text[group_end:]
    return f"{before}{newline}{newline}{block}{after}"


def render_generated_source(index: int, generated_count: int, width: int) -> str:
    name = f"UtrLarge_Module_{index:0{width}d}"
    lines = [
        '#include "device_control.h"',
        "",
        "extern unsigned long g_system_tick;",
        "",
    ]
    if generated_count > 1:
        next_index = (index + 1) % generated_count
        next_name = f"UtrLarge_Module_{next_index:0{width}d}"
        lines.extend([f"int {next_name}(int seed);", ""])
    lines.extend(
        [
            f"int {name}(int seed)",
            "{",
            "    int value;",
            f"    value = seed + {index % 97};",
            "    if ((value & 1) != 0) {",
            f"        value += {index % 31};",
            "    }",
        ]
    )
    if generated_count > 1:
        lines.extend(
            [
                "    if (seed > 0 && (seed % 17) == 0) {",
                f"        value += {next_name}(seed - 1);",
                "    }",
            ]
        )
    lines.extend(
        [
            "    if ((seed % 29) == 0) {",
            "        g_system_tick += (unsigned long)(value & 255);",
            "    }",
            "    return value;",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def count_files(root: Path | str) -> int:
    return sum(1 for path in Path(root).rglob("*") if path.is_file())


def slash(value: Path | str) -> str:
    return str(value).replace("\\", "/")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an external VC6-style large-application fixture for unitTestRunner."
    )
    parser.add_argument("--base", type=Path, default=default_base_root())
    parser.add_argument("--root", type=Path, default=default_perf_root())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--entries", type=int)
    parser.add_argument(
        "--tiers",
        nargs="?",
        const=",".join(str(entry) for entry in DEFAULT_TIER_ENTRIES),
        help="Comma-separated source-entry counts. Omit the value to use 7000,16000,31000.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if args.tiers and (args.entries is not None or args.output is not None):
        raise ValueError("--tiers cannot be combined with --entries or --output")

    perf_root = args.root.expanduser().resolve()
    base_root = args.base.expanduser().resolve()
    if args.tiers:
        summaries = [
            generate_fixture(
                base_root=base_root,
                output_root=output_root_for_entries(perf_root, entries),
                source_entries=entries,
                perf_root=perf_root,
            )
            for entries in parse_tier_entries(args.tiers)
        ]
        payload: dict[str, object] = {
            "base_root": slash(base_root),
            "performance_root": slash(perf_root),
            "tiers": summaries,
        }
    else:
        entries = args.entries if args.entries is not None else int(
            os.environ.get("UNIT_TEST_RUNNER_LARGE_ENTRIES", DEFAULT_SOURCE_ENTRIES)
        )
        if entries <= 0:
            raise ValueError("--entries must be a positive integer")
        output_root = args.output or output_root_for_entries(perf_root, entries)
        payload = generate_fixture(base_root, output_root, entries, perf_root)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
