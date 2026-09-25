---
name: scan-source
description: >-
  Use this skill when the user wants to know whether third-party code they did NOT
  write is safe to use — a cloned repo, downloaded archive, a dependency/package
  they're about to add, or something already sitting in node_modules. Triggers on
  intent like: "is this repo/folder safe to run/install", "check ~/path for malware
  or sketchy install scripts", "could this package be a typosquat or compromised",
  "does this phone home / read env vars / exfiltrate", "anything dangerous in this
  download", "audit this dependency tree", or naming a folder/repo they just pulled
  and asking if it's risky — even if they never say "scan". This runs a local,
  layered scan that catches supply-chain malware (npm/PyPI-style attacks) plus known
  CVEs, leaked secrets, and insecure code, then explains which findings actually
  matter. NOT for reviewing the user's own code quality, threat-modeling their own
  app, or checking a URL/link.
---

# scan-source

Vet downloaded/cloned source for security problems, then explain the results in
plain terms and recommend the specific fixes. The scanner is bundled with this
skill — you do not depend on anything in the user's `PATH`.

## Why this exists (the mental model you must convey)

There are **two unrelated threats**, and they need different tools. Keep them
separate when you report, because users conflate them:

1. **Malicious packages** — the recent-style supply-chain attacks: typosquats,
   compromised maintainer accounts, malicious post-install scripts, obfuscated
   exfiltration. Antivirus and CVE databases largely **miss** these because the
   package is brand-new and not yet in any advisory feed. → caught heuristically
   by **GuardDog** (and optionally Socket).
2. **Known vulnerabilities (CVEs)** in legitimate-but-outdated dependencies, plus
   leaked secrets and insecure code patterns. → caught by **Trivy**, **OSV-Scanner**,
   **pip-audit**, and **Semgrep**.

A clean scan is **not proof of safety**, and a "FINDINGS" verdict is **not proof of
malice** — it is a prompt to investigate. Your job is to do that investigation for
the user and tell them what actually matters.

## Workflow

Paths below are relative to **this skill directory** (`SKILL_DIR`), not the plugin
root. Resolve `SKILL_DIR` in this order:

1. The "Base directory for this skill" path that the harness shows above this file.
2. `${CLAUDE_PLUGIN_ROOT}/skills/scan-source`. `CLAUDE_PLUGIN_ROOT` is the plugin
   root, one level above `skills/`. `${CLAUDE_PLUGIN_ROOT}/scripts` does not exist.
3. The directory that contains this `SKILL.md`.

The scanner is `$SKILL_DIR/scripts/scan-download`. The installer is
`$SKILL_DIR/scripts/install-security-scanners.sh`.

**Native Windows:** the scanners are Linux tools. Run every command in this skill
inside WSL through `wsl.exe -e bash -lc '<command>'`. Convert each path to its WSL
form: `C:\Users\x\...` becomes `/mnt/c/Users/x/...`. Do not check for the tools in
Git Bash, because they are installed only in WSL. Both scripts exit with code 2
and print the WSL command if they are started from Git Bash.

**macOS:** the scripts run under the stock `/bin/bash` 3.2 and do not need GNU
`timeout`. The installer needs `curl`, `jq`, and `pipx` (`brew install pipx jq`)
and downloads the `darwin`/`macOS` builds of osv-scanner and trivy for the Mac's
CPU (Intel or Apple silicon).

**CRLF error:** `$'\r': command not found` or `set: pipefail: invalid option name`
means that a Windows git clone with `core.autocrlf=true` converted the scripts to
CRLF. The repo's `.gitattributes` prevents this on new clones. For an old clone, run
an LF copy from your scratchpad: `tr -d '\r' < "$SKILL_DIR/scripts/scan-download" >
<scratchpad>/scan-download`. Do not edit the plugin cache.

### 1. Identify the target

Confirm the absolute path to the source tree to scan (a cloned repo or extracted
download). If the user named a project, resolve it to a directory. Never scan the
whole home directory — scan the specific repo.

### 2. Ensure the tools are installed

The scanner needs five CLIs: `guarddog`, `semgrep`, `pip-audit`, `osv-scanner`,
`trivy`. Check quickly:

```bash
for t in guarddog semgrep pip-audit osv-scanner trivy; do
  command -v "$t" >/dev/null 2>&1 && echo "$t ok" || echo "$t MISSING"
done
```

If any are missing, run the bundled installer (no `sudo`; pipx + two static
binaries into `~/.local/bin`):

```bash
bash "$SKILL_DIR/scripts/install-security-scanners.sh"
```

Tell the user this installs `guarddog`, `semgrep`, `pip-audit` via pipx and
`osv-scanner`, `trivy` as static binaries. These are all long-established,
high-profile tools (well past any reasonable minimum-package-age threshold).
`socket` is optional and skipped unless they set `INSTALL_SOCKET=1` and log in.

### 3. Run the scan

```bash
bash "$SKILL_DIR/scripts/scan-download" "<absolute-target-path>"
```

