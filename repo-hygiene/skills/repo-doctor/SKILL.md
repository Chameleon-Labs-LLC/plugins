---
name: repo-doctor
description: Audit a repo's agent-facing documentation layer and dispatch the right fix — instruction-file topology (AGENTS.md canonical? CLAUDE.md/GEMINI.md @import it?), always-loaded token cost, CodeMap freshness and line-number accuracy, broken pointers, changelog-vs-code version drift. Read-only; reports first, then offers remediation in dependency order. Use when asked to "check this repo", "audit the agent docs", "is my CLAUDE.md/AGENTS.md set up right", "are the docs stale", "check the code map", "health check this project", or when onboarding an unfamiliar repo and you want to know whether its docs can be trusted. Also on /repo-doctor. NOT for code review, tests, dependency or security audits.
---

# Repo Doctor

Diagnose the docs an agent actually reads. This skill is the **triage** layer
over four remediation skills — it decides *what* is wrong and *in what order*
to fix it; the other skills do the fixing.

| Axis | Question | Owner |
|------|----------|-------|
| Topology | Is `AGENTS.md` canonical, with `CLAUDE.md`/`GEMINI.md` as `@import` pointers? | `unify-agents-md` |
| Content | Is the always-loaded context rightsized? | `claude-md-optimizer` |
| Accuracy | Is `Docs/CodeMap.md` fresh and are its line numbers real? | `update-code-map` |
| Currency | Do the changelog and the code agree on the version? | `version-manager` |

## Order matters

**Topology → content → accuracy → currency.** Never reorder these:

- Rightsizing a `CLAUDE.md` that is about to be *replaced* by an `@import`
  pointer throws the work away. Unify first.
- A CodeMap rebuild is the most expensive step (many agents, real tokens). Run
  it after the cheap structural fixes, and only once.

If the repo has `CLAUDE.md` but no `AGENTS.md`, say so plainly and offer
`/unify-agents-md` **before** anything else — non-Claude CLIs (Codex, Copilot,
agy, Pi) read `AGENTS.md` and are currently running with no repo rules at all.

## Process

### 1. Measure (never guess)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/repo-doctor/audit.py --repo <abs-path>
```

Add `--json` for machine-readable output, `--sample N` to change how many
CodeMap claims get spot-checked (default 40), `--seed N` for reproducibility.
Exit code 0 = clean, 1 = findings.

The script is the source of truth for everything measurable: file sizes,
`@import` wiring, CodeMap age, sampled line-number accuracy, broken pointers,
version drift. **Do not estimate any of these yourself.**

### 2. Read what the script cannot

The script measures shape, not substance. Skim the instruction files and judge:

- Content the model can already observe (folder trees, tech stack, standard
  build commands) — that is deletable weight.
- Absolute bans that a Claude 5 model could reason through, versus genuine
  hard rules (credentials, destructive operations, compliance) that stay verbatim.
- Repo-specific **gotchas** — the non-obvious traps. These are the highest-value
  content and are usually *under*-represented. If the file has none, that is a
  finding worth reporting even though no automated check catches it.

### 3. Report, then offer

Lead with the verdict and the single most consequential finding. Present the
recommended order and ask which to run — do not start a CodeMap rebuild
unprompted; it is expensive.

When the user agrees, invoke the remediation skills **one at a time**, in order,
and re-run `audit.py` at the end to confirm the findings actually cleared.

## Interpreting results

- **`accuracy=unmeasurable`** — the CodeMap exists but is not in the
  `update-code-map` format (no `**Path**:` blocks or `file.py:NNN` claims), so
  claims could not be extracted. Report it as "cannot verify", never as "fine".
- **Accuracy below 90%** with a *recent* timestamp is worse than a stale map:
  it means the map was written from estimates rather than an extractor.
- **Token caps** (soft 2,500 / hard 5,000) are guidance, not law. A repo with
  genuinely unusual constraints can justify more — say so rather than cutting
  content that earns its place.
- A repo that is a **config mirror, asset store, or docs-only** project may
  legitimately have no `AGENTS.md` and no CodeMap. Use judgment; do not file
  findings against a repo that has no code to navigate.

## Scope

Covers only the agent-facing documentation layer. It does **not** review code,
run tests, or audit dependencies or security — say so if asked to conflate them,
and point at `/code-review`, `/security-review`, or `scan-source` instead.
