---
name: version-manager
description: Use when bumping a version, cutting a release, or when a CHANGELOG is stale, missing versions, or disagrees with the code — and before opening any PR. Also on /version-manager [check|backfill|release], or when the user says "bump the version", "cut a release", "the changelog is old". Auto-detects version locations in any stack (pyproject, package.json, VERSION file, module constants, README display) — no per-repo config.
---

# Version Manager

Standardized version bumping and changelog currency across every project.
Auto-detects where a repository keeps its version, reconciles that against git
history and the changelog, and cuts releases that update **every** location at
once.

- **Tool:** `${CLAUDE_PLUGIN_ROOT}/skills/version-manager/version_tool.py` (stdlib only, no install)
- **Scope:** one repository at a time — there is deliberately no cross-repo sweep
- **Convention:** the version bump and changelog entry travel in the same commit,
  before every PR or release

## Verbs

Run with `"$PY" "${CLAUDE_PLUGIN_ROOT}/skills/version-manager/version_tool.py" --repo <ABS_PATH> <verb>`,
where `PY=python3; "$PY" -c '' 2>/dev/null || PY=python` runs first in the same
Bash call. That line picks `python3` on Linux/macOS and falls back to `python` on
native Windows, where `python3` is often missing or the Microsoft Store stub.
`--repo` defaults to the current directory; always pass an absolute path.

| Verb | Writes? | Use it for |
|------|---------|-----------|
| `check` | never | Report drift: location disagreement, versions missing from the changelog, wrong dates, commits since last tag |
| `backfill --apply` | yes | **One-time per repo.** Reconstruct tags from history, fill changelog gaps, advance a placeholder version |
| `release <major\|minor\|patch> --apply` | yes | Bump every location, write the changelog section, commit, tag |

`backfill` and `release` are **dry runs by default** — they print the plan and
write nothing until you add `--apply`. Always show the user the dry run first.

## Standard workflow

**Before opening a PR:**

```bash
PY=python3; "$PY" -c '' 2>/dev/null || PY=python
T="${CLAUDE_PLUGIN_ROOT}/skills/version-manager/version_tool.py"
"$PY" "$T" --repo /abs/path/to/repo release minor            # dry run: read the draft
"$PY" "$T" --repo /abs/path/to/repo release minor --notes <scratchpad>/notes.md --apply
```

Pick the level from what actually shipped — `major` for a breaking change,
`minor` for a feature, `patch` for fixes and docs. The dry run prints the level
the commits suggest; it never picks silently.

**Curate the changelog body.** The generated draft is raw commit subjects. Rewrite
it into prose in a file and pass `--notes FILE`. On native Windows give `FILE`
as a Windows path (`C:/...`), not `/tmp/...`: a file written with the Write tool
at `/tmp/...` lands in `<drive>:\tmp`, while Git Bash maps the same `/tmp`
argument to its own temp dir, so the tool would read a different file. This is the deliberate manual
step — generated draft, curated release.

**Adopting the tool in a repo for the first time:**

```bash
"$PY" "$T" --repo /abs/path check                    # see what is wrong
"$PY" "$T" --repo /abs/path backfill                 # dry run
"$PY" "$T" --repo /abs/path backfill --apply         # tags + changelog gaps
"$PY" "$T" --repo /abs/path backfill --apply --fix-dates   # only if dates are wrong
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

**Claude Code plugin marketplaces** (`.claude-plugin/marketplace.json`):

- **One plugin:** that plugin entry's `version` is canonical. `metadata.version`
  is the catalog's own series and is left alone.
- **Several plugins with `metadata.version`:** `metadata.version` is canonical.
  It drives the changelog and the `v*` tag. Each plugin keeps its own version.
  Bump plugins in the same release with repeatable `--plugin NAME[=LEVEL]`
  (LEVEL defaults to the release level). The flag updates the marketplace entry
  and `<plugin>/.claude-plugin/plugin.json` together. It refuses when the two
  disagree, when a plugin has an external source, or when a name is unknown.
  The dry run lists each plugin that has commits since its `plugin.json` last
  changed but is not named:

  ```bash
  "$PY" "$T" --repo /abs/path release minor \
      --plugin scan-source --plugin docs-toolkit=patch --notes <scratchpad>/notes.md
  ```

The changelog keeps its existing heading style: Keep a Changelog
`## [1.2.0] - date`, or unbracketed `## 1.2.0 — date`.

## Gotchas

- **`release` refuses on a dirty tree, an existing tag, or disagreeing version
  locations.** A Python service currently disagrees (`src/version.py` 0.9.0 vs
  `VERSION`/`pyproject.toml` 0.2.0) — resolve by hand once, then it stays fixed.
- **Backfill never invents history.** Versions in the changelog with no locatable
  bump commit are reported and left untagged rather than tagged at a guess.
  Repos with a real bump record get nothing inserted between real releases.
- **Placeholder detection:** a version set once and never moved (a project
  stuck at `0.1.0` for its whole history, a small web app, a personal site) is treated as a default, not a
  record — the series is synthesized from PR/feature boundaries, never per commit.
  Above 60 boundaries they are grouped by calendar month so a busy repo does not
  land on something like `0.348.0`.
- **Dates are only corrected with `--fix-dates`,** because changelog entries are
  hand-written prose. Gap-filling is additive and needs no such flag.
- Writes are surgical regex substitutions — `package.json` key order and
  indentation survive a bump.

## Tests

```bash
PY=python3; "$PY" -c '' 2>/dev/null || PY=python   # any Python with pytest installed
"$PY" -m pytest "${CLAUDE_PLUGIN_ROOT}/skills/version-manager/tests/" -q
```

Each fixture reproduces a defect that is actually present in one of the user's
repositories, so a failure means a real repo would be mishandled.
