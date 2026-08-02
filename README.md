# Chameleon Labs — Claude Code plugin marketplace

Plugins from [Chameleon Labs LLC](https://github.com/Chameleon-Labs-LLC) for [Claude Code](https://claude.com/claude-code). Skills, agents, commands, and tooling you can install with one command.

## Install

In Claude Code:

```
/plugin marketplace add Chameleon-Labs-LLC/plugins
/plugin install scan-source@chameleon-labs
```

Or from the shell:

```bash
claude plugin marketplace add Chameleon-Labs-LLC/plugins
claude plugin install scan-source@chameleon-labs
```

Swap `scan-source` for any plugin name from the table below (e.g. `agent-spawner@chameleon-labs`).

After installing, verify:

```
/plugin list
```

Update later:

```
/plugin marketplace update chameleon-labs
```

## Available plugins

| Plugin | Description | Source |
|---|---|---|
| `agent-spawner` | Scaffold, package, and deploy Claude agents (Telegram/Slack/Discord channels, local + managed + hybrid runtimes, HMAC-signed bridges, SCP/SSH deploy to Linux). | [Chameleon-Labs-LLC/agent-spawner](https://github.com/Chameleon-Labs-LLC/agent-spawner) |
| `license-validator` | Shared license verification for Chameleon Labs commercial plugins. Install once; all paid plugins use it to verify licenses and cache a 24-hour offline token. | [Chameleon-Labs-LLC/license-validator](https://github.com/Chameleon-Labs-LLC/license-validator) |
| `scan-source` | Layered local security scan for downloaded/cloned source — malware/supply-chain (GuardDog), known CVEs + leaked secrets (Trivy, OSV-Scanner, pip-audit), and insecure-code SAST (Semgrep). Interprets results and recommends concrete fixes. | [bundled in this repo](./scan-source) |
| `humanizer` | Strips AI fingerprints from prose and rewrites it in a personal voice, with a guided setup that builds your voice profile. | [bundled in this repo](./humanizer) |
| `repo-hygiene` | Keep any repo's agent-facing layer healthy: standardized version bumps + changelogs (`version-manager`), agent-docs audits (`repo-doctor`), CLAUDE.md rightsizing (`claude-md-optimizer`), and canonical AGENTS.md unification across coding CLIs (`unify-agents-md`). | [bundled in this repo](./repo-hygiene) |
| `docs-toolkit` | Generate and maintain project documentation: user-facing feature docs + sitemap, developer/API docs, feature inventories, a verified CodeMap.md, and `.raginclude` files for RAG indexing. | [bundled in this repo](./docs-toolkit) |
| `yt-transcript` | Download YouTube transcripts from any URL form or bare video ID, with the Python venv lifecycle handled by a bundled runner. | [bundled in this repo](./yt-transcript) |
| `model-registry` | Wire any project to a daily-refreshed public registry of current LLM model IDs (Claude, GPT, Gemini) so code stops hardcoding model names that go stale. | [bundled in this repo](./model-registry) |

Looking for a knowledge-graph skill? We recommend [Graphify](https://github.com/Graphify-Labs/graphify) by Safi Shamsi (`uv tool install graphifyy`) — it ships its own Claude Code skill, so we don't repackage it here.

More plugins land here as we build them. Most plugins live in their own repo and are referenced by this index; some smaller ones (like `scan-source`) are bundled directly in this repo under their own directory.

## Team rollout

To auto-install this marketplace for your team when they open a project, add to `.claude/settings.json` in the project:

```json
{
  "extraKnownMarketplaces": {
    "chameleon-labs": {
      "source": {
        "source": "github",
        "repo": "Chameleon-Labs-LLC/plugins"
      }
    }
  },
  "enabledPlugins": {
    "agent-spawner@chameleon-labs": true
  }
}
```

On the next Claude Code session, teammates who trust the project will be prompted to install the marketplace and any enabled plugins automatically.

## Contributing

Each plugin lives in its own repo. To propose a new one:

1. Build and test the plugin in a standalone repo under the Chameleon-Labs-LLC org (include `.claude-plugin/plugin.json`, or use `strict: false` in the marketplace entry).
2. Open a PR against this repo adding an entry to `.claude-plugin/marketplace.json`.
3. Run `claude plugin validate .` locally to confirm the JSON is well-formed.

## License

The marketplace manifest and README in this repo are MIT-licensed. Each listed plugin carries its own license — see the plugin's repository.
