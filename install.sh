#!/usr/bin/env bash
# Parley installer - installs Parley CLI with MCP support
# Detects uv/pipx/pip and uses the best available installer

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

VERSION="${1:-latest}"
FORCE=false
NO_MCP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --force) FORCE=true; shift ;;
        --no-mcp) NO_MCP=true; shift ;;
        -*) echo "Unknown option: $1"; exit 1 ;;
        *) VERSION="$1"; shift ;;
    esac
done

echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Parley Installer                     ║${NC}"
echo -e "${CYAN}║   Drive your WhatsApp Desktop            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# Get latest version if not specified
if [[ "$VERSION" == "latest" ]]; then
    echo -e "${YELLOW}Fetching latest release...${NC}"
    VERSION=$(curl -s https://api.github.com/repos/Sachitt-AV-08/parley/releases/latest | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')
    if [[ -z "$VERSION" ]]; then
        echo -e "${RED}Failed to fetch latest release, using v0.3.0${NC}"
        VERSION="v0.3.0"
    fi
fi

echo -e "${CYAN}Target version: ${VERSION}${NC}"
echo ""

# Detect installer
if command -v uv &> /dev/null; then
    echo -e "${GREEN}Found uv - using uv tool install${NC}"
    if [[ "$NO_MCP" == true ]]; then
        uv tool install "parley-wa@${VERSION}"
    else
        uv tool install "parley-wa[mcp]@${VERSION}"
    fi
elif command -v pipx &> /dev/null; then
    echo -e "${GREEN}Found pipx - using pipx install${NC}"
    if [[ "$NO_MCP" == true ]]; then
        pipx install "parley-wa==${VERSION#v}"
    else
        pipx install "parley-wa[mcp]==${VERSION#v}"
    fi
elif command -v pip &> /dev/null; then
    echo -e "${GREEN}Found pip - using pip install${NC}"
    WHEEL_URL="https://github.com/Sachitt-AV-08/parley/releases/download/${VERSION}/parley_wa-${VERSION#v}-py3-none-any.whl"
    if [[ "$NO_MCP" == true ]]; then
        pip install "$WHEEL_URL"
    else
        pip install "$WHEEL_URL[mcp]"
    fi
else
    echo -e "${RED}No installer found (uv/pipx/pip). Please install Python first.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✓ Parley installed successfully!${NC}"
echo ""
echo -e "${CYAN}Quick start:${NC}"
echo "  parley setup              # Enable WhatsApp debugging port"
echo "  parley doctor             # Verify connection"
echo "  parley send --to Ava --text \"hi\""
echo "  parley serve              # HTTP API at :8300"
echo ""
echo -e "${CYAN}MCP config (Claude Desktop / Cursor / Copilot):${NC}"
cat << 'EOF'
{
  "mcpServers": {
    "parley": { "command": "parley", "args": ["mcp"], "type": "stdio" }
  }
}
EOF