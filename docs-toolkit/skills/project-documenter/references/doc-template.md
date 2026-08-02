# Doc Template for User-Facing Feature Documentation

Use this exact structure for each feature area doc. Adapt headings to the specific feature.

---

```markdown
# {Feature Area Name}

> {One-sentence summary of what this feature area provides to users.}

## Overview

{2-3 sentences describing the feature area. What problem does it solve? Who uses it?}

## Features

### {Feature Name}

{What it does in plain language.}

**How to use it:**
1. {Step 1}
2. {Step 2}
3. {Step 3}

**Options:**
- {Option/setting and what it controls}

### {Next Feature}

{Repeat pattern for each feature in this area.}

## Common Questions

**Q: {Anticipated user question}**
A: {Clear answer.}

**Q: {Another common question}**
A: {Answer with resolution steps if applicable.}

**Q: {Edge case or confusion point}**
A: {Clarification.}
```

---

## Writing Guidelines

- **Read the actual source code** before writing. Don't guess behavior.
- **Write for end users** — someone who has never seen the app. Use "you" and "your".
- **No technical jargon** — no API paths, status codes, database fields, or env vars. Those belong in `technical-documenter`.
- **Limits and quotas**: If the code enforces limits (rate limits, file size limits, tier restrictions), state them in user-friendly terms.
- **No screenshots**: These docs are text-only for RAG indexing.
- **Length**: Aim for 100-300 lines per doc. Shorter for simple features, longer for complex ones.
