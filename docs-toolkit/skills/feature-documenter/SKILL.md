---
name: feature-documenter
description: Analyzes a codebase and generates comprehensive user-facing feature documentation. Use this skill when users ask to document features, create a feature list, generate product documentation, or write a Features.md file. Triggers on requests like "document the features", "what does this project do", "create feature documentation", or "list all capabilities".
---

# Feature Documenter

Generate comprehensive user-facing feature documentation by analyzing existing docs and code.

## Workflow

### 1. Gather Existing Documentation

Read these files if they exist (in priority order):
- `README.md` - Primary project description
- `CLAUDE.md` or `AGENTS.md` - AI-specific project context
- `Docs/` or `docs/` directory - Existing documentation
- `CHANGELOG.md` - Feature history
- Package files (`package.json`, `setup.py`, `pyproject.toml`) - Dependencies reveal capabilities

### 2. Analyze Code for Features

Scan for user-facing capabilities:

**Entry Points:**
- `main.py`, `main.ts`, `index.js` - Application entry
- CLI argument parsers (`argparse`, `click`, `commander`)
- GUI windows/dialogs

**Feature Indicators:**
- Public API endpoints (`@app.route`, `router.get`)
- GUI components (buttons, menus, dialogs)
- CLI commands and subcommands
- Configuration options users can set
- Export/import functionality

**Pattern Recognition:**
```
# Look for these patterns
Glob: **/cli/*.py, **/commands/*.py  # CLI features
Glob: **/gui/*.py, **/views/*.tsx    # GUI features
Glob: **/api/*.py, **/routes/*.ts    # API features
Grep: "def main", "@click.command", "argparse"
```

### 3. Cross-Reference and Verify

**Critical:** Verify documentation matches actual code:
- Check if documented features exist in code
- Find undocumented features in code
- Note version mismatches or outdated descriptions
- Flag deprecated features still in docs

### 4. Generate Features.md

Output a single `Features.md` file using this structure:

```markdown
# [Project Name] Features

> [One-sentence project description]

## Core Features

### [Feature Category 1]
- **[Feature Name]** - [Brief description of what it does for users]
- **[Feature Name]** - [Description]

### [Feature Category 2]
- **[Feature Name]** - [Description]

## Getting Started

[Brief quickstart - how to access the main features]

## Feature Details

### [Major Feature 1]
[2-3 sentences explaining the feature]
- [Key capability]
- [Key capability]

### [Major Feature 2]
[Description and capabilities]

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| [name] | [what it controls] | [value] |

## Supported Formats/Integrations

- [Format/Integration 1] - [brief note]
- [Format/Integration 2] - [brief note]
```

## Output Guidelines

- Write for end users, not developers
- Focus on what users can DO, not how code works
- Use active voice: "Generate images" not "Images can be generated"
- Group related features logically
- Include practical examples where helpful
- Keep descriptions concise (1-2 sentences per feature)

## Verification Checklist

Before finalizing, confirm:
- [ ] All major entry points have corresponding features documented
- [ ] No documented features are missing from code
- [ ] Feature descriptions match current behavior
- [ ] Configuration options are accurate
- [ ] Quickstart actually works

## Example Output

See `references/example_features.md` for a complete example.
