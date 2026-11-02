# Build a filtered PUBLIC MIRROR of the private working repo. Never pushes: it only PRINTS the push command.
# Making the repo public is a human action (AGENTS.md section 12.3).
#
# Usage: scripts\make_public_mirror.ps1 [-Run] [-Src DIR] [-Out DIR] [-Python PY]
#   default is dry-run: prints the plan and checks prerequisites, changes nothing.
# Exit: 0 ok · 1 lint failed · 2 usage/other error · 3 git-filter-repo missing
param(
    [switch]$Run,
    [string]$Src = (Split-Path -Parent $PSScriptRoot),
    [string]$Out = "",
    [string]$Python = "python"
)
$ErrorActionPreference = "Continue"
if (-not $Out) { $Out = Join-Path (Split-Path -Parent $Src) "kodiac-public-mirror" }

$strip = @("HACKATHON.md", "docs/research/", "docs/private/", ".agents/", "HUMAN_TODO.md")
$filterArgs = @("filter-repo", "--invert-paths")
foreach ($p in $strip) { $filterArgs += @("--path", $p) }

& git filter-repo --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "git-filter-repo is not installed. Install: pip install git-filter-repo (https://github.com/newren/git-filter-repo)" -ErrorAction Continue
    exit 3
}

Write-Output "source : $Src"
Write-Output "mirror : $Out"
Write-Output "plan   : git clone --no-local SRC OUT; git $($filterArgs -join ' '); lint_public.py --history"
if (-not $Run) {
    Write-Output "DRY RUN: nothing was cloned or modified. Re-run with -Run to build the mirror."
    exit 0
}

if (Test-Path $Out) { Write-Error "refusing to overwrite existing $Out" -ErrorAction Continue; exit 2 }
& git clone --no-local $Src $Out
if ($LASTEXITCODE -ne 0) { exit 2 }
& git -C $Out @filterArgs
if ($LASTEXITCODE -ne 0) { exit 2 }

$lintArgs = @((Join-Path $Src "scripts\lint_public.py"), "--repo", $Out, "--history")
$lineage = Join-Path $Src "docs\private\lineage_terms.txt"
if (Test-Path $lineage) { $lintArgs += @("--lineage-file", $lineage) }
& $Python @lintArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "LINT FAILED (or lineage list unverifiable): the mirror is NOT safe to publish." -ErrorAction Continue
    exit 1
}

Write-Output ""
Write-Output "Mirror lint passed. The human may publish with (NOT executed by this script):"
Write-Output "  git -C `"$Out`" remote add origin <PUBLIC_REPO_URL>; git -C `"$Out`" push -u origin --all; git -C `"$Out`" push origin --tags"
