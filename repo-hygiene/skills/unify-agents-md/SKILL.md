---
name: unify-agents-md
description: Restructure a project's (or the whole machine's) AI-agent instruction files so AGENTS.md is the single canonical guide that every coding CLI follows — Claude Code, Codex, Copilot, Antigravity/agy, Gemini, Pi — with CLAUDE.md and GEMINI.md reduced to thin @import pointers plus tool-specific extras. Use this whenever the user wants non-Claude agents to behave the same as Claude, mentions consolidating or unifying AGENTS.md / CLAUDE.md / GEMINI.md, says things like "make all my agents follow the same rules", "share my house rules across CLIs", "make Codex/Copilot/Gemini work like Claude", or wants to clean up duplicated/​drifting instruction files. Works on the LOCAL project by default, then asks whether to also do the GLOBAL ~/.claude machine-wide setup. Trigger it even if the user doesn't name the skill.
---

# unify-agents-md

Make **one** instruction file — `AGENTS.md` — the source of truth that every AI
coding assistant reads, so Codex, Copilot, Gemini, Antigravity, and Pi all behave
like Claude does. `CLAUDE.md`/`GEMINI.md` shrink to a one-line `@import` of
`AGENTS.md` plus whatever is genuinely tool-specific.

## The mental model

- **AGENTS.md is canonical and tool-agnostic.** All the *conventions* — how to
  code here, project structure, build/test, security rules, output formatting,
  issue workflow — live here so every agent follows the same rules. If a
  convention is only in `CLAUDE.md`, the other agents won't follow it; that's the
  whole problem this fixes.
- **CLAUDE.md / GEMINI.md hold only tool-specifics.** Which *skill/agent/command*
  implements a convention (e.g. "use the `code-reviewer` agent"), plus the
  `@import` line that pulls in AGENTS.md. The convention itself goes in AGENTS.md;
  the mechanism stays here.
- **Coding vs admin is the boundary, not "marketing vs everything."** Coding and
  non-admin work get full latitude for every agent. Admin/infra (cloud mutations,
  host/EC2 ops, live billing, prod DB, secrets) stays hands-off — but the real
  enforcement is **credential-gating**: an agent that can't see the keys can't do
  the action. So AGENTS.md doesn't need heavy "you may not" walls; it states the
  coding conventions and hands admin off. Keep admin *runbooks* in CLAUDE.md
  (Claude/the operator runs them), not in the shared file.

Read `references/tool-matrix.md` for the verified per-tool paths and — critically —
which tools support `@import` (only Claude + Gemini) versus need a symlink (Codex,
Copilot). That table drives every wiring decision below.

## Two scopes

1. **Local project (default).** Run this automatically on the current repo.
2. **Global machine (ask after local).** Only after local is done, ask the user
   whether to also wire the home-level setup so every CLI shares their global
   house rules. Never jump straight to global.

---

## Part 1 — Local project (do this first, by default)

1. **Locate the project root** (git root if available, else cwd). Operate there.

2. **Inventory** existing instruction files: `AGENTS.md`, `CLAUDE.md`,
   `GEMINI.md`, `.github/copilot-instructions.md`, and any nested `AGENTS.md`.

