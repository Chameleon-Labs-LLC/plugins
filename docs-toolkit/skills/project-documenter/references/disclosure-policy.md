# Disclosure Policy — What May and May Not Appear in User-Facing Docs

These docs are written for **customers and the public**, and are indexed into a RAG
knowledge base that answers support questions. Anything in them can end up in front
of a user or a competitor. The goal: **help users help themselves without handing out
the keys to the castle.**

Both the doc-writing agents (defense in depth) and the dedicated **disclosure
reviewer** apply this policy. The reviewer is the gate of record.

## SAFE to disclose (this is the job — be generous here)

- What a feature does and **how to use it**, step by step
- Navigation: where pages/buttons are, how to get from A to B
- Plan/tier differences expressed in **product terms** ("Pro includes X")
- **User-facing limits** stated as the user experiences them ("free tier: 5 messages/hour",
  "uploads up to 25 MB") — these help users, and they already hit them
- Settings, options, and what each one controls
- Supported file types, integrations a user can connect, exportable formats
- Common errors a user can see and **how to resolve them**

## DO NOT disclose (redact — these are the keys to the castle)

**Infrastructure & internals**
- AWS/cloud resource names: Lambda function names, S3 bucket names, IAM roles,
  EC2 hostnames, RDS endpoints, ARNs, Function URLs
- Internal API route paths, service-to-service endpoints, internal hostnames
- Database schema, table/column names, model internals
- Internal architecture detail that isn't needed to *use* the product

**Secrets & security mechanics**
- Any secret, API key, token, password, env-var **value**, connection string
- Env-var **names** that reveal infra (`*_SERVICE_KEY`, `*_SECRET`, signing keys)
- How auth/signing works under the hood (HMAC schemes, webhook signature verification,
  service-key headers, session internals) — anything that helps someone **bypass** a control
- Exact security thresholds whose value is in being secret (lockout internals,
  anti-abuse heuristics, fraud rules). User-facing rate limits are fine; the
  *evasion-relevant* internals are not.

**Business & strategy**
- Pricing **formulas**, cost structure, margins, vendor/wholesale costs
- Proprietary algorithms, model prompts, ranking/scoring logic, trade-secret methods
- Internal roadmap, unreleased or feature-flagged capabilities not yet public
- Revenue figures, customer counts, internal metrics

**Access & scope**
- Admin-only or internal-only capabilities described as if available to ordinary users
  (documenting the existence of an admin panel to customers, internal ops tooling, etc.)
- Anything gated behind staff/admin roles that a customer cannot reach

**PII**
- Real customer names, emails, account IDs, or any identifying data pulled from code,
  fixtures, or seed data

## When unsure

Ask: *"Does a customer need this to use or troubleshoot the product?"*
- **Yes** → keep it, in user terms.
- **No, and it exposes how we're built or run** → redact and note it in the report.

Borderline items are **flagged for human review**, not silently kept.
