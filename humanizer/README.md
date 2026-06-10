# humanizer

A Claude Code skill that strips AI fingerprints from writing and rewrites it in your own voice. No API key, no external service — Claude reads two reference files and applies them directly.

## What it does

- **De-AI existing text.** Paste AI-sounding prose and it scrubs the tells (em dashes, "in today's fast-paced world," the relentless rule-of-three, reflexive hedging) and rewrites it to sound like a person.
- **Write fresh in your voice.** Ask for a post, email, or intro and it drafts in your voice from the first word, not generic AI prose.

## How it works

Two reference files drive every rewrite:

| File | Role |
|------|------|
| `skills/humanizer/references/writing_guardrails.md` | 200+ AI tells to avoid (the negative rules) |
| `~/.claude/humanizer/voice_profile.md` | Your personal voice profile, built by setup (the positive rules; a bundled template is the fallback) |

## Make it yours

After installing, say **"set up humanizer"**. A guided setup builds your personal voice profile from your real writing: samples you paste, files on disk you pick from a list, or sent emails you select (only if you have an email integration connected, and only the messages you choose). Your profile is saved to `~/.claude/humanizer/voice_profile.md`, outside the plugin, so plugin updates never overwrite it.

Skip setup and it still works — the bundled template has sane defaults. But even one real writing sample makes the output noticeably more you.

## Install

```
/plugin marketplace add Chameleon-Labs-LLC/plugins
/plugin install humanizer@chameleon-labs
```

Then say **"set up humanizer"** to build your voice profile, and ask Claude to "humanize this" or "write this in my voice."

## Credit

The AI-fingerprint catalog is adapted from Craig's "AI Tell Eliminator" NotebookLM + Gemini workflow ([@CraigDoesAi](https://www.notion.so/I-Built-This-NotebookLM-Gemini-Workflow-to-Destroy-AI-Fingerprints-335606421d12802da336fa1b41a04970)). The original Anthropic Managed Agent implementation lives at [Chameleon-Labs-LLC/humanizer](https://github.com/Chameleon-Labs-LLC/humanizer).

## License

MIT. Copyright (c) 2026 Chameleon Labs LLC.
