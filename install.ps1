# Cirax installer for Windows (PowerShell).
#
#   irm https://raw.githubusercontent.com/baselanaya/Cirax/main/install.ps1 | iex
#
# Bootstraps uv (winget or the official installer) and installs the cirax
# CLI as a uv tool. Engines are separate: run `cirax doctor --show-missing`
# afterwards — it prints scoop/winget commands for everything it knows.
#
# Env overrides: CIRAX_SRC (local checkout), CIRAX_REPO (git URL),
#               CIRAX_REF (branch), CIRAX_VERSION (PyPI version)
$ErrorActionPreference = "Stop"

$Repo = if ($env:CIRAX_REPO) { $env:CIRAX_REPO } else { "https://github.com/baselanaya/Cirax" }
$Ref = if ($env:CIRAX_REF) { $env:CIRAX_REF } else { "main" }
$Src = $env:CIRAX_SRC

Write-Host "==> cirax installer"

# 1. uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "==> installing uv"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id=astral-sh.uv -e --accept-source-agreements --accept-package-agreements
    } else {
        irm https://astral.sh/uv/install.ps1 | iex
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        # fresh PATH for this session
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    }
}

# 2. cirax
if ($Src) {
    uv tool install --force --upgrade $Src
    Write-Host "==> installed (local: $Src)"
} elseif (-not $env:CIRAX_REPO -or $env:CIRAX_FROM -eq "pypi") {
    uv tool install --force --upgrade cirax
    Write-Host "==> installed (PyPI)"
} else {
    Write-Host "==> installing from git ($Repo@$Ref)"
    $Tmp = Join-Path $env:TEMP ("cirax-" + [guid]::NewGuid().ToString("N"))
    git clone --depth 1 --branch $Ref $Repo $Tmp
    uv tool install --force $Tmp
    Remove-Item -Recurse -Force $Tmp
    Write-Host "==> installed (git)"
}

Write-Host ""
Write-Host "==> done. Try:"
Write-Host "      cirax doctor                  # what can this machine convert?"
Write-Host "      cirax convert a.png -t webp"
Write-Host "      cirax doctor --show-missing   # scoop/winget hints for engines"
Write-Host ""
Write-Host "    If 'cirax' is not found, reopen your terminal (PATH refresh)."
