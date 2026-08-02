---
name: update-code-map
description: Use when users ask to update or create the code map / CodeMap.md, refresh documentation line numbers, document new files, or when Docs/CodeMap.md is missing or older than 7 days. Triggers on "update the code map", "refresh CodeMap", "the code map is outdated", "update line numbers in documentation".
---

# Update Code Map

Create or update `Docs/CodeMap.md`, the codebase navigation guide.

## Core Principle

**Line numbers come from a deterministic extractor; agents write prose; a
separate verify pass checks the result.** An LLM must never estimate a line
number — estimated numbers drift by hundreds of lines and nothing catches it.

## Process

### 1. Scout (inline, no agents)

```bash
date +"%Y-%m-%d %H:%M:%S"                      # real timestamp — never guess
head -3 Docs/CodeMap.md                        # last-updated, if it exists
git log --since="<last-updated>" --name-only --pretty=format: | sort -u  # changed files
```

Exclude vendored/generated trees everywhere: `.venv*`, `node_modules`,
`__pycache__`, `.repo_cache`, `bin`, `obj`, `dist`, `build`, `.git`.

### 2. Build the symbol inventory (ground truth)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/update-code-map/references/extract_symbols.py \
    --root . --out <scratchpad>/inventory.json
```

Python is parsed with `ast` (exact lines + end lines + signatures); JS/TS/C#/XAML
fall back to regex scanning. Every line number in the CodeMap is copied from
this file. Spot-check two entries with `sed -n '<line>p' <file>` before trusting
a fresh run on a new language.

### 3. Pick the execution mode

| Condition | Mode |
|---|---|
| < ~30 source files AND < ~10k source lines | **SINGLE-AGENT** — skip the workflow; document directly from the inventory, following the spec |
| CodeMap exists and < ~25% of source files changed since last update | **INCREMENTAL** — regenerate only the module groups containing changed files; splice into the existing map |
| No CodeMap, placeholder line numbers found, or widespread changes | **FULL** — regenerate all sections |

### 4. Orchestrate with the Workflow tool (INCREMENTAL / FULL)

Group files into module groups of ≤ ~8k source lines (a file > 5k lines gets
its own group; group by package/subsystem, not alphabetically). Then adapt the
script in `references/workflow-template.md`:

- **Document phase** — `pipeline()` over groups, one agent each; agents read
  the inventory for line numbers and the source for prose only.
- **Dependencies phase** — one agent, after a barrier (it needs all sections).
- **Verify phase** — an independent spot-checker per section runs
  `sed -n '<line>p' <file>` against ≥12 sampled claims and reports mismatches.

Fix reported mismatches from the inventory; don't re-run the workflow.

### 5. Assemble mechanically

Follow the required structure in the base spec —
`${CLAUDE_PLUGIN_ROOT}/skills/update-code-map/references/CLAUDE_CodeMap.md` — and the language guidelines in
`references/` (`python-guidelines.md`, `csharp-guidelines.md`,
`javascript-guidelines.md`, `xaml-guidelines.md`).

- Timestamp: `*Last Updated: YYYY-MM-DD HH:MM:SS*` from `date`, not memory.
- ASCII diagram boxes: compute padding mathematically (max content width + 4);
  verify every line of a box has identical width with a python one-liner —
  including diagrams carried over from the previous CodeMap.
- INCREMENTAL: splice regenerated sections in place; keep untouched sections;
  update the timestamp and TOC for the whole file.
- TOC line numbers **last**, after every other edit: `grep -n "^## "` on the
  final content, fill in the numbers, verify each entry points at its heading.
  Any later content change — even removing a duplicate heading — shifts every
  number. Never leave `[ACTUAL_LINE]` placeholders.
- Final gate before installing: random-sample ~25 `file:line` claims and check
  each with `sed -n '<line>p' <file>`.

### 6. Report

Summarize: files/symbols documented, mode used, verification stats
(claims checked, mismatches found and fixed), CodeMap location and total lines.

## Red Flags — STOP

- You are about to write a line number you didn't copy from the inventory or a
  `grep -n`/`sed -n` result. **Stop — re-extract.**
- "The file barely changed, the old line numbers are probably close." Close is
  wrong. A 22k-line file drifts +3,000 lines in a few months.
- "Reading the whole 20k-line file to document it." Read selectively around
  inventory line numbers.
- Skipping the verify phase "because the inventory is deterministic." Prose
  agents still mis-copy; verification is cheap.
- Running a FULL rebuild when only a handful of files changed — that cost is
  why code maps go stale. Prefer INCREMENTAL.

## Common Mistakes

| Mistake | Fix |
|---|---|
| LLM-estimated line numbers | Copy from `inventory.json` only |
| One agent reads the whole repo | Fan out per module group via Workflow |
| Documenting `.repo_cache`/vendored clones | Use the extractor's default excludes |
| TOC written before content | Two-pass: content, then `grep -n "^## "` |
| Box borders eyeballed | Mathematical padding + width check |
| Guessed timestamp | `date +"%Y-%m-%d %H:%M:%S"` |
