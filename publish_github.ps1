#Requires -Version 5.1
<#
  Authenticate GitHub CLI with a PAT, create repo HKLBA_Champion_Path, push current branch.

  Option A — environment variable (recommended):
    $env:GH_TOKEN = 'github_pat_...'   # fine-grained, or classic ghp_... with repo scope
    .\publish_github.ps1

  Option B — file (gitignored):
    Put the token in .github_token (single line) in this folder, then:
    .\publish_github.ps1

  Classic PAT: repo, read:org (per gh auth login --with-token).
#>
param(
    [string] $RepoName = 'HKLBA_Champion_Path',
    [switch] $Private
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$token = $env:GH_TOKEN
if (-not $token -and (Test-Path (Join-Path $PSScriptRoot '.github_token'))) {
    $token = (Get-Content (Join-Path $PSScriptRoot '.github_token') -Raw).Trim()
}
if (-not $token) {
    throw 'Set GH_TOKEN or create .github_token (see script header).'
}

$ghCmd = Get-Command gh -ErrorAction SilentlyContinue
$gh = if ($ghCmd) { $ghCmd.Source } else { $null }
if (-not $gh) { $gh = 'C:\Program Files\GitHub CLI\gh.exe' }
if (-not (Test-Path -LiteralPath $gh)) {
    throw 'GitHub CLI (gh) not found. Install: winget install GitHub.cli'
}

$token | & $gh auth login --hostname github.com --git-protocol https --with-token
if ($LASTEXITCODE -ne 0) { throw 'gh auth login --with-token failed.' }

git branch -M main 2>$null

$hasOrigin = $true
git remote get-url origin 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { $hasOrigin = $false }

if (-not $hasOrigin) {
    if ($Private) {
        & $gh repo create $RepoName --private --source=. --remote=origin --push
    } else {
        & $gh repo create $RepoName --public --source=. --remote=origin --push
    }
    if ($LASTEXITCODE -ne 0) { throw 'gh repo create failed (name taken or network).'}
} else {
    git push -u origin main
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
}

Write-Host "Done. Remote: origin -> $RepoName"
