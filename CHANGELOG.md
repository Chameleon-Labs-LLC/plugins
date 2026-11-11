# Changelog

Marketplace releases, newest first. Versions track `metadata.version` in
`.claude-plugin/marketplace.json`; individual plugins version independently in
their own `plugin.json`.

## 0.4.0 — 2026-09-25

- **Cross-platform:** every bundled plugin runs on Linux, macOS (Intel and Apple silicon), and native Windows. CI now tests all three.
- **Line endings:** a root `.gitattributes` keeps every script LF. Windows clones with `core.autocrlf=true` used to get CRLF scripts, and bash failed with `$'\r': command not found`.
- `scan-source` 0.2.0:
  - Fixed the script path in SKILL.md.
  - On native Windows the scanners run in WSL, and both scripts refuse to run in Git Bash.
  - `scan-download` runs under macOS's bash 3.2 and works without GNU `timeout`.
  - The installer downloads the right osv-scanner and trivy builds for Linux or macOS on amd64 or arm64.
  - New workflow steps: a saved report, a generated fix script, sanitized shareable copies, and an offer to file an upstream issue.
- `yt-transcript` 0.2.0: `run.sh` works in Git Bash on Windows. It uses a separate venv per platform, so WSL and Windows can share one clone, and falls back from `python3` to `py -3` or `python`.
- `repo-hygiene` 0.2.0:
  - `repo-doctor` no longer crashes on Windows. It used to raise `UnicodeEncodeError`.
  - `version-manager` handles plugin marketplaces. `release --plugin NAME[=LEVEL]` bumps each plugin in a multi-plugin catalog.
  - `unify-agents-md` makes real symlinks on Windows.
- `docs-toolkit` 0.1.1: `extract_symbols.py` writes UTF-8 output, and the CodeMap command falls back to `python` when `python3` is missing.

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
