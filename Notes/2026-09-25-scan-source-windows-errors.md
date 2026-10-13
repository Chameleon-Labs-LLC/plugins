# 2026-09-25 — scan-source errors on native Windows, and the cross-platform fix

Context: `/scan-source:scan-source <repo>` ran in native Windows Claude Code on
2026-09-24. The plugin came from the `chameleon-labs` marketplace and was
installed the same evening. The scan finished only after three manual
workarounds. The same review then found related gaps on macOS and in the other
bundled plugins. Every item below is fixed on branch `feat/cross-platform`.

## Summary

| # | Error | Severity | Cause | Fix |
|---|-------|----------|-------|-----|
| 1 | Scripts have CRLF line endings; bash cannot run them | Blocker | Windows git checkout with `core.autocrlf=true`; the repo had no `.gitattributes` | Root `.gitattributes` forces LF; CI rejects CRLF in the index |
| 2 | SKILL.md gives the wrong script path | Blocker | `${CLAUDE_PLUGIN_ROOT}/scripts` does not exist; the scripts are in `skills/scan-source/scripts/` | SKILL.md resolves `SKILL_DIR` explicitly |
| 3 | SKILL.md checks for tools in the current shell | Major | On Windows the scanners exist only in WSL; Git Bash reports all five as missing | SKILL.md Windows section; both scripts refuse to run in Git Bash and print the WSL command |
| 4 | `scan-download` fails on macOS | Blocker | `declare -A` needs bash 4; macOS ships bash 3.2 | Parallel indexed arrays |
| 5 | Semgrep layer fails on macOS | Major | GNU `timeout` is absent on macOS | `with_timeout`: `timeout` → `gtimeout` → background watchdog (exit 124) |
| 6 | Installer downloads Linux x86_64 binaries everywhere | Blocker (macOS, arm64) | Asset selectors hardcoded `linux_amd64` / `Linux-64bit` | Selects by `uname -s` / `uname -m`; checks prerequisites first |
| 7 | `repo-doctor` crashes on Windows | Blocker | Piped stdout is cp1252; the report prints `→` (`UnicodeEncodeError`) | UTF-8 stdout/stderr in `audit.py`, `version_tool.py`, `extract_symbols.py`; git output decoded as UTF-8 |
| 8 | `python3` in SKILL.md commands | Major | On Windows `python3` is often missing or the Microsoft Store stub | `PY=python3; "$PY" -c '' 2>/dev/null \|\| PY=python` |
| 9 | yt-transcript venv fails on Windows | Blocker | `bin/activate` is `Scripts/activate` there; `python3` not guaranteed | `run.sh` picks a venv whose interpreter exists for the platform and calls it directly |
| 10 | `unify-agents-md` symlinks silently copy on Windows | Major | Git Bash `ln -s` copies unless `MSYS=winsymlinks:nativestrict` | Windows symlink instructions + verification |

## Error 1 — CRLF scripts

Symptom (from `wsl.exe -e bash -lc 'bash .../scan-download <target>'`):

```
scan-download: line 20: set: pipefail: invalid option name
scan-download: line 21: $'\r': command not found
scan-download: line 25: syntax error near unexpected token `$'do\r''
```

`git ls-files --eol` in the installed marketplace clone showed `i/lf w/crlf`
for all three scripts: the index was LF, and git converted the working tree on
checkout because the system git config sets `core.autocrlf=true`.

Fix: a root `.gitattributes` with `* text=auto eol=lf`, `*.sh text eol=lf`, and
an explicit entry for the extensionless `scan-download`. Five Markdown files that
were committed with CRLF were renormalized. A new CI job fails on any `i/crlf`
entry.

Users with an old clone can run an LF copy (`tr -d '\r' < scan-download > copy`)
or set `git config --global core.autocrlf input`, which also protects
third-party plugins that ship no `.gitattributes`.

## Error 2 — wrong script path

Old SKILL.md text pointed at `${CLAUDE_PLUGIN_ROOT}/scripts`. `CLAUDE_PLUGIN_ROOT`
is the plugin root; the scripts are one level down in `skills/scan-source/`.
SKILL.md now resolves `SKILL_DIR` from, in order: the harness's "Base directory
for this skill", `${CLAUDE_PLUGIN_ROOT}/skills/scan-source`, or the directory
holding `SKILL.md`.

## Error 3 — tool check in the wrong shell

On Windows the Bash tool is Git Bash, where the WSL-installed scanners are
invisible. SKILL.md now says to run everything through
`wsl.exe -e bash -lc '...'` with `/mnt/<drive>/...` paths. As a backstop,
`scan-download` and `install-security-scanners.sh` detect `MINGW*/MSYS*/CYGWIN*`
and exit 2 with the WSL command, instead of reporting every tool missing.

## macOS and the other plugins

- **scan-download** now runs under `/bin/bash` 3.2 with no GNU coreutils. The
  CI `shell-scripts` job runs a stub-scanner smoke test on `macos-latest`, with
  and without `timeout` on `PATH`.
- **install-security-scanners.sh** selects `osv-scanner_<os>_<arch>` and
  `trivy_*_<Linux|macOS>-<64bit|ARM64>.tar.gz`, verified against the current
  release asset lists. It lists missing prerequisites with the `brew`/`apt`
  command, and warns when `~/.local/bin` is not on `PATH`.
- **docs-toolkit / repo-hygiene** Python tools force UTF-8 output. The
  SKILL.md commands choose `python3` or `python` at run time and quote
  `${CLAUDE_PLUGIN_ROOT}` (paths with spaces). version-manager's `--notes` example
  no longer uses `/tmp`, which Git Bash and native Windows Python resolve to
  different directories.
- **yt-transcript** `run.sh` works in Git Bash on Windows (`.venv` /
  `.venv_windows` with `Scripts/python.exe`, bootstrapped with `py -3`), keeps
  `.venv_linux` for Linux/WSL so both can share one clone, and sets
  `PYTHONUTF8=1`.

## version-manager and multi-plugin marketplaces

Bumping this repo exposed one more gap: `version_tool.py` skipped any
marketplace with more than one plugin, so it found no version to bump. It now
treats `metadata.version` as the repo version in that case. The new
`release <level> --plugin NAME[=LEVEL]` flag bumps each named plugin's
marketplace entry and `plugin.json` in the same release commit. The dry run
names any plugin that changed since its last bump but was not named. The
changelog keeps its existing heading style (`## 0.3.0 — date` here). Eight new
tests cover it.

## Verification

- Native Windows (Git Bash): `audit.py` and `version_tool.py` run through a
  pipe without errors; `run.sh` bootstraps a fresh `.venv` with `py -3` and runs
  against an existing `.venv_windows`; both scan-source scripts exit 2 with the
  WSL hint; the version-manager suite (34 tests before the marketplace work)
  passes.
- WSL (bash 5.2): `tests/smoke-scan-download.sh` passes with and without
  `timeout`; `run.sh` uses the existing `.venv_linux`; the full version-manager
  suite (42 tests) passes.
- macOS: covered by the CI matrix (`shell-scripts` on `macos-latest`,
  `cross-platform-python` on ubuntu/macos/windows). Not run on a local Mac.

## Remaining actions

1. After merge, refresh installed copies: `/plugin marketplace update
   chameleon-labs`, then update each plugin. Confirm the cached `scan-download`
   has no CRLF: `grep -c $'\r' <cache>/scan-download` prints `0`.
