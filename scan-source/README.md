# scan-source

A Claude Code plugin that runs a **layered local security scan** on any downloaded or
cloned source tree, then **interprets the results and recommends concrete fixes**.

It defends against the two distinct threats ordinary antivirus and a single CVE
scanner miss:

1. **Malicious packages** — the recent npm/PyPI-style supply-chain attacks (typosquats,
   compromised maintainers, malicious install scripts, obfuscated exfiltration),
   detected heuristically.
2. **Known vulnerabilities** — CVEs in legitimate-but-outdated dependencies, plus
   leaked secrets and insecure code patterns.

## What it runs

| Layer | Tool | Catches |
|-------|------|---------|
| 1 — malware / supply-chain | [GuardDog](https://github.com/DataDog/guarddog) | malicious install scripts, obfuscation, typosquats |
| 2 — known CVEs + secrets | [Trivy](https://github.com/aquasecurity/trivy), [OSV-Scanner](https://github.com/google/osv-scanner), [pip-audit](https://github.com/pypa/pip-audit) | vulnerable deps, leaked secrets, misconfigs |
| 3 — insecure code (SAST) | [Semgrep](https://github.com/semgrep/semgrep) | injection, hardcoded secrets, dangerous calls |
| 4 — behavioral (optional) | [Socket](https://socket.dev) | package risk scoring (needs free account) |

All tools are free/open-source and install without `sudo` (pipx + two static binaries
into `~/.local/bin`). The scanner script is **bundled** with the plugin — it does not
depend on anything in your `PATH`.

## Usage

Once installed via your marketplace, just ask Claude things like:

- "Is this repo safe to use before I install it? `~/code/3rdParty/somelib`"
- "Scan this download for malware."
- "Audit the dependencies in this project and tell me what to fix."

Claude will ensure the tools are installed, run the scan, read the full log, and give
you a verdict (**SAFE TO USE** / **REVIEW BEFORE USING** / **DO NOT RUN**) with a
prioritized findings list and concrete fix commands.

### Running the scanner directly

The bundled scanner also works as a standalone command:

```bash
bash skills/scan-source/scripts/scan-download /path/to/repo        # full scan
bash skills/scan-source/scripts/scan-download --quick /path/to/repo # skip Semgrep SAST
```

A full log is written to `<repo>/.scan-reports/scan-<timestamp>.log`. Exit code:
`0` = clean, `1` = findings present, `2` = usage error.

## Installing the tools

```bash
bash skills/scan-source/scripts/install-security-scanners.sh
# optional behavioral layer (needs a free account):
INSTALL_SOCKET=1 bash skills/scan-source/scripts/install-security-scanners.sh && socket login
```

## Interpreting results

The plugin reasons about findings rather than dumping raw counts — it distinguishes
heuristic false positives from real malware, production dependencies from dev/build
ones, and flags no-fix CVEs and abandoned packages. See
[`skills/scan-source/references/interpreting-results.md`](skills/scan-source/references/interpreting-results.md)
for the full interpretation and per-ecosystem fix guide.

## How to read findings (the short version)

- A **"FINDINGS" verdict is a prompt to investigate, not proof of malice.** GuardDog
  is heuristic and routinely flags benign patterns (a legit API URL, dynamic dispatch).
- **Large CVE counts on a monorepo are normal** — mostly *transitive* dev/build deps
  that don't execute when you simply use the package. Triage by severity × reachability
  × fix-available.
- **A clean scan is not proof of safety.** For brand-new packages, a minimum
  package-age policy (e.g. 7 days) remains the cheapest first defense — most malicious
  packages are caught and yanked within days of publishing.

## License

MIT — see [LICENSE](LICENSE).
