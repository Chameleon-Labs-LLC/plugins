---
name: version-manager
description: Use when bumping a version, cutting a release, or when a CHANGELOG is stale, missing versions, or disagrees with the code — and before opening any PR, per the versioning rule in AGENTS.md. Also on /version-manager [check|backfill|release], or when the user says "bump the version", "cut a release", "the changelog is old". Auto-detects version locations in any stack (pyproject, package.json, VERSION file, module constants, README display) — no per-repo config.
---

# Version Manager

Standardized version bumping and changelog currency across every project.
Auto-detects where a repository keeps its version, reconciles that against git
history and the changelog, and cuts releases that update **every** location at
once.

- **Tool:** `${CLAUDE_PLUGIN_ROOT}/skills/version-manager/version_tool.py` (stdlib only, no install)
- **Design:** `.claude_code/Docs/plans/2026-07-25-version-manager-design.md`
- **Scope:** one repository at a time — there is deliberately no cross-repo sweep
- **Enforced by:** the versioning rule in `~/.config/agents/AGENTS.md`, which every
  CLI imports — so Codex, Copilot, Gemini and Pi are bound by it too

## Verbs

Run with `python3 ${CLAUDE_PLUGIN_ROOT}/skills/version-manager/version_tool.py --repo <ABS_PATH> <verb>`.
`--repo` defaults to the current directory; always pass an absolute path.

| Verb | Writes? | Use it for |
|------|---------|-----------|
| `check` | never | Report drift: location disagreement, versions missing from the changelog, wrong dates, commits since last tag |
| `backfill --apply` | yes | **One-time per repo.** Reconstruct tags from history, fill changelog gaps, advance a placeholder version |
| `release <major\|minor\|patch> --apply` | yes | Bump every location, write the changelog section, commit, tag |

`backfill` and `release` are **dry runs by default** — they print the plan and
write nothing until you add `--apply`. Always show the user the dry run first.

## Standard workflow

**Before opening a PR** (this is the house rule in `~/.config/agents/AGENTS.md`):

```bash
T=${CLAUDE_PLUGIN_ROOT}/skills/version-manager/version_tool.py
python3 $T --repo /abs/path/to/repo release minor            # dry run: read the draft
python3 $T --repo /abs/path/to/repo release minor --notes /tmp/notes.md --apply
```

Pick the level from what actually shipped — `major` for a breaking change,
`minor` for a feature, `patch` for fixes and docs. The dry run prints the level
the commits suggest; it never picks silently.

**Curate the changelog body.** The generated draft is raw commit subjects. Rewrite
it into prose in a file and pass `--notes FILE`. This is the deliberate manual
step — generated draft, curated release.

**Adopting the tool in a repo for the first time:**

```bash
python3 $T --repo /abs/path check                    # see what is wrong
python3 $T --repo /abs/path backfill                 # dry run
python3 $T --repo /abs/path backfill --apply         # tags + changelog gaps
python3 $T --repo /abs/path backfill --apply --fix-dates   # only if dates are wrong
```

## What it detects (no manifest)

First match wins as **canonical**; everything else becomes a **mirror** synced on
release.

1. An explicit pointer comment — `The actual version is managed in src/version.py`,
   or `# See src/version.py for centralized version management`
2. `pyproject.toml` `version = `, or `package.json` `"version":`
3. Module constants — `**/version.py`, `*/constants.py` `VERSION =`,
   `<pkg>/__init__.py` `__version__ =`
4. A bare `VERSION` file
5. Nothing found → one is created, seeded from the ledger derived from git
   history, **never** a hardcoded `0.1.0`

`README.md`'s `**Version X.Y.Z**` display is always a mirror, never canonical.
An empty `{}` `package.json` is a stub and is skipped, not filled.

## Gotchas

- **`release` refuses on a dirty tree, an existing tag, or disagreeing version
  locations.** A Python service currently disagrees (`src/version.py` 0.9.0 vs
  `VERSION`/`pyproject.toml` 0.2.0) — resolve by hand once, then it stays fixed.
- **Backfill never invents history.** Versions in the changelog with no locatable
  bump commit are reported and left untagged rather than tagged at a guess.
  Repos with a real bump record get nothing inserted between real releases.
- **Placeholder detection:** a version set once and never moved (a busy web app'
  `0.1.0`, a small web app, a personal site) is treated as a default, not a
  record — the series is synthesized from PR/feature boundaries, never per commit.
  Above 60 boundaries they are grouped by calendar month so a busy repo does not
  land on something like `0.348.0`.
- **Dates are only corrected with `--fix-dates`,** because changelog entries are
  hand-written prose. Gap-filling is additive and needs no such flag.
- Writes are surgical regex substitutions — `package.json` key order and
  indentation survive a bump.

## Tests

```bash
source /path/to/your/venv/bin/activate
python3 -m pytest ${CLAUDE_PLUGIN_ROOT}/skills/version-manager/tests/ -q
```

Each fixture reproduces a defect that is actually present in one of the user's
repositories, so a failure means a real repo would be mishandled.
