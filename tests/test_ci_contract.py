from pathlib import Path
import re
import subprocess
import unittest


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


def _python_ci_contract_violations(text: str) -> list[str]:
    violations: list[str] = []
    job = _job_block(text, "python-tests", violations)
    if job is None:
        return violations

    run_info = _named_step(job, "Run Python tests in isolated processes", violations)
    upload_info = _named_step(job, "Upload Python failure log", violations)
    if run_info is None or upload_info is None:
        return violations
    run_step, run_position = run_info
    upload_step, upload_position = upload_info
    if run_position >= upload_position:
        violations.append("Python failure upload must follow the isolated test step")

    forbidden = 'python -m unittest discover -s tests -p "test_*.py"'
    if forbidden in job:
        violations.append(f"forbidden command present in python-tests: {forbidden}")
    if "-Recurse" in run_step:
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
        position = run_step.find(token)
        if position < 0:
            violations.append(f"isolated Python step missing: {token}")
        token_positions.append(position)
    if all(position >= 0 for position in token_positions) and token_positions != sorted(
        token_positions
    ):
        violations.append("Python enumeration, sorting, conversion, and loop are out of order")

    loop_match = re.search(
        r"^          foreach \(\$module in \$modules\) \{\s*\n"
        r"(?P<body>.*?)"
        r"^          \}\s*$",
        run_step,
        re.MULTILINE | re.DOTALL,
    )
    if loop_match is None:
        violations.append("isolated Python module loop is missing")
        return violations

    loop_body = loop_match.group("body")
    if "& python -m unittest $module -v" not in loop_body:
        violations.append("module unittest command must run inside the module loop")
    if "$failed += $module" not in loop_body:
        violations.append("failed modules must be collected inside the module loop")
    if loop_body.count("Tee-Object -FilePath $log -Append") < 2:
        violations.append("per-module log writes must append")
    if re.search(
        r"(?im)^\s*(?:throw|exit|break|return)\b",
        loop_body,
    ):
        violations.append("module failures must not stop later module iterations")

    post_loop = run_step[loop_match.end() :]
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
        compiler_step,
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
    if any(
        re.search(pattern, job, re.IGNORECASE)
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
    return _python_ci_contract_violations(text) + _fixture_ci_contract_violations(text)


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

        text = workflow.read_text(encoding="utf-8")
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

        text = workflow.read_text(encoding="utf-8")
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
        }

        for name, mutant in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(text, mutant, f"mutation was not applied: {name}")
                self.assertNotEqual(
                    [],
                    _ci_contract_violations(mutant),
                    f"CI contract accepted mutant: {name}",
                )

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
