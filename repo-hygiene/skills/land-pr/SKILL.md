---
name: land-pr
description: Use when a pull request needs finishing or the open-PR list needs clearing — before reporting work done in any repo you opened a PR in, when the user says "land it", "merge when green", "finish the PRs", "why are these PRs still open", "clear the PR backlog", or on /land-pr [status|land <ref>|sweep]. Classifies every open PR, lands the ready ones (version bump, checks, merge, tag) and closes superseded autofix drafts. Every PR carries its release notes, and the version bump is cut at merge time.
---

# Land PR

Every pull request ends merged or closed. This tool does the last mile
mechanically, so finishing a PR costs one command and any session can do it
for any PR.

- **Tool:** `${CLAUDE_PLUGIN_ROOT}/skills/land-pr/pr_tool.py` (stdlib + `gh` + `git`)
- **Bumps:** delegated to `${CLAUDE_PLUGIN_ROOT}/skills/version-manager/version_tool.py`
- **Rules it implements:** every PR ends merged or closed; a PR's body
  carries a `## Release notes` section (below) and never a version number; the
  bump is cut at merge time, so concurrent PRs never claim the same version
- Read-only until `--apply`. On Windows use `python` and a Windows path.

## Verbs

```bash
T=${CLAUDE_PLUGIN_ROOT}/skills/land-pr/pr_tool.py
python3 $T status                         # every open PR, classified
python3 $T status --repo OWNER/NAME       # one repo (use before reporting done)
python3 $T land OWNER/NAME#N              # dry run: release level, merge style
python3 $T land OWNER/NAME#N --apply      # bump, wait, merge, tag, clean up
python3 $T sweep                          # dry run of the whole backlog
python3 $T sweep --apply                  # close superseded, land all READY
python3 $T threads OWNER/NAME#N           # unresolved review threads, with ids
python3 $T threads OWNER/NAME#N --resolve ID [ID ...]
```

Exit codes: `0` done or nothing to do, `1` refused or failed, `3` waiting on
checks, `10` work pending (`status`, `sweep` dry run).

**Exit 3 means run the same command again.** `land` keeps no state of its own;
it reads everything from the PR. A run that pushed the bump and timed out
waiting for CI is finished by the next run, from any session or machine. The
default wait is 8 minutes so a foreground call fits a tool timeout; raise it
with `--wait 25` in a background run.

## What `land --apply` does

1. Refuses unless the PR is READY (table below).
2. Reads the release level and notes from the PR body.
3. In a throwaway detached worktree: drops a stale bump if the branch has one,
   merges `origin/<base>`, runs `version_tool.py release <level> --no-tag`,
   and pushes that one commit. No force-push, ever.
4. Waits for checks on the bump commit.
5. Merges in the repo's own style (read from recent history), with
   `--match-head-commit` so nothing unreviewed rides along. A squash subject
   becomes `title (vX.Y.Z) (#N)`.
6. Tags the merge commit through the API and deletes the branch.
7. Closes `autofix/pr-N` drafts for the PR it just merged.

After a merge to a deploying branch, the deploy watch and production smoke
test in AGENTS.md "Shipping autonomy" are still yours.

## The PR body section the lander reads

```markdown
## Release notes

Release: patch

- What changed, in words a user would recognize.
```

`Release:` is `major`, `minor`, `patch` or `none`. With no section the lander
infers the level (`none` when every changed path ships nothing, otherwise from
commit subjects) and drafts notes from commits. Never put a version number in
a PR title or a file; the lander assigns it at merge.

## States

| State | Meaning | Who moves it |
|---|---|---|
| `READY` | the current head is green and reviewed, every thread resolved, mergeable | `land` |
| `WAITING` | head pushed under 3 min ago, or checks, a workflow run or the automated review not in yet on it | time; re-run |
| `THREADS` | unresolved review threads | fix or answer each, then resolve it |
| `FAILING` | a check failed, or one never reported on the head within 30 min | fix and push, or re-run it |
| `CONFLICT` | conflicts with the base branch | merge base in, resolve |
| `REVIEW` | auth / billing / migration paths, no adversarial review recorded | run it, add the line `Adversarial review: <result>` to the PR body |
| `BLOCKED` | a branch rule refuses the merge | read `gh pr merge` output |
| `SUPERSEDED` | autofix draft whose source PR merged or closed | `sweep --apply` closes it |
| `AUTOFIX` | autofix draft, source still open | fold into the source, or close |
| `DRAFT` | draft PR | finish or close |
| `STACKED` | based on another PR's branch, not the default branch | land the base PR first: GitHub retargets this one to the default branch, then `land` it. Or merge the whole stack with `gh stack merge` (skill `github-stacked-prs`) and run `land` on the top PR to tag |
| `EXTERNAL` | outside contributor | the user |
| `ELSEWHERE` | your PR in someone else's repo | that repo's owner |
| `STALE(...)` | any of the above, idle 14+ days | the user: close or revive |

`sweep` lands only `READY` that is not stale, and closes only `SUPERSEDED`.
Everything else it lists and leaves. Report the `STALE`, `EXTERNAL` and
`ELSEWHERE` rows to the user as decisions; do not close a feature PR yourself.

## Who you are lives in a config file

Which accounts' repositories count as yours, and where your clones are, is
per machine, so it is not in the tool. Put it in `~/.claude/land-pr.json`
(`PR_TOOL_CONFIG` points elsewhere):

```json
{"owners": ["your-login", "your-org"], "code_roots": ["~/code"]}
```

Owners are taken from `--owner`, then `PR_TOOL_OWNERS=a,b`, then the config
file, then the account `gh` is signed in as. With nothing set, `status` says
it is surveying only the signed-in account: PRs in an organization's
repositories then show as ELSEWHERE and are never merged. Clones are looked
for under `PR_TOOL_CODE_ROOT`, then `code_roots`, then the current directory
and its parent; with none found the tool works in a temporary clone. A config
file that exists but cannot be parsed is an error, not a silent default.

