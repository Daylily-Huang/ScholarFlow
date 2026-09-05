<#
.SYNOPSIS
    ScholarFlow One-Click Skill Installer for Windows
.DESCRIPTION
    Installs ScholarFlow skills into:
    1. Global .agents/skills (%USERPROFILE%\.agents\skills)
    2. Global .claude/skills (%USERPROFILE%\.claude\skills)
.PARAMETER Target
    Optional custom destination path.
#>
param (
    [string]$Target = ""
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SkillsSource = Join-Path $RepoRoot "skills"

if (-not (Test-Path $SkillsSource)) {
    Write-Error "[-] skills directory not found at: $SkillsSource"
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
        Copy-Item -Path $skill.FullName -Destination $skillDest -Recurse -Force
    }
}

Write-Host ""
Write-Host "[SUCCESS] ScholarFlow skills installed successfully!" -ForegroundColor Green
Write-Host "Available skills:" -ForegroundColor White
foreach ($skill in $Skills) {
    Write-Host "  - $($skill.Name)" -ForegroundColor Gray
}
