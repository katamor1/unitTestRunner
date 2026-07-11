from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .c90_writer import sha256_file
from .dependency_dispatcher import apply_dependency_dispatcher, augment_call_report_for_dependency_policy
from .harness_report_writer import write_harness_report
from .harness_skeleton_generator import generate_harness_skeleton as _generate_harness_skeleton
from .parameter_init_compat import apply_parameter_init_compat
from .runner_output_enhancer import enhance_runner_output
from .state_setup_reflector import reflect_state_setups
from .target_invocation_compat import apply_target_invocation_compat
from .type_bridge import enrich_signature_bridge_types

apply_target_invocation_compat()
apply_parameter_init_compat()


def generate_harness_skeleton(
    function_signature: Any,
    global_access: Any,
    call_report: Any,
    test_case_design: Any,
    output_root: Path | str,
    overwrite: bool = False,
    dependency_policy: Any | None = None,
):
    output_root = Path(output_root).resolve()
    policy = dependency_policy or _load_dependency_policy(output_root)
    augmented_call_report = augment_call_report_for_dependency_policy(call_report, policy)
    signature_payload = function_signature.to_dict() if hasattr(function_signature, "to_dict") else function_signature
    if isinstance(signature_payload, dict):
        signature_payload = enrich_signature_bridge_types(signature_payload)
    report = _generate_harness_skeleton(signature_payload, global_access, augmented_call_report, test_case_design, output_root, overwrite)
    changed = []
    changed.extend(apply_dependency_dispatcher(output_root, policy, test_case_design, report))
    changed.extend(reflect_state_setups(output_root, test_case_design, report.function_name))
    changed.append(enhance_runner_output(output_root, report.function_name, report.test_skeletons))
    _refresh_generated_file_hashes(output_root, report, changed)
    write_harness_report(output_root, report)
    return report


def _load_dependency_policy(output_root: Path) -> dict[str, Any] | None:
    path = output_root / "reports" / "dependency_policy.json"
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _refresh_generated_file_hashes(output_root: Path, report, changed_paths: list[Path]) -> None:
    changed_relatives = {path.resolve().relative_to(output_root) for path in changed_paths if path.exists()}
    for item in report.generated_files:
        if item.path in changed_relatives:
            item.sha256 = sha256_file(output_root / item.path)
            item.overwrite = True


__all__ = ["generate_harness_skeleton"]
