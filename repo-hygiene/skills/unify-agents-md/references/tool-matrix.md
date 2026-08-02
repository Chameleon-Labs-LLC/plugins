# Agent CLI instruction-file matrix

Verified June 2026. This is the ground truth the skill relies on for *how* each
tool ingests instructions. Re-verify if a tool changes; the wiring choices below
follow directly from the "import support" column.

## Per-tool support

| Tool | Project file(s) it reads | Global personal file | `@import`? | Wiring for global house rules |
|------|--------------------------|----------------------|-----------|-------------------------------|
| **Claude Code** | `CLAUDE.md` (does **not** auto-read `AGENTS.md`) | `~/.claude/CLAUDE.md` | **Yes** (absolute paths) | `CLAUDE.md` line 1 = `@<shared>`, then Claude-only extras |
| **Codex CLI** | `AGENTS.md` (per-dir, root→leaf), `AGENTS.override.md` | `~/.codex/AGENTS.md` (or `AGENTS.override.md`) | **No** — concatenates AGENTS.md per level | **symlink** `~/.codex/AGENTS.md` → `<shared>` |
| **Copilot CLI** | root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.github/instructions/**` | `~/.copilot/copilot-instructions.md` | **No** | **symlink** `~/.copilot/copilot-instructions.md` → `<shared>`, plus `copilot(){ command copilot --add-dir "$HOME/.claude/instructions" "$@"; }` in `~/.bash_aliases` so it can follow pointer paths (it denies out-of-cwd reads non-interactively) |
| **Gemini CLI** | `GEMINI.md` (hierarchical), also `AGENTS.md`/`CLAUDE.md` | `~/.gemini/GEMINI.md` | **Yes** (`@path`) | `GEMINI.md` line 1 = `@<shared>` + extras (or symlink). ⚠ 2026-07: Google cut the free tier for gemini-cli ("migrate to Antigravity") — dead without an API key/paid tier |
| **Antigravity / `agy`** | `GEMINI.md`/`AGENTS.md` (standalone files or `rules/` dir at each customization root; global root = `~/.gemini/`) | `~/.gemini/GEMINI.md` + `~/.gemini/AGENTS.md` | **No** (does NOT resolve GEMINI.md's `@import` line) | **symlink** `~/.gemini/AGENTS.md` → `<shared>` — coexists with GEMINI.md, no conflict (verified 2026-07-28, agy 1.1.2) |
| **Pi** | auto-discovers `AGENTS.md` and `CLAUDE.md` (cwd-upward); `--no-context-files` disables | none auto at home level | n/a | shell wrapper: `pi(){ command pi --append-system-prompt "<shared>" "$@"; }` |

## Critical gotchas

- **Claude Code never auto-reads `AGENTS.md`.** It reads `CLAUDE.md`. So the only
  way AGENTS.md reaches Claude is a `CLAUDE.md` that imports it. This is why the
  canonical-file-plus-import pattern exists.
- **`@import` is NOT portable.** Only Claude Code and Gemini honor `@`. Codex,
  Copilot, and agy do not — the AGENTS.md spec hasn't standardized imports (open
  proposals agents.md#11, #66, #135). So never split content and expect it to be
  **auto-loaded** via imports. **On-demand pointer reads DO work**, though
  (verified 2026-07-28): a slim AGENTS.md with prose pointers like
  `~/.claude/instructions/<topic>.md` — the model reads the file with its own
  tools when the task needs it. Codex ✓ (sandbox allows reads anywhere), agy ✓,
  Pi ✓ (unrestricted reads), Copilot ✓ with the `--add-dir` alias above. Keep
  pointers as plain backticked paths, never `@`-prefixed at line start (Claude/
  Gemini would inline them at load time). The portable way to scope *auto-loaded*
  content remains **nested `AGENTS.md`** (directory-scoped), which
  Codex/Copilot/Cursor all honor.
- **Import directive must be line 1, no indentation**, or the tool treats it as
  literal text instead of an import.
- **Copilot reads `CLAUDE.md`/`GEMINI.md` only at repo root**, and globally only
  `~/.copilot/copilot-instructions.md` — so nothing in `CLAUDE.md` is truly
  "Claude-private."

## `agy` (Antigravity) — probe RESOLVED 2026-07-28 (agy 1.1.2)

Binary strings + live probes established: agy's rules system reads standalone
`GEMINI.md` / `AGENTS.md` files (or a `rules/` dir) at each customization root;
the **global root is `~/.gemini/`**. It loaded `~/.gemini/GEMINI.md` but did
**not** resolve that file's `@import` line — so before wiring, the shared house
rules never reached it. Fix: `ln -s ~/.config/agents/AGENTS.md ~/.gemini/AGENTS.md`.
Verified: with both files present it loads both (no "conflicting global rules"
error) and correctly answered a Sol-restriction question from the shared file.
It can also read `~/.claude/instructions/*` on demand from a project dir with
no permission prompt. Re-probe recipe if a new agy version changes behavior:
ask `agy -p` (1) whether the house-rules heading is in context, (2) to read an
instructions file and quote its first heading.

## Sources

- Copilot AGENTS.md support: https://github.blog/changelog/2025-08-28-copilot-coding-agent-now-supports-agents-md-custom-instructions/
- Copilot CLI custom instructions (`~/.copilot/copilot-instructions.md`): https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions
- Claude Code reads CLAUDE.md, not AGENTS.md (use `@import`): https://bestagent.dev/claude-md-vs-agents-md-2026/
- Codex `~/.codex/AGENTS.md` hierarchy: https://www.codegateway.dev/en/blog/agents-md-playbook-2026
- Gemini CLI `~/.gemini/GEMINI.md` + `@import`: https://github.com/google-gemini/gemini-cli
- agents.md import proposal: https://github.com/agentsmd/agents.md/issues/11
