---
name: project-documenter
description: "Generate user-facing feature documentation, Google sitemap, and navigational site map for any project. Writes markdown docs to the project's docs directory, generates sitemap.xml for SEO, and updates .raginclude for RAG indexing. Uses parallel agents to document multiple feature areas simultaneously. For developer/technical docs (API endpoints, data models, error handling), use the technical-documenter skill instead. Triggers on: 'document this project', 'generate feature docs', 'write support documentation', 'create product docs', 'document all features', 'update project documentation', 'generate sitemap'."
---

# Project Documenter

Generate user-facing feature documentation, a Google sitemap, and a navigational site map for any project using parallel agents. Docs are written for end users — no technical/developer details. New docs are appended to `.raginclude` for RAG indexing. For developer documentation (API endpoints, data models, error handling), use the `technical-documenter` skill.

## Process

### Phase 1: Scout

Scan the project to build a feature map and establish conventions.

#### Step 1a: Detect Project Conventions

Before writing anything, determine the project's directory conventions:

1. **List the project root** — run `ls -la` at the project root
2. **Check for existing doc directories** — look for `docs/`, `Docs/`, `documentation/`, `doc/`
3. **Set `$DOCS_DIR`** — use whatever the project already has. If none exists, default to `Docs/`
4. **Check for existing feature docs** — list contents of `$DOCS_DIR/Features/` (or equivalent) to identify docs that already exist and will be overwritten

If existing docs are found, note them and inform the user which files will be replaced during the approval step.

#### Step 1b: Scan Source Files

First, **classify the project**, because the user-facing surface lives in different places depending on type:

- **Web app** (has `app/`, `pages/`, `src/routes/`) — features live in routes/pages **and** interactive components. Use the full list below.
- **CLI tool** (has a `bin/`, `cli`, `argparse`/`click`/`commander`/`cobra` usage, or a `[project.scripts]`/`bin` entry) — the user-facing surface is **commands, subcommands, flags, and their help text**, not routes. Enumerate every command and option; treat each command group as a feature area.
- **Library / SDK** — the surface is the **public/exported API** (exported functions, classes, types) and its usage examples. Treat each public module as a feature area.
- **Desktop / TUI app** — the surface is **menus, panels, keyboard shortcuts, and dialogs**.

Then read these files (adapt to the project type above):

1. **package.json / pyproject.toml / Cargo.toml / go.mod** (or equivalent) — project name, description, entry points, `bin`/`scripts`
2. **Route/page files** — `app/**/page.tsx`, `pages/**/*.tsx`, `src/routes/**`
3. **API routes** — `app/api/**/route.ts`, `pages/api/**`
4. **Interactive components** — `components/**`, `src/components/**`, `app/**/_components/**`. **Do not skip this.** Many user-facing features are not routes: modals, dialogs, drawers, command palettes, bulk/multi-select actions, export/import, search & filter & sort, toggles (e.g. dark mode), notification bells, toasts, keyboard shortcuts, drag-and-drop. Read component files and the settings/preferences sub-components a page renders, not just the page shell.
5. **CLI / command definitions** — `bin/**`, `cli/**`, `**/commands/**`, `**/__main__.py`, argparse/click/commander/cobra setup (for CLI projects)
6. **Layouts & middleware** — `app/layout.tsx`, `middleware.ts`, `src/layouts/**`
7. **Context providers** — `src/context/**`, `app/providers.tsx`, `lib/providers/**`
8. **Schema** — `prisma/schema.prisma`, `**/models/**`, `src/services/db.ts`
9. **User-facing emails & notifications** — `emails/**`, `**/templates/**`, `lib/email/**`, `lib/notify/**`, any Discord/Slack/SMS dispatch. Transactional emails (welcome, receipt, password-reset), digests, and in-app notifications are real user touchpoints even though they aren't pages.
10. **Existing docs** — `$DOCS_DIR/**/*.md`, `README.md`
11. **Product config** — `lib/products.ts`, `lib/config.ts`, `src/config/**`. **Monorepos:** if the repo hosts multiple products, segment feature areas per product rather than blending them into one flat set.

