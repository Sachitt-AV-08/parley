<#>
.SYNOPSIS
    Parley installer - installs Parley CLI with MCP support
.DESCRIPTION
    Downloads the latest Parley release wheel from GitHub and installs it.
    Detects uv/pipx/pip and uses the best available installer.
#>

param(
    [string]$Version = "latest",
    [switch]$Force,
    [switch]$NoMcp
)

$ErrorActionPreference = "Stop"

# Colors
$Green  = [ConsoleColor]::Green
$Yellow = [ConsoleColor]::Yellow
$Red    = [ConsoleColor]::Red
$Cyan   = [ConsoleColor]::Cyan

function Write-Color($msg, $color) {
    $orig = $Host.UI.RawUI.ForegroundColor
    $Host.UI.RawUI.ForegroundColor = $color
    Write-Host $msg
    $Host.UI.RawUI.ForegroundColor = $orig
}

function Get-LatestRelease {
    $api = "https://api.github.com/repos/Sachitt-AV-08/parley/releases/latest"
    try {
        $resp = Invoke-RestMethod -Uri $api -Headers @{ "Accept" = "application/vnd.github.v3+json" }
        return $resp.tag_name
    } catch {
        Write-Color "Failed to fetch latest release: $($_.Exception.Message)" $Red
        return "v0.3.0"
    }
}

function Get-WheelUrl($tag) {
    $api = "https://api.github.com/repos/Sachitt-AV-08/parley/releases/tags/$tag"
    try {
        $resp = Invoke-RestMethod -Uri $api -Headers @{ "Accept" = "application/vnd.github.v3+json" }
        $wheel = $resp.assets | Where-Object { $_.name -like "*.whl" } | Select-Object -First 1
        if ($wheel) { return $wheel.browser_download_url }
    } catch { }
    $version = $tag.TrimStart('v')
    return "https://github.com/Sachitt-AV-08/parley/releases/download/$tag/parley_wa-$version-py3-none-any.whl"
}

Write-Color "╔══════════════════════════════════════════╗" $Cyan
Write-Color "║     Parley Installer                     ║" $Cyan
Write-Color "║   Drive your WhatsApp Desktop            ║" $Cyan
Write-Color "╚══════════════════════════════════════════╝" $Cyan
Write-Host ""

if ($Version -eq "latest") {
    Write-Color "Fetching latest release..." $Yellow
    $Version = Get-LatestRelease
}
Write-Color "Target version: $Version" $Cyan

$hasUv    = (Get-Command uv -ErrorAction SilentlyContinue) -ne $null
$hasPipx  = (Get-Command pipx -ErrorAction SilentlyContinue) -ne $null
$hasPip   = (Get-Command pip -ErrorAction SilentlyContinue) -ne $null

if ($hasUv) {
    Write-Color "Found uv - using uv tool install" $Green
    $installCmd = "uv tool install"
    if ($NoMcp) { $installCmd += " 'parley-wa'" } else { $installCmd += " 'parley-wa[mcp]'" }
    if ($Version -ne "latest") { $installCmd += "@$Version" }
    Write-Color "Running: $installCmd" $Cyan
    & $installCmd
} elseif ($hasPipx) {
    Write-Color "Found pipx - using pipx install" $Green
    $installCmd = "pipx install"
    if ($NoMcp) { $installCmd += " parley-wa" } else { $installCmd += " 'parley-wa[mcp]'" }
    if ($Version -ne "latest") { $installCmd += "==$($Version.TrimStart('v'))" }
    Write-Color "Running: $installCmd" $Cyan
    & $installCmd
} elseif ($hasPip) {
    Write-Color "Found pip - using pip install" $Green
    $wheelUrl = Get-WheelUrl $Version
    Write-Color "Downloading wheel: $wheelUrl" $Cyan
    $installCmd = "pip install"
    if (-not $NoMcp) { $installCmd += " 'parley-wa[mcp]'" } else { $installCmd += " parley-wa" }
    $installCmd += " $wheelUrl"
    Write-Color "Running: $installCmd" $Cyan
    & $installCmd
} else {
    Write-Color "No installer found (uv/pipx/pip). Please install Python first." $Red
    exit 1
}

Write-Host ""
Write-Color "✓ Parley installed successfully!" $Green
Write-Host ""
Write-Color "Quick start:" $Cyan
Write-Host "  parley setup              # Enable WhatsApp debugging port"
Write-Host "  parley doctor             # Verify connection"
Write-Host "  parley send --to Ava --text \"hi\""
Write-Host "  parley serve               # HTTP API at :8300"
Write-Host ""
Write-Color "MCP config (Claude Desktop / Cursor / Copilot):" $Cyan
Write-Host @"
{
  "mcpServers": {
    "parley": { "command": "parley", "args": ["mcp"], "type": "stdio" }
  }
}
"@