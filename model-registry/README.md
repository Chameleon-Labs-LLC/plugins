# model-registry

Wire any project to a daily-refreshed public registry of current LLM model IDs (Claude, GPT, Gemini) so code stops hardcoding model names that go stale. Installs the zero-dependency Python/TypeScript client, migrates hardcoded IDs, and manages bundled fallbacks.

## Skills

- **model-registry** — Use when a project hardcodes LLM model IDs (claude-*, gpt-*, gemini-*) that go stale, when the user wants current model IDs resolved at runtime, or on /model-registry [install|migrate|status|refresh-fallback].

## Install

```
/plugin marketplace add Chameleon-Labs-LLC/plugins
/plugin install model-registry@chameleon-labs
```

MIT licensed. Part of the [Chameleon Labs plugin marketplace](https://github.com/Chameleon-Labs-LLC/plugins).