#### Step 1c: Build Feature Map

From the scanned files, identify **feature areas** — groups of related user-facing functionality. Typical areas:

| Area | What to look for |
|------|-----------------|
| Authentication | Auth routes, sign-in/sign-up pages, password reset, OAuth providers |
| User Account | Profile, settings, preferences pages (including each toggle/option rendered by sub-components) |
| Billing | Stripe routes, subscription pages, pricing |
| Products/Apps | Product pages, app dashboards, feature pages |
| Chat/AI | Chat components, AI routes, model config |
| In-page / interactive features | Modals, dialogs, command palettes, bulk actions, export/import, search & filter & sort, dark-mode toggle, keyboard shortcuts, drag-and-drop — features that live in components, not routes |
| Emails & notifications | Transactional emails, digests, in-app notifications, Discord/Slack/SMS messages users receive |
| CLI commands | Each command/subcommand and its flags (CLI projects) |
| Admin | Admin pages, admin API routes |
| API/Integrations | OAuth, webhooks, external API routes |

> The agent that *writes* each doc only ever sees the files you bin into its area here. A feature you miss in this map is a feature that never gets documented — the Phase 4 completeness pass is the backstop, but bin thoroughly now.

Also build a **route inventory** for sitemap generation — a list of every public route with:
- Path (e.g., `/dashboard`, `/inventory`)
- Page title or description
- Whether it requires authentication
- Associated source file

Finally, capture an **authoritative feature menu** — the single best source of "everything a user can reach." This is what the Phase 4 completeness pass checks the docs against. Use whichever exists:
- Web: the nav bar / sidebar / bottom-nav component, plus the route inventory
- CLI: the top-level `--help` command list (every command and subcommand)
- Library: the package's exported/public API surface
- Desktop/TUI: the menu tree

Save this list — the completeness reviewer needs it.

Present the feature map, route inventory, authoritative menu, and any files that will be overwritten to the user for approval before proceeding.

### Phase 2: Document (parallel agents)

Spawn one `general-purpose` agent per feature area using the **Task tool**. Each agent:

1. **Reads** the relevant source files for its area
2. **Writes** one markdown file to `$DOCS_DIR/Features/` following the template in `references/doc-template.md`
3. Reports back with the file path written

**Dispatch pattern:**

```
Task tool call:
  subagent_type: "general-purpose"
  name: "doc-{area-slug}"
  description: "Document {area name} features"
  mode: "acceptEdits"
  prompt: |
    You are documenting the {area name} features of {project name}.

    Read these files to understand the feature:
    {list of files for this area}

    Write a markdown documentation file to: {$DOCS_DIR/Features/area-name.md}
    Follow this structure exactly:

    # {Area Name}

    ## Overview
    Brief description of what this feature area does.

    ## Features
    ### {Feature 1}
    - What it does
    - How to use it
    - Available options/settings

    ### {Feature 2}
    ...

    ## Common Questions
    Q&A format — anticipate what users would ask.

    These docs are public and indexed for customer support. Follow the disclosure
    policy in references/disclosure-policy.md: document what users need to use and
    troubleshoot the feature, but do NOT include infrastructure names, secrets,
    env-var names, internal API paths, auth/signing internals, pricing formulas,
    proprietary algorithms, admin-only capabilities, or PII. When unsure, omit it
    and note it for review.
```

Launch up to 4 agents in parallel. If more than 4 areas, batch them.

> Reference: `references/disclosure-policy.md` defines exactly what is SAFE vs DO-NOT-DISCLOSE. The writing agents apply it as a first filter; the Phase 4 disclosure reviewer is the gate of record.

### Phase 3: Sitemap & Navigation

After all documentation agents complete, generate two outputs:

#### 3a: Google Sitemap

Generate a sitemap for search engine crawling. Auto-detect the framework:

**Next.js (App Router)** — Create `app/sitemap.ts`:
```typescript
import type { MetadataRoute } from 'next';

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://example.com';
  return [
    { url: baseUrl, lastModified: new Date(), changeFrequency: 'weekly', priority: 1.0 },
    // ... one entry per public route from the route inventory
  ];
}
```

