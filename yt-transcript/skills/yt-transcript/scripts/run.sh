#!/usr/bin/env bash
# Cross-platform runner for the yt-transcript skill (Linux, WSL, macOS, and
# Git Bash on native Windows). Picks a venv that works on this platform,
# creates one if none does, ensures youtube-transcript-api is installed,
# then runs the script.
set -euo pipefail

# Local clone of the yt-transcript project (auto-cloned on first run).
# Source: https://github.com/lelandg/yt-transcript
# Override the location by exporting YT_TRANSCRIPT_PROJECT before invoking.
PROJECT="${YT_TRANSCRIPT_PROJECT:-$HOME/code/yt-transcript}"
YT_TRANSCRIPT_REPO="${YT_TRANSCRIPT_REPO:-https://github.com/lelandg/yt-transcript.git}"

if [ ! -d "$PROJECT" ]; then
    echo ">>> yt-transcript project not found at $PROJECT — cloning $YT_TRANSCRIPT_REPO ..." >&2
    if ! git clone --depth 1 "$YT_TRANSCRIPT_REPO" "$PROJECT"; then
        echo "ERROR: could not clone $YT_TRANSCRIPT_REPO to $PROJECT" >&2
        echo "Clone it manually, or set YT_TRANSCRIPT_PROJECT to an existing clone." >&2
        exit 1
    fi
fi

cd "$PROJECT"

# WSL and Windows can share one clone on /mnt/<drive>, and a venv built on one
# does not run on the other, so each platform keeps its own:
#   Linux/WSL: .venv_linux (bin/python)   macOS: .venv (bin/python)
#   Windows:   .venv or .venv_windows (Scripts/python.exe)
# A candidate counts only if its interpreter exists for this platform.
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        VENVS=(.venv .venv_windows); VENV_PY="Scripts/python.exe"; BOOT=("py -3" python python3) ;;
    Darwin)
        VENVS=(.venv .venv_linux); VENV_PY="bin/python"; BOOT=(python3 python) ;;
    *)
        VENVS=(.venv_linux .venv); VENV_PY="bin/python"; BOOT=(python3 python) ;;
esac

VENV=""
for v in "${VENVS[@]}"; do
    if [ -x "$v/$VENV_PY" ]; then VENV="$v"; break; fi
done

if [ -z "$VENV" ]; then
    # Create the first candidate that does not exist yet. An existing one
    # belongs to the other platform (e.g. a Linux .venv in a clone shared
    # with Windows), and `python -m venv` would merge into it.
    for v in "${VENVS[@]}"; do
        if [ ! -e "$v" ]; then VENV="$v"; break; fi
    done
    if [ -z "$VENV" ]; then
        echo "ERROR: ${VENVS[*]} all exist in $PROJECT but none has $VENV_PY." >&2
        echo "Remove the broken one and re-run." >&2
        exit 1
    fi
    # On Windows, "python3" may be the Microsoft Store stub, which exits
    # non-zero. Probe each launcher instead of trusting `command -v`.
    PYBOOT=()
    for cand in "${BOOT[@]}"; do
        read -r -a cmd <<<"$cand"
        if "${cmd[@]}" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
            PYBOOT=("${cmd[@]}"); break
        fi
    done
    if [ "${#PYBOOT[@]}" -eq 0 ]; then
        echo "ERROR: no Python 3.8+ found (tried: ${BOOT[*]})." >&2
        exit 1
    fi
    echo ">>> No venv found. Creating $PROJECT/$VENV with ${PYBOOT[*]} ..."
    "${PYBOOT[@]}" -m venv "$VENV"
fi

PY="$VENV/$VENV_PY"
# Windows consoles default to cp1252; transcripts are often not ASCII.
export PYTHONUTF8=1

if ! "$PY" -c "import youtube_transcript_api" 2>/dev/null; then
    echo ">>> Installing requirements into $VENV ..."
    "$PY" -m pip install --quiet --upgrade pip
    "$PY" -m pip install --quiet -r requirements.txt
fi

# Default behavior: reformat into prose. If the ML punctuation deps are
# installed, upgrade to NL-based punctuation restore (-m full); otherwise
# fall back to the lightweight stdlib reformatter (-m light is the script
# default). User-supplied flags win via argparse last-wins.
DEFAULTS=(-r)
if "$PY" -c "import deepmultilingualpunctuation, transformers, nltk" 2>/dev/null; then
    DEFAULTS+=(-m full)
fi

# Default output dir is ./Notes (we're cwd'd into the project),
# so user-supplied -d will override it via argparse last-wins.
exec "$PY" yt_transcript.py "${DEFAULTS[@]}" "$@"