Useful flags: `--quick` skips the slower Semgrep SAST pass;
`SEMGREP_TIMEOUT=900 bash "$SKILL_DIR/scripts/scan-download" <path>` raises the Semgrep timeout.
A full combined log is written to `<target>/.scan-reports/scan-<timestamp>.log`.
Exit code `0` = nothing flagged, `1` = findings present (this is normal and
expected, not an error), `2` = usage error.

The scan can take several minutes on a large tree — GuardDog walking a big
`node_modules` is usually the long pole. That is expected; do not assume it hung.

### 4. Read the full log, not just the summary

The console summary tells you *which* layers flagged something. The real signal is
in the log. Read `<target>/.scan-reports/scan-<timestamp>.log` and extract, per
layer: GuardDog indicator lines (file:line), the Trivy and OSV vulnerability
tables, and the Semgrep findings.

### 5. Interpret — this is the whole point

Do not just relay raw counts. A monorepo throwing 120 CVEs can be perfectly fine to
use, while 1 GuardDog indicator can be the thing that matters. Read
`references/interpreting-results.md` and apply its rules to:

- separate **heuristic false positives** from real malware (GuardDog),
- separate **production-dependency** CVEs from **dev/build** ones (Trivy suppresses
  dev deps by default and reports the production picture; OSV includes everything —
  the gap between them is the dev/build chain),
- flag **no-fix CVEs** (`Fixed Version: --`) and **abandoned packages**,
- judge **reachability** (is the vulnerable code path actually used?).

### 6. Report using this structure

```
# Security scan: <repo>

Scanned: <absolute-target-path> on <YYYY-MM-DD>
Raw log: .scan-reports/scan-<timestamp>.log

## Verdict: <SAFE TO USE | REVIEW BEFORE USING | DO NOT RUN>
One-sentence justification.

## Layers
| Layer | Tool(s) | Result |
(malware / CVEs+secrets / SAST / behavioral)

## What actually matters
Prioritized list of the real findings (severity × reachability × fix-available).
Note explicitly which GuardDog hits are benign false positives and why.

## Recommended fixes
Concrete commands (see references/interpreting-results.md for per-ecosystem fixes).
Fix script: .scan-reports/scan-<timestamp>-fix.sh  (or "none generated — no actual vulns")

## Caveats
- Clean ≠ proof of safety; what was scanned (git clone vs published artifact);
  honor the 7-day minimum-package-age rule on install.
```

Set the verdict honestly: **DO NOT RUN** only for credible malware (real GuardDog
indicators that survive scrutiny, or Semgrep secret/backdoor hits in first-party
code). Outdated dependencies with known CVEs are **REVIEW BEFORE USING**, not a
malware verdict.

### 7. Save the report beside the log (always)

After presenting the report in chat, **always** write the same content to a markdown
file next to the raw log, so the interpretation is preserved with the scan it
describes. Use the log's own timestamp so the report sorts directly beside it:

```
<target>/.scan-reports/scan-<timestamp>-report.md
```

e.g. log `scan-2026-06-21_094935.log` → report `scan-2026-06-21_094935-report.md`.
This is not optional and not a separate "do you want me to save it?" step — the saved
report is part of the deliverable (and matches the house rule about writing a summary
file when finishing a substantial task). Tell the user the path you wrote it to.

### 8. Generate the fix script beside the report

If — and only if — the report contains at least one **actual vulnerability** (a
real CVE/advisory in a dependency, confirmed non-false-positive), write an
executable fix script next to the report and `chmod +x` it:

```
<target>/.scan-reports/scan-<timestamp>-fix.sh
```

The script is the "Recommended fixes" section made runnable. It never runs
automatically — the user reviews it and runs it themselves. Rules for its content:

- **One step per actual vuln (or per-lockfile group of vulns) with a viable fix**
  — the concrete ecosystem command (`cargo update -p … --precise …`,
  `pnpm up …`, an override edit, etc.), exactly as recommended in the report.
- **An actual vuln with no viable automatic fix** (Fixed Version `--`, abandoned
  package, or a transitive dep whose fix needs an upstream semver-major bump)
  gets **no fix command — never invent one**. Instead the script reports an
  error in that step: print `ERROR: <vuln> — <why it cannot be auto-fixed and
  what to do instead>` to stderr and count it as a failure, so the script exits
  non-zero even when every runnable step succeeds.
- **Nothing else goes in the script**: no false positives, no unmaintained-crate
  informational notices, no Docker/Helm best-practice nits, no allowlist edits.
- Steps must keep going after a failure (no `set -e`); track failures and exit
  `1` if any step failed or any vuln was unfixable, `0` only when everything
  was fixed.
- End by reminding the user to re-run the scan to confirm, and honor the 7-day
  minimum-package-age rule on any bump the script performs.

Skeleton (adapt paths and steps to the actual findings):

