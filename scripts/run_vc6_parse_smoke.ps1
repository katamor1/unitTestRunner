param(
    [string]$FixtureRoot = "",
    [string]$Dsw = "Product.dsw",
    [string]$Source = "src\device_control.c",
    [string]$Project = "DeviceControl",
    [string]$Configuration = "DeviceControl - Win32 Debug",
    [string]$ExpectedSecondProject = "FactoryTest",
    [string]$ExpectedDefine = "DEVICE_CONTROL_FEATURE=1",
    [string]$OutRoot = "",
    [string]$PythonLauncher = "py"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

if ([string]::IsNullOrWhiteSpace($FixtureRoot)) {
    $FixtureRoot = Join-Path $RepoRoot "tests\fixtures\vc6_practical_project"
}
$FixtureRoot = (Resolve-Path $FixtureRoot).Path

if ([string]::IsNullOrWhiteSpace($OutRoot)) {
    $OutRoot = Join-Path $env:TEMP "unitTestRunner-vc6-parse-smoke"
}
New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null
$OutRoot = (Resolve-Path $OutRoot).Path

if ([System.IO.Path]::IsPathRooted($Dsw)) {
    $DswPath = (Resolve-Path $Dsw).Path
    $DswForDiscover = $DswPath
} else {
    $DswPath = (Resolve-Path (Join-Path $FixtureRoot $Dsw)).Path
    $DswForDiscover = $Dsw
}

$ProjectsJson = Join-Path $OutRoot "dsw_dsp_projects.json"
$ProjectsMarkdown = Join-Path $OutRoot "dsw_dsp_projects.md"
$MembershipAllJson = Join-Path $OutRoot "source_membership_all.json"
$MembershipAllMarkdown = Join-Path $OutRoot "source_membership_all.md"
$MembershipFilteredJson = Join-Path $OutRoot "source_membership_devicecontrol_debug.json"
$SummaryText = Join-Path $OutRoot "summary.txt"

function Invoke-UtrCommand {
    param([string[]]$Arguments)

    $output = & $PythonLauncher @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Command failed with exit code $exitCode`: $PythonLauncher $($Arguments -join ' ')`n$output"
    }
    return $output
}

function Assert-True {
    param([bool]$Condition, [string]$Message)

    if (-not $Condition) {
        throw $Message
    }
}

$PreviousPythonPath = $env:PYTHONPATH
try {
    if ([string]::IsNullOrWhiteSpace($PreviousPythonPath)) {
        $env:PYTHONPATH = Join-Path $RepoRoot "src"
    } else {
        $env:PYTHONPATH = (Join-Path $RepoRoot "src") + [System.IO.Path]::PathSeparator + $PreviousPythonPath
    }

    Invoke-UtrCommand -Arguments @(
        "-m", "unit_test_runner",
        "--json",
        "discover-projects",
        "--workspace", $FixtureRoot,
        "--dsw", $DswForDiscover,
        "--with-dsp-details",
        "--out", $ProjectsJson
    ) | Out-Null

    Invoke-UtrCommand -Arguments @(
        "-m", "unit_test_runner",
        "discover-projects",
        "--workspace", $FixtureRoot,
        "--dsw", $DswForDiscover,
        "--with-dsp-details",
        "--out", $ProjectsMarkdown
    ) | Out-Null

    Invoke-UtrCommand -Arguments @(
        "-m", "unit_test_runner",
        "--json",
        "map-source",
        "--dsw", $DswPath,
        "--source", $Source,
        "--out", $MembershipAllJson
    ) | Out-Null

    Invoke-UtrCommand -Arguments @(
        "-m", "unit_test_runner",
        "map-source",
        "--dsw", $DswPath,
        "--source", $Source,
        "--out", $MembershipAllMarkdown
    ) | Out-Null

    $filteredArgs = @(
        "-m", "unit_test_runner",
        "--json",
        "map-source",
        "--dsw", $DswPath,
        "--source", $Source,
        "--out", $MembershipFilteredJson
    )
    if (-not [string]::IsNullOrWhiteSpace($Project)) {
        $filteredArgs += @("--project", $Project)
    }
    if (-not [string]::IsNullOrWhiteSpace($Configuration)) {
        $filteredArgs += @("--configuration", $Configuration)
    }
    Invoke-UtrCommand -Arguments $filteredArgs | Out-Null

    $projectsPayload = Get-Content -Raw -Path $ProjectsJson -Encoding UTF8 | ConvertFrom-Json
    $workspace = @($projectsPayload.workspaces)[0]
    $projects = @($workspace.projects)
    $projectNames = @($projects | ForEach-Object { $_.name })
    Assert-True ($projectNames -contains $Project) "Expected project was not discovered: $Project"
    if (-not [string]::IsNullOrWhiteSpace($ExpectedSecondProject)) {
        Assert-True ($projectNames -contains $ExpectedSecondProject) "Expected second project was not discovered: $ExpectedSecondProject"
    }

    $selectedProject = @($projects | Where-Object { $_.name -eq $Project })[0]
    $configurations = @($selectedProject.dsp_summary.configurations)
    Assert-True ($configurations -contains $Configuration) "Expected configuration was not parsed from DSP: $Configuration"
    if (-not [string]::IsNullOrWhiteSpace($ExpectedDefine)) {
        $defines = @($selectedProject.dsp_summary.defines)
        Assert-True ($defines -contains $ExpectedDefine) "Expected define was not parsed from DSP: $ExpectedDefine"
    }

    $membershipAll = Get-Content -Raw -Path $MembershipAllJson -Encoding UTF8 | ConvertFrom-Json
    $allMatches = @($membershipAll.matches)
    Assert-True ($allMatches.Count -ge 1) "Source membership did not find any DSP source entries."
    if (-not [string]::IsNullOrWhiteSpace($ExpectedSecondProject)) {
        $allProjectNames = @($allMatches | ForEach-Object { $_.project_name })
        Assert-True ($membershipAll.status -eq "multiple_matches") "Expected multiple project membership for the smoke fixture."
        Assert-True ($allProjectNames -contains $Project) "Primary project membership was not found: $Project"
        Assert-True ($allProjectNames -contains $ExpectedSecondProject) "Second project membership was not found: $ExpectedSecondProject"
    }

    $membershipFiltered = Get-Content -Raw -Path $MembershipFilteredJson -Encoding UTF8 | ConvertFrom-Json
    $filteredMatches = @($membershipFiltered.matches)
    Assert-True ($membershipFiltered.status -eq "ok") "Filtered membership did not resolve to a single project."
    Assert-True ($filteredMatches.Count -eq 1) "Filtered membership should have exactly one match."
    Assert-True ($filteredMatches[0].project_name -eq $Project) "Filtered membership resolved to the wrong project."

    $summary = @(
        "VC6 DSW/DSP parse smoke completed.",
        "FixtureRoot: $FixtureRoot",
        "DSW: $DswPath",
        "Source: $Source",
        "Project: $Project",
        "Configuration: $Configuration",
        "OutputRoot: $OutRoot",
        "Outputs:",
        "  $ProjectsJson",
        "  $ProjectsMarkdown",
        "  $MembershipAllJson",
        "  $MembershipAllMarkdown",
        "  $MembershipFilteredJson"
    )
    $summary | Set-Content -Path $SummaryText -Encoding UTF8
    $summary -join [Environment]::NewLine
} finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
