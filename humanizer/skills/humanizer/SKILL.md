---
name: humanizer
description: >-
  Strips AI fingerprints from writing and rewrites it in your own voice. Use this
  WHENEVER you want prose to sound human instead of AI-generated — both for cleaning
  up existing text and for drafting new text from scratch. Trigger on: "humanize
  this", "make this sound like me", "remove the AI tells", "de-slop this", "rewrite
  in my voice", pasting AI-sounding text and asking to fix it, OR any request to
  draft a LinkedIn post, blog post, email, newsletter, README intro, announcement,
  or other human-facing prose where generic AI phrasing would be a problem. Use it
  even when the user doesn't say the word "humanize" — if the deliverable is prose a
  person will read and it should not sound like a chatbot wrote it, this skill
  applies. Do NOT use for code, code comments, commit messages, structured data, or
  conversational chat itself.
---

# Humanizer

Most AI prose carries a fingerprint: a cluster of overused words, predictable sentence shapes, reflexive hedging, and tidy formatting that makes a reader's "a bot wrote this" alarm go off. This skill removes that fingerprint and replaces it with a specific human voice — the user's.

Two reference files do the work:

- **`references/writing_guardrails.md`** — the catalog of AI tells to avoid. Banned words, phrases, sentence structures, punctuation habits, formatting patterns. These are negative rules: things to *never* do. They apply to everything, every time.
- **The voice profile** — `~/.claude/humanizer/voice_profile.md` if it exists, otherwise the bundled `references/voice_profile.md` template. Rhythm, vocabulary, humor, how they open and close, what they value in writing. These are positive rules: the target the rewrite aims for.

The point is not to pass an "AI detector." The point is that the writing sounds like a specific person actually said it.

## The voice profile

Resolve the profile in this order:

1. **`~/.claude/humanizer/voice_profile.md`** — the user's personal profile, built by the `humanizer-setup` skill. It lives outside the plugin on purpose: plugin updates never overwrite it.
2. **`references/voice_profile.md`** — the bundled template with sane STARTER DEFAULTS. A workable baseline, but it's nobody's actual voice.

If you fall back to the template on a real writing task, offer once (not on every task): "Want me to build your voice profile from your actual writing? Say *set up humanizer*." Then get on with the writing — the template still works.

## When this fires

Two situations, same underlying job:

1. **De-AI existing text.** The user gives you prose (pasted, a file, a draft you just produced) and wants the AI smell gone. Rewrite it. Keep the meaning and structure; change the texture.
2. **Write fresh in-voice.** The user asks you to draft something new — a post, an email, a blog intro. Write it in their voice from the first word, not as generic AI prose you clean up afterward. (Though you should still self-check against the guardrails before handing it over.)

If you're unsure whether prose counts, lean toward using the skill. The cost of consulting two reference files is low; the cost of handing over chatbot-flavored writing under someone's name is high.

## How to do it

Always load both reference files before writing or rewriting. Read them fully — the guardrails list is long and specific, and skimming it defeats the purpose.

1. **Read `references/writing_guardrails.md`.** This is your "do not" list. The most important sections, because they're the most common tells: the banned verbs/adjectives/nouns (§1), the "it's not X, it's Y" negation pattern and self-posed questions (§4), em-dash overuse (§3), and the rhythm/burstiness tells (§6).

2. **Read the voice profile** (resolved per "The voice profile" above). This is your target voice. Where a section still shows a STARTER DEFAULT rather than a filled-in YOUR VERSION, use the default — it's a sane baseline — but know the filled-in sections carry more weight.

3. **Write or rewrite.** Hold both in mind at once. Strip every tell; aim for the voice.

4. **Read it back as if out loud.** This is the single most useful check. If a line sounds like it could appear verbatim in any other AI's output, it's not done. Rewrite it until it sounds like this specific person said it. Vary sentence length on purpose — humans swing from three-word fragments to long sprawling sentences; AI clusters everything around 15-20 words. If two sentences in a row are the same length, you're drifting back toward the fingerprint.

5. **Hand it over clean.** Give the user the rewritten text. If you cut something they might want back (a caveat, a specific claim), say so briefly. Don't narrate the guardrails you applied unless they ask.

## The handful that matter most

You will not memorize 200 banned words, and you don't need to. But these few tells account for most of the "AI wrote this" reaction, so internalize them:

- **Em dashes.** The number-one tell of the era. Use a comma, a period, parentheses, or a colon instead. Rewrite the sentence if you have to.
- **"It's not X, it's Y."** The single most recognizable AI sentence shape. Also its cousins: "not just X, but Y," "the question isn't X, it's Y." Kill all of them.
- **Self-posed questions.** "The best part? It's this." "The problem? Nobody noticed." AI asks a question nobody was asking, then answers it for drama. Don't.
- **The opener throat-clear.** "In today's fast-paced world," "Let's dive in," "It's worth noting that." Start in the middle of the actual thought.
- **The summary bow.** "In conclusion," "Overall," "At the end of the day." End on the thing you want them to carry out, or just stop.
- **Reflexive hedging and false balance.** "However, there are merits to consider." Have an opinion. Say something is bad if it's bad.
- **The Rule of Three.** One tricolon is elegant. Three in a row is a fingerprint. Break the pattern — use two, use four, get the rhythm wrong on purpose.

When everything else is right but the writing still feels off, it's almost always rhythm. Real writing is bursty and uneven. Make it uneven.

## Updating the voice profile

The voice profile improves over time. If the user reacts to a rewrite ("too stiff," "I'd never say 'leverage'," "that's exactly right"), that's signal — fold it into `~/.claude/humanizer/voice_profile.md` so the next rewrite starts closer. If that file doesn't exist yet, copy the bundled template there first, then fold the correction in. Never write corrections into the bundled `references/voice_profile.md` — plugin updates overwrite it. The guardrails file rarely changes; the voice file is meant to.
