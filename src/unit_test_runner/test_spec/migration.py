from __future__ import annotations

import copy
from typing import Any, Mapping

from unit_test_runner import __version__
from unit_test_runner.contracts import ContractViolation
from unit_test_runner.execution.test_result_writer import current_producer_commit

from .models import TestSpecContractError


def migrate_legacy_test_case_design(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Losslessly wrap the final v0.1 test-case-design shape as TEST_SPEC v1.

    Identity or authority fields are never invented or silently discarded. Older
    partial reports therefore fail with typed contract violations instead of
    becoming executable specifications with fabricated provenance.
    """
    if str(payload.get("schema_version") or "") != "0.1":
        raise TestSpecContractError(
            (ContractViolation("unsupported_version", "$.schema_version", "Only the v0.1 legacy alias is compatible."),)
        )
    required = {
        "spec_id": payload.get("spec_id"),
        "revision": payload.get("revision"),
        "source.path": (payload.get("source") or {}).get("path"),
        "source.sha256": (payload.get("source") or {}).get("sha256"),
        "function.function_id": (payload.get("function") or {}).get("function_id"),
        "function.name": (payload.get("function") or {}).get("name"),
        "function.signature_sha256": (payload.get("function") or {}).get("signature_sha256"),
    }
    missing = [name for name, value in required.items() if value is None or value == ""]
    if missing:
        raise TestSpecContractError(
            tuple(
                ContractViolation(
                    "migration_requires_fabrication",
                    f"$.{name}",
                    "Lossless v0.1 migration requires this identity field.",
                    "blocking",
                )
                for name in missing
            )
        )
    source = copy.deepcopy(dict(payload["source"]))
    function = copy.deepcopy(dict(payload["function"]))
    data_fields = (
        "spec_id",
        "revision",
        "generated_from",
        "generation_policy",
        "test_cases",
        "additional_case_candidates",
        "coverage_summary",
        "unresolved_items",
        "warnings",
        "review_item_ids",
    )
    data = {name: copy.deepcopy(payload.get(name)) for name in data_fields}
    data["source"] = source
    data["function"] = function
    return {
        "artifact_kind": "test_spec",
        "schema_version": "1.1.0",
        "producer": {
            "name": "unit-test-runner",
            "version": __version__,
            "commit": current_producer_commit(),
        },
        "subject": {
            "function_id": function["function_id"],
            "source_path": source["path"],
            "source_sha256": source["sha256"],
        },
        "data": data,
        "extensions": {
            "migration": {
                "source_version": "0.1",
                "source_artifact_kind": "test_case_design",
                "in_memory_only": True,
            }
        },
    }
