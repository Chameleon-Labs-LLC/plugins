---
name: scan-source
description: >-
  Run a layered local security scan on a downloaded or cloned source tree, then
  interpret the results and recommend concrete fixes. Use this whenever the user
  is about to install, run, clone, or download open-source code and wants to know
  if it is safe — e.g. "is this repo/package safe to use", "scan this for malware",
  "check this download before I run it", "audit the dependencies", "any supply-chain
  risk here", or names a folder/repo they just pulled. Catches the two distinct
  threats antivirus misses: malicious packages (the recent npm/PyPI-style attacks)
  AND known CVEs + leaked secrets + insecure code. Prefer this skill over ad-hoc
  `npm audit`/`pip-audit` calls because it runs all layers and explains what the
  findings actually mean. Trigger even if the user doesn't say the word "scan".
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

Paths below are relative to this skill directory. Use `${CLAUDE_PLUGIN_ROOT}` when
it is set (plugin context); otherwise resolve relative to this `SKILL.md`. The
scanner lives at `scripts/scan-download`.

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
bash scripts/install-security-scanners.sh
```

Tell the user this installs `guarddog`, `semgrep`, `pip-audit` via pipx and
`osv-scanner`, `trivy` as static binaries. These are all long-established,
high-profile tools (well past any reasonable minimum-package-age threshold).
`socket` is optional and skipped unless they set `INSTALL_SOCKET=1` and log in.

### 3. Run the scan

```bash
bash scripts/scan-download "<absolute-target-path>"
```

Useful flags: `--quick` skips the slower Semgrep SAST pass;
`SEMGREP_TIMEOUT=900 bash scripts/scan-download <path>` raises the Semgrep timeout.
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

## Caveats
- Clean ≠ proof of safety; what was scanned (git clone vs published artifact);
  honor the 7-day minimum-package-age rule on install.
```

Set the verdict honestly: **DO NOT RUN** only for credible malware (real GuardDog
indicators that survive scrutiny, or Semgrep secret/backdoor hits in first-party
code). Outdated dependencies with known CVEs are **REVIEW BEFORE USING**, not a
malware verdict.

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
