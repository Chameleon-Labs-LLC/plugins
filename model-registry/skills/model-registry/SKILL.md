---
name: model-registry
description: Use when a project hardcodes LLM model IDs (claude-*, gpt-*, gemini-*) that go stale, when the user wants current model IDs resolved at runtime, or on /model-registry [install|migrate|status|refresh-fallback]. Works in TypeScript/Next.js, Python, and any project that can fetch JSON.
---

# Model Registry

Wire a project to the published model registry so it resolves **current** LLM model IDs
at runtime instead of hardcoding IDs that go stale.

- **Registry URL:** `https://chameleonlabs-model-registry.s3.us-east-1.amazonaws.com/models/latest.json` (public, refreshed daily ~3 AM by `agents/model-discovery/` in the ChameleonLabs repo)
- **Canonical clients (source of truth):** https://github.com/Chameleon-Labs-LLC/model-registry-client — Python (`python/src/model_registry/client.py`) + TypeScript (`typescript/registry.ts`), both zero-dependency and vendorable
- **Env override:** `MODEL_REGISTRY_URL` points clients at a different registry

## Schema (v2)

| Key | Meaning |
|-----|---------|
| `families[provider][family]` | **primary lookup** — current model ID, e.g. `families.anthropic.opus` → `"claude-opus-4-8"` |
| `families_detail[provider][family]` | `{active, stable?, preview?}` channels |
| `available[provider]` | full curated ID list |
| `capabilities[model_id]` | `{context_window}` |
| `unmatched[provider]` | IDs with no family (never migrate these to family lookups) |
| `schema_version`, `fetched_at`, `providers_ok` | validate `schema_version >= 2`; `fetched_at` age = staleness |

Families: anthropic `opus|sonnet|haiku`; openai `gpt|gpt-mini|gpt-nano|gpt-pro|chat`; gemini `pro|flash|flash-lite`.

## Verbs (`/model-registry <verb>`)

**No args** → show this verb table and ask which to run.

**`install`** — detect project type, then:
1. Get the client in: Python → offer `pip install "chameleonlabs-model-registry @ git+https://github.com/Chameleon-Labs-LLC/model-registry-client#subdirectory=python"` OR vendor `client.py` (single file, stdlib-only — prefer vendoring for projects with no dep management). TypeScript → vendor `registry.ts` (fetch raw from the repo). Other languages → port from the canonical client; behavior contract below.
2. Snapshot the fallback: `curl -sf <registry-url> -o <project>/model-registry.fallback.json` — place it **beside the project's central models module** (e.g. next to `llm_models.py` / `lib/ai/`). If installing via pip, also add the git URL line to `requirements.txt`/`pyproject.toml`.
3. Wire the fallback into the client call (`fallback_path=` / `createRegistryClient({fallback})`).
4. Wire a refresh step: Amplify → prebuild curl in `amplify.yml`; other CI → equivalent; plain Python apps → document manual `refresh-fallback`.

**`migrate`** — grep for hardcoded IDs (`claude-[a-z0-9.-]+|gpt-[a-z0-9.-]+|gemini-[a-z0-9.-]+|o[0-9]-`), usually centralized in `llm_models.py` / `models.ts` / `constants`. For each: map to `resolve(provider, family)` if it belongs to a family **lineage** — older/dated variants map to their line (`gpt-4o` → `gpt`, `claude-sonnet-4-20250514` → `sonnet`, `gpt-4.1-mini` → `gpt-mini`); suffixes `-mini`/`-nano`/`-pro` pick the matching family. **Leave alone** anything in `unmatched`, pinned-for-a-reason IDs (ask if unsure), and non-chat models (tts/transcribe/image/embedding). Keep sync call sites reading the bundled fallback JSON; only async paths get live data. Propose diffs before applying; run the project's tests/`tsc` after.

**`status`** — fetch live registry; report `fetched_at` age, diff vs the project's bundled fallback (family IDs that changed), and any remaining hardcoded IDs from the migrate grep.

**`refresh-fallback`** — re-run the snapshot curl over the project's fallback file; show the family-level diff.

## Client behavior contract (for ports + reviews)

1-hour in-memory TTL cache; 5s fetch timeout; honor `MODEL_REGISTRY_URL`; validate `schema_version >= 2` + `families` present. Failure ladder: **serve cache (even expired) → serve bundled fallback → only then error.** With a fallback configured, never throw — model pickers must always work. Log failures to stderr/console. Ports use the language's idiomatic embed for the fallback (e.g. Rust `include_str!`); everything else above is the contract.

## Gotchas (production-proven, ChameleonLabs PR #223)

- **Node 24 native TS:** JSON imports need `with { type: "json" }` (`ERR_IMPORT_ATTRIBUTE_MISSING` otherwise).
- **Sync defaults:** modules needing a sync model ID at import time read the **bundled fallback JSON**, not a hardcoded ID — no drift, still synchronous.
- **Amplify:** refresh the fallback in the `preBuild` phase so each deploy ships a fresh last-known-good.
- ChameleonLabs (the web repo) already has its own wired consumer (`lib/ai/registry.ts`) — don't reinstall there.
