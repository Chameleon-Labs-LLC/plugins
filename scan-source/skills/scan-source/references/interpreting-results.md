# Interpreting scan-source results

Read this before writing the report. It covers how to read each layer, how to tell
benign findings from real ones, and the exact fixes to recommend per ecosystem.

## Contents
1. Layer 1 — GuardDog (malware / supply-chain)
2. Layer 2 — Trivy + OSV-Scanner + pip-audit (known CVEs + secrets)
3. Layer 3 — Semgrep (insecure code patterns)
4. Layer 4 — Socket (optional behavioral)
5. Reading a CVE line
6. Triage priority
7. Recommended fixes per ecosystem
8. Setting the verdict

---

## 1. Layer 1 — GuardDog (malware / supply-chain)

GuardDog uses **heuristics**, so it produces false positives routinely. The count is
a starting point, never a verdict. For each indicator it prints the rule, the
`file:line`, and the offending source. Open each one and judge it.

Common **benign** patterns that GuardDog flags (call these out as false positives and
explain why):

| Rule | Frequently-benign trigger | Why it's usually fine |
|------|---------------------------|------------------------|
| `shady-links` | A URL to a real service (`api.telegram.org`, a webhook) | Legitimate integrations use real endpoints. Malice = the URL is *unexpected* for the package's purpose, or paired with exfil of env/secrets. |
| `npm-api-obfuscation` | `MAP[key]?.(args)`, `rules[field](...)` | Ordinary dynamic dispatch / computed member access in JS/TS — not obfuscation. |
| `code-execution` / `exec` | A build tool legitimately spawning a subprocess | Real build/test tooling runs processes. Malice = running a *downloaded* payload, or shelling out in an `install` hook. |

What makes an indicator **actually suspicious** (escalate these):
- Behavior in an **install/postinstall hook** (runs automatically on `npm install`).
- Reading `process.env` / `~/.ssh` / `~/.aws` / browser data **and** sending it to a
  network endpoint.
- Obfuscated/base64-decoded-then-`eval`'d payloads, especially fetched at runtime.
- A package whose name typosquats a popular one, doing anything network-related.

GuardDog `scan <dir>` **exits 0 even with indicators** — the bundled scanner parses
its output to score this correctly, but if you ever run GuardDog directly, do not
trust its exit code.

## 2. Layer 2 — Trivy + OSV-Scanner + pip-audit (known CVEs + secrets)

These cross-reference dependencies against live advisory databases. They overlap but
differ in important ways:

- **Trivy** by default **suppresses dev/test dependencies** and reports the
  **production** picture. It also scans for **leaked secrets** and **misconfigs**.
  `Trivy: 0 vulns` means the *runtime* deps are clean.
- **OSV-Scanner** scans **everything in the lockfile, including dev/build deps.**

**The gap between them is the dev/build chain.** If Trivy says 0 and OSV says 22,
those 22 are almost certainly build tooling (`vite`, `rollup`, `postcss`,
`esbuild`, `webpack`, `picomatch`, `tar`, etc.). For a tool the user merely
*installs and runs*, dev/build CVEs **do not execute** — they only matter to someone
*developing/building* the project. Say this explicitly; it is the difference between
"alarming number" and "actually fine."

**Leaked secrets** (Trivy `secret` scanner) are high-priority and real — a committed
API key, private key, or token. Flag these prominently; recommend rotation.

## 3. Layer 3 — Semgrep (insecure code patterns)

SAST over the **first-party source**. Findings are about how *this code* is written,
not its dependencies. Common categories and how to weight them:

- `detected-jwt-token`, `detected-private-key`, hardcoded secrets → **verify they are
  examples/test fixtures, not real**. A real secret is serious.
- `dockerfile.security.missing-user` → container runs as root. Best-practice, low
  urgency unless the user is deploying it as-is.
- Injection patterns (`tainted-sql-string`, `command-injection`) in reachable code →
  genuine, weight by whether untrusted input reaches them.

Semgrep finding source code that *executes a downloaded payload* or *exfiltrates
secrets* in first-party code is a **DO NOT RUN** signal — that is malware, not a
style nit.

