---
name: yt-transcript
description: Download a YouTube video's transcript to the yt-transcript project's Notes directory. Use whenever the user provides a YouTube URL (youtube.com/watch, youtu.be, shorts, embed) or a bare 11-character video ID and asks to fetch, save, download, grab, or transcribe the transcript/captions/subtitles — even if they don't explicitly name this skill. Also trigger on phrases like "get the transcript of this video", "save the captions", or "transcribe https://youtu.be/...".
---

# yt-transcript

Downloads a YouTube transcript via the `yt_transcript.py` script in a local `yt-transcript` project clone and saves the output into that project's `Notes/` directory.

## Prerequisites

This skill drives the [lelandg/yt-transcript](https://github.com/lelandg/yt-transcript) project (`yt_transcript.py` + `requirements.txt`). On first run, `scripts/run.sh` clones it automatically to `~/code/yt-transcript` if it isn't there. To use an existing clone instead, set the `YT_TRANSCRIPT_PROJECT` env var to its path (and `YT_TRANSCRIPT_REPO` to override the clone URL). Requires `git` and `python3`.

## When to use

Trigger whenever the user supplies a YouTube URL or a bare 11-character video ID and wants the transcript captured to a file. Accepts any URL form the underlying script supports: full `youtube.com/watch?v=...`, `youtu.be/...`, `/shorts/...`, `/embed/...`, or a raw ID like `dQw4w9WgXcQ`.

## How to run

Use the bundled Bash wrapper at `scripts/run.sh`. It handles the full venv lifecycle so we don't depend on whatever Python happens to be on PATH or a stale global pip install:

1. cd into the yt-transcript project
2. Pick a venv: prefer `.venv_linux`, fall back to `.venv`, create `.venv_linux` if neither exists
3. Activate it
4. Install `requirements.txt` if `youtube_transcript_api` isn't importable
5. Run `yt_transcript.py` with whatever args we pass

**Invoke it via the Bash tool:**

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/yt-transcript/scripts/run.sh "<URL_OR_ID>"
```

The script is cwd'd into the project, so the `yt_transcript.py` default output of `./Notes` lands in the right place automatically. Pass `-d <path>` to override.

First run will create the venv and install deps — subsequent runs skip that and just execute. If the wrapper is not executable yet, `bash <path>` invocation above sidesteps that entirely.

**Why a venv (not `uv run`, not global pip):** `uv run` installs the latest `youtube-transcript-api` on every fresh cache, and newer releases trip YouTube's bot-block much more aggressively on the same residential IP. A pinned venv avoids that churn — once the venv has a working version, it keeps working.

## Default behavior

The wrapper always passes `-r` so output is reformatted into readable prose. It then probes the venv for the ML punctuation deps (`deepmultilingualpunctuation`, `transformers`, `nltk`) and:

- **If installed** → adds `-m full` for NL-based punctuation restore.
- **If missing** → falls back to the script's built-in `-m light` reformatter.

Paragraph length stays at the script default (`-p 4`, ~3–4 sentences per paragraph). Any user-supplied flag overrides these defaults via argparse last-wins, so passing `-m light` or `-p 6` works as expected.

If the user wants the raw, unformatted transcript, they need to bypass the wrapper (call `python yt_transcript.py` directly inside the venv) — there is no "no-reformat" flag.

## Useful flags

Pass these through when the user asks for the corresponding behavior — don't add them speculatively:

| User intent | Flag |
|---|---|
| Custom filename | `-o <name>` |
| Include `[HH:MM:SS]` timestamps | `-t` |
| Non-English / specific language | `-l <code>` (e.g. `-l es`) |
| Force lightweight reformat (skip ML even if installed) | `-m light` |
| Force ML punctuation restore | `-m full` |
| Sentences per paragraph | `-p <N>` |

Example with flags:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/yt-transcript/scripts/run.sh "<URL>" -t -p 3
```

## After running

Report the saved file path (the script logs `INFO: Saved to: ...` on the last stdout line). If the user asked to read or summarize it, read the file from the project's `Notes/` directory afterward.

## Failure modes

- **IP-blocked by YouTube** — surface the error verbatim; don't retry. If the venv has a newer `youtube-transcript-api` that got blocked, suggest pinning to an older version inside the venv (`source .venv_linux/bin/activate && pip install 'youtube-transcript-api<1.0'`) or running from a different IP where an older version already works.
- **Transcripts disabled on the video** — script exits non-zero with a clear error; surface it and stop.
- **Bare ID not 11 chars** — ask the user to confirm the URL or ID rather than guessing.
- **`-r -m full` missing deps** — tell the user to `pip install "deepmultilingualpunctuation>=1.0" "transformers<5" nltk` *inside the activated venv*, or drop back to `-m light`.
