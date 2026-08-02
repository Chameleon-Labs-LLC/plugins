---
name: raginclude-generator
description: "Generate a .raginclude file for any project to feed its RAG knowledge base. Use when the user asks to create, generate, or update a .raginclude file, set up RAG indexing for a project, configure which files should be indexed for AI chat support, or make a project's documentation available to a RAG pipeline. Triggers on: 'create raginclude', 'generate raginclude', 'set up RAG for this project', 'index this project for chat', 'update raginclude'."
---

# .raginclude Generator

Generate a `.raginclude` file that tells the RAG pipeline which project files to index for AI-powered product support chat.

## Goal

Select files that document **how the app works for users** so the RAG system can answer any user question — without exposing trade secrets, credentials, or proprietary implementation details.

## .raginclude Format

One glob pattern per line. `#` for comments. Blank lines ignored. Patterns resolved relative to project root via node `glob`.

```
# Documentation
docs/**/*.md
README.md

# API surface
app/api/**/route.ts
```

## Process

### 0. Read Existing .raginclude (if present)

If `.raginclude` already exists, read it first. Note its patterns so you can:
- Preserve intentional custom patterns the user added manually
- Update stale or outdated patterns
- Avoid losing manual exclusions

**Deletion handling:** Glob patterns are resolved at index time, not at generation time. If a previously-matched file is later deleted, the glob simply stops matching it — no cleanup of `.raginclude` needed.

### 1. Detect Project Stack

Scan project root for framework indicators:

| File/Dir | Stack |
|----------|-------|
| `next.config.*` | Next.js |
| `package.json` | Node.js |
| `pyproject.toml` / `setup.py` | Python |
| `requirements.txt` + `discord` dependency | Python Discord Bot (e.g. a Discord bot project) |
| `Cargo.toml` | Rust |
| `go.mod` | Go |
| `prisma/schema.prisma` | Prisma ORM |
| `docker-compose.yml` | Docker |
| `plugin.json` + `skills/` dir | Claude Code plugin |
| `CLAUDE.md` or `AGENTS.md` alone | Claude Code / AI-native app |

Read `package.json` (or equivalent) for framework-specific dependencies.

### 2. Select File Patterns

#### ALWAYS include

| Category | Example patterns | Why |
|----------|-----------------|-----|
| Documentation | `README.md`, `docs/**/*.md`, `CHANGELOG.md`, `Features.md` | Primary knowledge source |
| AI/agent context | `AGENTS.md` | How the AI assistant is configured — see CLAUDE.md caveat below |
| API routes | `app/api/**/route.ts`, `pages/api/**/*.ts` | Endpoint documentation |
| Schema/models | `prisma/schema.prisma`, `**/schema.graphql` | Data structure reference |
| Type definitions | `types/**/*.ts`, `**/types.ts` | Public interfaces |
| Config (non-secret) | `next.config.*`, `tsconfig.json`, `package.json` | Stack context |
| Public constants | `lib/products.ts`, `**/constants.ts` | Feature definitions |
| Notes/plans (docs only) | `docs/plans/**/*.md` | Feature context — **audit before including `Notes/**`** |

#### NEVER include

| Category | Why |
|----------|-----|
| `.env*`, `*secret*`, `*.pem`, `*.key` | Security — credentials |
| `config.yaml`, `config.yml` (actual config, not example) | May contain real API keys — always exclude live config |
| `node_modules/**`, `.venv/**`, `.venv_linux/**` | Not project-specific |
| `.next/**`, `dist/**`, `build/**` | Generated artifacts |
| `lib/generated/**`, `prisma/migrations/**` | Auto-generated |
| `*.png`, `*.jpg`, `*.mp4`, `*.woff*` | Not text-indexable |
| `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock` | Noise |
| `.git/**` | Not authoritative |
| `infra/lambda/**`, `infra/**` | Infrastructure internals |
| `scripts/**/*.py`, `Scripts/**/*.py`, `scripts/**/*.sh`, `Scripts/**/*.sh` | Internal ops tooling — but `Scripts/**/*.md` may be user-facing command docs (include those) |
| `*Deployment*.md`, `*Deploy*.md`, `AWS_*.md` | Infrastructure details — server IPs, SSH keys, instance IDs |
| `*Security_Audit*.md`, `*OAUTH*.md`, `*AUTH_GUIDE*.md` | Security internals and auth implementation details |
| `Notes/**` | Usually internal plans, compliance notes, roadmap — audit before including; exclude by default |

