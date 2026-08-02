# CodeMap Workflow Template

Adapt this script for the Workflow tool. Placeholders to fill before launching:
`args` gets `{ groups, inventoryPath, specPath, guidelinePaths, codeMapPath, mode, timestamp }`
built during the inline scout. Each *group* is
`{ key, files: [...], sectionHeading }` — ≤ ~8k source lines per group; a giant
file (>5k lines) gets its own group.

Pass real values via `args` (arrays as JSON, not strings). `Date.now()` is
unavailable inside workflow scripts — pass `timestamp` in.

```javascript
export const meta = {
  name: 'update-code-map',
  description: 'Regenerate CodeMap sections in parallel with verified line numbers',
  phases: [
    { title: 'Document', detail: 'one agent per module group' },
    { title: 'Dependencies', detail: 'cross-file dependency map' },
    { title: 'Verify', detail: 'spot-check line numbers against source' },
  ],
}

// args can arrive JSON-encoded as a string — parse defensively or every
// A.<field> access silently becomes undefined ("pipeline() expects an array").
const A = typeof args === 'string' ? JSON.parse(args) : args

const SECTION_SCHEMA = {
  type: 'object',
  required: ['heading', 'markdown'],
  properties: {
    heading: { type: 'string' },
    markdown: { type: 'string', description: 'Complete CodeMap section markdown' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  required: ['checked', 'mismatches'],
  properties: {
    checked: { type: 'integer' },
    mismatches: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim', 'actual'],
        properties: { claim: { type: 'string' }, actual: { type: 'string' } },
      },
    },
  },
}

const docPrompt = (g) => `You are documenting one section of a CodeMap (codebase
navigation guide). Work from the repo root.

<instructions>
1. Read the symbol inventory at ${A.inventoryPath} and extract ONLY the
   entries for these files: ${g.files.join(', ')}.
2. Every line number you write MUST be copied verbatim from the inventory.
   Never estimate or count lines yourself. If a number seems wrong, re-read
   the inventory entry — never publish a guessed number or an uncertainty
   footnote ("might be line X?").
3. For prose (what a class/function does), read the source near the inventory
   line numbers. For files over 5000 lines, read selectively around symbols —
   never the whole file.
4. Follow the section format in the spec at ${A.specPath} and the
   language-specific table formats in: ${A.guidelinePaths.join(', ')}.
5. Include per-file line counts from the inventory's "lines" field.
6. Return the finished markdown for the section "${g.sectionHeading}".
</instructions>`

const sections = await pipeline(
  A.groups,
  (g) => agent(docPrompt(g), { label: `doc:${g.key}`, phase: 'Document', schema: SECTION_SCHEMA }),
)

// Barrier is correct here: the dependency map needs every section's summary.
const deps = await agent(`Read the symbol inventory at ${A.inventoryPath}.
Using these documented sections as orientation:
${sections.filter(Boolean).map((s) => s.heading).join('\n')}
Grep the codebase for imports/usages between the main modules and write the
"Cross-File Dependencies" CodeMap section (spec: ${A.specPath}). Every
file:line reference must come from the inventory or a grep -n result you ran.`,
  { label: 'deps', phase: 'Dependencies', schema: SECTION_SCHEMA })

// Verification: independent spot-checkers, one per documented section.
const verified = await pipeline(
  sections.filter(Boolean).concat(deps ? [deps] : []),
  (s, _item, i) => agent(`Adversarially verify this CodeMap section. For at
least 12 of its file:line claims (or all, if fewer), run: sed -n '<LINE>p' <FILE>
and check the source line actually contains the named symbol. Report every
mismatch.\n\n<section>\n${s.markdown}\n</section>`,
    { label: `verify:${i}`, phase: 'Verify', schema: VERIFY_SCHEMA })
    .then((v) => ({ section: s, verify: v })),
)

return {
  sections: verified.filter(Boolean).map((r) => r.section),
  verification: verified.filter(Boolean).map((r) => ({
    heading: r.section.heading,
    checked: r.verify?.checked ?? 0,
    mismatches: r.verify?.mismatches ?? [],
  })),
}
```

## After the workflow returns

The main agent (you) assembles mechanically:

1. Any `mismatches`? Fix those entries from the inventory (the inventory is
   ground truth) — do not re-run the whole workflow.
2. Stitch: header + timestamp, Quick Navigation, architecture diagram,
   project structure, the returned sections in spec order, then the static
   tail sections (Architecture Patterns, Development Guidelines, Performance
   Considerations — carry over from the old CodeMap unless stale).
3. In INCREMENTAL mode, splice regenerated sections into the existing
   CodeMap, leaving untouched groups' sections as-is.
4. Box-alignment check on ASCII diagrams: every line between a box's `┌...┐`
   and `└...┘` must have identical display width — verify with a short python
   one-liner, not by eye. Check carried-over diagrams too; they can be
   misaligned already.
5. Two-pass TOC mechanically, as the VERY LAST edit: any content change after
   filling the TOC (even removing one duplicate heading) shifts every number.
   Write final content, `grep -n "^## " Docs/CodeMap.md`, fill in the numbers,
   then verify each TOC entry points at its heading before installing.
6. Final gate: random-sample ~25 `file:line` claims from the assembled file
   and check each with `sed -n '<line>p'` — install only on PASS.
