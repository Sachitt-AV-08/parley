#!/usr/bin/env sh
# parley installer — macOS / Linux
# Run it directly from the README one-liner:
#   curl -fsSL https://raw.githubusercontent.com/Sachitt-AV-08/parley/main/install.sh | sh
#
# Installs parley, enables the local debugging port, and prints next steps.
# On this platform setup only exports the (per-user) env var that opens the
# WebView2/Chrome debug port — undo with `parley setup --undo`.

set -e

REPO="https://github.com/Sachitt-AV-08/parley"
RELEASE="${PARLEY_RELEASE:-v0.3.0}"
WHL="$REPO/releases/download/$RELEASE/parley_wa-${RELEASE#v}-py3-none-any.whl"

printf '\n  \033[1;36mparley installer\033[0m\n'
printf '  source : %s\n' "$REPO"
printf '  release: %s\n\n' "$RELEASE"
printf '  Note: WhatsApp for Web/Destop debugging here needs Chromium flags;\n'
printf '  parley setup will do its best, and parley doctor will tell you the truth.\n\n'

# 1) install ----------------------------------------------------------------
install_with_uv() {
    printf '\033[1;32m[1/3] installing with uv ...\033[0m\n'
    uv tool install --force "$WHL"
}

install_with_pip() {
    printf '\033[1;32m[1/3] installing with pip ...\033[0m\n'
    command -v python3 >/dev/null 2>&1 || { echo "no python3 found"; exit 1; }
    python3 -m pip install --user --upgrade "$WHL"
    export PATH="$PATH:$HOME/.local/bin"
}

if command -v uv >/dev/null 2>&1; then
    install_with_uv
elif command -v pipx >/dev/null 2>&1; then
    install_with_pip
else
    install_with_pip
fi

# 2) enable the port (best-effort, but honest) ------------------------------
if [ "${PARLEY_NOSETUP:-0}" != "1" ]; then
    printf '\033[1;32m[2/3] enabling the local debugging port ...\033[0m\n'
    parley setup || echo "setup could not self-configure here — run  parley doctor  to see why."
    printf '\n    restart the app once after this.\n\n'
fi

# 3) verify -----------------------------------------------------------------
printf '\033[1;32m[3/3] verifying ...\033[0m\n'
parley --version
if parley --demo status >/dev/null 2>&1; then
    printf '\033[1;32m   simulator: OK\033[0m\n'
else
    printf '\033[1;31m   simulator check failed\033[0m\n'
fi

printf '\n  \033[1;36mNext:\033[0m\n'
printf '  1. parley doctor\n'
printf "  2. parley send --to <name> --text 'hi'\n"
printf "  3. agents: pip install 'parley-wa[mcp]'  &&  parley mcp\n"
printf '     parley skill install          # Claude Code skill\n'
printf '  more: %s#readme\n\n' "$REPO"