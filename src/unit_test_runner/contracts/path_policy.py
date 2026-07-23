from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .kinds import ArtifactKind


@dataclass(frozen=True)
class ContractPathPolicy:
    scalar_fields: frozenset[str]
    list_fields: frozenset[str]
    nullable_scalar_fields: frozenset[str]


@dataclass(frozen=True)
class ContractPathValue:
    json_path: str
    field_name: str
    value: str
    container: Any
    key: str | int
    is_list_item: bool


_DEFAULT_SCALAR_FIELDS = frozenset(
    {
        "path",
        "source_path",
        "masked_source_path",
        "workspace_path",
        "working_directory",
        "source_file",
        "object_file",
        "log_file",
        "stdout_log",
        "stderr_log",
        "combined_log",
        "completion_plan",
        "input_probe_report",
        "probe_report",
        "related_file",
        "header_file",
        "stub_source_path",
        "stub_header_path",
        "markdown_path",
        "source_artifact",
    }
)

_DEFAULT_LIST_FIELDS = frozenset({"log_files"})

_DEFAULT_NULLABLE_SCALAR_FIELDS = frozenset(
    {
        "source_path",
        "masked_source_path",
        "log_file",
        "stdout_log",
        "stderr_log",
        "combined_log",
        "probe_report",
        "related_file",
        "source_file",
        "header_file",
        "stub_source_path",
        "stub_header_path",
        "markdown_path",
        "source_artifact",
    }
)

_BUILD_SCALAR_FIELDS = frozenset(
    {
        "output_root",
        "workspace_root",
        "original_path",
        "file",
        "included_from",
        "missing_from",
    }
)

_BUILD_LIST_FIELDS = frozenset(
    {
        "link_units",
        "include_dirs",
        "library_dirs",
        "forced_includes",
        "candidate_dirs",
        "target_files",
        "candidate_paths",
        "candidate_include_dirs",
        "generated_files",
    }
)

_BUILD_NULLABLE_SCALAR_FIELDS = frozenset(
    {
        "original_path",
        "file",
        "included_from",
        "missing_from",
    }
)

_DEFAULT_POLICY = ContractPathPolicy(
    scalar_fields=_DEFAULT_SCALAR_FIELDS,
    list_fields=_DEFAULT_LIST_FIELDS,
    nullable_scalar_fields=_DEFAULT_NULLABLE_SCALAR_FIELDS,
)

_BUILD_POLICY = ContractPathPolicy(
    scalar_fields=_DEFAULT_SCALAR_FIELDS | _BUILD_SCALAR_FIELDS,
    list_fields=_DEFAULT_LIST_FIELDS | _BUILD_LIST_FIELDS,
    nullable_scalar_fields=(
        _DEFAULT_NULLABLE_SCALAR_FIELDS | _BUILD_NULLABLE_SCALAR_FIELDS
    ),
)

_BUILD_ARTIFACT_KINDS = frozenset(
    {
        ArtifactKind.BUILD_CONTEXT,
        ArtifactKind.BUILD_WORKSPACE_REPORT,
        ArtifactKind.BUILD_PROBE_REPORT,
        ArtifactKind.BUILD_COMPLETION_PLAN,
        ArtifactKind.BUILD_COMPLETION_ITERATION,
        ArtifactKind.BUILD_COMPLETION_HISTORY,
    }
)


def path_policy_for(kind: ArtifactKind) -> ContractPathPolicy:
    if kind in _BUILD_ARTIFACT_KINDS:
        return _BUILD_POLICY
    return _DEFAULT_POLICY


def iter_contract_path_values(
    value: Any,
    policy: ContractPathPolicy,
    json_path: str = "$",
) -> Iterator[ContractPathValue]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{json_path}.{key}"
            if key in policy.scalar_fields and isinstance(child, str):
                yield ContractPathValue(
                    json_path=child_path,
                    field_name=key,
                    value=child,
                    container=value,
                    key=key,
                    is_list_item=False,
                )
            if key in policy.list_fields and isinstance(child, list):
                for index, item in enumerate(child):
                    if isinstance(item, str):
                        yield ContractPathValue(
                            json_path=f"{child_path}[{index}]",
                            field_name=key,
                            value=item,
                            container=child,
                            key=index,
                            is_list_item=True,
                        )
            yield from iter_contract_path_values(child, policy, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_contract_path_values(
                child,
                policy,
                f"{json_path}[{index}]",
            )
