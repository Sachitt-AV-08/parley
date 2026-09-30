# parley installer — Windows (PowerShell)
# Run it directly from the README one-liner:
#   irm https://raw.githubusercontent.com/Sachitt-AV-08/parley/main/install.ps1 | iex
#
# It installs parley, enables the local debugging port, and prints the two
# commands you actually need next. Everything can be undone with
# `parley setup --undo`.

param(
    [string]$Release = "",          # default: latest release version below
    [switch]$NoSetup                # skip enabling the WebView2 debug port
)

$ErrorActionPreference = "Stop"
$Repo   = "https://github.com/Sachitt-AV-08/parley"
if (-not $Release) { $Release = "v0.3.0" }
$WhlUrl = "$Repo/releases/download/$Release/parley_wa-$($Release.TrimStart('v'))-py3-none-any.whl"

Write-Host ""
Write-Host "  parley installer" -ForegroundColor Cyan
Write-Host "  -----------------"
Write-Host "  source : $Repo"
Write-Host "  release: $Release"
Write-Host ""

function Install-WithUv {
    Write-Host "[1/3] installing with uv ..." -ForegroundColor Green
    uv tool install --force $WhlUrl
    return $true
}

function Install-WithPip {
    Write-Host "[1/3] installing with pip ..." -ForegroundColor Green
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
    if (-not $py) { throw "no Python found — install Python 3.10+ from python.org, or install uv (https://docs.astral.sh/uv/)" }
    & ($py) -m pip install --upgrade $WhlUrl
    return $lastExitCode -eq 0
}

# ------------------------------------------------------------------ install
$ok = $false
if (Get-Command uv -ErrorAction SilentlyContinue) { $ok = Install-WithUv }
elseif (Get-Command pipx -ErrorAction SilentlyContinue) { $ok = Install-WithPip }
else { $ok = Install-WithPip }

if (-not $ok) { throw "install failed" }

# ---------------------------------------------------------------- the port
if (-not $NoSetup) {
    Write-Host "[2/3] enabling the local debugging port ..." -ForegroundColor Green
    parley setup
    Write-Host ""
    Write-Host "    WhatsApp must be fully closed and restarted once." -ForegroundColor Yellow
    Write-Host "    (undo anytime with:  parley setup --undo)" -ForegroundColor DarkGray
    Write-Host ""
}

# ------------------------------------------------------------------- verify
Write-Host "[3/3] verifying ..." -ForegroundColor Green
$ver = parley --version
try { parley --demo status | Out-Null; Write-Host "   simulator: OK  ($ver)" -ForegroundColor Green }
catch { Write-Host "   simulator check failed: $_" -ForegroundColor Red }

Write-Host ""
Write-Host "  Next:" -ForegroundColor Cyan
if (-not $NoSetup) { Write-Host "  1. restart WhatsApp Desktop (fully quit, reopen, log in)" }
Write-Host "  2. parley doctor        # confirm it can attach"
Write-Host "  3. parley send --to <name> --text 'hi'   # send for real"
Write-Host "  agents: pip install 'parley-wa[mcp]'  &&  parley mcp"
Write-Host "          parley skill install          # Claude Code skill"
Write-Host "  more:  https://github.com/Sachitt-AV-08/parley#readme"
Write-Host ""