from __future__ import annotations

from pathlib import Path
from typing import Any

from .c90_writer import sha256_file
from .harness_report_writer import write_harness_report
from .harness_skeleton_generator import generate_harness_skeleton as _generate_harness_skeleton
from .runner_output_enhancer import enhance_runner_output
from .state_setup_reflector import reflect_state_setups


def generate_harness_skeleton(
    function_signature: Any,
    global_access: Any,
    call_report: Any,
    test_case_design: Any,
    output_root: Path | str,
    overwrite: bool = False,
):
    report = _generate_harness_skeleton(function_signature, global_access, call_report, test_case_design, output_root, overwrite)
    output_root = Path(output_root).resolve()
    changed = []
    changed.extend(reflect_state_setups(output_root, test_case_design, report.function_name))
    changed.append(enhance_runner_output(output_root, report.function_name, report.test_skeletons))
    _refresh_generated_file_hashes(output_root, report, changed)
    write_harness_report(output_root, report)
    return report


def _refresh_generated_file_hashes(output_root: Path, report, changed_paths: list[Path]) -> None:
    changed_relatives = {path.resolve().relative_to(output_root) for path in changed_paths if path.exists()}
    for item in report.generated_files:
        if item.path in changed_relatives:
            item.sha256 = sha256_file(output_root / item.path)
            item.overwrite = True


__all__ = ["generate_harness_skeleton"]
