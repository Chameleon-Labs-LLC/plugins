#!/usr/bin/env bash
# Smoke test for scan-source's scan-download, using stub scanners.
#
# Usage: bash tests/smoke-scan-download.sh [--no-timeout]
#   --no-timeout  hide `timeout`/`gtimeout` from PATH to exercise the watchdog
#                 fallback (macOS has neither by default).
#
# Runs under whatever bash invokes it; CI runs it with macOS /bin/bash 3.2.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
SD="$HERE/../scan-source/skills/scan-source/scripts/scan-download"
MODE="${1:-}"

W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
FB="$W/bin"; mkdir -p "$FB" "$W/target"
echo 'requests==2.0' >"$W/target/requirements.txt"
echo 'print(1)' >"$W/target/a.py"

# guarddog: 2 indicators, one of them allowlisted -> net 1 finding
cat >"$FB/guarddog" <<'EOF'
#!/bin/sh
echo "Found 2 potentially malicious indicators"
echo "  * This package has benign-thing"
echo "  * This package has evil-thing"
EOF
printf '#!/bin/sh\nexit 0\n' >"$FB/trivy"
printf '#!/bin/sh\n[ "$1" = scan ] && [ "$2" = --help ] && exit 0\nexit 1\n' >"$FB/osv-scanner"
printf '#!/bin/sh\nexit 0\n' >"$FB/pip-audit"
printf '#!/bin/sh\nsleep 30\n' >"$FB/semgrep"   # must be cut off by the timeout
chmod +x "$FB"/*
printf 'benign-thing\n' >"$W/allow.txt"

if [ "$MODE" = --no-timeout ]; then
  U="$W/util"; mkdir -p "$U"
  for c in date mkdir find grep head awk tee sed sleep mktemp rm pkill uname cat sh env; do
    p="$(command -v "$c")" && ln -s "$p" "$U/$c"
  done
  P="$FB:$U"
else
  P="$FB:$PATH"
fi

start=$(date +%s)
out="$(env -i HOME="$W" PATH="$P" SCAN_ALLOWLIST="$W/allow.txt" SEMGREP_TIMEOUT=3 \
  "$BASH" "$SD" "$W/target" 2>&1 | sed $'s/\033\\[[0-9;]*m//g')"
elapsed=$(( $(date +%s) - start ))
# Exit code check on a second, fast run (--quick skips semgrep).
env -i HOME="$W" PATH="$P" SCAN_ALLOWLIST="$W/allow.txt" \
  "$BASH" "$SD" --quick "$W/target" >/dev/null 2>&1
rc=$?
printf '%s\n' "$out"

fail=0
expect() {  # expect <regex> <description>
  if printf '%s\n' "$out" | grep -qE "$1"; then echo "PASS: $2"; else echo "FAIL: $2" >&2; fail=1; fi
}
expect 'gd_py +FINDINGS'                       'guarddog indicators survive the allowlist'
expect 'allowlist|1 INDICATOR'                 'allowlist suppressed the benign indicator'
expect 'trivy +clean'                          'trivy exit 0 is clean'
expect 'osv +FINDINGS'                         'osv-scanner exit 1 is a finding'
expect 'semgrep +SKIP: timed out after 3s'     'semgrep is cut off by the timeout'
expect 'VERDICT: findings present'             'overall verdict'
if [ "$rc" = 1 ]; then echo "PASS: --quick run exits 1 on findings"; else echo "FAIL: --quick exit code $rc" >&2; fail=1; fi
if [ "$elapsed" -lt 25 ]; then echo "PASS: finished in ${elapsed}s"; else echo "FAIL: took ${elapsed}s; timeout did not fire" >&2; fail=1; fi
exit "$fail"