**Static / other frameworks** — Create `public/sitemap.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{baseUrl}/</loc><lastmod>{date}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>
  <!-- one entry per public route -->
</urlset>
```

**Sitemap rules:**
- Only include public (non-authenticated) routes. Auth-required pages get lower priority (0.3) or are omitted depending on user preference.
- Use `NEXT_PUBLIC_SITE_URL` or equivalent env var for the base URL. If not set, leave a placeholder and warn the user.
- Set `lastModified` from git timestamps when available: `git log -1 --format="%cI" -- {source-file}`
- Landing/home page = priority 1.0, core feature pages = 0.8, secondary pages = 0.5

#### 3b: Site Navigation Doc (for RAG)

Generate `$DOCS_DIR/Features/site-navigation.md` — a human-readable navigational guide:

```markdown
# Site Navigation

> A guide to every page in {project name} and how to find what you need.

## Public Pages (no sign-in required)

### Home (`/`)
{What the landing page shows. Key actions available.}

### Pricing (`/pricing`)
{What's on this page.}

## App Pages (sign-in required)

### Dashboard (`/dashboard`)
{What users see here. Key widgets/actions. How to get here: sign in → lands here automatically.}

### Inventory (`/inventory`)
{What this page does. How to navigate here: bottom nav → Items.}

...

## Navigation Reference

| Page | Path | Access | Nav Location |
|------|------|--------|-------------|
| Dashboard | `/dashboard` | Signed in | Bottom nav → Home |
| Inventory | `/inventory` | Signed in | Bottom nav → Items |
| ... | ... | ... | ... |
```

This doc helps RAG-powered chat answer "where do I find X?" and "how do I get to Y?" questions.

### Phase 4: Verify (completeness + disclosure)

This is the gate before anything is indexed for support. Run **two independent reviewer
agents in parallel** — they have opposite mandates, so keep them separate. Both read every
generated markdown file (the feature docs, `site-navigation.md`, and the README index).

Nothing reaches Phase 5 (RAG indexing) until disclosure review passes. **No doc is
published or indexed while a disclosure finding is unresolved.**

#### 4a: Completeness reviewer

**Mandate: find user-facing features that are MISSING from the docs.** Dispatch a
`general-purpose` agent:

```
Task tool call:
  subagent_type: "general-purpose"
  name: "verify-completeness"
  description: "Find undocumented user-facing features"
  prompt: |
    You are auditing documentation coverage for {project name}.

    Authoritative feature menu (everything a user can reach), captured in Phase 1:
    {paste the nav/sidebar list, route inventory, CLI --help command list, or public API surface}

    Generated docs to check:
    {list every file in $DOCS_DIR/Features/}

    For EACH item in the authoritative menu, confirm it is documented in the generated
    docs. Also re-scan components/, commands/, and email/notification templates for any
    user-facing feature (modal, bulk action, toggle, export, shortcut, transactional
    email, CLI flag) that appears in NEITHER the menu NOR the docs.

    Report ONLY gaps, as a list:
    - Feature name — where it lives (file/route/command) — why it's user-facing — which doc should cover it
    If coverage is complete, say "COMPLETE — no gaps." Do not rewrite docs.
```

For every gap reported, either dispatch a documenting agent to cover it (re-running the
relevant Phase 2 agent with the missing files) or, if it's intentionally out of scope,
record why. Re-run the completeness reviewer if you added docs.

#### 4b: Disclosure reviewer (trade-secret gate)

**Mandate: find anything in the docs that must NOT be shown to a customer**, and redact it.

**Scope = the publish manifest, not just the docs you generated.** If the project has a
`.raginclude` (or equivalent index manifest), resolve its patterns and review EVERY file
that will be indexed — pre-existing files included. The RAG boundary is the manifest;
a leaky legacy doc in `.raginclude` ships to customers just as surely as a new one.
Files that fail review and aren't part of this run's output should be removed from the
manifest (or relocated out of its globs), not silently left in place.

Dispatch a `general-purpose` agent:

