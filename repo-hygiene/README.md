# repo-hygiene

Keep any repo's agent-facing layer healthy — version-manager (standardized version bumps + changelogs, auto-detects where the version lives), repo-doctor (audit of AGENTS.md/CLAUDE.md topology, CodeMap freshness, token cost, doc drift), claude-md-optimizer (rightsize CLAUDE.md per Anthropic context-engineering guidance), and unify-agents-md (make AGENTS.md the single canonical guide every coding CLI follows).

## Skills

- **claude-md-optimizer** — Audit and rightsize CLAUDE.md / AGENTS.md and skills per Anthropic's Claude 5 context-engineering guidance (Thariq, 2026-07-24) — cut rules the model can judge, extract detail to on-demand files/skills, dedupe layers, and verify.
- **repo-doctor** — Audit a repo's agent-facing documentation layer and dispatch the right fix — instruction-file topology (AGENTS.md canonical? CLAUDE.md/GEMINI.md @import it?), always-loaded token cost, CodeMap freshness and line-number accuracy, broken pointers, changelog-vs-code version drift.
- **unify-agents-md** — Restructure a project's (or the whole machine's) AI-agent instruction files so AGENTS.md is the single canonical guide that every coding CLI follows — Claude Code, Codex, Copilot, Antigravity/agy, Gemini, Pi — with CLAUDE.md and GEMINI.md reduced to thin @import pointers plus tool-specific extras.
- **version-manager** — Use when bumping a version, cutting a release, or when a CHANGELOG is stale, missing versions, or disagrees with the code — and before opening any PR, per the versioning rule in AGENTS.md.

## Install

```
/plugin marketplace add Chameleon-Labs-LLC/plugins
/plugin install repo-hygiene@chameleon-labs
```

MIT licensed. Part of the [Chameleon Labs plugin marketplace](https://github.com/Chameleon-Labs-LLC/plugins).
