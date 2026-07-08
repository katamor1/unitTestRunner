from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .build_models import BuildDiagnostic, BuildPathEntry, CompileUnit


@dataclass
class VerificationBuildResult:
    executed: bool
    exit_code: int | None
    command_line: str
    log_text: str
    diagnostics: list[BuildDiagnostic] = field(default_factory=list)
    compiler: str | None = None


def render_verification_build_info(cc: Path | str | None = None) -> str:
    compiler = str(cc) if cc else "UNIT_TEST_RUNNER_CC, CC, or auto-detected host C compiler"
    return "\n".join(
        [
            "# Verification build",
            "",
            "This workspace was prepared for a non-VC6 verification build.",
            "",
            "- CLI: unit-test-runner build-probe --workspace <workspace> --run --toolchain verification",
            f"- Compiler: {compiler}",
            "- Default compiler search order: UNIT_TEST_RUNNER_CC, CC, cl, gcc, clang, clang-cl, cc",
            "- The VC6 Makefile/build.bat is still generated for the real environment.",
            "",
        ]
    )


def run_verification_build(
    output_root: Path,
    compile_units: list[CompileUnit],
    include_dirs: list[BuildPathEntry],
    defines: list[str],
    compiler_options: list[str],
    cc: Path | str | None = None,
    timeout_seconds: int = 120,
    env_setup: Path | str | None = None,
) -> VerificationBuildResult:
    output_root = Path(output_root).resolve()
    log_path = output_root / "logs" / "build.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path = output_root / "bin" / "utr_probe.exe"
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    (output_root / "obj").mkdir(parents=True, exist_ok=True)

    compiler = _select_compiler(cc, env_setup)
    log_lines = ["VERIFICATION BUILD", f"workspace: {output_root}"]
    if compiler is None:
        message = "Host C compiler was not found. Set UNIT_TEST_RUNNER_CC, CC, or pass --cc for --toolchain verification."
        diagnostic = BuildDiagnostic("missing_host_c_compiler", "error", message, None, None, None)
        log_lines.append(message)
        log_text = "\n".join(log_lines) + "\n"
        log_path.write_text(log_text, encoding="utf-8")
        return VerificationBuildResult(False, None, "verification build", log_text, [diagnostic], None)

    flavor = _compiler_flavor(compiler)
    include_paths = _include_paths(output_root, include_dirs)
    object_paths: list[Path] = []
    command_lines: list[str] = []
    diagnostics: list[BuildDiagnostic] = []
    log_lines.append(f"compiler: {compiler}")
    log_lines.append(f"flavor: {flavor}")

    for unit in compile_units:
        source = output_root / unit.source_file
        obj = output_root / unit.object_file
        obj.parent.mkdir(parents=True, exist_ok=True)
        command = _compile_command(compiler, flavor, source, obj, include_paths, defines, compiler_options)
        command_text = _command_text(command)
        command_lines.append(command_text)
        exit_code, output = _run_command(command, cwd=output_root, timeout_seconds=timeout_seconds, env_setup=env_setup)
        log_lines.append("")
        log_lines.append(command_text)
        if output:
            log_lines.append(output.rstrip())
        if exit_code != 0:
            diagnostics.append(
                BuildDiagnostic(
                    "verification_build_failed",
                    "error",
                    "Verification build failed during compilation. See logs/build.log.",
                    unit.source_file,
                    None,
                    output.strip() or None,
                )
            )
            log_text = "\n".join(log_lines) + "\n"
            log_path.write_text(log_text, encoding="utf-8")
            return VerificationBuildResult(True, exit_code, command_text, log_text, diagnostics, compiler)
        object_paths.append(obj)

    link_command = _link_command(compiler, flavor, object_paths, exe_path)
    link_command_text = _command_text(link_command)
    command_lines.append(link_command_text)
    exit_code, output = _run_command(link_command, cwd=output_root, timeout_seconds=timeout_seconds, env_setup=env_setup)
    log_lines.append("")
    log_lines.append(link_command_text)
    if output:
        log_lines.append(output.rstrip())
    if exit_code != 0:
        diagnostics.append(
            BuildDiagnostic(
                "verification_link_failed",
                "error",
                "Verification build failed during linking. See logs/build.log.",
                None,
                None,
                output.strip() or None,
            )
        )
    else:
        log_lines.append(f"output: {exe_path}")

    log_text = "\n".join(log_lines) + "\n"
    log_path.write_text(log_text, encoding="utf-8")
    return VerificationBuildResult(True, exit_code, " && ".join(command_lines), log_text, diagnostics, compiler)


def _select_compiler(cc: Path | str | None, env_setup: Path | str | None) -> str | None:
    if cc:
        return str(cc)
    env_cc = os.environ.get("UNIT_TEST_RUNNER_CC") or os.environ.get("CC")
    if env_cc:
        return env_cc
    if env_setup:
        return "cl"
    for candidate in ("cl", "gcc", "clang", "clang-cl", "cc"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _compiler_flavor(compiler: str) -> str:
    name = compiler.replace("\\", "/").split("/")[-1].lower()
    if name in {"cl", "cl.exe", "clang-cl", "clang-cl.exe"}:
        return "msvc"
    return "unix"


def _include_paths(output_root: Path, include_dirs: list[BuildPathEntry]) -> list[Path]:
    paths: list[Path] = []
    for entry in include_dirs:
        if "$(" in entry.raw:
            continue
        if entry.workspace_path:
            paths.append(output_root / entry.workspace_path)
        elif entry.original_path:
            paths.append(entry.original_path)
        else:
            paths.append(Path(entry.raw))
    return paths


def _compile_command(
    compiler: str,
    flavor: str,
    source: Path,
    object_file: Path,
    include_paths: list[Path],
    defines: list[str],
    compiler_options: list[str],
) -> list[str]:
    if flavor == "msvc":
        options = [item for item in compiler_options if item.startswith("/")]
        if "/nologo" not in options:
            options.insert(0, "/nologo")
        if not any(item.startswith("/W") for item in options):
            options.append("/W3")
        return [
            compiler,
            *options,
            *[f"/D{define}" for define in defines],
            *[f"/I{path}" for path in include_paths],
            f"/Fo{object_file}",
            "/c",
            str(source),
        ]
    return [
        compiler,
        "-std=c90",
        "-Wall",
        "-Wextra",
        *[f"-D{define}" for define in defines],
        *[f"-I{path}" for path in include_paths],
        "-o",
        str(object_file),
        "-c",
        str(source),
    ]


def _link_command(compiler: str, flavor: str, object_paths: list[Path], exe_path: Path) -> list[str]:
    if flavor == "msvc":
        return [compiler, "/nologo", *[str(path) for path in object_paths], f"/Fe{exe_path}"]
    return [compiler, *[str(path) for path in object_paths], "-o", str(exe_path)]


def _run_command(command: list[str], cwd: Path, timeout_seconds: int, env_setup: Path | str | None = None) -> tuple[int, str]:
    try:
        if env_setup:
            if os.name != "nt":
                return 127, "Environment setup batch files are supported only on Windows.\n"
            command_line = f'call "{env_setup}" && {subprocess.list2cmdline(command)}'
            completed = subprocess.run(
                ["cmd.exe", "/c", command_line],
                cwd=cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
        else:
            completed = subprocess.run(
                command,
                cwd=cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
        return completed.returncode, completed.stdout
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        return 124, stdout + f"\nCommand timed out after {timeout_seconds} seconds.\n"


def _command_text(command: list[str]) -> str:
    return " ".join(shlex.quote(str(item)) for item in command)
