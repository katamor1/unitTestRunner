from enum import StrEnum


class ArtifactKind(StrEnum):
    FUNCTION_DOSSIER = "function_dossier"
    TEST_SPEC = "test_spec"
    REVIEW_RECORD = "review_record"
    BUILD_PROBE_REPORT = "build_probe_report"
    TEST_RUN_REPORT = "test_run_report"
    REANALYSIS_REPORT = "reanalysis_report"
    SUITE_MANIFEST = "suite_manifest"
    SUITE_RUN_REPORT = "suite_run_report"


class RunOutcome(StrEnum):
    PLANNED = "planned"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    ERROR = "error"
