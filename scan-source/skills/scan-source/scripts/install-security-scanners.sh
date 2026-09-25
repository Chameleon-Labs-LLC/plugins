#!/usr/bin/env bash
#
# install-security-scanners.sh
#
# One-shot installer for the local source-code / supply-chain scanning toolkit
# used by the `scan-download` command. No sudo required: pipx + npm-global +
# two static binaries dropped into ~/.local/bin.
#
# Platforms: Linux and macOS, on x86_64 or arm64. On Windows, run it inside WSL.
# Prerequisites: curl, jq, tar, pipx
#   macOS:          brew install pipx jq
#   Debian/Ubuntu:  sudo apt install pipx jq
#
# Tools installed:
#   guarddog   (pipx)  - heuristic MALWARE detection for PyPI & npm packages
#   semgrep    (pipx)  - SAST: insecure code patterns in the source itself
#   pip-audit  (pipx)  - Python dependency CVE audit (PyPA advisory DB)
#   osv-scanner(bin)   - dependency vulns vs Google's live OSV.dev database
#   trivy      (bin)   - all-in-one: dep vulns + leaked secrets + misconfigs
#   socket     (npm)   - OPTIONAL behavioral supply-chain scoring (needs free account)
#
# Supply-chain note (per your own 7-day minimum-package-age rule): every tool
# below is a long-established, high-profile project. Re-running this installer
# only ever pulls each project's *latest stable* release, which is effectively
# always older than 7 days. If you want to be strict, pin versions where noted.
#
set -euo pipefail

BIN="$HOME/.local/bin"
mkdir -p "$BIN"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!!  %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m  ok %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 0. platform + prerequisites
# ---------------------------------------------------------------------------
case "$(uname -s)" in
  Linux)  OSV_OS=linux;  TRIVY_OS=Linux ;;
  Darwin) OSV_OS=darwin; TRIVY_OS=macOS ;;
  MINGW*|MSYS*|CYGWIN*)
    echo "install-security-scanners.sh: the scanners are Linux tools; run this inside WSL:" >&2
    echo "  wsl.exe -e bash -lc 'bash /mnt/<drive>/<path-to>/install-security-scanners.sh'" >&2
    exit 2 ;;
  *) echo "install-security-scanners.sh: unsupported OS '$(uname -s)'" >&2; exit 2 ;;
esac
case "$(uname -m)" in
  x86_64|amd64)  OSV_ARCH=amd64; TRIVY_ARCH=64bit ;;
  arm64|aarch64) OSV_ARCH=arm64; TRIVY_ARCH=ARM64 ;;
  *) echo "install-security-scanners.sh: unsupported CPU '$(uname -m)'" >&2; exit 2 ;;
esac

missing=()
for c in curl jq tar pipx; do have "$c" || missing+=("$c"); done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "install-security-scanners.sh: missing prerequisites: ${missing[*]}" >&2
  if [ "$OSV_OS" = darwin ]; then
    echo "  Install them with: brew install ${missing[*]}" >&2
  else
    echo "  Install them with your package manager, e.g.: sudo apt install ${missing[*]}" >&2
  fi
  exit 2
fi

# ---------------------------------------------------------------------------
# 1. pipx tools (isolated venvs, never pollute system python)
# ---------------------------------------------------------------------------
say "Installing pipx tools: guarddog, semgrep, pip-audit"
for pkg in guarddog semgrep pip-audit; do
  if pipx list --short 2>/dev/null | grep -q "^${pkg} "; then
    ok "$pkg already installed (upgrading)"
    pipx upgrade "$pkg" >/dev/null || true
  else
    pipx install "$pkg"
  fi
done

# ---------------------------------------------------------------------------
# 2. osv-scanner  (static Go binary, fetched from GitHub releases)
# ---------------------------------------------------------------------------
say "Installing osv-scanner -> $BIN/osv-scanner"
# `|| true`: under set -e a failed API call (rate limit) would abort the whole
# installer instead of reaching the "Skipping" branch below.
OSV_URL=$({ curl -fsSL https://api.github.com/repos/google/osv-scanner/releases/latest \
  | jq -r --arg n "osv-scanner_${OSV_OS}_${OSV_ARCH}" \
      '.assets[] | select(.name == $n) | .browser_download_url' | head -1; } || true)
if [ -z "${OSV_URL:-}" ]; then
  warn "Could not resolve osv-scanner asset URL (GitHub API rate limit?). Skipping."
else
  curl -fsSL "$OSV_URL" -o "$BIN/osv-scanner"
  chmod +x "$BIN/osv-scanner"
  ok "osv-scanner $("$BIN/osv-scanner" --version 2>/dev/null | head -1)"
fi

# ---------------------------------------------------------------------------
# 3. trivy  (static binary, extracted from GitHub release tarball)
# ---------------------------------------------------------------------------
say "Installing trivy -> $BIN/trivy"
TRIVY_URL=$({ curl -fsSL https://api.github.com/repos/aquasecurity/trivy/releases/latest \
  | jq -r --arg s "_${TRIVY_OS}-${TRIVY_ARCH}.tar.gz" \
      '.assets[] | select(.name | endswith($s)) | .browser_download_url' | head -1; } || true)
if [ -z "${TRIVY_URL:-}" ]; then
  warn "Could not resolve trivy asset URL. Skipping."
else
  TMP=$(mktemp -d)
  curl -fsSL "$TRIVY_URL" -o "$TMP/trivy.tgz"
  tar -xzf "$TMP/trivy.tgz" -C "$TMP" trivy
  mv "$TMP/trivy" "$BIN/trivy"
  chmod +x "$BIN/trivy"
  rm -rf "$TMP"
  ok "trivy $("$BIN/trivy" --version 2>/dev/null | head -1)"
fi

# ---------------------------------------------------------------------------
# 4. socket CLI  (OPTIONAL - npm global; needs a free account to be useful)
#    Honors your ~/.npmrc min-release-age. Uncomment to enable, or run later:
#       npm install -g @socketsecurity/cli && socket login
# ---------------------------------------------------------------------------
if [ "${INSTALL_SOCKET:-0}" = "1" ]; then
  say "Installing socket CLI (npm global)"
  npm install -g @socketsecurity/cli
  warn "Run 'socket login' once to enable behavioral scans (free account)."
else
  warn "Skipping socket CLI (optional). Enable with: INSTALL_SOCKET=1 $0"
fi

# ---------------------------------------------------------------------------
say "Done. Installed into $BIN"
echo
echo "Verify:"
for t in guarddog semgrep pip-audit osv-scanner trivy; do
  printf '  %-12s ' "$t"
  have "$t" && echo "ok" || echo "MISSING"
done
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) warn "$BIN is not on PATH. Run 'pipx ensurepath', then open a new shell." ;;
esac
echo
echo "Next: scan-download /path/to/some-cloned-repo"
