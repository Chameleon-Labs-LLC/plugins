#!/usr/bin/env bash
# Linux/WSL runner for the yt-transcript skill.
# Picks .venv_linux > .venv, creates one if neither exists,
# ensures youtube-transcript-api is installed, then runs the script.
set -euo pipefail

# Point this at your local clone of the yt-transcript project.
# Override by exporting YT_TRANSCRIPT_PROJECT before invoking.
PROJECT="${YT_TRANSCRIPT_PROJECT:-$HOME/code/yt-transcript}"

if [ ! -d "$PROJECT" ]; then
    echo "ERROR: project not found at $PROJECT" >&2
    echo "Set YT_TRANSCRIPT_PROJECT or edit this script to point at your clone." >&2
    exit 1
fi

cd "$PROJECT"

if [ -d ".venv_linux" ]; then
    VENV=".venv_linux"
elif [ -d ".venv" ]; then
    VENV=".venv"
else
    VENV=".venv_linux"
    echo ">>> No venv found. Creating $PROJECT/$VENV ..."
    python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

if ! python -c "import youtube_transcript_api" 2>/dev/null; then
    echo ">>> Installing requirements into $VENV ..."
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
fi

# Default behavior: reformat into prose. If the ML punctuation deps are
# installed, upgrade to NL-based punctuation restore (-m full); otherwise
# fall back to the lightweight stdlib reformatter (-m light is the script
# default). User-supplied flags win via argparse last-wins.
DEFAULTS=(-r)
if python -c "import deepmultilingualpunctuation, transformers, nltk" 2>/dev/null; then
    DEFAULTS+=(-m full)
fi

# Default output dir is ./Notes (we're cwd'd into the project),
# so user-supplied -d will override it via argparse last-wins.
exec python yt_transcript.py "${DEFAULTS[@]}" "$@"
