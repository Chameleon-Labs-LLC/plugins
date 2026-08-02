# yt-transcript

Download YouTube transcripts from any URL form (watch, youtu.be, shorts, embed) or bare video ID into a local project's Notes directory, with full venv lifecycle handled by a bundled runner.

## Skills

- **yt-transcript** — Download a YouTube video's transcript to the yt-transcript project's Notes directory.

## How it works

The skill drives [lelandg/yt-transcript](https://github.com/lelandg/yt-transcript) (`yt_transcript.py`), auto-cloning it to `~/code/yt-transcript` on first run (override with `YT_TRANSCRIPT_PROJECT` / `YT_TRANSCRIPT_REPO`). Requires `git` and `python3`.

## Install

```
/plugin marketplace add Chameleon-Labs-LLC/plugins
/plugin install yt-transcript@chameleon-labs
```

MIT licensed. Part of the [Chameleon Labs plugin marketplace](https://github.com/Chameleon-Labs-LLC/plugins).
