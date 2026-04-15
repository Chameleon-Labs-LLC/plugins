# Chameleon Labs — Claude Code plugin marketplace

Plugins from [Chameleon Labs LLC](https://github.com/Chameleon-Labs-LLC) for [Claude Code](https://claude.com/claude-code). Skills, agents, commands, and tooling you can install with one command.

## Install

In Claude Code:

```
/plugin marketplace add Chameleon-Labs-LLC/plugins
/plugin install agent-spawner@chameleon-labs
```

Or from the shell:

```bash
claude plugin marketplace add Chameleon-Labs-LLC/plugins
claude plugin install agent-spawner@chameleon-labs
```

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

More plugins land here as we build them. Each plugin lives in its own repo; this marketplace is just the index.

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
