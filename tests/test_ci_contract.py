from pathlib import Path
import hashlib
import re
import subprocess
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]


def _job_block(text: str, job_id: str, violations: list[str]) -> str | None:
    pattern = re.compile(
        rf"^  {re.escape(job_id)}:\s*\n.*?(?=^  [a-z][a-z0-9-]+:\s*$|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        violations.append(f"expected one {job_id} job, found {len(matches)}")
        return None
    return matches[0].group(0)


def _named_step(
    job_text: str,
    step_name: str,
    violations: list[str],
) -> tuple[str, int] | None:
    pattern = re.compile(
        rf"^      - name: {re.escape(step_name)}\s*\n"
        r".*?(?=^      - name: |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(job_text))
    if len(matches) != 1:
        violations.append(f"expected one {step_name} step, found {len(matches)}")
        return None
    return matches[0].group(0), matches[0].start()


def _without_full_line_comments(text: str) -> str:
    return re.sub(r"(?m)^[ \t]*#.*(?:\n|\Z)", "", text)


def _normalized_executable_text(text: str) -> str:
    executable = _without_full_line_comments(text)
    return "\n".join(
        line.rstrip() for line in executable.splitlines() if line.strip()
    )


_PYTHON_ISOLATED_SCRIPT = (
    '$log = Join-Path $env:RUNNER_TEMP "python-tests.log"',
    "$modules = Get-ChildItem -LiteralPath .\\tests -Filter 'test_*.py' -File |",
    "  Sort-Object Name |",
    "  ForEach-Object { 'tests.' + $_.BaseName }",
    "if ($modules.Count -eq 0) {",
    "  throw 'isolated Python test discovery returned no modules'",
    "}",
    "$failed = @()",
    "foreach ($module in $modules) {",
    '  "`n=== $module ===" | Tee-Object -FilePath $log -Append',
    "  & python -m unittest $module -v *>&1 |",
    "    Tee-Object -FilePath $log -Append",
    "  if ($LASTEXITCODE -ne 0) { $failed += $module }",
    "}",
    '"isolated_modules=$($modules.Count) failures=$($failed.Count)" |',
    "  Tee-Object -FilePath $log -Append",
    "if ($failed.Count -ne 0) {",
    "  throw ('isolated Python failures: ' + ($failed -join ', '))",
    "}",
)

_FIXTURE_COMPILER_SCRIPT = (
    "$compiler = Get-Command gcc, clang, cc -ErrorAction SilentlyContinue |",
    "  Select-Object -First 1",
    "if ($null -eq $compiler) {",
    "  throw 'VC6 fixture smoke requires gcc, clang, or cc on PATH.'",
    "}",
    '"fixture_compiler=$($compiler.Source)"',
)

_FIXTURE_SMOKE_SCRIPT = (
    '$log = Join-Path $env:RUNNER_TEMP "fixture-smoke.log"',
    "& python -m unittest tests.test_fixture_cli_smoke "
    "tests.test_vc6_fixture_build_e2e -v *>&1 | Tee-Object -FilePath $log",
    "$testExit = $LASTEXITCODE",
    "if ($testExit -ne 0) { exit $testExit }",
)

_EXPECTED_WORKFLOW_PREAMBLE = (
    "name: CI",
    "on:",
    "  push:",
    "  pull_request:",
    "  workflow_dispatch:",
    "jobs:",
)
_EXPECTED_EXECUTABLE_WORKFLOW_SHA256 = (
    "6bf9468ab020390dd94969bbd9cad45dd10531fdc938d624d9042e45db211b42"
)

_EXPECTED_PYTHON_JOB = (
    "python-tests:",
    "  name: Python tests",
    "  runs-on: windows-latest",
    "  env:",
    '    UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"',
    "  steps:",
    "    - name: Checkout",
    "      uses: actions/checkout@v4",
    "    - name: Set up Python",
    "      uses: actions/setup-python@v5",
    "      with:",
    '        python-version: "3.12"',
    "    - name: Install Python dependencies",
    "      run: |",
    '        python -m pip install "setuptools>=61" wheel',
    "        python -m pip install -e .",
    "    - name: Run Python tests in isolated processes",
    "      shell: pwsh",
    "      run: |",
) + tuple(f"        {line}" for line in _PYTHON_ISOLATED_SCRIPT) + (
    "    - name: Upload Python failure log",
    "      if: failure()",
    "      uses: actions/upload-artifact@v4",
    "      with:",
    "        name: python-test-failure",
    "        path: ${{ runner.temp }}\\python-tests.log",
)

_EXPECTED_FIXTURE_JOB = (
    "fixture-smoke:",
    "  name: VC6 fixture smoke",
    "  runs-on: windows-latest",
    "  steps:",
    "    - name: Checkout",
    "      uses: actions/checkout@v4",
    "    - name: Set up Python",
    "      uses: actions/setup-python@v5",
    "      with:",
    '        python-version: "3.12"',
    "    - name: Install Python dependencies",
    "      run: |",
    '        python -m pip install "setuptools>=61" wheel',
    "        python -m pip install -e .",
    "    - name: Require host C compiler",
    "      shell: pwsh",
    "      run: |",
) + tuple(f"        {line}" for line in _FIXTURE_COMPILER_SCRIPT) + (
    "    - name: Run fixture smoke",
    "      run: |",
) + tuple(f"        {line}" for line in _FIXTURE_SMOKE_SCRIPT) + (
    "    - name: Upload fixture-smoke failure log",
    "      if: failure()",
    "      uses: actions/upload-artifact@v4",
    "      with:",
    "        name: fixture-smoke-failure",
    "        path: ${{ runner.temp }}\\fixture-smoke.log",
)


def _normalized_job_lines(
    job_text: str,
    job_name: str,
    violations: list[str],
) -> tuple[str, ...] | None:
    executable = _without_full_line_comments(job_text)
    normalized = []
    for line in executable.splitlines():
        if not line.strip():
            continue
        if not line.startswith("  "):
            violations.append(f"{job_name} has invalid job-block indentation")
            return None
        normalized.append(line[2:].rstrip())
    return tuple(normalized)


def _require_exact_executable_workflow(
    text: str,
    violations: list[str],
) -> None:
    normalized = _normalized_executable_text(text)
    actual = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if actual != _EXPECTED_EXECUTABLE_WORKFLOW_SHA256:
        violations.append("workflow executable SHA-256 differs from contract")


def _require_exact_workflow_preamble(
    text: str,
    violations: list[str],
) -> None:
    lines = _normalized_executable_text(text).splitlines()
    job_markers = [index for index, line in enumerate(lines) if line == "jobs:"]
    if len(job_markers) != 1:
        violations.append("workflow must contain one top-level jobs mapping")
        return
    preamble = tuple(
        line.rstrip()
        for line in lines[: job_markers[0] + 1]
        if line.strip()
    )
    if preamble != _EXPECTED_WORKFLOW_PREAMBLE:
        violations.append("workflow triggers or top-level defaults differ from contract")


def _require_exact_job(
    job_text: str,
    job_name: str,
    expected: tuple[str, ...],
    violations: list[str],
) -> None:
    actual = _normalized_job_lines(job_text, job_name, violations)
    if actual is not None and actual != expected:
        violations.append(f"{job_name} job differs from its canonical contract")


def _run_script_lines(
    step_text: str,
    step_name: str,
    violations: list[str],
) -> tuple[str, ...] | None:
    marker = "        run: |"
    lines = step_text.splitlines()
    positions = [
        index for index, line in enumerate(lines) if line.rstrip() == marker
    ]
    if len(positions) != 1:
        violations.append(
            f"{step_name} must contain one literal PowerShell run block"
        )
        return None

    executable_lines = []
    for line in lines[positions[0] + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith("          "):
            violations.append(f"{step_name} has an invalid run-block indentation")
            return None
        executable_lines.append(line[10:].rstrip())
    return tuple(executable_lines)


def _require_exact_run_script(
    step_text: str,
    step_name: str,
    expected: tuple[str, ...],
    violations: list[str],
) -> None:
    actual = _run_script_lines(step_text, step_name, violations)
    if actual is not None and actual != expected:
        violations.append(f"{step_name} executable script differs from its contract")


def _python_ci_contract_violations(text: str) -> list[str]:
    violations: list[str] = []
    job = _job_block(text, "python-tests", violations)
    if job is None:
        return violations
    _require_exact_job(job, "python-tests", _EXPECTED_PYTHON_JOB, violations)

    run_info = _named_step(job, "Run Python tests in isolated processes", violations)
    upload_info = _named_step(job, "Upload Python failure log", violations)
    if run_info is None or upload_info is None:
        return violations
    run_step, run_position = run_info
    upload_step, upload_position = upload_info
    _require_exact_run_script(
        run_step,
        "isolated Python test step",
        _PYTHON_ISOLATED_SCRIPT,
        violations,
    )
    if run_position >= upload_position:
        violations.append("Python failure upload must follow the isolated test step")

    executable_job = _without_full_line_comments(job)
    executable_run_step = _without_full_line_comments(run_step)
    forbidden = 'python -m unittest discover -s tests -p "test_*.py"'
    if forbidden in executable_job:
        violations.append(f"forbidden command present in python-tests: {forbidden}")
    if "-Recurse" in executable_run_step:
        violations.append("Python module enumeration must remain top-level")

    ordered_tokens = (
        "Get-ChildItem -LiteralPath .\\tests -Filter 'test_*.py' -File",
        "Sort-Object Name",
        "ForEach-Object { 'tests.' + $_.BaseName }",
        "$failed = @()",
        "foreach ($module in $modules) {",
    )
    token_positions = []
    for token in ordered_tokens:
        position = executable_run_step.find(token)
        if position < 0:
            violations.append(f"isolated Python step missing: {token}")
        token_positions.append(position)
    if all(position >= 0 for position in token_positions) and token_positions != sorted(
        token_positions
    ):
        violations.append("Python enumeration, sorting, conversion, and loop are out of order")

    executable_log_lines = [
        line.strip()
        for line in executable_run_step.splitlines()
        if "$log" in line
    ]
    log_initializer = '$log = Join-Path $env:RUNNER_TEMP "python-tests.log"'
    if executable_log_lines.count(log_initializer) != 1:
        violations.append("isolated Python log must have one Join-Path initializer")
    invalid_log_lines = [
        line
        for line in executable_log_lines
        if line != log_initializer
        and (
            line.count("$log") != 1
            or re.fullmatch(
                r"(?:.+\|\s*)?Tee-Object -FilePath \$log -Append",
                line,
            )
            is None
        )
    ]
    if invalid_log_lines:
        violations.append("isolated Python log may only be initialized or appended")

    loop_match = re.search(
        r"^          foreach \(\$module in \$modules\) \{\s*\n"
        r"(?P<body>.*?)"
        r"^          \}\s*$",
        executable_run_step,
        re.MULTILINE | re.DOTALL,
    )
    if loop_match is None:
        violations.append("isolated Python module loop is missing")
        return violations

    loop_body = loop_match.group("body")
    if "& python -m unittest $module -v" not in loop_body:
        violations.append("module unittest command must run inside the module loop")
    loop_lines = [line.strip() for line in loop_body.splitlines() if line.strip()]
    exact_guard = "if ($LASTEXITCODE -ne 0) { $failed += $module }"
    guard_count = len(re.findall(r"(?i)\bif\s*\(", loop_body))
    if loop_lines.count(exact_guard) != 1 or guard_count != 1:
        violations.append("module loop must contain exactly the canonical failure guard")
    if loop_body.count("Tee-Object -FilePath $log -Append") < 2:
        violations.append("per-module log writes must append")
    if re.search(
        r"(?i)\b(?:throw|exit|break|return)\b",
        loop_body,
    ):
        violations.append("module failures must not stop later module iterations")

    post_loop = executable_run_step[loop_match.end() :]
    summary = '"isolated_modules=$($modules.Count) failures=$($failed.Count)"'
    summary_position = post_loop.find(summary)
    if summary_position < 0:
        violations.append("isolated Python result summary is missing")
    else:
        summary_tail = post_loop[summary_position + len(summary) :]
        if re.match(
            r"\s*\|\s*\n\s*Tee-Object -FilePath \$log -Append",
            summary_tail,
        ) is None:
            violations.append("isolated Python result summary must append to the log")

    guard_search_start = max(summary_position, 0)
    final_guard = re.search(
        r"if \(\$failed\.Count -ne 0\) \{\s*"
        r"throw \('isolated Python failures: ' \+ "
        r"\(\$failed -join ', '\)\)\s*\}",
        post_loop[guard_search_start:],
        re.MULTILINE | re.DOTALL,
    )
    if final_guard is None:
        violations.append("a final failed-module guard and throw are required after the loop")

    if "if: failure()" not in upload_step:
        violations.append("Python failure log must upload on failure")
    if "uses: actions/upload-artifact@v4" not in upload_step:
        violations.append("Python failure log must use actions/upload-artifact@v4")
    if re.search(
        r"^          name: python-test-failure\s*$",
        upload_step,
        re.MULTILINE,
    ) is None:
        violations.append("Python failure artifact must be named python-test-failure")
    return violations


def _fixture_ci_contract_violations(text: str) -> list[str]:
    violations: list[str] = []
    job = _job_block(text, "fixture-smoke", violations)
    if job is None:
        return violations
    _require_exact_job(job, "fixture-smoke", _EXPECTED_FIXTURE_JOB, violations)

    install_info = _named_step(job, "Install Python dependencies", violations)
    compiler_info = _named_step(job, "Require host C compiler", violations)
    smoke_info = _named_step(job, "Run fixture smoke", violations)
    upload_info = _named_step(job, "Upload fixture-smoke failure log", violations)
    if any(
        info is None
        for info in (install_info, compiler_info, smoke_info, upload_info)
    ):
        return violations

    install_step, install_position = install_info
    compiler_step, compiler_position = compiler_info
    smoke_step, smoke_position = smoke_info
    upload_step, upload_position = upload_info
    _require_exact_run_script(
        compiler_step,
        "fixture compiler precondition step",
        _FIXTURE_COMPILER_SCRIPT,
        violations,
    )
    _require_exact_run_script(
        smoke_step,
        "fixture smoke step",
        _FIXTURE_SMOKE_SCRIPT,
        violations,
    )
    if not (
        install_position < compiler_position < smoke_position < upload_position
    ):
        violations.append(
            "fixture steps must order dependencies, compiler precondition, smoke, upload"
        )

    if "python -m pip install -e ." not in install_step:
        violations.append("fixture dependency installation is missing")
    if "Get-Command gcc, clang, cc -ErrorAction SilentlyContinue" not in compiler_step:
        violations.append("fixture compiler discovery is missing")
    missing_compiler_branch = re.search(
        r"if \(\$null -eq \$compiler\) \{\s*"
        r"throw 'VC6 fixture smoke requires gcc, clang, or cc on PATH\.'\s*\}",
        _without_full_line_comments(compiler_step),
        re.MULTILINE | re.DOTALL,
    )
    if missing_compiler_branch is None:
        violations.append("missing fixture compiler must throw")

    dynamic_install_patterns = (
        r"\bchoco\s+install\b",
        r"\bwinget\s+install\b",
        r"\bscoop\s+install\b",
        r"\bapt-get\s+install\b",
        r"\bbrew\s+install\b",
        r"\bInstall-Package\b",
    )
    executable_job = _without_full_line_comments(job)
    if any(
        re.search(pattern, executable_job, re.IGNORECASE)
        for pattern in dynamic_install_patterns
    ):
        violations.append("fixture-smoke must not install a compiler dynamically")

    fixture_command = (
        "python -m unittest tests.test_fixture_cli_smoke "
        "tests.test_vc6_fixture_build_e2e -v"
    )
    if fixture_command not in smoke_step:
        violations.append("fixture smoke command is missing from its step")
    if "if: failure()" not in upload_step:
        violations.append("fixture failure log must upload on failure")
    if "uses: actions/upload-artifact@v4" not in upload_step:
        violations.append("fixture failure log must use actions/upload-artifact@v4")
    if re.search(
        r"^          name: fixture-smoke-failure\s*$",
        upload_step,
        re.MULTILINE,
    ) is None:
        violations.append("fixture failure artifact must be named fixture-smoke-failure")
    return violations


def _ci_contract_violations(text: str) -> list[str]:
    violations: list[str] = []
    _require_exact_executable_workflow(text, violations)
    _require_exact_workflow_preamble(text, violations)
    return (
        violations
        + _python_ci_contract_violations(text)
        + _fixture_ci_contract_violations(text)
    )


def _move_step_after(text: str, step_name: str, after_name: str) -> str:
    step_pattern = re.compile(
        rf"^      - name: {re.escape(step_name)}\n.*?(?=^      - name: |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    source = step_pattern.search(text)
    if source is None:
        raise AssertionError(f"step not found: {step_name}")
    source_text = source.group(0)
    without_source = text[: source.start()] + text[source.end() :]

    after_pattern = re.compile(
        rf"^      - name: {re.escape(after_name)}\n.*?(?=^      - name: |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    target = after_pattern.search(without_source)
    if target is None:
        raise AssertionError(f"step not found: {after_name}")
    return (
        without_source[: target.end()]
        + source_text
        + without_source[target.end() :]
    )


class CiContractTests(unittest.TestCase):
    def test_python_build_package_sources_are_not_ignored(self):
        completed = subprocess.run(
            [
                "git",
                "check-ignore",
                "--no-index",
                "-q",
                "src/unit_test_runner/build/dependency_rewriter.py",
            ],
            cwd=REPO_ROOT,
            check=False,
        )

        self.assertNotEqual(0, completed.returncode)

    def test_github_actions_runs_python_and_vscode_extension_gates(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        self.assertTrue(workflow.exists())
        text = workflow.read_text(encoding="utf-8")
        self.assertEqual([], _python_ci_contract_violations(text))
        self.assertIn("npm.cmd test", text)
        self.assertIn("vscode/extension", text)

    def test_github_actions_uses_six_independent_required_jobs(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        text = _normalized_executable_text(
            workflow.read_text(encoding="utf-8")
        )
        jobs_text = text.split("\njobs:\n", maxsplit=1)[1]
        job_ids = set(re.findall(r"^  ([a-z][a-z0-9-]+):\s*$", jobs_text, re.MULTILINE))
        self.assertEqual(
            {
                "source-integrity",
                "python-tests",
                "vscode-tests",
                "vscode-activation",
                "fixture-smoke",
                "package-contract",
            },
            job_ids,
        )
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("needs:", text)
        self.assertNotIn("continue-on-error", text)

    def test_github_actions_runs_activation_fixture_and_failure_log_contracts(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        text = workflow.read_text(encoding="utf-8")
        self.assertIn("npm.cmd run test:extension-host", text)
        self.assertEqual([], _fixture_ci_contract_violations(text))
        self.assertIn("uses: actions/upload-artifact@v4", text)
        self.assertIn("if: failure()", text)

    def test_github_actions_ci_contract_rejects_mutants(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        text = _normalized_executable_text(
            workflow.read_text(encoding="utf-8")
        )
        alias_env = (
            "    env:\n"
            '      UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"\n'
        )
        relocated_alias_env = text.replace(alias_env, "", 1).replace(
            "  source-integrity:\n",
            "  source-integrity:\n" + alias_env,
            1,
        )
        mutants = {
            "missing module sort": text.replace(
                "            Sort-Object Name |\n",
                "",
                1,
            ),
            "missing failure collection": text.replace(
                "            if ($LASTEXITCODE -ne 0) { $failed += $module }\n",
                "",
                1,
            ),
            "missing final throw": text.replace(
                "            throw ('isolated Python failures: ' + "
                "($failed -join ', '))\n",
                "",
                1,
            ),
            "missing append logging": text.replace(
                "Tee-Object -FilePath $log -Append",
                "Tee-Object -FilePath $log",
            ),
            "compiler precondition after fixture smoke": _move_step_after(
                text,
                "Require host C compiler",
                "Run fixture smoke",
            ),
            "dynamic compiler installation": text.replace(
                '          "fixture_compiler=$($compiler.Source)"\n',
                "          choco install mingw\n"
                '          "fixture_compiler=$($compiler.Source)"\n',
                1,
            ),
            "renamed Python failure artifact": text.replace(
                "          name: python-test-failure\n",
                "          name: renamed-python-test-failure\n",
                1,
            ),
            "inline exit after failure collection": text.replace(
                "if ($LASTEXITCODE -ne 0) { $failed += $module }",
                "if ($LASTEXITCODE -ne 0) { "
                "$failed += $module; exit $LASTEXITCODE }",
                1,
            ),
            "success polarity failure collection": text.replace(
                "if ($LASTEXITCODE -ne 0) { $failed += $module }",
                "if ($LASTEXITCODE -eq 0) { $failed += $module }",
                1,
            ),
            "post-loop log truncation": text.replace(
                '          "isolated_modules=$($modules.Count) '
                'failures=$($failed.Count)" |\n'
                "            Tee-Object -FilePath $log -Append\n",
                '          "isolated_modules=$($modules.Count) '
                'failures=$($failed.Count)" |\n'
                "            Tee-Object -FilePath $log -Append\n"
                '          Set-Content -Path $log -Value "truncated"\n',
                1,
            ),
            "pipelined log truncation before append": text.replace(
                '          "isolated_modules=$($modules.Count) '
                'failures=$($failed.Count)" |\n'
                "            Tee-Object -FilePath $log -Append\n",
                '          "isolated_modules=$($modules.Count) '
                'failures=$($failed.Count)" |\n'
                "            Tee-Object -FilePath $log -Append\n"
                "          'truncated' | Set-Content -Path $log | "
                "Tee-Object -FilePath $log -Append\n",
                1,
            ),
            "zero Python tests via selector": text.replace(
                "& python -m unittest $module -v *>&1 |",
                "& python -m unittest $module -v -k __never_match__ *>&1 |",
                1,
            ),
            "zero fixture tests via selector": text.replace(
                "tests.test_vc6_fixture_build_e2e -v *>&1 |",
                "tests.test_vc6_fixture_build_e2e -v -k __never_match__ *>&1 |",
                1,
            ),
            "post-loop failure reset": text.replace(
                '          "isolated_modules=$($modules.Count) ',
                "          $failed = @()\n"
                '          "isolated_modules=$($modules.Count) ',
                1,
            ),
            "compiler overwritten after discovery": text.replace(
                '          "fixture_compiler=$($compiler.Source)"\n',
                "          $compiler = $null\n"
                '          "fixture_compiler=$($compiler.Source)"\n',
                1,
            ),
            "literal-path log truncation": text.replace(
                '          "isolated_modules=$($modules.Count) '
                'failures=$($failed.Count)" |\n'
                "            Tee-Object -FilePath $log -Append\n",
                '          "isolated_modules=$($modules.Count) '
                'failures=$($failed.Count)" |\n'
                "            Tee-Object -FilePath $log -Append\n"
                "          Set-Content -LiteralPath "
                '(Join-Path $env:RUNNER_TEMP "python-tests.log") '
                '-Value "truncated"\n',
                1,
            ),
            "8dot3 required mode moved to another job": relocated_alias_env,
            "disabled Python test step": text.replace(
                "      - name: Run Python tests in isolated processes\n"
                "        shell: pwsh\n",
                "      - name: Run Python tests in isolated processes\n"
                "        if: ${{ false }}\n"
                "        shell: pwsh\n",
                1,
            ),
            "disabled fixture compiler step": text.replace(
                "      - name: Require host C compiler\n"
                "        shell: pwsh\n",
                "      - name: Require host C compiler\n"
                "        if: ${{ false }}\n"
                "        shell: pwsh\n",
                1,
            ),
            "disabled fixture smoke step": text.replace(
                "      - name: Run fixture smoke\n"
                "        run: |\n",
                "      - name: Run fixture smoke\n"
                "        if: ${{ false }}\n"
                "        run: |\n",
                1,
            ),
            "disabled Python job": text.replace(
                "  python-tests:\n"
                "    name: Python tests\n",
                "  python-tests:\n"
                "    if: ${{ false }}\n"
                "    name: Python tests\n",
                1,
            ),
            "disabled fixture job": text.replace(
                "  fixture-smoke:\n"
                "    name: VC6 fixture smoke\n",
                "  fixture-smoke:\n"
                "    if: ${{ false }}\n"
                "    name: VC6 fixture smoke\n",
                1,
            ),
            "Python step alias override": text.replace(
                "      - name: Run Python tests in isolated processes\n"
                "        shell: pwsh\n",
                "      - name: Run Python tests in isolated processes\n"
                "        env:\n"
                '          UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "0"\n'
                "        shell: pwsh\n",
                1,
            ),
            "Python custom shell masks failure": text.replace(
                "      - name: Run Python tests in isolated processes\n"
                "        shell: pwsh\n",
                "      - name: Run Python tests in isolated processes\n"
                '        shell: pwsh -Command "pwsh -File \'{0}\'; exit 0"\n',
                1,
            ),
            "lowercase alias override": text.replace(
                '      UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"\n',
                '      UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"\n'
                '      unit_test_runner_require_8dot3_alias: "0"\n',
                1,
            ),
            "pretest step hides tests": text.replace(
                "      - name: Run Python tests in isolated processes\n",
                "      - name: Hide Python tests\n"
                "        shell: pwsh\n"
                "        run: |\n"
                "          Rename-Item -LiteralPath .\\tests -NewName tests-hidden\n"
                "          New-Item -ItemType Directory -Path .\\tests | Out-Null\n"
                "\n"
                "      - name: Run Python tests in isolated processes\n",
                1,
            ),
            "fixture install hides tests": text.replace(
                "          python -m pip install -e .\n"
                "      - name: Require host C compiler\n",
                "          python -m pip install -e .\n"
                "          Rename-Item -LiteralPath .\\tests -NewName tests-hidden\n"
                "          New-Item -ItemType Directory -Path .\\tests | Out-Null\n"
                "      - name: Require host C compiler\n",
                1,
            ),
            "missing zero-module guard": text.replace(
                "          if ($modules.Count -eq 0) {\n"
                "            throw 'isolated Python test discovery returned no modules'\n"
                "          }\n",
                "",
                1,
            ),
            "workflow default shell masks failures": text.replace(
                "jobs:\n",
                "defaults:\n"
                "  run:\n"
                '    shell: pwsh -Command "pwsh -File \'{0}\'; exit 0"\n'
                "\n"
                "jobs:\n",
                1,
            ),
            "missing push trigger": text.replace(
                "  push:\n",
                "",
                1,
            ),
            "missing pull-request trigger": text.replace(
                "  pull_request:\n",
                "",
                1,
            ),
            "disabled source-integrity job": text.replace(
                "  source-integrity:\n"
                "    name: Source integrity\n",
                "  source-integrity:\n"
                "    if: ${{ false }}\n"
                "    name: Source integrity\n",
                1,
            ),
            "disabled VS Code unit-test job": text.replace(
                "  vscode-tests:\n"
                "    name: VS Code unit tests\n",
                "  vscode-tests:\n"
                "    if: ${{ false }}\n"
                "    name: VS Code unit tests\n",
                1,
            ),
            "disabled VS Code activation job": text.replace(
                "  vscode-activation:\n"
                "    name: VS Code Extension Host activation\n",
                "  vscode-activation:\n"
                "    if: ${{ false }}\n"
                "    name: VS Code Extension Host activation\n",
                1,
            ),
            "disabled package-contract job": text.replace(
                "  package-contract:\n"
                "    name: Package contract\n",
                "  package-contract:\n"
                "    if: ${{ false }}\n"
                "    name: Package contract\n",
                1,
            ),
        }

        self.assertEqual(35, len(mutants))
        for name, mutant in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(text, mutant, f"mutation was not applied: {name}")
                self.assertNotEqual(
                    [],
                    _ci_contract_violations(mutant),
                    f"CI contract accepted mutant: {name}",
                )

    def test_github_actions_ci_contract_accepts_harmless_comments(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        text = workflow.read_text(encoding="utf-8")
        commented = text.replace(
            "name: CI\n",
            "name: CI   \n\n",
            1,
        ).replace(
            "jobs:\n",
            "jobs:   \n\n",
            1,
        ).replace(
            "on:\n",
            "on:\n"
            "  # Run the same gates for branch and pull-request updates.\n",
            1,
        ).replace(
            '      UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"\n',
            "      # Require a real alias on the hosted Windows runner.\n"
            '      UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"\n',
            1,
        ).replace(
            "      - name: Run Python tests in isolated processes\n"
            "        shell: pwsh\n",
            "      - name: Run Python tests in isolated processes\n"
            "        # Keep the canonical PowerShell shell.\n"
            "        shell: pwsh\n",
            1,
        ).replace(
            "          $failed = @()\n",
            "          $failed = @()\n"
            "          # Keep each module in a fresh process.\n",
            1,
        ).replace(
            "        shell: pwsh\n"
            "        run: |\n"
            '          $log = Join-Path $env:RUNNER_TEMP "python-tests.log"\n',
            "        shell: pwsh   \n"
            "        run: |   \n"
            '          $log = Join-Path $env:RUNNER_TEMP "python-tests.log"\n',
            1,
        ).replace(
            '          "fixture_compiler=$($compiler.Source)"\n',
            "          # Never choco install a compiler here.\n"
            '          "fixture_compiler=$($compiler.Source)"\n',
            1,
        ).replace(
            "      - name: Require host C compiler\n"
            "        shell: pwsh\n",
            "      - name: Require host C compiler\n"
            "        # Keep compiler discovery explicit.\n"
            "        shell: pwsh\n",
            1,
        ).replace(
            "        shell: pwsh\n"
            "        run: |\n"
            "          $compiler = Get-Command gcc, clang, cc ",
            "        shell: pwsh   \n"
            "        run: |   \n"
            "          $compiler = Get-Command gcc, clang, cc ",
            1,
        ).replace(
            "          if ($null -eq $compiler) {\n"
            "            throw 'VC6 fixture smoke requires gcc, clang, or cc on PATH.'\n"
            "          }\n",
            "          if ($null -eq $compiler) {\n"
            "            # Fail before running any fixture tests.\n"
            "            throw 'VC6 fixture smoke requires gcc, clang, or cc on PATH.'\n"
            "            # Keep the branch explicit for reviewers.\n"
            "          }\n",
            1,
        ).replace(
            "      - name: Run fixture smoke\n"
            "        run: |\n",
            "      - name: Run fixture smoke\n"
            "        # Use the default Windows PowerShell runner.\n"
            "        run: |\n",
            1,
        ).replace(
            "      - name: Run fixture smoke\n"
            "        # Use the default Windows PowerShell runner.\n"
            "        run: |\n",
            "      - name: Run fixture smoke\n"
            "        # Use the default Windows PowerShell runner.\n"
            "        run: |   \n",
            1,
        ).replace(
            "          & python -m unittest tests.test_fixture_cli_smoke "
            "tests.test_vc6_fixture_build_e2e -v *>&1 | "
            "Tee-Object -FilePath $log\n",
            "          # Run both fixture checks together.\n"
            "          & python -m unittest tests.test_fixture_cli_smoke "
            "tests.test_vc6_fixture_build_e2e -v *>&1 | "
            "Tee-Object -FilePath $log\n",
            1,
        ).replace(
            "          python -m pip install -e .\n\n"
            "      - name: Require host C compiler\n",
            "          python -m pip install -e .\n"
            "\n"
            "      # Compiler discovery remains a separate step.\n"
            "      - name: Require host C compiler\n",
            1,
        )

        self.assertNotEqual(text, commented, "comment control was not applied")
        self.assertEqual([], _ci_contract_violations(commented))
        with mock.patch.object(Path, "read_text", return_value=commented):
            for test_name in (
                "test_github_actions_runs_python_and_vscode_extension_gates",
                "test_github_actions_uses_six_independent_required_jobs",
                "test_github_actions_runs_activation_fixture_and_failure_log_contracts",
                "test_github_actions_ci_contract_rejects_mutants",
                "test_github_actions_checks_rewriter_tracking_and_python_compilation",
                "test_github_actions_installs_runtime_dependencies_and_tests_wheel_contract",
            ):
                with self.subTest(comment_control=test_name):
                    getattr(self, test_name)()

    def test_github_actions_checks_rewriter_tracking_and_python_compilation(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        text = workflow.read_text(encoding="utf-8")
        tracking = (
            "git ls-files --error-unmatch "
            "src/unit_test_runner/build/dependency_rewriter.py"
        )
        self.assertIn(tracking, text)
        self.assertIn("python -m compileall -q src", text)
        self.assertLess(text.index(tracking), text.index("Run Python tests"))
        self.assertLess(text.index("python -m compileall -q src"), text.index("Run Python tests"))

    def test_github_actions_installs_runtime_dependencies_and_tests_wheel_contract(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        text = workflow.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("python -m pip install -e ."), 3)
        self.assertIn("python -m pip wheel --no-deps", text)
        self.assertIn("python -m venv", text)
        self.assertIn("-m unit_test_runner --help", text)
        self.assertIn("unit_test_runner.schemas", text)
        self.assertIn("Select-Object -First 1", text)
        self.assertNotIn("Select-Object -Single", text)
        self.assertIn('python -m pip install "setuptools>=61" wheel', text)
        self.assertNotIn("py -m", text)


if __name__ == "__main__":
    unittest.main()
