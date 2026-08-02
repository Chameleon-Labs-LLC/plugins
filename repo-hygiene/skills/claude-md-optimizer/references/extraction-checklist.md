# CLAUDE.md audit rubric — keep/cut, extraction, and token math

Companion to the six shifts in SKILL.md (source: Anthropic's Claude 5
context-engineering guidance, Thariq 2026-07-24).

## Keep vs. cut

**KEEP (always loaded):**

- Purpose paragraph — one paragraph on what the repo/setup is *for*.
- Codebase-specific **gotchas** Claude cannot infer from the file structure —
  the highest-value content in the whole file.
- **Hard constraints**: security/money/data-loss rules, regulatory/compliance
  requirements (finance, healthcare, audited environments). Verbatim.
- Skill/instruction **pointers** (1–2 lines each).
- Identity/contact and small always-relevant facts.

**CUT:**

- Folder structure and tech-stack descriptions (observable from the repo).
- Standard build/tool commands already in config files.
- Generic safety sermons the model handles inherently.
- Full playbooks and multi-step procedures (→ skills).
- Style rules phrased as absolute bans (→ one adaptive line, or delete).
- Prose few-shot examples of tool/format usage (→ schemas, enums, real artifacts).
- Duplicates of rules whose canonical home is another layer.
- Session diary content accumulated via the `#` hotkey (→ auto-memory).

## Extraction decision matrix

```
Is it a hard security/money/data-loss/compliance rule?
├─ YES → keep verbatim in the core file
└─ NO → Can the model infer it from the repo or its own judgment?
         ├─ YES → delete (or one adaptive line if there's a real preference)
         └─ NO → Is it a multi-step procedure with a natural trigger?
                  ├─ YES → skill (description = when to trigger, ~80 tokens at startup)
                  └─ NO → instructions/ reference file + 1–2 line pointer
```

Old size heuristic (still useful): a section >50 lines used in <50% of
sessions is an extraction candidate; instruction blocks of ~275–8,000 tokens
are the classic skill-migration range.

## High-value extraction candidates

| Section type | Typical size | Destination |
|--------------|--------------|-------------|
| Cloud/infra runbooks | 200–400 lines | `instructions/aws-{project}.md` or an ops skill |
| API reference | 100–300 lines | `instructions/api-{service}.md` |
| DB schemas / migration procedure | 50–400 lines | skill (procedure) or reference (schema) |
| Deployment commands | 50–150 lines | skill with safety guardrails |
| Plan/template formats | 100–200 lines | `instructions/plan-templates.md` |
| Credential patterns | 50–100 lines | `instructions/credentials.md` |
| Issue/label workflow | 30–80 lines | `instructions/github-issues.md` |
| Environment/tooling detail | 30–80 lines | `instructions/environment.md` |

## Pointer format

```markdown
- Detailed {topic}: `~/.claude/instructions/{topic}.md`.
```

Brief (1–2 lines), plain backticked path, just enough context to know when to
read it. Shared-file caveats (files also read by Codex/Copilot/agy/Pi): no
`@`-prefixed lines (Claude/Gemini auto-inline them), no skill-name-only
pointers (other CLIs can't invoke skills — name the underlying script/file),
and remember Copilot needs `--add-dir` (alias) to read outside the cwd.

## Interface-over-example conversions

| Before (prose in CLAUDE.md) | After |
|---|---|
| "status must be pending, in_progress, or completed" | `enum: ["pending","in_progress","completed"]` in the tool schema |
| Three worked examples of a commit message | one-line convention + the repo's own `git log` as the exemplar |
| A pasted "good output" sample | pointer to a real golden file / passing test / HTML mockup |

## Token math (why this matters)

- Tokens ≈ bytes/4. An 8,000-token CLAUDE.md cut to 1,500 saves ~6,500 tokens
  **per request** — ~1.3M tokens over a 200-turn session.
- Skill metadata costs ~80 tokens at startup; the body loads only on trigger.
- More context ≠ better: focused inputs measurably beat full-history dumps.
- Documented upside: prompt rightsizing alone produced ~+10% on SWE-Bench-class
  evals for the Claude Code team.

## Verification checklist

- [ ] Before/after token counts reported
- [ ] Every pointer target exists on disk
- [ ] No rule now exists in two layers (grep the changed value everywhere)
- [ ] Hard (a)-class rules survived verbatim
- [ ] `/doctor` run and reconciled
- [ ] Private evals re-run (or the user explicitly waived it)
