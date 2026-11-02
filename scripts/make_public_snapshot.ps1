# scripts/make_public_snapshot.ps1: Build a clean public mirror snapshot (Option A)
# Creates a clean public repository snapshot with no internal hackathon notes or history.
#
# Usage:
#   powershell -File scripts\make_public_snapshot.ps1 [-Out <DIR>] [-Run]
# Default is dry-run. Add -Run to execute.

param(
    [switch]$Run,
    [string]$Src = (Split-Path -Parent $PSScriptRoot),
    [string]$Out = "",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
if (-not $Out) {
    $Out = Join-Path (Split-Path -Parent $Src) "kodiac-public"
}
if (-not $Python) {
    $Python = Join-Path $Src ".venv\Scripts\python.exe"
}

$forbidden = @(
    ".agents",
    ".git",
    ".venv",
    ".cache",
    ".pytest_cache",
    ".ruff_cache",
    "docs\research",
    "docs\private",
    "HACKATHON.md",
    "HUMAN_TODO.md"
)

Write-Host "Kodiac Public Mirror Snapshot Generator" -ForegroundColor Cyan
Write-Host "Source : $Src"
Write-Host "Mirror : $Out"
Write-Host "Python : $Python"

if (-not $Run) {
    Write-Host "`nDRY RUN: No files copied. Re-run with -Run to build the public snapshot." -ForegroundColor Yellow
    exit 0
}

if (Test-Path $Out) {
    Write-Host "Removing existing destination: $Out" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $Out
}

New-Item -ItemType Directory -Path $Out -Force | Out-Null

Write-Host "Copying repository files excluding private notes..." -ForegroundColor Cyan

# Copy items individually to exclude forbidden paths cleanly
Get-ChildItem -Path $Src -Force | ForEach-Object {
    $name = $_.Name
    $skip = $false
    foreach ($f in $forbidden) {
        if ($name -ieq $f -or $name -ieq (Split-Path $f -Leaf)) {
            $skip = $true
            break
        }
    }
    if (-not $skip) {
        Copy-Item -Path $_.FullName -Destination $Out -Recurse -Force
    }
}

# Remove any nested forbidden items if present
foreach ($f in $forbidden) {
    $target = Join-Path $Out $f
    if (Test-Path $target) {
        Remove-Item -Recurse -Force $target -ErrorAction SilentlyContinue
    }
}

Write-Host "Initializing fresh git repository in $Out..." -ForegroundColor Cyan
& git -C $Out init -b main
& git -C $Out config user.name "Team Kodiac"
& git -C $Out config user.email "team@kodiac-robotics.dev"
& git -C $Out add .
& git -C $Out commit -m "feat: Kodiac 1.0 - tests, git bisect, and git blame for robots"

Write-Host "`nRunning public mirror lint..." -ForegroundColor Cyan
$lintScript = Join-Path $Src "scripts\lint_public.py"
& $Python $lintScript --repo $Out --history

Write-Host "`nPublic snapshot built and verified successfully!" -ForegroundColor Green
Write-Host "To publish this mirror to GitHub:" -ForegroundColor White
Write-Host "  1. Create a public GitHub repository (e.g. github.com/<your-username>/kodiac)"
Write-Host "  2. Run:" -ForegroundColor Cyan
Write-Host "     cd `"$Out`""
Write-Host "     git remote add origin https://github.com/<your-username>/kodiac.git"
Write-Host "     git push -u origin main"