#### CONDITIONALLY include

| Category | Include when |
|----------|-------------|
| `components/**/*.tsx` | UI framework detected; helps explain UI features |
| `middleware.ts`, `lib/auth.ts` | Auth/routing middleware exists |
| `lib/**/*.ts` | Defines public behavior (exclude internal helpers) |
| `skills/**/*.md` | Claude Code plugin detected (has `plugin.json` + `skills/` dir) |
| `agents/**/*.md` | Claude Code plugin with agents detected |
| `commands/**/*.md` | Claude Code plugin with slash commands detected |
| `hooks/**/*.md` | Claude Code plugin with hooks detected |
| `plugin.json` | Claude Code plugin manifest |
| `Scripts/**/*.md` | Python Discord bot: command reference docs; always include |
| `personalities.md`, `*_USER_GUIDE.md` | Python Discord bot user-facing guides |
| `config.example.yaml` | Python Discord bot: shows configurable options without real secrets |

### 3. Open-Source Check

**If the project is open-source**, the trade-secret filter mostly doesn't apply. Committed documentation is intentionally public. Use broad glob patterns and let `.gitignore` handle exclusions:

```
*.md
Docs/**/*.md
requirements.txt   # or package.json, etc.
```

This is simpler, stays current automatically, and lets you use the repo to educate developers (code reviews, implementation notes, LLM contracts, etc. are all useful context).

**Still exclude even in open-source:**
- `*.log` — runtime logs, not useful; may be on disk but not gitignored
- `.env`, `config.json`, `*.key` — credentials that may exist locally even if gitignored

### 4. Trade-Secret Filter (private/commercial projects)

REMOVE patterns that would expose:
- Proprietary algorithms or business logic
- Internal pricing formulas or margin calculations
- Unreleased feature code or roadmap items not yet shipped
- Security infrastructure details (HMAC signing, token verification, session internals)
- AI provider API keys, model IDs, or internal routing/cost logic
- Lambda/serverless implementation internals (streaming mechanism, S3 payload approach, etc.)
- Admin-only routes or tools not accessible to regular users
- Database connection pooling or infrastructure configuration

**Rule:** If a file describes *what* the app does for users or *how to use it* — include. If it describes *how it's built internally* with no user-facing value — exclude.

**For AI-native apps:** Include docs about AI features available to users (e.g., which AI commands exist, what the assistant can do). Exclude which specific providers, API keys, cost routing logic, or internal model selection strategies are used behind the scenes.

**`CLAUDE.md` caveat:** `CLAUDE.md` is valuable for RAG context but must be audited before inclusion. It commonly contains infrastructure secrets: server IPs, SSH key paths, EC2 instance IDs, internal deployment commands, and admin credentials. If `CLAUDE.md` contains such details, either exclude it or confirm a sanitized version exists for RAG indexing. Prefer `AGENTS.md` if it covers only behavioral context.

### 4. Write .raginclude

```
# Project: {name} — .raginclude for RAG knowledge base
# Generated: {date}
# Stack: {detected stack}
#
# Glob patterns are resolved at index time.
# Deleted files are automatically excluded — no manual cleanup needed.
# Include files that document how the app works for users.
# Exclude secrets, build artifacts, and proprietary implementation details.

# Documentation
{doc patterns}

# AI & Agent Context
{CLAUDE.md / AGENTS.md / skill patterns if applicable}

# API Surface
{api patterns}

# Data Models & Schema
{schema patterns}

# Configuration & Constants
{config patterns}

# Additional Context
{conditional patterns}
```

### 5. Verify

After writing:
1. Show active pattern count (non-comment, non-blank lines)
2. Spot-check 2-3 matched files for appropriateness
3. Warn if any pattern matches 0 files (stale or wrong path)
4. Confirm `.raginclude` **is committed to git** — it contains no secrets and should be version-controlled alongside the codebase

> **Important:** `.raginclude` should NOT be in `.gitignore`. It is a configuration file with no sensitive content.

## Framework-Specific Patterns

See `references/framework-patterns.md` for detailed per-framework pattern sets, including Python Discord bots and Claude Code plugins.