## 4. Layer 4 — Socket (optional behavioral)

Only runs if installed and logged in; otherwise cleanly skipped. When present, it
scores packages on behavior (network, filesystem, env access, install scripts).
Treat a high Socket risk score the same as a GuardDog indicator: investigate, don't
assume.

## 5. Reading a CVE line

```
| OSV URL | CVSS | ECOSYSTEM | PACKAGE | VERSION | FIXED VERSION | SOURCE |
```
- **CVSS** — severity 0–10 *if exploited*. Not the same as risk to this user.
- **FIXED VERSION = `--`** — **no fix exists**. The package may be abandoned. This is
  more important than a high CVSS with an easy bump, because you cannot just update.
- **SOURCE** — which lockfile; tells you the ecosystem and whether it's the main app
  or a sub-project (e.g. `rust/Cargo.lock`).
- **Direct vs transitive** — most lockfile CVEs are *transitive* (a dep of a dep).
  You often cannot fix them directly; you wait for the parent to bump, or force a
  version with an override.

## 6. Triage priority

Rank findings by **severity × reachability × fix-available**:

1. **Real malware** (escalated GuardDog/Semgrep) → top priority, blocks the verdict.
2. **Leaked secrets** → rotate immediately.
3. **CRITICAL/HIGH CVE, production dep, fix available** → bump now.
4. **CRITICAL/HIGH CVE, no fix (`--`) or abandoned package** → replace, sandbox, or
   formally accept the risk; don't silently ignore.
5. **CVE in dev/build deps only** → low urgency for users; matters for contributors.
6. **Unreachable / dev-only / best-practice** → note and move on.

"Reachability": a command-injection in `systeminformation` only bites if untrusted
input actually flows into it. Many transitive CVEs sit in code paths the project
never calls.

## 7. Recommended fixes per ecosystem

Give concrete commands. Re-run the scan after fixing to confirm counts drop.

### npm / pnpm / yarn
- Direct dep bump: `npm update <pkg>` (or `pnpm up <pkg>`, `yarn up <pkg>`).
- Transitive pin (the dep isn't yours to bump directly):
  - npm: add `"overrides": { "<pkg>": "<fixed-version>" }` to `package.json`.
  - pnpm: add `"pnpm": { "overrides": { "<pkg>": "<fixed>" } }`.
  - yarn: add `"resolutions": { "<pkg>": "<fixed>" }`.
- Abandoned package with no npm fix (classic: `xlsx`/SheetJS, where fixes ship only
  via the vendor CDN): recommend **replacing** the library (e.g. `exceljs`) or
  pinning to the vendor's patched build, not just `npm update`.
- Honor the 7-day minimum-package-age rule on any bump.

### pip / uv / poetry
- `pip install -U <pkg>` then re-freeze, or bump the pin in `requirements.txt` /
  `pyproject.toml`.
- uv: `uv pip install -U <pkg>` (consider `--exclude-newer` for the age rule).
- Verify the fixed version's publish date is ≥7 days old before pinning.

### cargo (Rust)
- `cargo update -p <pkg>` to move within semver, or bump the version requirement in
  `Cargo.toml` if the fix is a new major.

## 8. Setting the verdict

- **SAFE TO USE** — GuardDog/Semgrep clean (or only explained false positives), no
  leaked secrets, no reachable CRITICAL/HIGH in production deps. Dev/build CVEs may
  exist; say so but don't let them block.
- **REVIEW BEFORE USING** — real CVEs in production deps, leaked secrets, or
  GuardDog indicators you couldn't fully clear. Tell the user exactly what to check.
- **DO NOT RUN** — credible malware: install-hook exfiltration, obfuscated runtime
  payloads, typosquat behavior, or first-party code that steals secrets / runs
  downloaded code. Be specific about the evidence.

Always close with: what was scanned (git clone vs the published package — the
published artifact often has fewer dev deps and is cleaner), that a clean scan is not
a guarantee, and the 7-day age rule as the cheapest first defense for new packages.
