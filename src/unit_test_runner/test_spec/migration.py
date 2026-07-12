from __future__ import annotations

from typing import Any, Mapping

from unit_test_runner.contracts import ArtifactKind, ContractViolation, migrate_payload

from .models import TestSpecContractError


def migrate_legacy_test_case_design(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Losslessly wrap the final v0.1 test-case-design shape as TEST_SPEC v1.

    Identity or authority fields are never invented or silently discarded. Older
    partial reports therefore fail with typed contract violations instead of
    becoming executable specifications with fabricated provenance.
    """
    try:
        return migrate_payload(
            ArtifactKind.TEST_SPEC,
            payload,
            target_version="1.1.0",
        )
    except (TypeError, ValueError) as error:
        raise TestSpecContractError(
            (
                ContractViolation(
                    "migration_error",
                    "$",
                    str(error),
                    "blocking",
                ),
            )
        ) from error
