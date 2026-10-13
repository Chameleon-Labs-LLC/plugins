#!/usr/bin/env bash
# Smoke test for yt-transcript's run.sh against a stub project: checks that it
# finds a working Python, creates the platform's venv, and runs the script with
# the venv's interpreter. Works on Linux, macOS, and Git Bash on Windows.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RUN="$HERE/../yt-transcript/skills/yt-transcript/scripts/run.sh"

W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
P="$W/yt-transcript"; mkdir -p "$P"
: >"$P/requirements.txt"
cat >"$P/yt_transcript.py" <<'EOF'
import sys
print("STUB", sys.prefix, sys.argv[1:], "— utf8 ok")
EOF

out="$(YT_TRANSCRIPT_PROJECT="$P" bash "$RUN" dQw4w9WgXcQ -t)"
printf '%s\n' "$out"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) want=.venv ;;
  Darwin)               want=.venv ;;
  *)                    want=.venv_linux ;;
esac
[ -d "$P/$want" ] || { echo "FAIL: expected venv $want" >&2; exit 1; }
printf '%s\n' "$out" | grep -q "STUB .*$want" || { echo "FAIL: script did not run in $want" >&2; exit 1; }
printf '%s\n' "$out" | grep -q -- "'-r', 'dQw4w9WgXcQ', '-t'" || { echo "FAIL: args not passed through" >&2; exit 1; }
printf '%s\n' "$out" | grep -q 'utf8 ok' || { echo "FAIL: non-ASCII output" >&2; exit 1; }
echo "PASS: run.sh created $want and ran the script"
