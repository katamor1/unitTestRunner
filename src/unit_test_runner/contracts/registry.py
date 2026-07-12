from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .kinds import ArtifactKind


CURRENT_CONTRACT_VERSION = "1.0.0"
CURRENT_TEST_SPEC_VERSION = "1.1.0"
CURRENT_REVIEW_DECISIONS_VERSION = "1.1.0"
CURRENT_FUNCTION_DOSSIER_VERSION = "1.1.0"
CURRENT_DOSSIER_MANIFEST_VERSION = "1.1.0"


@dataclass(frozen=True)
class ContractDefinition:
    kind: ArtifactKind
    current_version: str
    schema_resource: str
    compatible_source_versions: tuple[str, ...]
    semantic_validator: str


_TASK6_CURRENT_VERSIONS = {
    ArtifactKind.REVIEW_DECISIONS: CURRENT_REVIEW_DECISIONS_VERSION,
    ArtifactKind.FUNCTION_DOSSIER: CURRENT_FUNCTION_DOSSIER_VERSION,
    ArtifactKind.DOSSIER_MANIFEST: CURRENT_DOSSIER_MANIFEST_VERSION,
}

_DEFAULT_CONTRACTS = tuple(
    ContractDefinition(
        kind=kind,
        current_version=_TASK6_CURRENT_VERSIONS.get(kind, CURRENT_CONTRACT_VERSION),
        schema_resource=f"{kind.value}.schema.json",
        compatible_source_versions=(
            ("1.0.0", "0.1") if kind in _TASK6_CURRENT_VERSIONS else ("0.1",)
        ),
        semantic_validator=kind.value,
    )
    for kind in ArtifactKind
    if kind is not ArtifactKind.TEST_SPEC
)

_TASK6_V1_CONTRACTS = tuple(
    ContractDefinition(
        kind=kind,
        current_version="1.0.0",
        schema_resource=f"{kind.value}_v1_0.schema.json",
        compatible_source_versions=("0.1",),
        semantic_validator=kind.value,
    )
    for kind in _TASK6_CURRENT_VERSIONS
)


_TEST_SPEC_V1 = ContractDefinition(
    kind=ArtifactKind.TEST_SPEC,
    current_version="1.0.0",
    schema_resource="test_spec_v1_0.schema.json",
    compatible_source_versions=("0.1",),
    semantic_validator=ArtifactKind.TEST_SPEC.value,
)

_TEST_SPEC_CURRENT = ContractDefinition(
    kind=ArtifactKind.TEST_SPEC,
    current_version=CURRENT_TEST_SPEC_VERSION,
    schema_resource="test_spec.schema.json",
    compatible_source_versions=("1.0.0", "0.1"),
    semantic_validator=ArtifactKind.TEST_SPEC.value,
)

_CONTRACTS = _DEFAULT_CONTRACTS + (_TEST_SPEC_CURRENT,)
_CONTRACT_VERSIONS = _CONTRACTS + (_TEST_SPEC_V1,) + _TASK6_V1_CONTRACTS

_BY_KIND = {contract.kind: contract for contract in _CONTRACTS}
_BY_KIND_AND_VERSION = {
    (contract.kind, contract.current_version): contract
    for contract in _CONTRACT_VERSIONS
}


def iter_contracts() -> Iterator[ContractDefinition]:
    return iter(_CONTRACTS)


def iter_contract_versions() -> Iterator[ContractDefinition]:
    return iter(_CONTRACT_VERSIONS)


def get_contract(
    kind: ArtifactKind,
    version: str | None = None,
) -> ContractDefinition:
    if version is None:
        return _BY_KIND[kind]
    try:
        return _BY_KIND_AND_VERSION[(kind, version)]
    except KeyError as error:
        raise ValueError(
            f"Unsupported contract version for {kind.value}: {version}"
        ) from error
