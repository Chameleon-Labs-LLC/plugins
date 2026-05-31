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
| `skills/humanizer/references/voice_profile.md` | Your personal voice profile (the positive rules) |

## Make it yours

`voice_profile.md` ships as a template with sane defaults and a `YOUR VERSION` line under each section. It works out of the box, but it gets much better once you fill in even a section or two with your actual voice. The fastest way: paste a paragraph you've written and are happy with, and let the skill fill the profile from it.

## Install

```
/plugin marketplace add Chameleon-Labs-LLC/plugins
/plugin install humanizer@chameleon-labs
```

Then ask Claude to "humanize this" or "write this in my voice." Edit `voice_profile.md` to teach it who you are.

## Credit

The AI-fingerprint catalog is adapted from Craig's "AI Tell Eliminator" NotebookLM + Gemini workflow ([@CraigDoesAi](https://www.notion.so/I-Built-This-NotebookLM-Gemini-Workflow-to-Destroy-AI-Fingerprints-335606421d12802da336fa1b41a04970)). The original Anthropic Managed Agent implementation lives at [Chameleon-Labs-LLC/humanizer](https://github.com/Chameleon-Labs-LLC/humanizer).

## License

MIT. Copyright (c) 2026 Chameleon Labs LLC.