```
Task tool call:
  subagent_type: "general-purpose"
  name: "verify-disclosure"
  description: "Redact trade secrets from user-facing docs"
  prompt: |
    You are the disclosure gate for public, customer-facing, RAG-indexed documentation
    of {project name}. Apply the policy in:
      {skill dir}/references/disclosure-policy.md

    Review every file in $DOCS_DIR/Features/ (including site-navigation.md and README.md),
    PLUS every additional file resolved from the project's .raginclude (or equivalent
    RAG manifest) — pre-existing files ship to customers too:
    {list any extra manifest-resolved files here}

    Flag and REDACT anything in the DO-NOT-DISCLOSE categories: infrastructure/resource
    names, secrets, env-var names, internal API paths, auth/signing internals, exact
    evasion-relevant security thresholds, pricing formulas/costs/margins, proprietary
    algorithms, internal roadmap / unreleased features, admin-only capabilities shown to
    users, and PII. Keep everything a customer genuinely needs to use or troubleshoot
    the product (user-facing limits and plan differences are SAFE).

    For each finding: edit the file to remove or rephrase the leak, then report:
    - file:line — category — what was removed — how you rephrased it (or "removed")
    Mark borderline cases "FLAG FOR HUMAN" and leave them in place but call them out.
    If a doc is clean, say so. End with a verdict: SAFE TO PUBLISH or NEEDS HUMAN REVIEW.
```

Present the disclosure reviewer's report (and any "FLAG FOR HUMAN" items) to the user.
**Do not proceed to Phase 5 until the verdict is SAFE TO PUBLISH** or the user clears the
flagged items.

### Phase 5: Index & RAG Integration

After all outputs are generated and the Phase 4 disclosure gate has passed:

1. **Create index file** — Write `$DOCS_DIR/Features/README.md` listing all generated docs with one-line descriptions
2. **Update .raginclude** — Read the existing `.raginclude` file (or create one if it doesn't exist). Ensure glob patterns cover all generated docs:
   ```
   # Feature documentation
   $DOCS_DIR/Features/**/*.md
   ```
   - If the pattern already exists, skip.
   - If `.raginclude` exists but lacks the pattern, append it.
   - If `.raginclude` doesn't exist, create it with the pattern plus a header comment.
   - Also add any other doc output files (e.g., `$DOCS_DIR/Environment-Variables.md`).
3. **Prompt for RAG indexing** — If the project has a RAG indexing script (e.g., `scripts/index-rag.ts`), remind the user to run it so the new docs are embedded and searchable:
   ```
   New docs are in .raginclude. To make them searchable in chat, run the indexing script:
     DATABASE_URL="..." OPENAI_API_KEY="..." npx tsx scripts/index-rag.ts --clean
   ```
   If no indexing script exists, note that the docs are ready for manual indexing.
4. **Report** — List all files created and their sizes, noting which were new vs replaced

## Output Structure

```
$DOCS_DIR/Features/
├── README.md                  (index of all feature docs)
├── site-navigation.md         (navigational guide for RAG)
├── authentication.md
├── user-account.md
├── billing-subscriptions.md
├── products.md
├── ai-chat.md
├── admin-panel.md
└── api-integrations.md

app/sitemap.ts                 (Next.js App Router)
  — OR —
public/sitemap.xml             (static/other frameworks)
```

## Doc Quality Rules

- **Write for end users** — as if explaining to a customer. No jargon, no API details.
- **Concrete over abstract** — "Click Settings > Profile" not "navigate to the profile management interface"
- **Include current behavior** — read the actual code, don't guess. If a feature has limits (e.g., "5 messages per hour for free tier"), state them.
- **No trade secrets** — omit internal pricing formulas, proprietary algorithms, security/infrastructure details, secrets, env-var names, internal API paths, admin-only capabilities, and PII. The full policy is `references/disclosure-policy.md`; the Phase 4 disclosure reviewer enforces it before anything is indexed.
- **Respect existing work** — when replacing existing docs, preserve any manually-added content that isn't auto-generated (look for markers like `<!-- manual -->` or sections not matching the template)

## Doc Template

See `references/doc-template.md` for the full template each agent should follow.