## Policy lives at the top of the tool

`STALE_DAYS`, `REVIEW_GRACE_MIN`, `SETTLE_MIN`, `MISSING_CHECK_MIN`,
`REVIEWER_BOTS`, `REVIEWER_CHECKS`, `SHIPS_NOTHING` (paths that need no
version bump) and `SENSITIVE` (paths that need the adversarial review) are
constants at the top of `pr_tool.py`. Change behavior there, not in the logic
below.

## Gotchas

- **Every verdict is about the current head, not the PR.** Right after a push
  the head's check list is empty or partial, and an empty list has nothing
  failing in it. So a head is never READY in its first 3 minutes, while a
  workflow run GitHub has created for it is unfinished, or while a reviewer
  check that ran on an earlier commit has not reported on it. A review counts
  only if it names the head commit: the bot's written review of that commit
  (one with a body), or a reviewer check that PASSED on it. Three things
  look like evidence and are not: a bot comment (it has no commit); a
  "review" with an empty body (GitHub files every reply in a review thread
  as one, on the head); and a skipped or neutral reviewer check, which is
  the reviewer saying it did NOT review that commit (CodeRabbit reports
  "Review paused" that way: re-trigger it with `@coderabbitai review`). It
  is safe to run `land --apply` straight after pushing a fix; it waits.
- **A reviewer that skips the whole PR is not owed a review.** CodeRabbit on
  a Dependabot PR reports "Review skipped: author ignored by configuration"
  on every commit; that PR lands on its checks. The rule below applies only
  once a reviewer has really reviewed something on the PR.
- **Once a reviewer has reviewed a PR, the head needs its review.** Its
  silence on a new head is WAITING for 30 minutes, then `FAILING`, never
  READY: re-trigger it (GrepTile does not re-review a push). The 15-minute
  grace applies only where no reviewer has ever acted. This holds for bot
  authors too: a Dependabot PR skips only the wait for a reviewer that has
  never shown up. If the reviewer is gone for good,
  `land <ref> --apply --accept-missing-review` says so for that one PR;
  `sweep` never implies it.
- **A workflow run that exists and has not finished always blocks,** WAITING
  then `FAILING` after 30 minutes. No flag skips it: re-run it. Only the
  newest run of each workflow per event counts, so re-firing the event (close
  and reopen the PR) replaces a run that is stuck for good.
- **A check that is still pending is WAITING for six hours,** then `FAILING`
  as stuck. Six hours is GitHub's limit for a hosted job; the 30-minute rule
  is for a workflow or reviewer that never started, not for one that is
  running.
- **A head with no check suite yet has an unknown push time,** which counts
  as "just pushed" (the PR's last update), never as old as the commit.
- **Findings written in a review's body are invisible to the tool.**
  CodeRabbit puts comments on lines outside the diff there, not in threads,
  and a body has no "resolved" state to read. Read the review itself before
  landing; the tool can only tell you a review of the head exists.
- **The record for a sensitive PR is a line of its own:**
  `Adversarial review: <result and where it ran>`. The word alone, an empty
  result, or `none` / `not run` / `pending` does not count.
- **`land` on a merged PR finishes it.** If a run died after the merge, or the
  tag was refused, run the same command again: it tags the merge commit if
  the version is untagged, deletes the branch if it is still as merged, and
  closes leftover autofix drafts. A failed tag exits `1`, never "LANDED".
- **Merged means GitHub says merged.** With a merge queue `gh pr merge` only
  enqueues; the tool then reports NOT MERGED YET, exits `3`, and tags nothing.
- **A conflict from a stale bump is repaired, any other is refused.** On a
  CONFLICT PR that ships something, `land --apply` checks the branch for a
  stale version bump, drops it, merges the base and re-cuts. If that is not
  the cause, nothing is pushed and the PR stays CONFLICT.
- **A PR too big to read in one page is `BLOCKED`,** not passed on the part
  that was read (over 100 review threads or checks). Changed files are read
  in full; if some still cannot be seen the PR counts as sensitive.
- **The lander's own commits carry the earlier review, when proven.** A
  release bump or a clean merge of the base adds no code, so the review of
  the commit before them still covers the head. The title is only a claim:
  a release commit must change nothing but version lines and the changelog,
  and a merge must be of a commit already on the base, with exactly the tree
  `git merge-tree` gives (checked in a local clone; no clone, no proof).

- **Unresolved means unresolved.** An outdated thread still blocks. Reply in
  the thread, then `threads --resolve`. Never resolve without a fix or reply.
- **Reviewer checks are checks.** CodeRabbit's status goes pending on every
  push, so `WAITING` already covers "re-review in progress". GrepTile does not
  re-review a push; its findings are threads, and those block.
- **No version location** (repo never ran `version_tool.py backfill`): the PR
  lands without a bump and the tool says so. Run backfill there afterwards.
- **A bump commit already on the branch** is kept if it is still the next
  version, otherwise dropped and re-cut; a hand-written changelog section is
  carried over as the notes.
- **Fork PRs** land without a bump: the tool cannot push to the fork.
- **One landing per repo at a time** on this machine (lock under
  `~/.claude/state/land-pr/`). A lock older than 45 minutes is taken over.

## Tests

```bash
python3 -m pytest ${CLAUDE_PLUGIN_ROOT}/skills/land-pr/tests/ -q
```

On Windows run pytest from inside the skill folder and pass `--basetemp` if
the default temp folder is not writable. Classification tests are pure; the
bump tests build real git repositories and run the real version tool.
