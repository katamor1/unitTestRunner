[CmdletBinding()]
param(
    [string]$PythonLauncher = "py",
    [string]$PythonVersion = "",
    [switch]$SkipTests,
    [switch]$ReuseReleaseVenv
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "build_distribution.ps1 supports Windows only because it creates the bundled win32-x64 executable."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseVenv = Join-Path $repoRoot ".venv-release"
$venvPython = Join-Path $releaseVenv "Scripts\python.exe"
$distRoot = Join-Path $repoRoot "dist"
$releaseBuildRoot = Join-Path $repoRoot "build\release"
$pyinstallerWorkRoot = Join-Path $releaseBuildRoot "pyinstaller"
$pyinstallerSpecRoot = Join-Path $releaseBuildRoot "spec"
$extensionRoot = Join-Path $repoRoot "vscode\extension"
$bundledCliRoot = Join-Path $extensionRoot "bin\win32-x64"
$bundledCliPath = Join-Path $bundledCliRoot "unit-test-runner.exe"
$entryPoint = Join-Path $repoRoot "scripts\pyinstaller_entry.py"
$fixtureRoot = Join-Path $repoRoot "tests\fixtures\vc6_project"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$WorkingDirectory = $repoRoot
    )

    Push-Location $WorkingDirectory
    try {
        Write-Host ("> " + $FilePath + " " + ($Arguments -join " "))
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code $LASTEXITCODE: $FilePath $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-BootstrapPython {
    param([string[]]$Arguments)

    $launcherArgs = @()
    if ($PythonVersion) {
        if ([System.IO.Path]::GetFileNameWithoutExtension($PythonLauncher) -ne "py") {
            throw "-PythonVersion is supported only with the Python launcher 'py'."
        }
        $launcherArgs += "-$PythonVersion"
    }
    $launcherArgs += $Arguments
    Invoke-Native -FilePath $PythonLauncher -Arguments $launcherArgs -WorkingDirectory $repoRoot
}

function Test-VsixContainsBundledCli {
    param([Parameter(Mandatory = $true)][string]$VsixPath)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($VsixPath)
    try {
        $entryName = "extension/bin/win32-x64/unit-test-runner.exe"
        $entry = $archive.GetEntry($entryName)
        if ($null -eq $entry -or $entry.Length -le 0) {
            throw "VSIX does not contain a non-empty bundled CLI entry: $entryName"
        }
    }
    finally {
        $archive.Dispose()
    }
}

if (-not $ReuseReleaseVenv -and (Test-Path -LiteralPath $releaseVenv)) {
    Remove-Item -LiteralPath $releaseVenv -Recurse -Force
}
if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-BootstrapPython -Arguments @("-m", "venv", $releaseVenv)
}

Invoke-Native -FilePath $venvPython -Arguments @("-c", "import sys; assert sys.version_info >= (3, 12), sys.version")
Invoke-Native -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
Invoke-Native -FilePath $venvPython -Arguments @("-m", "pip", "install", "-e", ".[test]")
Invoke-Native -FilePath $venvPython -Arguments @("-m", "pip", "install", "pyinstaller")

if (-not $SkipTests) {
    $testModules = Get-ChildItem -LiteralPath (Join-Path $repoRoot "tests") -Filter "test_*.py" -File |
        Sort-Object Name |
        ForEach-Object { "tests." + $_.BaseName }
    if ($testModules.Count -eq 0) {
        throw "No Python test modules were found."
    }
    foreach ($module in $testModules) {
        Invoke-Native -FilePath $venvPython -Arguments @("-m", "unittest", $module, "-v")
    }
}

New-Item -ItemType Directory -Force -Path $distRoot, $pyinstallerWorkRoot, $pyinstallerSpecRoot | Out-Null
$exePath = Join-Path $distRoot "unit-test-runner.exe"
if (Test-Path -LiteralPath $exePath) {
    Remove-Item -LiteralPath $exePath -Force
}

$pyinstallerArguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--console",
    "--name", "unit-test-runner",
    "--paths", (Join-Path $repoRoot "src"),
    "--hidden-import", "unit_test_runner.schemas",
    "--collect-data", "unit_test_runner.schemas",
    "--distpath", $distRoot,
    "--workpath", $pyinstallerWorkRoot,
    "--specpath", $pyinstallerSpecRoot,
    $entryPoint
)
Invoke-Native -FilePath $venvPython -Arguments $pyinstallerArguments

if (-not (Test-Path -LiteralPath $exePath)) {
    throw "PyInstaller did not create the expected executable: $exePath"
}
Invoke-Native -FilePath $exePath -Arguments @("--version")
Invoke-Native -FilePath $exePath -Arguments @("--help")

$smokeRoot = Join-Path $env:TEMP ("unitTestRunner-release-smoke-" + [guid]::NewGuid().ToString("N"))
$dossierPath = Join-Path $smokeRoot "reports\function_dossier.json"
$smokeSucceeded = $false
try {
    Invoke-Native -FilePath $exePath -Arguments @(
        "--json",
        "analyze-function",
        "--workspace", $fixtureRoot,
        "--dsw", (Join-Path $fixtureRoot "Product.dsw"),
        "--source", "src\control.c",
        "--function", "Control_Update",
        "--configuration", "Win32 Debug",
        "--project", "Control",
        "--out", $smokeRoot,
        "--finalize-dossier"
    )
    if (-not (Test-Path -LiteralPath $dossierPath)) {
        throw "Executable smoke test did not create the finalized dossier: $dossierPath"
    }
    Invoke-Native -FilePath $exePath -Arguments @(
        "--json",
        "prepare-review",
        "--dossier", $dossierPath
    )
    $smokeSucceeded = $true
}
finally {
    if ($smokeSucceeded -and (Test-Path -LiteralPath $smokeRoot)) {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force
    }
    elseif (-not $smokeSucceeded) {
        Write-Warning "Executable smoke artifacts were preserved for diagnosis: $smokeRoot"
    }
}

New-Item -ItemType Directory -Force -Path $bundledCliRoot | Out-Null
Copy-Item -LiteralPath $exePath -Destination $bundledCliPath -Force

$npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
Invoke-Native -FilePath $npmCommand -Arguments @("ci") -WorkingDirectory $extensionRoot
if (-not $SkipTests) {
    Invoke-Native -FilePath $npmCommand -Arguments @("test") -WorkingDirectory $extensionRoot
}

$extensionManifest = Get-Content -LiteralPath (Join-Path $extensionRoot "package.json") -Raw | ConvertFrom-Json
$vsixPath = Join-Path $distRoot ("unit-test-runner-vscode-{0}.vsix" -f $extensionManifest.version)
if (Test-Path -LiteralPath $vsixPath) {
    Remove-Item -LiteralPath $vsixPath -Force
}
Invoke-Native -FilePath $npmCommand -Arguments @(
    "exec",
    "--yes",
    "--package", "@vscode/vsce",
    "--",
    "vsce", "package",
    "--out", $vsixPath
) -WorkingDirectory $extensionRoot

if (-not (Test-Path -LiteralPath $vsixPath)) {
    throw "VSIX packaging did not create the expected file: $vsixPath"
}
Test-VsixContainsBundledCli -VsixPath $vsixPath

[pscustomobject]@{
    executable = $exePath
    bundled_cli = $bundledCliPath
    vsix = $vsixPath
    extension_version = [string]$extensionManifest.version
    tests_skipped = [bool]$SkipTests
} | ConvertTo-Json -Depth 3
