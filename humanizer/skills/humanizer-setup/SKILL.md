---
name: humanizer-setup
description: >-
  Builds or updates your personal voice profile for the humanizer skill. Use when
  the user says "set up humanizer", "set up my voice", "create my voice profile",
  "build my voice profile", "import my writing samples", "add this to my voice
  profile", or "update my voice profile" — or when the humanizer skill offered to
  build a profile and the user said yes. Walks the user through importing real
  writing samples (pasted text, files they pick, sent emails they select) and
  distills them into ~/.claude/humanizer/voice_profile.md, which survives plugin
  updates. Do NOT use for actually rewriting or drafting prose — that's the
  humanizer skill.
---

# Humanizer Setup

The humanizer skill rewrites prose to sound like a specific person. This skill builds the profile that tells it who that person is. It creates `~/.claude/humanizer/voice_profile.md` (outside the plugin, so plugin updates never touch it) and fills it by distilling the user's real writing.

Ground rules, and say them to the user up front: everything stays local under `~/.claude/humanizer/`. Nothing gets uploaded or shared. Disk and email access are opt-in, and the user picks every individual item that gets imported.

## Step 1: Name

Run `git config user.name`. Confirm with the user: "Should I build the profile for <first name>?" Use their first name from then on. Only ask for a name if git has no answer or they correct you.

## Step 2: Create the files

```bash
mkdir -p ~/.claude/humanizer/raw_samples
```

Copy the bundled template into place. The template lives in the sibling skill: `${CLAUDE_PLUGIN_ROOT}/skills/humanizer/references/voice_profile.md` (equivalently, `../humanizer/references/voice_profile.md` relative to this skill's base directory). Copy it to `~/.claude/humanizer/voice_profile.md`.

If `~/.claude/humanizer/voice_profile.md` already exists, don't overwrite it — treat this run as an update (see "Re-runs and updates").

Then edit the new file's header: retitle it `# TEXT DNA BIBLE — <First name>` and add a line directly under the title: `Last updated: <today's date>` (get the real date with `date '+%Y-%m-%d'`).

## Step 3: Gather writing samples

Best sources first. Offer the ones that apply and let the user choose. Save every imported sample to `~/.claude/humanizer/raw_samples/<short-name>.md` with a one-line header noting source and date.

**a. Direct.** Anything they paste or a file they point you at. The best samples are casual and real: posts, emails to friends or colleagues, blog paragraphs they're proud of. Formal documents they wrote to sound corporate are the worst samples — they hide the voice.

**b. Disk scan — ask first.** Offer: "Want me to look for writing of yours on disk? I'll show you a list and you pick. I won't import anything you don't choose." Good hunting grounds:

- READMEs and docs in their git repos where `git log --author="<name>" --format=%H -- <file>` shows they wrote it
- Blog-post folders: directories named `posts/`, `blog/`, `_posts/`, `content/`
- Social-media data exports in `~/Downloads` or `~/Documents`: LinkedIn exports (`Shares.csv`), Twitter/X archives (`tweets.js`)
- `~/Documents` for essays, newsletters, talks

Present candidates as a list (path, first line, modified date). Import only what they select. Never import an unselected file.

**c. Sent email — ask first, and only if available.** Check your available tools for a connected email integration (Gmail, Outlook, or similar MCP). If there is none, skip this option silently — don't advertise it. If there is one:

1. Ask permission explicitly: "I can pull a few of your sent emails as voice samples. Want me to search your sent mail and show you candidates to pick from?"
2. Search **sent** mail only — never the inbox, never anyone else's words.
3. Show a candidate list: subject, date, first line.
4. Import only the messages the user selects.
5. Before saving, strip quoted replies, signatures, and legal footers. Only the user's own words go in the profile.

**No samples at all?** Fall back to interview-only (the Step 4 questions). The result is still far better than the raw template.

## Step 4: Distill

Samples are *evidence of voice*, not text to copy. Read them looking for:

- Rhythm: sentence lengths, fragments, parentheticals, how bursty the writing is
- Vocabulary: pet words, plain vs. fancy, contractions, idioms
- Punctuation and emoji habits
- How they open and how they close
- Directness, hedging, humor, warmth

Fill in the matching numbered sections of the profile, replacing each YOUR VERSION line you have evidence for. Quote tiny phrases from the samples as examples, the way a style guide would. Leave STARTER DEFAULTS in place for sections with no evidence.

Then interview for what samples can't show — at most 3-4 questions, asked one at a time, skipping anything the samples already answered:

1. Humor: "Where's your humor, on a dial from deadpan to goofy? Anywhere it's off-limits?"
2. Pet peeves: "What words or writing habits make you cringe when you read them?"
3. Philosophy: "What should your writing do to the reader?"

## Step 5: Finish

1. Update the `Last updated` stamp.
2. Play back a 3-5 line summary of the voice you captured ("short sentences, lots of parentheticals, dry humor, no emoji...") and ask if that sounds like them. Fix what they correct.
3. Offer a test drive: take a short AI-flavored paragraph and rewrite it in their new voice with the humanizer skill.

## Re-runs and updates

"Add this post to my voice profile" or "update my voice profile": save the new sample to `raw_samples/`, re-read the profile, adjust only the sections the new evidence changes, and update the stamp. Small corrections during normal humanizer use ("I'd never say that") are folded in directly by the humanizer skill; this skill is for sample imports and bigger refreshes.

## Privacy rules

- Everything lives under `~/.claude/humanizer/`. Nothing is uploaded, posted, or shared anywhere.
- Never import a file or email the user didn't explicitly select.
- Sent mail only, never the inbox. Strip other people's quoted words — only the user's writing belongs in their profile.
- If `~/.claude/humanizer/` can't be created or written, say so and stop. The humanizer skill keeps working from its bundled template.