3. **Back up every file you'll edit**, timestamped and non-clobbering:
   `cp -n <file> <file>.bak-$(date '+%Y%m%d-%H%M%S')`. Never overwrite an existing
   backup. (Get the real date — run `date`, don't guess.)

4. **Bucket the content — lose nothing:**
   - *Shared coding conventions* (overview, structure, build/test, code style,
     security, output formatting, issue/label workflow, review principles, the
     systemic-root-cause habit, "verify a subagent's file actually exists", etc.)
     → **AGENTS.md**, phrased tool-agnostically. For each behavior currently
     written as a Claude mechanism ("use the X skill/agent"), put the *convention*
     in AGENTS.md ("when asked to review, do a structured review") and leave the
     *mechanism* in CLAUDE.md.
   - *Admin/infra runbooks* (deploy commands, env-var management, billing CLI,
     cloud/host specifics) → stay in **CLAUDE.md** under a clearly admin section.
   - *Tool-specific mechanisms* (skill/agent/command names, the `<env>` date
     source, slash-command triggers) → stay in **CLAUDE.md**.

5. **Make AGENTS.md self-contained and well-sectioned.** Do **not** split it into
   referenced topic files and expect every tool to load them — `@import` isn't
   portable (see the matrix). The portable way to scope content is a **nested
   `AGENTS.md`** in a subdirectory whose conventions genuinely differ (e.g. a
   Python `agents/` fleet inside a Next.js repo). Use that only when a concern
   maps cleanly to a directory.

6. **Rewrite the pointer files:**
   - `CLAUDE.md`: **line 1** = `@AGENTS.md` (no indentation, or Claude treats it
     as literal text), then a short "Claude Code specifics" section with the
     tool-specific bits + admin runbooks.
   - `GEMINI.md`: line 1 = `@AGENTS.md` + a tagline / one-line summary (Gemini
     honors `@`). If there's nothing Gemini-specific, a thin pointer is fine.
   - Copilot/Codex need no project pointer — they read root `AGENTS.md` directly.

7. **Verify:** confirm each `@import` is on line 1 with no leading whitespace
   (`head -1 CLAUDE.md | cat -A` → should show `@AGENTS.md$`). Confirm no content
   was dropped (diff the backup against the union of new files if unsure).

8. **Leave changes uncommitted for review** in a git repo (or, if the user asked,
   commit on a branch). Summarize what moved where, and the backups created.

Then **stop and report**, and move to Part 2's question.

---

## Part 2 — Global machine setup (only after asking)

After local completes, ask plainly, e.g.: *"Local project done. Want me to also
do the global machine-wide setup so Codex, Copilot, Gemini, Pi, etc. all share
your global house rules?"* Proceed only on yes.

1. **Detect installed tools:** `for c in claude codex copilot gemini agy pi; do
   command -v "$c"; done`. Only wire what's present.

2. **Create the canonical shared file** `~/.config/agents/AGENTS.md`
   (`mkdir -p ~/.config/agents`). Extract the **tool-agnostic** house rules from
   `~/.claude/CLAUDE.md` into it, generalized so any CLI can follow them
   (drop Claude-only tool names; keep the conventions). This mirrors Part 1 one
   level up.

3. **Back up before editing any existing file**, timestamped + non-clobbering
   (`cp -n`). Verify a fresh backup equals the current live file so it's a valid
   rollback.

4. **Wire each present tool** (full detail + the symlink-vs-import reasoning is in
   `references/tool-matrix.md`). Only create a symlink when the target is absent
   (guard with `[ -e ] || [ -L ]`); never clobber:
   - **Claude:** `~/.claude/CLAUDE.md` → line 1 `@/home/<user>/.config/agents/AGENTS.md`
     + Claude-only extras. (Use the absolute path; `~` may not expand in imports.)
   - **Codex:** `ln -s ~/.config/agents/AGENTS.md ~/.codex/AGENTS.md` (no import —
     it concatenates).
   - **Copilot:** `ln -s ~/.config/agents/AGENTS.md ~/.copilot/copilot-instructions.md`.
   - **Gemini:** `~/.gemini/GEMINI.md` → line 1 `@<shared>` + extras (or symlink
     if nothing Gemini-specific).
   - **Pi:** add a wrapper to `~/.bash_aliases` (or the user's rc):
     `pi(){ command pi --append-system-prompt "$HOME/.config/agents/AGENTS.md" "$@"; }`
     — Pi already auto-reads project `AGENTS.md`/`CLAUDE.md`; this adds the global
     layer. Syntax-check with `bash -n`.
   - **agy / Antigravity:** **probe first** (see the matrix). Don't guess its
     wiring; confirm how it loads instructions, then wire or report findings.

5. **Report** the wiring table, the backups, and that Claude's own change takes
   effect on the **next** session (the current session already loaded the old
   global file). Note rollback commands.

---

## Guardrails (the why)

- **No content loss.** You're re-bucketing, not deleting. When in doubt, keep it.
- **Backups always, never clobbered.** Timestamp them; the user may have prior
  `.bak` files you must not touch.
- **Additive-first.** Symlinks/aliases for tools that had no global instructions
  are pure upside and fully reversible; do those before editing existing files.
- **Don't over-restrict.** Credential-gating is the real admin boundary, so
  AGENTS.md should read as "here's how we code," not a wall of prohibitions.
- **Self-contained AGENTS.md.** Topic-file `@import` isn't portable; nested
  AGENTS.md is the only portable split.
- **High-blast-radius edits** (the global `~/.claude/CLAUDE.md`) deserve a visible
  backup and a clear summary; offer the rollback command.
