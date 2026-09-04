param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$Message
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Args -join ' ')"
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or is not available on PATH."
}

$insideRepo = & git rev-parse --is-inside-work-tree 2>$null
if ($LASTEXITCODE -ne 0 -or $insideRepo -ne "true") {
    throw "Run this script from inside a Git repository."
}

$branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
    throw "Could not determine the current branch. Detached HEAD is not supported."
}

$originUrl = (& git remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($originUrl)) {
    throw "Remote 'origin' is not configured."
}

Write-Host ""
Write-Host "Repository : $((Get-Location).Path)"
Write-Host "Branch     : $branch"
Write-Host "Remote     : $originUrl"
Write-Host ""

Invoke-Git -Args @("add", "-A")

$stagedFiles = @(& git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect staged files."
}

$sensitiveFiles = @(
    $stagedFiles | Where-Object {
        $p = $_ -replace "\\", "/"

        (
            ($p -match '(^|/)\.env($|\.)' -and $p -notmatch '(^|/)\.env\.example$') -or
            $p -match '(^|/)\.venv/' -or
            $p -match '\.(pem|key|p12|pfx)$' -or
            $p -match '(^|/)(id_rsa|id_ed25519)$'
        )
    }
)

if ($sensitiveFiles.Count -gt 0) {
    & git restore --staged -- @sensitiveFiles
    Write-Host ""
    Write-Host "Blocked: sensitive file(s) were staged and have been automatically unstaged:"
    $sensitiveFiles | ForEach-Object { Write-Host "  - $_" }
    Write-Host ""
    throw "Review these files before committing. Secrets must never be committed."
}

& git diff --cached --quiet
$hasStagedChanges = ($LASTEXITCODE -ne 0)

if ($hasStagedChanges) {
    Write-Host "Staged changes:"
    Invoke-Git -Args @("status", "--short")
    Write-Host ""

    Invoke-Git -Args @("commit", "-m", $Message)
} else {
    Write-Host "No new changes to commit."
}

Invoke-Git -Args @("push", "-u", "origin", $branch)

Write-Host ""
Write-Host "Done."
Write-Host "Branch '$branch' is committed (if needed) and pushed to origin."
