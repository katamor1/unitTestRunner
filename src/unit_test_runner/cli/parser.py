from __future__ import annotations

import argparse

from unit_test_runner import __version__


class ArgumentParseError(Exception):
    def __init__(self, message: str, usage: str, command: str) -> None:
        super().__init__(message)
        self.message = message
        self.usage = usage
        self.command = command


class CLIArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        parts = self.prog.split()
        command = parts[-1] if len(parts) > 1 else "unknown"
        raise ArgumentParseError(message, self.format_usage(), command)


def build_parser() -> argparse.ArgumentParser:
    parser = CLIArgumentParser(prog="unit-test-runner")
    parser.add_argument("--version", action="version", version=f"unit-test-runner {__version__}")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    parser.add_argument("--quiet", action="store_true", help="Reduce non-essential output.")
    parser.add_argument("--log-file", help="Write logs to this file.")
    parser.add_argument("--json", action="store_true", help="Write machine-readable JSON to stdout.")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output.")
    subcommands = parser.add_subparsers(dest="command", required=True, parser_class=CLIArgumentParser)

    subcommands.add_parser("doctor", help="Check the local execution environment.")

    discover = subcommands.add_parser("discover-projects", help="Discover VC6 projects from a workspace.")
    discover.add_argument("--workspace", required=True)
    discover.add_argument("--dsw")
    discover.add_argument("--out")
    discover.add_argument("--with-dsp-details", action="store_true")

    map_source = subcommands.add_parser("map-source", help="Map a C source file to VC6 project candidates.")
    map_source.add_argument("--workspace")
    map_source.add_argument("--dsw", required=True)
    map_source.add_argument("--source", required=True)
    map_source.add_argument("--configuration")
    map_source.add_argument("--project")
    map_source.add_argument("--out")

    list_funcs = subcommands.add_parser("list-functions", help="List function definitions in a C source file.")
    list_funcs.add_argument("--source", required=True)

    analyze = subcommands.add_parser("analyze-function", help="Generate a function-level dossier.")
    analyze.add_argument("--workspace")
    analyze.add_argument("--dsw", required=True)
    analyze.add_argument("--source", required=True)
    analyze.add_argument("--function", required=True)
    analyze.add_argument("--configuration", default="Win32 Debug")
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--project")
    analyze.add_argument("--emit-json", action="store_true")
    analyze.add_argument("--emit-md", action="store_true")
    analyze.add_argument("--emit-csv", action="store_true")
    analyze.add_argument("--phase", choices=["analysis", "design", "harness", "build", "execution"], default="design")
    analyze.add_argument("--analyze-build-errors", action="store_true")
    analyze.add_argument("--apply-safe-completions", action="store_true")
    analyze.add_argument("--run-tests", action="store_true")
    analyze.add_argument("--finalize-dossier", action="store_true")
    analyze.add_argument("--reuse-existing-tests", action="store_true")
    analyze.add_argument("--previous-dossier")
    analyze.add_argument("--previous-test-case-design")
    analyze.add_argument("--generate-updated-test-case-design", action="store_true")
    analyze.add_argument("--overwrite-test-case-design", action="store_true")
    analyze.add_argument("--include-low-confidence-matches", action="store_true")

    reanalyze = subcommands.add_parser("reanalyze-function", help="Reanalyze a function and reconcile existing test design assets.")
    reanalyze.add_argument("--workspace")
    reanalyze.add_argument("--dsw", required=True)
    reanalyze.add_argument("--source", required=True)
    reanalyze.add_argument("--function", required=True)
    reanalyze.add_argument("--configuration", default="Win32 Debug")
    reanalyze.add_argument("--out", required=True)
    reanalyze.add_argument("--project")
    reanalyze.add_argument("--previous-dossier")
    reanalyze.add_argument("--previous-test-case-design")
    reanalyze.add_argument("--generate-updated-test-case-design", action="store_true")
    reanalyze.add_argument("--overwrite-test-case-design", action="store_true")
    reanalyze.add_argument("--include-low-confidence-matches", action="store_true")

    harness = subcommands.add_parser("generate-harness-skeleton", help="Generate C90 stub and harness skeleton files from analysis reports.")
    harness.add_argument("--function-signature", required=True)
    harness.add_argument("--global-access", required=True)
    harness.add_argument("--call-report", required=True)
    harness.add_argument("--test-case-design", required=True)
    harness.add_argument("--out", required=True)
    harness.add_argument("--overwrite", action="store_true")

    probe = subcommands.add_parser("build-probe", help="Run or prepare a build probe from a dossier or generated workspace.")
    probe.add_argument("--dossier")
    probe.add_argument("--workspace")
    probe.add_argument("--build-context")
    probe.add_argument("--source-digest")
    probe.add_argument("--harness-report")
    probe.add_argument("--vc6-bin")
    probe.add_argument("--vcvars")
    probe.add_argument("--out")
    probe.add_argument("--dry-run", action="store_true")
    probe.add_argument("--run", action="store_true")
    probe.add_argument("--timeout", type=int, default=120)
    probe.add_argument("--overwrite", action="store_true")

    build_errors = subcommands.add_parser("analyze-build-errors", help="Analyze build probe diagnostics and generate a completion plan.")
    build_errors.add_argument("--workspace")
    build_errors.add_argument("--build-workspace-report")
    build_errors.add_argument("--build-probe-report")
    build_errors.add_argument("--call-report")
    build_errors.add_argument("--harness-report")
    build_errors.add_argument("--source-root")
    build_errors.add_argument("--out")

    complete = subcommands.add_parser("complete-build", help="Apply safe build completions inside a generated workspace.")
    complete.add_argument("--workspace", required=True)
    complete.add_argument("--source-root")
    complete.add_argument("--apply-safe-completions", action="store_true")
    complete.add_argument("--run-probe-after-apply", action="store_true")
    complete.add_argument("--max-iterations", type=int, default=3)
    complete.add_argument("--generate-unknown-symbol-stubs", action="store_true")
    complete.add_argument("--overwrite-existing-generated-stubs", action="store_true")

    run_tests = subcommands.add_parser("run-tests", help="Run generated tests or prepare dry-run execution evidence.")
    run_tests.add_argument("--workspace", required=True)
    run_tests.add_argument("--executable")
    run_tests.add_argument("--run", action="store_true")
    run_tests.add_argument("--dry-run", action="store_true")
    run_tests.add_argument("--timeout", type=int, default=60)
    run_tests.add_argument("--allow-placeholder-tests", action="store_true")
    run_tests.add_argument("--treat-placeholder-as-inconclusive", action="store_true", default=True)

    evidence = subcommands.add_parser("prepare-evidence", help="Regenerate evidence manifest and package from a generated workspace.")
    evidence.add_argument("--workspace", required=True)
    evidence.add_argument("--out")

    finalize = subcommands.add_parser("finalize-dossier", help="Finalize function dossier and review workflow artifacts from a generated workspace.")
    finalize.add_argument("--workspace", required=True)
    finalize.add_argument("--function")
    finalize.add_argument("--out")
    finalize.add_argument("--mvp-level", choices=("mvp1", "mvp2", "mvp3", "mvp4", "auto"), default="auto")
    finalize.add_argument("--allow-missing-optional-artifacts", action="store_true", default=True)
    finalize.add_argument("--strict-schema-version", action="store_true")

    review = subcommands.add_parser("prepare-review", help="Regenerate review workflow artifacts from a finalized dossier.")
    review.add_argument("--dossier", required=True)
    review.add_argument("--out")

    design = subcommands.add_parser("generate-test-design", help="Generate a test design from a dossier or analysis reports.")
    design.add_argument("--dossier")
    design.add_argument("--function-signature")
    design.add_argument("--global-access")
    design.add_argument("--call-report")
    design.add_argument("--coverage-design")
    design.add_argument("--boundary-candidates")
    design.add_argument("--out")
    design.add_argument("--format", choices=("csv", "md", "json", "all"), default="csv")

    reconcile = subcommands.add_parser("reconcile-test-cases", help="Reconcile previous and current test case design reports.")
    reconcile.add_argument("--previous-test-case-design", required=True)
    reconcile.add_argument("--previous-coverage-design", required=True)
    reconcile.add_argument("--current-test-case-design", required=True)
    reconcile.add_argument("--current-coverage-design", required=True)
    reconcile.add_argument("--current-boundary-candidates", required=True)
    reconcile.add_argument("--out", required=True)
    reconcile.add_argument("--generate-updated-test-case-design", action="store_true")
    reconcile.add_argument("--include-low-confidence-matches", action="store_true")

    select_regression = subcommands.add_parser("select-regression-tests", help="Select impacted regression tests from Step19 reports.")
    select_regression.add_argument("--change-impact", required=True)
    select_regression.add_argument("--reconciliation", required=True)
    select_regression.add_argument("--out", required=True)

    return parser
