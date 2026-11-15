# Changelog

Marketplace releases, newest first. Versions track `metadata.version` in
`.claude-plugin/marketplace.json`; individual plugins version independently in
their own `plugin.json`.

## 0.3.0 — 2026-08-02

- **Four new bundled plugins:**
  - `repo-hygiene` — version-manager, repo-doctor, claude-md-optimizer, unify-agents-md.
  - `docs-toolkit` — project-documenter, technical-documenter, feature-documenter, update-code-map (CodeMap spec bundled), raginclude-generator.
  - `yt-transcript` — YouTube transcript downloader; auto-clones its source project ([lelandg/yt-transcript](https://github.com/lelandg/yt-transcript)) on first run.
  - `model-registry` — wire projects to a daily-refreshed public registry of current LLM model IDs.
- Bundled-tool invocations use `${CLAUDE_PLUGIN_ROOT}` paths so they resolve inside installed plugins.
- README: added the missing `humanizer` row; recommends upstream [Graphify](https://github.com/Graphify-Labs/graphify) for knowledge graphs rather than repackaging it.
- CI: validate workflow (JSON/structure checks + version-manager test suite).

## 0.2.0 — 2026-06-10

- `humanizer` plugin (0.2.0): AI-fingerprint removal + personal-voice rewriting, with guided voice-profile setup (`humanizer-setup` skill).

## 0.1.x — 2026-04-15 → 2026-05-29

- Initial marketplace: `agent-spawner`, `license-validator` (#1), and the bundled `scan-source` security-scan plugin.
