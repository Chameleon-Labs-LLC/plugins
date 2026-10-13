# PR #3 reviewed gaps — pre-push verification

Date: 2026-10-13. Branch: `feat/cross-platform`.
Reviewed and refreshed head: `1ad7498a49b26f9e2b7edaaa8ad448a49d2f253f`.

## Changes

- Scan sharing now creates a fresh `report.md` draft from a fixed template.
  The helper reads no scanner logs, private reports, or fix scripts. The skill
  permits only reviewed public facts in the draft, excludes raw/private content,
  warns against stale exports, and retains explicit approval of the exact
  content and destination before any external sharing. Local evidence remains
  intact. No disclosure was observed; this closes an unsafe export instruction.
- Single-plugin marketplaces discover the local `plugin.json` as a version
  mirror, for both `./` and nested local sources. Ordinary release synchronizes
  both files while leaving catalog metadata alone. Disagreeing, malformed,
  non-object, non-UTF-8, and unreadable manifests block release. `--plugin`
  remains for independent bumps in multi-plugin catalogs.
- The transcript runner requires Python 3.10+ for bootstrap launchers, reused
  venvs, and the resulting interpreter. Unsupported/broken environments are
  preserved and skipped; an unused candidate is created when possible.
  Documentation matches upstream's Python 3.10+ requirement.

## Verification

- Native Windows, Python 3.12.10 + Git Bash: **74 pytest tests passed**.
- Ubuntu WSL, Python 3.12.3: **74 pytest tests passed**.
- Before fixes, five new single-plugin regressions failed, including successful
  releases that left an invalid/stale manifest unchanged. Corrected transcript
  probes against the original runner produced **15 failures and 6 passes**;
  all 21 cases pass with the fix. The baseline share policy/helper checks failed.
- Sharing regression plants fake credentials, private code, private URLs,
  usernames, and Windows/Unix paths in the log, report, and fix script. None
  enters the new draft. Existing artifacts remain unchanged, and reruns cannot
  overwrite or merge into an existing export directory.
- Real Semgrep 1.164.0, offline local rule: raw text contained a planted source
  string; the generated draft omitted it and retained local evidence. This
  exercises real scanner output, beyond the existing scanner stubs.
- Real upstream transcript `--help` passed using existing Windows and WSL
  venvs. One live fetch of the skill's public example video succeeded on
  Windows, with output confined to the task scratch directory.
- Original transcript smoke tests passed on Windows and WSL with
  `PIP_NO_INDEX=1`, creating real disposable venvs without package downloads.
- Both scanner smoke modes passed in WSL, including the no-timeout fallback.
  Those tests use stub scanner CLIs; they do not validate every real scanner.
- CI shell syntax checks and ShellCheck error gate passed. ShellCheck 0.10.0
  was downloaded as a portable task-local tool (release 2024-03-08) and verified
  against SHA-256 `eb6cd53a54ea97a56540e9d296ce7e2fa68715aa507ff23574646c1e12b2e143`.
- Ruff, Python compilation, CI marketplace/plugin structure, LF checks, and
  `git diff --check` passed. Claude validated the marketplace and all three
  affected plugins; scan-source README install syntax received nonblocking advice.
- CI piped-output checks passed: version-manager exits 0; repo-doctor exits 1
  for existing agent-doc findings, with no traceback. Symbol extraction passed.
- One independent security-boundary investigation and one candidate review
  completed. The reviewer found the unreadable-manifest bypass; it was fixed
  and covered by the final passing tests. No surviving share-export bypass or
  transcript regression was reported.

Reproduce the Python suite from the repository root:

```sh
python -m pytest repo-hygiene/skills/version-manager/tests/ tests/ -q
```

## Boundaries and disposition

- macOS selection rules are exercised by controlled probes; no native macOS
  runtime or stock Bash 3.2 execution was available. Remote CI has not run the
  new patch. Real Python 3.8/3.9/3.10 runtimes were simulated for version probes;
  actual runtime checks used Python 3.12.
- No complete real GuardDog/Trivy/OSV/pip-audit scan or fresh network dependency
  installation was performed. Those components are unchanged.
- Manually added share-report content still requires a full content review and
  explicit publication approval. The default helper deliberately imports no
  findings; it does not claim to redact arbitrary scanner text reliably.
- This note records local validation before pushing the fixes. Release tests
  create commits/tags only inside disposable fixtures. No version bump or
  release is part of this patch.
