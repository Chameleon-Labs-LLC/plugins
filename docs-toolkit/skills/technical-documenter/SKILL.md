---
name: technical-documenter
description: "Generate developer and support-staff documentation for any project. Covers API endpoints, data models, error handling, configuration, and architecture. Outputs to $DOCS_DIR/Developer/ and is NOT added to .raginclude. Uses parallel agents to document multiple feature areas simultaneously. For user-facing docs, use the project-documenter skill instead. Triggers on: 'generate technical docs', 'document the API', 'create developer docs', 'write technical documentation', 'document endpoints', 'generate dev docs'."
---

# Technical Documenter

Generate developer and support-staff documentation for any project using parallel agents. Covers API endpoints, data models, error handling, configuration, and architecture. Outputs to `$DOCS_DIR/Developer/` and is **not** added to `.raginclude`. For user-facing documentation, use the `project-documenter` skill.

## Process

### Phase 1: Scout

Scan the project to build a feature map and establish conventions.

#### Step 1a: Detect Project Conventions

Before writing anything, determine the project's directory conventions:

1. **List the project root** — run `ls -la` at the project root
2. **Check for existing doc directories** — look for `docs/`, `Docs/`, `documentation/`, `doc/`
3. **Set `$DOCS_DIR`** — use whatever the project already has. If none exists, default to `Docs/`
4. **Check for existing developer docs** — list contents of `$DOCS_DIR/Developer/` (or equivalent) to identify docs that already exist and will be overwritten

If existing docs are found, note them and inform the user which files will be replaced during the approval step.

#### Step 1b: Scan Source Files

Read these files (adapt to project structure):

1. **package.json** (or equivalent) — project name, description, dependencies
2. **API routes** — `app/api/**/route.ts`, `pages/api/**`
3. **Middleware** — `middleware.ts`, auth middleware, rate limiters
4. **Schema** — `prisma/schema.prisma`, `**/models/**`, `src/services/db.ts`
5. **Config files** — `.env.example`, `next.config.js`, `tsconfig.json`
6. **DB helpers** — `lib/db/**`, `src/services/**`
7. **Auth config** — `auth.ts`, `lib/auth/**`, NextAuth/Clerk/etc. setup
8. **Existing docs** — `$DOCS_DIR/**/*.md`, `README.md`

#### Step 1c: Build Feature Map

From the scanned files, identify **technical areas** — groups of related backend/infrastructure functionality. Typical areas:

| Area | What to look for |
|------|-----------------|
| Authentication & Auth | Auth config, session management, middleware, OAuth providers |
| API Layer | API routes, request validation, response formats |
| Database & Models | Schema, migrations, DB helpers, seed data |
| Billing & Payments | Stripe integration, webhook handlers, subscription logic |
| Email & Notifications | SES/SendGrid config, email templates, notification triggers |
| Background Jobs | Queue workers, cron jobs, Lambda functions |
| External Integrations | Third-party API clients, webhooks, OAuth flows |
| Infrastructure | Deployment config, env vars, CI/CD, hosting |

Present the feature map and any files that will be overwritten to the user for approval before proceeding.

### Phase 2: Document (parallel agents)

Spawn one `general-purpose` agent per technical area using the **Task tool**. Each agent:

1. **Reads** the relevant source files for its area
2. **Writes** one markdown file to `$DOCS_DIR/Developer/` following the template in `references/dev-doc-template.md`
3. Reports back with the file path written

**Dispatch pattern:**

```
Task tool call:
  subagent_type: "general-purpose"
  name: "dev-doc-{area-slug}"
  description: "Document {area name} technical details"
  mode: "acceptEdits"
  prompt: |
    You are documenting the technical details of {area name} for {project name}.

    Read these files to understand the implementation:
    {list of files for this area}

    Write a markdown documentation file to: {$DOCS_DIR/Developer/area-name.md}
    Follow this structure exactly:

    # {Area Name}

    ## Overview
    Brief technical description of this area's role in the system.

    ## API Endpoints
    | Method | Path | Purpose | Auth Required |
    |--------|------|---------|---------------|

    ## Data Model
    Key tables/models with field descriptions.

    ## Error Handling
    | Error | Cause | Resolution |
    |-------|-------|------------|

    ## Configuration
    Environment variables and config that affects this area.

    ## Architecture Notes
    How this area connects to other parts of the system.
```

Launch up to 4 agents in parallel. If more than 4 areas, batch them.

### Phase 3: Index & Report

After all documentation agents complete:

1. **Create index file** — Write `$DOCS_DIR/Developer/README.md` listing all generated docs with one-line descriptions
2. **Do NOT update .raginclude** — developer docs are excluded from the RAG pipeline by design
3. **Report** — List all files created and their sizes, noting which were new vs replaced

## Output Structure

```
$DOCS_DIR/Developer/
├── README.md                  (index of all developer docs)
├── authentication.md
├── api-layer.md
├── database-models.md
├── billing-payments.md
├── email-notifications.md
├── background-jobs.md
├── external-integrations.md
└── infrastructure.md
```

## Doc Quality Rules

- **Write for developers and support staff** — assume familiarity with the tech stack
- **Include exact paths, status codes, and field names** — precision matters for debugging
- **Document actual behavior** — read the code, don't guess. Include rate limits, validation rules, error codes.
- **No trade secrets** — omit internal pricing formulas, proprietary algorithms, security infrastructure details
- **Respect existing work** — when replacing existing docs, preserve any manually-added content that isn't auto-generated (look for markers like `<!-- manual -->` or sections not matching the template)

## Doc Template

See `references/dev-doc-template.md` for the full template each agent should follow.
