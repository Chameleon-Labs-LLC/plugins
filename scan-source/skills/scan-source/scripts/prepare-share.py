#!/usr/bin/env python3
"""Create a fresh share draft without reading private scan artifacts."""
import argparse
from pathlib import Path


TEMPLATE = """# Security scan summary — DRAFT

Review this entire file and obtain explicit approval before sending it anywhere.
Raw logs, private reports, and executable fix scripts are intentionally omitted.
This draft contains no scan results until reviewed public facts are added.

## Scope and result

[Add only an approved public project name, scan date, and aggregate layer results.
Say which layers were skipped or failed. A clean scan is not proof of safety.]

## Findings and recommendations

[Summarize reviewed public advisory IDs, public package versions, and general
remediation. Omit source excerpts, credentials, private identifiers/endpoints,
local paths, and verbatim scanner output. If uncertain, leave the detail out.
Route exploitable first-party findings through private disclosure.]

## Reproduce this scan

The scan-source plugin from the Chameleon Labs marketplace runs GuardDog,
Trivy, OSV-Scanner, pip-audit, and Semgrep (subject to installed tools and flags).

Install in Claude Code:

```
/plugin marketplace add Chameleon-Labs-LLC/plugins
/plugin install scan-source@chameleon-labs
```

Verify with `/plugin list`, then run `/scan-source <path-to-your-clone>`.
On Windows, scanner commands run inside WSL. The skill checks scanner tools
and documents installation. Private local output lands in `.scan-reports/`.
Record any scan flags or skipped layers above after reviewing them.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="new directory for this scan's draft (must not exist)")
    args = parser.parse_args()
    try:
        # Refuse an existing directory, including a symlink. Never blend this
        # draft with stale exports or overwrite a previously reviewed report.
        args.output_dir.mkdir(parents=True, exist_ok=False)
        with (args.output_dir / "report.md").open("x", encoding="utf-8", newline="\n") as report:
            report.write(TEMPLATE)
    except OSError as exc:
        parser.exit(1, f"ERROR: could not create a fresh share draft: {exc}\n")
    print("Created report.md draft; review it and obtain explicit approval before sharing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
