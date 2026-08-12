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
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--log-file")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=CLIArgumentParser,
    )

    commands.add_parser("doctor", help="Check the local execution environment.")

    discover = commands.add_parser("discover-projects")
    discover.add_argument("--workspace", required=True)
    discover.add_argument("--dsw")
    discover.add_argument("--out")
    discover.add_argument("--with-dsp-details", action="store_true")

    map_source = commands.add_parser("map-source")
    map_source.add_argument("--workspace")
    map_source.add_argument("--dsw", required=True)
    map_source.add_argument("--source", required=True)
    map_source.add_argument("--configuration")
    map_source.add_argument("--project")
    map_source.add_argument("--out")

    list_functions = commands.add_parser("list-functions")
    list_functions.add_argument("--source", required=True)

    analyze = commands.add_parser("analyze-function")
    _add_function_target(analyze)
    analyze.add_argument("--out", required=True)
    analyze.add_argument(
        "--phase",
        choices=("analysis", "design", "harness"),
        default="design",
    )

    finalize = commands.add_parser("finalize-dossier")
    finalize.add_argument("--workspace", required=True)
    finalize.add_argument("--function")
    finalize.add_argument("--out")
    finalize.add_argument(
        "--mvp-level",
        choices=("mvp1", "mvp2", "mvp3", "auto"),
        default="auto",
    )
    review_set = commands.add_parser("review-set")
    review_set.add_argument("--workspace", required=True)
    review_set.add_argument("--artifact-kind", required=True)
    review_set.add_argument("--artifact-sha256", required=True)
    review_set.add_argument(
        "--decision",
        required=True,
        choices=("approved", "changes_requested"),
    )
    review_set.add_argument("--reviewer", required=True)
    review_set.add_argument("--comment", default="")
    review_set.add_argument("--reviewed-at")

    get_form = commands.add_parser("get-test-input-form")
    get_form.add_argument("--workspace", required=True)
    get_form.add_argument("--summary-only", action="store_true")

    apply_form = commands.add_parser("apply-test-input-form")
    apply_form.add_argument("--workspace", required=True)
    apply_form.add_argument("--input", required=True)
    apply_form.add_argument("--expected-revision", required=True, type=int)

    probe = commands.add_parser("build-probe")
    probe.add_argument("--workspace", required=True)
    probe.add_argument("--dry-run", action="store_true")
    probe.add_argument("--run", action="store_true")
    probe.add_argument("--timeout", type=int, default=120)
    probe.add_argument("--vcvars")
    probe.add_argument("--toolchain", choices=("vc6", "verification"), default="vc6")
    probe.add_argument("--cc")
    run_tests = commands.add_parser("run-tests")
    run_tests.add_argument("--workspace", required=True)
    run_tests.add_argument("--executable")
    test_selector = run_tests.add_mutually_exclusive_group(required=True)
    test_selector.add_argument("--case-id", action="append", dest="case_ids")
    test_selector.add_argument("--tag")
    test_selector.add_argument("--all", action="store_true")
    run_mode = run_tests.add_mutually_exclusive_group()
    run_mode.add_argument("--run", action="store_true")
    run_mode.add_argument("--plan", action="store_true")
    run_tests.add_argument("--timeout", type=int, default=60)
    run_tests.add_argument("--run-id")
    run_tests.set_defaults(
        dry_run=False,
        allow_placeholder_tests=False,
        treat_placeholder_as_inconclusive=False,
    )

    reanalyze = commands.add_parser("reanalyze-function")
    _add_function_target(reanalyze)
    reanalyze.add_argument("--out", required=True)
    reanalyze.add_argument("--previous-dossier")
    reanalyze.add_argument("--previous-test-spec")
    reanalyze.set_defaults(
        generate_updated_test_case_design=False,
        overwrite_test_case_design=False,
        include_low_confidence_matches=False,
    )

    apply_reanalysis = commands.add_parser("apply-reanalysis")
    apply_reanalysis.add_argument("--workspace", required=True)
    apply_reanalysis.add_argument("--candidate", required=True)
    apply_reanalysis.add_argument("--candidate-sha256", required=True)
    apply_reanalysis.add_argument("--expected-revision", required=True, type=int)

    suite_register = commands.add_parser("suite-register")
    _add_suite_write_args(suite_register)
    suite_register.add_argument("--workspace", required=True)

    suite_update = commands.add_parser("suite-update")
    _add_suite_write_args(suite_update)
    suite_update.add_argument("--entry-id", required=True)
    suite_update.add_argument("--workspace")
    suite_update.add_argument("--enabled", choices=("true", "false"))

    suite_remove = commands.add_parser("suite-remove")
    suite_remove.add_argument("--suite", required=True)
    suite_remove.add_argument("--entry-id", required=True)
    suite_remove.add_argument("--expected-revision", required=True, type=int)

    suite_list = commands.add_parser("suite-list")
    suite_list.add_argument("--suite", required=True)
    suite_list.add_argument("--tag")

    suite_run = commands.add_parser("suite-run")
    suite_run.add_argument("--suite", required=True)
    selector = suite_run.add_mutually_exclusive_group(required=True)
    selector.add_argument("--entry-id", action="append", dest="entry_ids")
    selector.add_argument("--tag")
    selector.add_argument("--all", action="store_true")
    mode = suite_run.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--plan", action="store_true")
    suite_run.add_argument("--timeout", type=int, default=60)
    suite_run.set_defaults(dry_run=False)

    return parser


def _add_function_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace")
    parser.add_argument("--dsw", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--configuration", default="Win32 Debug")
    parser.add_argument("--project")


def _add_suite_write_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--suite", required=True)
    parser.add_argument("--tags")
    parser.add_argument("--expected-revision", required=True, type=int)
