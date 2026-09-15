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
} elseif ($env:SCHOLARFLOW_SKILLS_DEST) {
    # P2-30（2026-09-15 集群审查）：POSIX 安装器早已识别该环境变量，Windows 侧
    # 却不认——CI/脚本按 install.sh 的约定设了它，本脚本仍会静默改写**全局**技能
    # 目录（%USERPROFILE%\.agents\skills 与 .claude\skills），在别人机器上覆盖真实配置。
    $Destinations += $env:SCHOLARFLOW_SKILLS_DEST
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

    # Canonical schemas live at the repository root; skill scripts resolve them
    # relative to the installed tree, so they must ship alongside `shared`.
    # (2026-09-15 部署层修复: the POSIX installer already did this; this one
    # silently omitted it, leaving the schema gate unreachable on Windows.)
    $schemasSource = Join-Path $RepoRoot "schemas"
    if (Test-Path $schemasSource) {
        $schemasDest = Join-Path $dest "schemas"
        Write-Host "  -> Installing canonical schemas (single copy)..." -ForegroundColor Green
        if (Test-Path $schemasDest) {
            Remove-Item -LiteralPath $schemasDest -Recurse -Force
        }
        Copy-Item -Path $schemasSource -Destination $schemasDest -Recurse -Force
        Get-ChildItem -Path $schemasDest -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "  [!] schemas directory not found at: $schemasSource" -ForegroundColor Yellow
    }

    # P2-06：技能文档按仓库布局写死了上溯级数，安装树平铺为 <dest>\<skill>\，
    # 比仓库少一层 skills\，这些相对链接装后全部断链。装后按实际深度改写，
    # 并补上被引用的那一份文档（docs\CAPABILITY_STATUS.md）。
    $docsSource = Join-Path $RepoRoot "docs\CAPABILITY_STATUS.md"
    if (Test-Path $docsSource) {
        $docsDest = Join-Path $dest "docs"
        if (-not (Test-Path $docsDest)) {
            New-Item -ItemType Directory -Path $docsDest -Force | Out-Null
        }
        Copy-Item -Path $docsSource -Destination (Join-Path $docsDest "CAPABILITY_STATUS.md") -Force
    }
    $linkFixer = Join-Path $RepoRoot "scripts\fix_installed_doc_links.py"
    if (Test-Path $linkFixer) {
        & python $linkFixer $dest
    }
}

if (-not $SkipVerification) {
    Write-Host ""
    Write-Host "[*] Verifying installed runtime (isolated interpreter, no site-packages)..." -ForegroundColor Yellow
    $verifyFailed = $false
    # Scope (2026-09-15 部署层修复): this loop used to probe agent_search.py only.
    # That script carries its own layout-tolerant locator, so the check could not
    # fail even when every other script had silently lost the engine. The list
    # below covers the entries that import `shared` or a sibling module.
    $verifyEntries = @(
        "literature-discovery-acquisition\scripts\agent_search.py",
        "literature-evidence-extraction\scripts\extraction_pipeline.py",
        "literature-evidence-extraction\scripts\claim_alignment.py",
        "literature-evidence-extraction\scripts\quote_audit.py",
        "literature-synthesis\scripts\controversy_analyzer.py",
        "literature-synthesis\scripts\evidence_to_claim.py",
        "research-idea-debate\scripts\session_store_cli.py",
        "research-idea-debate\scripts\validate_session.py"
    )
    foreach ($dest in $Destinations) {
        foreach ($rel in $verifyEntries) {
            $entry = Join-Path $dest $rel
            if (-not (Test-Path $entry)) {
                Write-Host "  [FAIL] $rel is missing from $dest" -ForegroundColor Red
                $verifyFailed = $true
                continue
            }
            $entryDir = Split-Path -Parent $entry
            $entryName = Split-Path -Leaf $entry
            Push-Location $entryDir
            try {
                & python -I -S $entryName --help *> $null
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  [PASS] $rel" -ForegroundColor Green
                } else {
                    Write-Host "  [FAIL] $rel cannot resolve its runtime" -ForegroundColor Red
                    $verifyFailed = $true
                }
            } catch {
                Write-Host "  [FAIL] $rel could not be executed: $_" -ForegroundColor Red
                $verifyFailed = $true
            } finally {
                Pop-Location
            }
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
