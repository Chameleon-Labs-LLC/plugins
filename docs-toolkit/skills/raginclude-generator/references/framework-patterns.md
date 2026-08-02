# Framework-Specific .raginclude Patterns

## Table of Contents
- [Next.js (App Router)](#nextjs-app-router)
- [Next.js (Pages Router)](#nextjs-pages-router)
- [Express / Node.js API](#express--nodejs-api)
- [Python (Django)](#python-django)
- [Python (FastAPI / Flask)](#python-fastapi--flask)
- [Rust (Cargo)](#rust-cargo)
- [Go](#go)
- [Monorepo](#monorepo)
- [Claude Code Plugin](#claude-code-plugin)
- [Example: Python Discord Bot](#chatmaster-python-discord-bot)

---

## Next.js (App Router)

```
# Documentation
README.md
docs/**/*.md
CHANGELOG.md
Notes/**/*.md

# API Routes (describes endpoints)
app/api/**/route.ts

# Page structure (shows app navigation)
app/**/page.tsx
app/**/layout.tsx

# Data models
prisma/schema.prisma
prisma/migrations/**/*.sql

# Shared types and constants
lib/products.ts
lib/config.ts
types/**/*.ts

# Component documentation (top-level only)
components/**/*.tsx

# Config
package.json
next.config.*
tsconfig.json
```

**Exclude:** `lib/generated/**`, `.next/**`, `node_modules/**`

## Next.js (Pages Router)

```
README.md
docs/**/*.md

pages/api/**/*.ts
pages/**/*.tsx

prisma/schema.prisma

lib/config.ts
types/**/*.ts

components/**/*.tsx

package.json
next.config.*
```

## Express / Node.js API

```
README.md
docs/**/*.md

src/routes/**/*.ts
src/controllers/**/*.ts
src/models/**/*.ts
src/middleware/**/*.ts

types/**/*.ts
package.json
tsconfig.json
```

**Exclude:** `src/services/**/*.ts` (often contains business logic)

## Python (Django)

```
README.md
docs/**/*.md

**/urls.py
**/views.py
**/models.py
**/serializers.py
**/admin.py

requirements.txt
pyproject.toml
```

**Exclude:** `**/management/commands/**` (internal ops), `**/migrations/*.py` (auto-generated)

## Python (FastAPI / Flask)

```
README.md
docs/**/*.md

app/routers/**/*.py
app/models/**/*.py
app/schemas/**/*.py

requirements.txt
pyproject.toml
```

## Rust (Cargo)

```
README.md
docs/**/*.md

src/lib.rs
src/main.rs
src/api/**/*.rs
src/models/**/*.rs

Cargo.toml
```

**Exclude:** `target/**`, `src/internal/**`

## Go

```
README.md
docs/**/*.md

cmd/**/*.go
pkg/**/*.go
api/**/*.go
internal/models/**/*.go

go.mod
```

**Exclude:** `vendor/**`, `internal/**` (except models)

## Monorepo

For monorepos, prefix patterns with the app directory:

```
# Root docs
README.md
docs/**/*.md

# Per-app patterns
apps/web/app/api/**/route.ts
apps/web/app/**/page.tsx
apps/api/src/routes/**/*.ts

# Shared packages
packages/shared/src/**/*.ts
packages/types/src/**/*.ts

# Root config
package.json
turbo.json
```

Adapt per-app patterns using the single-framework sections above.

---

## Claude Code Plugin

Detected by: `plugin.json` + `skills/` directory.

```
# Plugin manifest and configuration
plugin.json

# AI/agent context
AGENTS.md

# Skills (user-invocable workflows)
skills/**/*.md

# Agents (subagent definitions)
agents/**/*.md

# Slash commands
commands/**/*.md

# Hooks (event-driven automation)
hooks/**/*.md

# Documentation
README.md
docs/**/*.md
Features.md
```

**Exclude:**
- `skills/*/references/**` — internal implementation references, not user-facing
- `.local.md` files — per-user plugin state, not shared knowledge
- Any skill file that contains credentials or API keys in its body
- `CLAUDE.md` — audit first; often contains infrastructure details (IPs, SSH keys, instance IDs)

**Notes:**
- Skill `description:` fields (in frontmatter) tell the RAG what each skill does; the full skill body may contain implementation details — include selectively
- If the plugin is embedded inside a larger Next.js app, combine with the Next.js App Router patterns above

---

## Example: Python Discord Bot

Detected by: `requirements.txt` containing `discord` (discord.py) + `main.py` or `app/discord_client.py`.

```
# Primary docs — always include
README.md
AGENTS.md

# Feature documentation
Docs/Features/**/*.md
Docs/BotFeatures.md
Docs/Multimodal_Image_Support.md
Docs/Alert_API_Guide.md
Docs/AI_Report_User_Guide.md
Docs/AI_Disclosure_User_Flow.md
Docs/UniversalSearchLLM.md

# Command reference (user-facing markdown docs in Scripts/)
Scripts/Admin_Moderator_Features.md
Scripts/User_Features.md

# User guides at project root
personalities.md
MULTI_LLM_USER_GUIDE.md
PERSONALITY_USAGE.md

# Example config (shows what's configurable, no real secrets)
config.example.yaml

# Requirements (stack context)
requirements.txt
```

**Exclude (security / infrastructure):**
- `config.yaml` — real API keys and tokens
- `.env` — secrets
- `AWS_*.md`, `*_Deployment_*.md`, `*_Deploy_*.md` — EC2 IPs, SSH keys, instance IDs
- `ANTHROPIC_AUTH_GUIDE.md`, `OAUTH_IMPLEMENTATION.md` — auth internals
- `*Security_Audit*.md` — security findings
- `CLAUDE.md` — contains EC2 instance ID, public IP, and SSH key paths; do NOT index
- `Notes/**` — internal plans, compliance, bug bounty, roadmap; exclude by default
- `Plans/**` — internal implementation plans
- `Scripts/**/*.py`, `Scripts/**/*.sh` — internal ops scripts
- `app/**/*.py` — implementation internals; no user-facing value
- `bbs_app.sqlite3*`, `bbs_app.log*` — database and log files
- `backups/**` — backup files

**Notes:**
- `Scripts/Admin_Moderator_Features.md` and `Scripts/User_Features.md` are the primary command reference — always include despite the general `Scripts/**` exclusion rule
- `Docs/generated/` contains HTML help docs — these are fine to include if the RAG system can handle HTML, but markdown sources in `Docs/Features/` are preferred
- The `app/` directory is pure Python implementation — no file there is user-facing documentation
