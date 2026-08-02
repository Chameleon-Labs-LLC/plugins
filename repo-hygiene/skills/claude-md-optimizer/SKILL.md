---
name: claude-md-optimizer
description: Audit and rightsize CLAUDE.md / AGENTS.md and skills per Anthropic's Claude 5 context-engineering guidance (Thariq, 2026-07-24) — cut rules the model can judge, extract detail to on-demand files/skills, dedupe layers, and verify. Use when users mention slow /resume, CLAUDE.md being too long, reducing token usage, context optimization, rightsizing instructions, auditing CLAUDE.md, or following up on /doctor output. Triggers on "optimize CLAUDE.md", "rightsize my instructions", "my resume is slow", "CLAUDE.md is too big", "audit my CLAUDE.md", "apply the context-engineering rules", "slim down my instructions".
---

# CLAUDE.md Optimizer

Rightsize always-loaded context. Grounded in Anthropic's Claude 5
context-engineering guidance (Thariq, 2026-07-24: ~80% of Claude Code's system
prompt was removed for Opus 5 / Fable 5 with no measurable eval loss): modern
models need **judgment and gotchas, not rulebooks** — the instruction file is a
prompt, not documentation.

## Where content belongs (the layer model)

| Layer | Carries | Never carries |
|-------|---------|---------------|
| System prompt | Product/harness shape (harness builders only) | A second CLAUDE.md |
| `CLAUDE.md` / `AGENTS.md` | Purpose paragraph, repo-specific gotchas, hard constraints, pointers | Folder trees, tech-stack descriptions, playbooks, generic sermons |
| Skills | Multi-step team practices: review checklists, release rituals, domain vocab (metadata ~80 tokens at startup; body loads on trigger) | One-line preferences |
| Tool definitions | Constraints as schema: enums, typed params, validation errors | — |
| References (`@`-mention / pointer files) | Rich material: code, test suites, HTML mockups, rubrics, long tables | — |
| Auto-memory | Session-derived facts (the `#`-hotkey diary habit is deprecated) | Standing rules |

## The six shifts (audit rubric)

1. **Rules → judgment** — delete absolute bans unless they guard a documented
   failure mode the model can't reason through; rewrite the rest as adaptive
   one-liners ("match the surrounding idiom").
2. **Examples → interface design** — replace multi-page few-shots with schemas,
   enums, and validation errors where the content describes tools/formats.
3. **Upfront → progressive disclosure** — move playbooks and procedures into
   skills or `instructions/` files loaded on demand.
4. **Repetition → single source** — one canonical home per rule; everything
   else points at it.
5. **Memory dump → auto-memory** — session-specific notes don't belong in
   CLAUDE.md at all.
6. **Simple specs → rich references** — point at real artifacts (tests, mockups,
   rubrics) instead of paraphrasing them in prose.

Full rubric, keep/cut tables, and token math: `references/extraction-checklist.md`.

## Workflow

### 0. Back up and measure

```bash
mkdir -p ~/backups/claude-md-opt-$(date +%Y%m%d-%H%M) && cp -a <targets> ~/backups/claude-md-opt-*/
wc -c -w ~/.claude/CLAUDE.md ~/.config/agents/AGENTS.md ./CLAUDE.md ./AGENTS.md 2>/dev/null
```

Tokens ≈ bytes/4. Record the baseline; report savings at the end.

### 1. Classification pass (present BEFORE editing)

Classify every instruction; show the user the table and get a go-ahead:

- **(a) HARD RULE** — security/money/data-loss (credentials, destructive git,
  prod DB, compliance). Keep **verbatim**. Judgment does not replace these.
- **(b) JUDGMENT REWRITE** — procedure a Claude 5 model can infer from intent.
  Compress to one adaptive sentence (shift 1).
- **(c) MOVE** — situational detail → a skill (if it's a *procedure* with a
  trigger) or an `instructions/` file (if it's *reference*), pointer left behind
  (shift 3).
- **(d) DUPLICATE** — also stated in another layer. Delete; name the canonical
  home (shift 4).

### 2. Conflict pass

Grep for rules that contradict or duplicate each other across CLAUDE.md,
AGENTS.md, skills, and tool docs. Delete the losers — conflicting instructions
are worse than missing ones.

### 3. Obvious pass

Delete anything Claude can observe from the repo: language/framework (it reads
`package.json`/`pyproject.toml`), folder structure, standard build commands
already in config files, generic safety the model has by default ("ask before
deleting").

### 4. Example & interface pass

Where the file teaches a format or tool by example, move the constraint into
the tool/schema (enums, typed params) or point at a real artifact (a passing
test, a golden file) instead of prose few-shots (shifts 2, 6).

### 5. Extraction pass

For each (c) item: skills get a `description` written **for the model** —
when to trigger, not what it is. Reference detail goes to
`~/.claude/instructions/<topic>.md` (global) or the project's docs dir, with a
1–2 line pointer left behind. Cross-CLI caveat: if the file is shared with
non-Claude CLIs (Codex/Copilot/agy/Pi via symlinks or aliases), pointers must
be plain backticked paths — never `@`-prefixed lines (Claude/Gemini inline
those at load time), never skill-only references (other CLIs can't invoke
skills; name the script/file instead).

### 6. Memory pass

Move `#`-hotkey diary accumulation out: delete stale session notes; let
auto-memory own session-derived facts. CLAUDE.md keeps only standing rules.

### 7. Doctor pass

Have the user run `/doctor` (or `claude doctor`) — it diagnoses oversized
skills and CLAUDE.md and suggests simplifications. Reconcile its suggestions
with the classification table: accept cuts you both agree on; keep (a)-class
rules even if flagged.

### 8. Verify

```bash
wc -c -w <files>                        # report before/after tokens
# every pointer target must exist:
grep -o '~/[A-Za-z./_-]*\.md' <file> | sort -u | while read p; do
  f="${p/#\~/$HOME}"; [ -f "$f" ] || echo "MISSING $p"; done
```

- Smoke-test: from a project dir, ask a cheap agent (or a second CLI if the
  file is shared) a question whose answer lives behind a pointer — it should
  state the rule and follow the pointer.
- **Eval pass:** if the team has private coding evals, re-run them after the
  cuts — Anthropic's "no measurable loss" was verified against evals, not vibes.

## When NOT to apply

- Regulated/audited environments: compliance rules stay written even if the
  model "knows" them — that's (a)-class, keep verbatim.
- No eval set and a working setup: cut conservatively; the 80% figure came
  from teams that could measure regressions.
- Claude 4-era pinned workflows where migration cost exceeds the token savings.

## Target shape

A slim always-loaded file (~1,500–2,500 tokens): purpose paragraph → hard
rules verbatim → one-line judgment guidance → pointers. Detail lives in
skills, `instructions/`, tool schemas, and referenced artifacts. (Reducing an
8k-token CLAUDE.md to 1.5k saves ~6.5k tokens per request — over a million
tokens across a 200-turn session.)
