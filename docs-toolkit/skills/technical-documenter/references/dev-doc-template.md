# Doc Template for Developer/Technical Documentation

Use this exact structure for each technical area doc. Adapt headings to the specific area.

---

```markdown
# {Technical Area Name}

> {One-sentence summary of this area's role in the system.}

## Overview

{2-3 sentences describing the technical area. What does it handle? What are the key components?}

## API Endpoints

| Method | Path | Purpose | Auth Required |
|--------|------|---------|---------------|
| GET | `/api/example` | {description} | Yes |
| POST | `/api/example` | {description} | Yes |

### {Endpoint Group Name}

**`GET /api/example`**
- **Purpose**: {what it does}
- **Request**: {query params, body schema}
- **Response**: {response shape, status codes}
- **Rate limit**: {if applicable}

## Data Model

Key tables/models involved:

- **ModelName** — {purpose}
  - `fieldName` ({type}) — {what it stores}
  - `otherField` ({type}) — {what it stores}
  - Indexes: {list relevant indexes}

### Relationships
- ModelA → ModelB (one-to-many via `foreignKey`)

## Error Handling

| Error Code | Error | Cause | Resolution |
|------------|-------|-------|------------|
| 401 | Unauthorized | Session expired or not logged in | Re-authenticate |
| 429 | Rate Limited | Too many requests | Wait and retry |
| {code} | {error} | {cause} | {fix} |

## Configuration

Environment variables that affect this area:

| Variable | Purpose | Required | Default |
|----------|---------|----------|---------|
| `EXAMPLE_KEY` | {what it configures} | Yes | — |

## Architecture Notes

{How this area connects to other parts of the system. Key dependencies, data flow, and design decisions.}

### Dependencies
- {Service/library and what it's used for}

### Data Flow
{Brief description of how data moves through this area, e.g., "Request → middleware → handler → DB → response"}
```

---

## Writing Guidelines

- **Read the actual source code** before writing. Don't guess behavior.
- **Write for developers** — assume they know the tech stack but not this specific codebase.
- **Include exact values** — status codes, field names, env var names, rate limits, file paths.
- **Document edge cases** — what happens with null values, empty arrays, missing env vars?
- **No user-facing language** — skip "how to use" instructions. Those belong in `project-documenter`.
- **Length**: Aim for 200-500 lines per doc. Shorter for simple areas, longer for complex ones.
