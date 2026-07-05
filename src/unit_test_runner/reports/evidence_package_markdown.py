from __future__ import annotations

from unit_test_runner.execution.evidence_manifest import render_evidence_package
from unit_test_runner.execution.execution_models import EvidenceManifest, TestExecutionReport


def render_evidence_package_markdown(manifest: EvidenceManifest, report: TestExecutionReport) -> str:
    return render_evidence_package(manifest, report)
