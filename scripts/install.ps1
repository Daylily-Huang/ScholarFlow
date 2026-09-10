<#
.SYNOPSIS
    ScholarFlow One-Click Skill Installer for Windows
.DESCRIPTION
    Installs the three ScholarFlow skills plus the shared Python engine that the
    skill scripts import. The engine is copied exactly once per destination root
    (as <dest>\shared, beside the skill directories), so an installed skill tree
    can run outside the repository without accumulating drifting duplicate
    copies (R06).

    Destinations:
    1. Global .agents/skills (%USERPROFILE%\.agents\skills)
    2. Global .claude/skills (%USERPROFILE%\.claude\skills)
.PARAMETER Target
    Optional custom destination path.
.PARAMETER SkipVerification
    Skip the post-install isolated runtime check (not recommended).
#>
param (
    [string]$Target = "",
    [switch]$SkipVerification
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SkillsSource = Join-Path $RepoRoot "skills"
$SharedSource = Join-Path $RepoRoot "shared"

if (-not (Test-Path $SkillsSource)) {
    Write-Error "[-] skills directory not found at: $SkillsSource"
    exit 1
}

if (-not (Test-Path (Join-Path $SharedSource "__init__.py"))) {
    Write-Error "[-] shared engine package not found at: $SharedSource"
    Write-Host "    The skill scripts import 'shared.*'; install from a full checkout." -ForegroundColor Red
    exit 1
}

$Destinations = @()
if ($Target) {
    $Destinations += $Target
} else {
    $UserHome = [Environment]::GetFolderPath("UserProfile")
    $Destinations += (Join-Path $UserHome ".agents\skills")
    $Destinations += (Join-Path $UserHome ".claude\skills")
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  ScholarFlow Skills Installer" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$Skills = Get-ChildItem -Path $SkillsSource -Directory

foreach ($dest in $Destinations) {
    Write-Host "[*] Target directory: $dest" -ForegroundColor Yellow
    if (-not (Test-Path $dest)) {
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
    }

    foreach ($skill in $Skills) {
        $skillDest = Join-Path $dest $skill.Name
        Write-Host "  -> Installing $($skill.Name)..." -ForegroundColor Green
        if (Test-Path $skillDest) {
            Remove-Item -LiteralPath $skillDest -Recurse -Force
        }
        Copy-Item -Path $skill.FullName -Destination $skillDest -Recurse -Force
        Get-ChildItem -Path $skillDest -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }

    # A single vendored engine copy per destination root: <dest>\shared
    $sharedDest = Join-Path $dest "shared"
    Write-Host "  -> Installing shared Python engine (single copy)..." -ForegroundColor Green
    if (Test-Path $sharedDest) {
        Remove-Item -LiteralPath $sharedDest -Recurse -Force
    }
    Copy-Item -Path $SharedSource -Destination $sharedDest -Recurse -Force
    Get-ChildItem -Path $sharedDest -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not $SkipVerification) {
    Write-Host ""
    Write-Host "[*] Verifying installed runtime (isolated interpreter, no site-packages)..." -ForegroundColor Yellow
    $verifyFailed = $false
    foreach ($dest in $Destinations) {
        $entry = Join-Path $dest "literature-discovery-acquisition\scripts\agent_search.py"
        if (-not (Test-Path $entry)) { continue }
        $entryDir = Split-Path -Parent $entry
        $entryName = Split-Path -Leaf $entry
        Push-Location $entryDir
        try {
            & python -I -S $entryName --help *> $null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  [PASS] $entry resolves the shared engine" -ForegroundColor Green
            } else {
                Write-Host "  [FAIL] $entry cannot resolve the shared engine" -ForegroundColor Red
                $verifyFailed = $true
            }
        } catch {
            Write-Host "  [FAIL] $entry could not be executed: $_" -ForegroundColor Red
            $verifyFailed = $true
        } finally {
            Pop-Location
        }
    }

    if ($verifyFailed) {
        Write-Host ""
        Write-Host "[-] Installation copied files but the runtime could not be verified." -ForegroundColor Red
        Write-Host "    Re-run from a full checkout, or install the engine with: pip install scholarflow"
        exit 2
    }
}

Write-Host ""
Write-Host "[SUCCESS] ScholarFlow skills installed successfully!" -ForegroundColor Green
Write-Host "Engine location(s):" -ForegroundColor White
foreach ($dest in $Destinations) {
    Write-Host "  - $(Join-Path $dest 'shared')" -ForegroundColor Gray
}
Write-Host "Available skills:" -ForegroundColor White
foreach ($skill in $Skills) {
    Write-Host "  - $($skill.Name)" -ForegroundColor Gray
}