```bash
#!/usr/bin/env bash
# Generated by scan-source from scan-<timestamp>-report.md — REVIEW BEFORE RUNNING.
TARGET="<absolute-target-path>"
FAILURES=0

step() {  # step "<description>" <command...>
  local desc="$1"; shift
  echo "==> $desc"
  if "$@"; then echo "    OK"; else echo "    FAILED: $desc" >&2; FAILURES=$((FAILURES+1)); fi
}

unfixable() {  # unfixable "<vuln>" "<why + what to do instead>"
  echo "ERROR: $1 — $2" >&2
  FAILURES=$((FAILURES+1))
}

step "nostr 0.44.6 -> 0.44.7 (RUSTSEC-2026-0225..0230)" \
  cargo update -p nostr --precise 0.44.7 --manifest-path "$TARGET/Cargo.toml"
unfixable "quick-xml 0.38.4 (RUSTSEC-2026-0194/0195, HIGH)" \
  "fix is a semver-major of a transitive dep; parent crates must bump — track upstream"

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "$FAILURES step(s) failed or need manual action" >&2
  exit 1
fi
echo "All fixes applied — re-run the scan to confirm the counts drop"
```

If the report has **no actual vulns** (clean, or only false positives /
informational notices), do not create the script — state "no fix script
generated — no actual vulns" in the report's Recommended fixes section instead.
Tell the user the script path (or that none was needed) alongside the report path.

### 9. Create shareable copies (always)

The report, fix script, and log contain the user's local absolute paths and home
directory. Always produce sanitized copies the user can paste into an upstream
issue or hand to a third party, in:

```
<target>/.scan-reports/share/
```

Copy the report, the fix script (if one was generated), and the raw log, then
sanitize every file:

- the absolute target path → `~/code/<repo-name>` (both with and without the
  leading `/` — OSV prints source paths without it),
- the user's home directory → `~`,
- the local path of this skill's `scan-download` script → the literal text
  `scan-download (scan-source plugin)`,
- in the fix script, set `TARGET="$HOME/code/<repo-name>"` so it stays runnable.

Then **leak-check**: grep the `share/` directory for the username and for
distinctive fragments of the real paths — the grep must come back empty before
you hand the files over. Re-run `bash -n` on the sanitized fix script.

Append a **"Reproduce this scan"** section to the shared report so recipients
can run the same scan themselves:

````markdown
## Reproduce this scan

The scan ran with the **scan-source** plugin from the Chameleon Labs
marketplace (GuardDog malware heuristics, Trivy + OSV-Scanner CVE/secret
scanning, Semgrep SAST).

Install the plugin in Claude Code:

```
/plugin marketplace add Chameleon-Labs-LLC/plugins
/plugin install scan-source@chameleon-labs
```

Or from the terminal:

```bash
claude plugin marketplace add Chameleon-Labs-LLC/plugins
claude plugin install scan-source@chameleon-labs
```

Verify with `/plugin list`, then run `/scan-source ~/code/<repo-name>`. On
first use the skill installs the scanner CLIs it needs (pipx + static binaries
in `~/.local/bin`, no sudo). Reports land in `<target>/.scan-reports/`.
````

### 10. Offer to file an upstream issue (if the project allows it)

When the scan found **actual vulnerabilities that upstream should fix** (an
outdated lockfile, dependency bumps, a no-fix dep worth replacing), the
highest-leverage outcome is an upstream report. Do not skip this step — but
never file without asking.

1. **Check the project's rules first.** Read `CONTRIBUTING.md`, `SECURITY.md`,
   and `.github/ISSUE_TEMPLATE/` in the target repo, and confirm issues are
   enabled (`gh repo view <owner>/<repo> --json hasIssuesEnabled`). If
   contributing docs forbid unsolicited issues or the tracker is disabled, tell
   the user and stop here.
2. **Route by finding type.** Credible malware or an exploitable first-party
   vulnerability must **never** go in a public issue — follow the repo's
   `SECURITY.md` private-disclosure process instead (or advise the user to).
   Dependency-freshness/CVE reports are fine as public issues.
3. **Check for duplicates** (`gh issue list --search`, plus recent git history)
   before proposing anything.
4. **Ask the user** (AskUserQuestion) whether to submit, showing which repo,
   what the issue will say, and any template/conventions the repo requires
   (e.g. an agent-attribution line if the repo's docs mandate one). Filing an
   issue is outward-facing — it needs explicit consent every time.
5. On yes: file with `gh issue create`, drawing the body from the **sanitized
   shared report** (step 9), never from the unsanitized files. Give the user
   the issue URL.

## Allowlisting known-benign GuardDog hits

GuardDog is heuristic and re-flags the same benign patterns every run (e.g. a
legitimate `api.telegram.org` URL). To stop the noise, add narrow substrings to the
allowlist at `~/.config/scan-download/guarddog-allow.txt` (a template is bundled at
`scripts/guarddog-allow.txt.template`; copy it there on first use). Entries are
**global** across every scan, so keep them specific — everything still appears in the
full log regardless; the allowlist only changes the pass/fail verdict. Override the
path with `SCAN_ALLOWLIST=/path/to/file`.

## References

- `references/interpreting-results.md` — how to read each layer's output, tell false
  positives from real findings, and the exact fix recommendations per ecosystem
  (npm/pnpm/yarn, pip/uv, cargo). Read it before writing the report.
