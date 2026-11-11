#!/usr/bin/env python3
"""PR lander: drive every pull request to merged or closed.

    pr_tool.py status  [--repo OWNER/NAME] [--owner LOGIN ...] [--json]
    pr_tool.py land    OWNER/NAME#N | URL [--apply] [--level L] [--no-bump]
                       [--method squash|merge|rebase] [--clone PATH] [--wait MIN]
    pr_tool.py sweep   [--repo OWNER/NAME] [--owner LOGIN ...] [--apply]
                       [--max N] [--wait MIN]
    pr_tool.py threads OWNER/NAME#N [--resolve ID ...]

Standard library plus the `gh` and `git` CLIs. Read-only until --apply (or
--resolve) is passed.

Exit codes: 0 done or nothing to do; 1 refused or error; 3 waiting on checks
(re-run the same command); 10 work is pending (status, sweep dry run).

`land` is resumable. It reads all of its state from the pull request, so a run
that stops while checks are pending is finished by running it again, from any
session on any machine.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path

# --------------------------------------------------------------------------
# POLICY. These constants are the judgment calls. Everything below them is
# mechanism. Tune them here; nothing else needs to change.
# --------------------------------------------------------------------------

# Who you are is per machine, not per copy of this file, so it is NOT set
# here: an installed copy (a plugin cache) cannot be edited. In order:
#   --owner, PR_TOOL_OWNERS=a,b, `owners` in the config file, OWNERS below,
#   and last the account `gh` is signed in as.
# The config file is JSON, ~/.claude/land-pr.json (PR_TOOL_CONFIG overrides):
#   {"owners": ["me", "my-org"], "code_roots": ["~/code"]}
CONFIG_PATH = "~/.claude/land-pr.json"

# Accounts whose open PRs `status` and `sweep` look at, and whose repositories
# count as yours to merge in. PRs you authored elsewhere are always listed.
OWNERS: list[str] = []

# A PR that is not READY and has not moved for this long is STALE: a decision
# for a person (close or revive), never something the tool settles.
STALE_DAYS = 14

# With no automated review on the CURRENT head, wait this long after it was
# pushed before treating the repo as having no automated reviewer.
REVIEW_GRACE_MIN = 15

# A head pushed less than this long ago is never READY: checks and reviewers
# register seconds to minutes after a push, and until they do an empty check
# list looks exactly like a green one.
SETTLE_MIN = 3

# A check still pending this long after the push is stuck, not slow: GitHub's
# own limit for a hosted job is six hours. It becomes FAILING (re-run it).
STALLED_CHECK_MIN = 360

# Two things must be in on the head before it can be READY: every workflow
# run GitHub has created for it has finished, and every reviewer check that
# ran on an earlier commit of the PR has reported on it. Until this long
# after the push a missing one is WAITING; after that it is FAILING (re-run
# it or push again), never READY.
MISSING_CHECK_MIN = 30

REVIEWER_BOTS = {"coderabbitai", "greptile-apps",
                 "copilot-pull-request-reviewer", "claude"}
# Check names that ARE an automated review (matched case-insensitively).
REVIEWER_CHECKS = ["coderabbit*", "greptile*"]

# Commits the lander itself adds. They carry no new code to review, so review
# evidence on the last commit before them still counts for the head.
MECHANICAL_COMMIT = re.compile(
    r"^chore\(release\): (v\d|drop pre-landing bump)"
    r"|^Merge remote-tracking branch 'origin/[^']+' into HEAD$")

# A PR whose every changed path matches one of these changes nothing the
# product ships, so it lands with no version bump (`Release: none`).
SHIPS_NOTHING = [
    ".github/*", ".greptile/*", ".coderabbit.yaml", ".coderabbit.yml",
    ".snyk", ".gitleaks*", ".gitignore", ".gitattributes", ".editorconfig",
    ".pre-commit-config.yaml", "osv-scanner.toml", ".osv-scanner.toml",
    "tests/*", "test/*", "*/tests/*", "*/test/*", "*/__tests__/*",
    "*.test.*", "*.spec.*", "*_test.py", "test_*.py", "*/test_*.py",
    "Docs/*", "docs/*", "Plans/*", "Notes/*", "Discord/*",
    "README*", "CHANGELOG*", "LICENSE*", "SECURITY*", "CONTRIBUTING*",
    "AGENTS.md", "CLAUDE.md", "GEMINI.md",
]

# Paths that put a PR in the auth / billing / data-migration class. `sweep`
# will not land one unless the PR body records the adversarial review.
SENSITIVE = [
    "*auth*", "*billing*", "*stripe*", "*payment*", "*license*", "*licens*",
    "*/migrations/*", "migrations/*", "*.sql", "*schema.prisma",
]
# The record is a line of its own with a result after the colon:
#     Adversarial review: clean (codex, gpt-6-astra high, 2026-11-11)
# The word alone proves nothing ("no adversarial review was run" has it too),
# and neither does the line with an empty or negative result.
SENSITIVE_EVIDENCE = re.compile(
    r"^[ \t>*-]*\**Adversarial(?:[ \t]+\w+)?[ \t]+review\**[ \t]*:"
    r"[ \t]*\**[ \t]*(\S.*)$", re.I | re.M)
EVIDENCE_NEGATION = re.compile(
    # "no findings" is a result. "no", "No.", "no, not run" are not: any "no"
    # that is not directly followed by what was looked for is a negative.
    r"^(none\b"
    r"|no\b(?!\s+(?:findings?|issues?|problems?|defects?|bugs?|concerns?)\b)"
    r"|not\b|n/?a\b|skipped|pending|todo|tbd|to do|later)", re.I)
EVIDENCE_FORMAT = "Adversarial review: <result and where it ran>"


def adversarial_review_recorded(body: str) -> bool:
    return any(not EVIDENCE_NEGATION.match(m.group(1).strip(" *`_-"))
               and m.group(1).strip(" *`_-")
               for m in SENSITIVE_EVIDENCE.finditer(body or ""))

# Folders that hold local clones, searched as <root>/<repo> and
# <root>/Web/<repo>: PR_TOOL_CODE_ROOT=a;b, then `code_roots` in the config
# file, then these, then the current directory and its parent. With no clone
# found the tool works in a temporary one.
CODE_ROOTS: list[str] = []

# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------


class ToolError(RuntimeError):
    pass


_CACHE: dict[str, object] = {}


def config() -> dict:
    """The per-machine config file, or {} when there is none. A file that is
    there but unreadable is an error: silently ignoring it would quietly
    change whose PRs get merged."""
    path = Path(os.environ.get("PR_TOOL_CONFIG") or CONFIG_PATH).expanduser()
    key = f"config:{path}"
    if key not in _CACHE:
        if not path.is_file():
            _CACHE[key] = {}
        else:
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                raise ToolError(f"cannot read {path}: {exc}") from exc
            if not isinstance(data, dict):
                raise ToolError(f"{path} must hold a JSON object")
            _CACHE[key] = data
    return _CACHE[key]  # type: ignore[return-value]


def _names(value: object) -> list[str]:
    return [str(x) for x in value if x] if isinstance(value, list) else []


def run(cmd: list[str], cwd: str | Path | None = None, check: bool = True
        ) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise ToolError(f"{' '.join(cmd[:5])}: {detail}")
    return proc


def gh(*args: str, check: bool = True) -> str:
    # cwd is a neutral directory so gh never picks up a repo by accident
    return run(["gh", *args], cwd=tempfile.gettempdir(), check=check).stdout


def git(repo: Path, *args: str, check: bool = True) -> str:
    return run(["git", "-C", str(repo), *args], check=check).stdout


def gql(query: str, **variables: object) -> dict:
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
    data = json.loads(gh(*args))
    if data.get("errors"):
        raise ToolError(f"graphql: {data['errors'][0].get('message')}")
    return data["data"]


def load_version_tool():
    """Import the sibling version-manager tool; it owns every version write."""
    path = Path(os.environ.get("VERSION_TOOL") or
                Path(__file__).resolve().parent.parent
                / "version-manager" / "version_tool.py")
    if not path.exists():
        raise ToolError(f"version tool not found at {path}")
    spec = importlib.util.spec_from_file_location("version_tool", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["version_tool"] = mod   # dataclasses resolve via sys.modules
    spec.loader.exec_module(mod)
    return mod, path


REF_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[\w.-]+)/(?P<name>[\w.-]+)"
    r"(?:#|/pull/)(?P<n>\d+)")


def parse_ref(text: str) -> tuple[str, int]:
    m = REF_RE.match(text.strip())
    if not m:
        raise ToolError(f"not a pull request reference: {text!r} "
                        "(want OWNER/NAME#N or a PR URL)")
    return f"{m['owner']}/{m['name']}", int(m["n"])


def _when(text: str | None) -> datetime:
    if not text:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


# --------------------------------------------------------------------------
# reading a pull request
# --------------------------------------------------------------------------

PR_QUERY = """
query($owner:String!,$name:String!,$number:Int!){
  repository(owner:$owner,name:$name){
    squashMergeAllowed mergeCommitAllowed rebaseMergeAllowed
    defaultBranchRef{name}
    pullRequest(number:$number){
      number title body state isDraft url createdAt updatedAt
      isCrossRepository mergeable mergeStateStatus
      author{login __typename}
      baseRefName headRefName headRefOid
      mergeCommit{oid}
      files(first:100){totalCount nodes{path}}
      commits(last:100){nodes{commit{oid messageHeadline committedDate
        parents(first:3){nodes{oid}}}}}
      tail:commits(last:20){nodes{commit{oid
        checkSuites(first:100){totalCount nodes{createdAt status conclusion
          workflowRun{event workflow{databaseId name}}}}
        statusCheckRollup{contexts(first:100){nodes{__typename
          ... on CheckRun{name status conclusion}
          ... on StatusContext{context state}}}}}}}
      statusCheckRollup{contexts(first:100){totalCount nodes{__typename
        ... on CheckRun{name status conclusion}
        ... on StatusContext{context state}}}}
      reviewThreads(first:100){totalCount nodes{id isResolved isOutdated path line
        comments(first:1){nodes{author{login} body url}}}}
      reviews(last:50){totalCount nodes{author{login} commit{oid} body}}
    }}}
"""


@dataclass
class PR:
    repo: str
    number: int
    title: str = ""
    body: str = ""
    state: str = "OPEN"            # OPEN | MERGED | CLOSED
    draft: bool = False
    url: str = ""
    author: str = ""
    author_is_bot: bool = False
    cross_repo: bool = False
    base: str = "main"
    head: str = ""
    head_oid: str = ""
    mergeable: str = "MERGEABLE"   # MERGEABLE | CONFLICTING | UNKNOWN
    merge_state: str = "CLEAN"
    created: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    head_committed: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))
    files: list[str] = field(default_factory=list)
    files_total: int = 0
    subjects: list[str] = field(default_factory=list)
    commit_oids: list[str] = field(default_factory=list)   # parallel to subjects
    checks: list[tuple[str, str]] = field(default_factory=list)  # (name, bucket)
    threads: list[dict] = field(default_factory=list)            # unresolved
    # Everything below is about the CURRENT head, never the PR as a whole: a
    # verdict about an earlier commit says nothing about what would merge.
    head_pushed: datetime | None = None    # None: same as head_committed
    review_clock: datetime | None = None   # None: same as head_pushed
    reviewed_head: bool = False            # automated review covers the head
    reviewer_active: bool = False          # a reviewer has acted on this PR
    expected_checks: list[str] = field(default_factory=list)  # ran earlier
    running_workflows: list[str] = field(default_factory=list)  # unfinished
    unverifiable: list[str] = field(default_factory=list)  # truncated reads
    merge_commit: str | None = None
    methods: list[str] = field(default_factory=lambda: ["squash", "merge"])
    autofix_source_state: str | None = None
    default_branch: str = ""               # '' when not known

    def __post_init__(self) -> None:
        if self.head_pushed is None:
            self.head_pushed = self.head_committed
        if self.review_clock is None:
            self.review_clock = self.head_pushed

    @property
    def ref(self) -> str:
        return f"{self.repo}#{self.number}"


def check_bucket(node: dict) -> tuple[str, str]:
    """(name, pass|fail|pending|skip) for one status-check rollup entry."""
    if node.get("__typename") == "CheckRun":
        name = node.get("name") or "check"
        conclusion = node.get("conclusion")
        # A conclusion is the verdict. GitHub can leave status IN_PROGRESS on
        # a run that already has one (seen for a day on Heimdallr#6 and
        # AppTemplateWPF#3, 2026-11-11), so status only decides when there is
        # no conclusion yet.
        if not conclusion and node.get("status") != "COMPLETED":
            return name, "pending"
        if conclusion == "SUCCESS":
            return name, "pass"
        if conclusion in ("SKIPPED", "NEUTRAL"):
            return name, "skip"
        return name, "fail"
    name = node.get("context") or "status"
    state = node.get("state")
    if state == "SUCCESS":
        return name, "pass"
    if state in ("PENDING", "EXPECTED"):
        return name, "pending"
    return name, "fail"


def is_reviewer_check(name: str) -> bool:
    return any(fnmatchcase(name.lower(), p) for p in REVIEWER_CHECKS)


SEMVER = re.compile(r"\d+\.\d+\.\d+(?:\.\d+)?")

# The project's OWN version declaration, as a whole line, per file. These
# mirror what version_tool.py writes and nothing wider: "a line with the word
# version in it" also describes a dependency called compare-versions, and a
# lockfile is nothing but "version" lines for other people's packages.
_V = r"\d+\.\d+\.\d+"
VERSION_LINES: list[tuple[str, re.Pattern[str]]] = [
    ("package.json", re.compile(rf'^\s*"version"\s*:\s*"{_V}"\s*,?\s*$')),
    ("marketplace.json", re.compile(rf'^\s*"version"\s*:\s*"{_V}"\s*,?\s*$')),
    ("plugin.json", re.compile(rf'^\s*"version"\s*:\s*"{_V}"\s*,?\s*$')),
    ("pyproject.toml", re.compile(rf'^version\s*=\s*["\']{_V}["\']\s*$')),
    ("*.py", re.compile(rf'^(?:__version__|VERSION)\s*=\s*["\']{_V}["\']\s*$')),
    ("VERSION", re.compile(rf"^\s*{_V}\s*$")),
    ("README.md", re.compile(rf"^.*\*\*Version\s+{_V}\*\*.*$")),
    ("*.csproj", re.compile(
        rf"^\s*<(Version|AssemblyVersion|FileVersion)>\s*{_V}(?:\.\d+)?\s*</\1>\s*$")),
]
VERSION_PY_FILES = {"version.py", "constants.py", "__init__.py", "main.py",
                    "setup.py"}


def _version_line(base: str, line: str) -> bool:
    for name, pattern in VERSION_LINES:
        if name == "*.py":
            hit = base in VERSION_PY_FILES
        else:
            hit = fnmatchcase(base, name)
        if hit and pattern.match(line.rstrip("\r")):
            return True
    return False


def release_diff_is_mechanical(files: list[dict]) -> bool:
    """True when a commit changes nothing but version numbers and a changelog.

    `files` is the GitHub commit API's list. A commit titled like a release
    can hold anything, so the title is never trusted. A changelog may be
    added or edited freely. Everywhere else, the file must be one that holds
    the project's version, and every removed line must come back as the same
    line with only its version number changed, where that line is the
    project's own version declaration (VERSION_LINES). Anything the patch
    does not show (binary, too large, renamed, copied, added) fails.
    """
    if not files or len(files) > 20:
        return False
    for f in files:
        base = (f.get("filename") or "").rsplit("/", 1)[-1]
        status = f.get("status")
        if base.upper().startswith("CHANGELOG"):
            # Added or edited in place only: a product file RENAMED to
            # CHANGELOG.md is a product file leaving, not a changelog.
            if status not in ("modified", "added"):
                return False
            continue
        patch = f.get("patch")
        if not patch or status != "modified":
            return False
        lines = [x for x in patch.splitlines() if x[:1] in "+-"]
        minus = [x[1:] for x in lines if x[0] == "-"]
        plus = [x[1:] for x in lines if x[0] == "+"]
        if not plus or len(minus) != len(plus):
            return False
        if base.endswith(".json") and len(plus) != 1:
            return False    # a bump moves one line; more is something else
        for old, new in zip(minus, plus):
            if SEMVER.sub("V", old) != SEMVER.sub("V", new):
                return False
            if not (_version_line(base, old) and _version_line(base, new)):
                return False
    return True


def merge_is_clean(repo: str, base: str, oid: str, parents: list[str]) -> bool:
    """True when `oid` is a merge of the base branch with no hand edits.

    Checked two ways, both required: the merged-in parent is already on the
    base branch (so it brought in nothing unreviewed), and the commit's tree
    is exactly what `git merge-tree` produces for its two parents (so no
    conflict was resolved and nothing was slipped in). Needs a local clone;
    without one the answer is no.
    """
    if len(parents) != 2:
        return False
    on_base = gh("api", f"repos/{repo}/compare/{base}...{parents[1]}",
                 "--jq", ".status", check=False).strip()
    if on_base not in ("behind", "identical"):
        return False
    # The clone this run was told to use (--clone) counts too, not only the
    # ones the search finds.
    clone = find_clone(repo, _CACHE.get("clone_hint"))  # type: ignore[arg-type]
    if clone is None:
        return False
    for sha in (oid, *parents):
        if run(["git", "-C", str(clone), "cat-file", "-e", f"{sha}^{{commit}}"],
               check=False).returncode != 0:
            run(["git", "-C", str(clone), "fetch", "--quiet", "origin", sha],
                check=False)
    made = run(["git", "-C", str(clone), "merge-tree", "--write-tree",
                parents[0], parents[1]], check=False)
    want = (made.stdout.split() or [""])[0] if made.returncode == 0 else ""
    have = run(["git", "-C", str(clone), "rev-parse", f"{oid}^{{tree}}"],
               check=False).stdout.strip()
    return bool(want) and want == have


def verified_mechanical(repo: str, base: str, commits: list[dict]) -> set[str]:
    """The trailing commits that are provably the lander's own.

    Walks back from the head while a commit both LOOKS mechanical (its title)
    and IS (its content), and stops at the first that is not. Never includes
    the PR's first commit.
    """
    proven: set[str] = set()
    # Commits this very run created and pushed need no proof: the lander made
    # them, in a clone that may be temporary and gone from every search path.
    own: set[str] = _CACHE.get("own_commits", set())  # type: ignore[assignment]
    for c in reversed(commits[1:]):
        title = c.get("messageHeadline") or ""
        if not MECHANICAL_COMMIT.match(title):
            break
        if c.get("oid") in own:
            proven.add(c["oid"])
            continue
        parents =[p["oid"] for p in (c.get("parents") or {}).get("nodes", [])]
        if title.startswith("Merge "):
            good = merge_is_clean(repo, base, c["oid"], parents)
        else:
            good = len(parents) == 1 and release_diff_is_mechanical(
                commit_files(repo, c["oid"]))
        if not good:
            break
        proven.add(c["oid"])
    return proven


def head_facts(n: dict, commits: list[dict],
               head_checks: list[tuple[str, str]],
               mechanical: set[str] | None = None) -> dict:
    """What is known about the PR's CURRENT head, as opposed to the PR.

    pushed        when the head reached GitHub: its first check suite's
                  creation time (suites appear seconds after a push), else
                  the commit date.
    running       workflows GitHub has created a run for on the head that
                  have not finished. The run exists (queued) before any of
                  its jobs do, so this catches the gap right after a push
                  when the check list is still empty.
    expected      reviewer checks (REVIEWER_CHECKS) that ran on an earlier
                  commit of this PR and so must report on the head too. Only
                  reviewer checks: other apps' checks can be conditional on
                  the paths a commit touches (Dependabot's config check).
    reviewed      an automated review covers the head: a reviewer bot's
                  review OF THAT COMMIT with a body, or a reviewer check that
                  PASSED on it. Not evidence: a comment (it has no commit), a
                  body-less "review" (a thread reply), a skipped or neutral
                  reviewer check (the reviewer declined or paused).
    active        a reviewer has actually reviewed something on this PR (a
                  written review, or a reviewer check that passed on a
                  recent commit). Once one has, the head needs its review;
                  waiting it out is not an option. A reviewer that only ever
                  skipped the PR is not active.
    review_clock  when the wait for a review starts.

    The lander's own commits (release bump, clean merge of the base) carry no
    new code, so a review of the last commit before them still covers the
    head. `mechanical` is the set of commits PROVEN to be such by their
    content (verified_mechanical); a title alone proves nothing, and with no
    set given nothing is treated as mechanical.
    """
    mechanical = mechanical or set()
    tail = [c["commit"] for c in (n.get("tail") or {}).get("nodes", [])]

    def buckets(commit: dict) -> list[tuple[str, str]]:
        nodes = (commit.get("statusCheckRollup") or {}) \
            .get("contexts", {}).get("nodes", [])
        return [check_bucket(x) for x in nodes]

    committed = _when(commits[-1]["committedDate"]) if commits \
        else _when(n.get("updatedAt"))
    suite_nodes = ((tail[-1] if tail else {}).get("checkSuites") or {}) \
        .get("nodes", [])
    suites = [_when(s["createdAt"]) for s in suite_nodes if s.get("createdAt")]
    if suites:
        pushed = max(committed, min(suites))
    else:
        # No suite on the head yet, so the push time is unknown. The commit
        # date is NOT it: a commit can be hours old when it is pushed. The
        # PR's last update is at or after the push, so it errs toward "just
        # pushed" and toward waiting, never the other way.
        pushed = max(committed, _when(n.get("updatedAt")))
    def unfinished(s: dict) -> bool:
        # A conclusion wins over a stale status, as in check_bucket.
        return not (s.get("status") == "COMPLETED" or s.get("conclusion"))

    # Only the NEWEST run of each workflow, per triggering event, speaks for
    # the head. A run can be left queued for good (seen 2026-11-11: runs
    # created during an Actions outage could not start or be cancelled), and
    # a later run of the same workflow for the same event on the same commit
    # replaces it. At equal times the unfinished one is kept.
    # "The same workflow" is its identity, not its display name: two workflow
    # files may share a `name:`, and a finished run of one must never stand in
    # for an unfinished run of the other.
    newest: dict[tuple[str, str], dict] = {}
    for s in suite_nodes:
        wf = s.get("workflowRun")
        if not wf:
            continue    # other apps leave a suite queued forever; ignore
        flow = wf.get("workflow") or {}
        name = flow.get("name") or "workflow"
        key = (str(flow.get("databaseId") or f"name:{name}"),
               wf.get("event") or "")
        rank = (s.get("createdAt") or "", unfinished(s))
        if key not in newest or rank > (newest[key].get("createdAt") or "",
                                        unfinished(newest[key])):
            newest[key] = s
    running: list[str] = []
    for s in newest.values():
        name = ((s["workflowRun"].get("workflow") or {}).get("name")
                or "workflow")
        if unfinished(s) and name not in running:
            running.append(name)

    # Walk back over the lander's own commits to the last one with real code.
    i = len(commits) - 1
    while i > 0 and commits[i].get("oid") in mechanical:
        i -= 1
    mechanical_head = bool(commits) and i < len(commits) - 1
    covered = {c.get("oid") for c in commits[i:]} if commits else set()

    def bot(x: dict) -> bool:
        return ((x.get("author") or {}).get("login") or "").lower() in REVIEWER_BOTS

    reviews = n.get("reviews") or {}
    bot_reviews = [r for r in reviews.get("nodes", []) if bot(r)]
    # A review is one the bot WROTE: it has a body ("Actionable comments
    # posted: N", a summary). GitHub also files every reply in a review
    # thread as a "review" of the head with an empty body, so a bot answering
    # threads leaves a row of those on a commit it never reviewed.
    written = [r for r in bot_reviews if (r.get("body") or "").strip()]
    by_review = any((r.get("commit") or {}).get("oid") in covered
                    for r in written)
    # Only a reviewer check that PASSED is a review. A skipped or neutral
    # one is the reviewer saying it did not review this commit (CodeRabbit
    # reports "Review paused" that way): the opposite of evidence.
    by_check = any(is_reviewer_check(name) and b == "pass"
                   for name, b in head_checks) or any(
        is_reviewer_check(name) and b == "pass"
        for c in tail if c.get("oid") in covered for name, b in buckets(c))
    reviewed = by_review or by_check

    # "Active" means a reviewer has actually REVIEWED something on this PR: a
    # written review of any commit, or a reviewer check that passed on one.
    # A check that only ever skipped does not count: that is the reviewer
    # declining the whole PR (CodeRabbit on a bot's PR reports "Review
    # skipped: author ignored by configuration"), which is "no reviewer
    # here", not "the reviewer owes a review".
    passed = any(is_reviewer_check(name) and b == "pass"
                 for c in tail for name, b in buckets(c)) or any(
        is_reviewer_check(name) and b == "pass" for name, b in head_checks)
    active = bool(written or passed
                  # More reviews than were read: assume one was a reviewer's.
                  or reviews.get("totalCount", 0) > len(reviews.get("nodes", [])))

    expected: list[str] = []
    if not (mechanical_head and reviewed):
        for c in tail[:-1]:
            for name, _ in buckets(c):
                if is_reviewer_check(name) and name not in expected:
                    expected.append(name)

    return {"pushed": pushed, "expected": expected, "reviewed": reviewed,
            "running": running, "active": active,
            "review_clock": _when(commits[i]["committedDate"])
            if mechanical_head else pushed}


def pr_from_node(repo: str, repo_node: dict,
                 mechanical: set[str] | None = None) -> PR:
    n = repo_node["pullRequest"]
    if n is None:
        raise ToolError(f"{repo}: pull request not found")
    author = n.get("author") or {}
    commits = [c["commit"] for c in (n.get("commits") or {}).get("nodes", [])]
    rollup = (n.get("statusCheckRollup") or {}).get("contexts", {}).get("nodes", [])
    threads = []
    for t in (n.get("reviewThreads") or {}).get("nodes", []):
        if t.get("isResolved"):
            continue
        first = (t.get("comments", {}).get("nodes") or [{}])[0]
        threads.append({
            "id": t["id"], "path": t.get("path"), "line": t.get("line"),
            "outdated": bool(t.get("isOutdated")),
            "author": (first.get("author") or {}).get("login", ""),
            "body": (first.get("body") or "").strip(),
            "url": first.get("url", ""),
        })
    head = head_facts(n, commits, [check_bucket(c) for c in rollup], mechanical)
    # One page of each list is read. A PR too big for a page must not pass a
    # gate on the part that was read: say so and let classify refuse it.
    unverifiable = []
    seen_threads = (n.get("reviewThreads") or {})
    if seen_threads.get("totalCount", 0) > len(seen_threads.get("nodes", [])):
        unverifiable.append(f"{seen_threads['totalCount']} review threads; only "
                            "the first 100 were read, so not all are known resolved")
    seen_checks = (n.get("statusCheckRollup") or {}).get("contexts", {})
    if seen_checks.get("totalCount", 0) > len(rollup):
        unverifiable.append(f"{seen_checks['totalCount']} checks; only the "
                            "first 100 were read")
    # An unfinished workflow run past the page that was read is invisible to
    # the "has every run finished" gate, so more than one page is a refusal.
    tail_nodes = (n.get("tail") or {}).get("nodes", [])
    head_suites = ((tail_nodes[-1].get("commit") or {}).get("checkSuites") or {}) \
        if tail_nodes else {}
    if head_suites.get("totalCount", 0) > len(head_suites.get("nodes", [])):
        unverifiable.append(f"{head_suites['totalCount']} check suites on the "
                            "head; only the first 100 were read, so not every "
                            "workflow run is known finished")
    methods =[m for m, ok in (("squash", repo_node.get("squashMergeAllowed")),
                               ("merge", repo_node.get("mergeCommitAllowed")),
                               ("rebase", repo_node.get("rebaseMergeAllowed")))
               if ok]
    return PR(
        repo=repo, number=n["number"], title=n.get("title") or "",
        body=n.get("body") or "", state=n.get("state") or "OPEN",
        draft=bool(n.get("isDraft")), url=n.get("url") or "",
        author=author.get("login") or "",
        author_is_bot=author.get("__typename") == "Bot",
        cross_repo=bool(n.get("isCrossRepository")),
        base=n.get("baseRefName") or "main", head=n.get("headRefName") or "",
        head_oid=n.get("headRefOid") or "",
        mergeable=n.get("mergeable") or "UNKNOWN",
        merge_state=n.get("mergeStateStatus") or "UNKNOWN",
        created=_when(n.get("createdAt")), updated=_when(n.get("updatedAt")),
        head_committed=_when(commits[-1]["committedDate"]) if commits
        else _when(n.get("updatedAt")),
        files=[f["path"] for f in (n.get("files") or {}).get("nodes", [])],
        files_total=(n.get("files") or {}).get("totalCount", 0),
        subjects=[c["messageHeadline"] for c in commits],
        commit_oids=[c.get("oid") or "" for c in commits],
        checks=[check_bucket(c) for c in rollup],
        threads=threads,
        head_pushed=head["pushed"], review_clock=head["review_clock"],
        reviewed_head=head["reviewed"], reviewer_active=head["active"],
        expected_checks=head["expected"],
        running_workflows=head["running"], unverifiable=unverifiable,
        merge_commit=(n.get("mergeCommit") or {}).get("oid"),
        methods=methods or ["merge"],
        default_branch=(repo_node.get("defaultBranchRef") or {}).get("name") or "",
    )


def all_files(repo: str, number: int) -> list[str]:
    """Every changed path, for a PR with more than one GraphQL page of them.

    The path gates (SENSITIVE, SHIPS_NOTHING) must see the whole list: a
    licensing file at position 101 is still a licensing file. REST serves up
    to 3000; past that `files_total` still exceeds the list and the gates
    fail closed.
    """
    out = gh("api", "--paginate", f"repos/{repo}/pulls/{number}/files?per_page=100",
             "--jq", ".[].filename", check=False)
    return [line for line in out.splitlines() if line]


def _parse(repo: str, repo_node: dict) -> PR:
    """pr_from_node, after proving which trailing commits are the lander's own
    (only asked when the head's title claims to be one; it costs API calls)."""
    n = repo_node.get("pullRequest") or {}
    commits = [c["commit"] for c in (n.get("commits") or {}).get("nodes", [])]
    proven: set[str] = set()
    if n.get("state") == "OPEN" and commits and MECHANICAL_COMMIT.match(
            commits[-1].get("messageHeadline") or ""):
        proven = verified_mechanical(repo, n.get("baseRefName") or "main",
                                     commits)
    return pr_from_node(repo, repo_node, proven)


def fetch_pr(repo: str, number: int) -> PR:
    owner, name = repo.split("/", 1)
    data = gql(PR_QUERY, owner=owner, name=name, number=number)
    pr = _parse(repo, data["repository"])
    if pr.state == "OPEN" and pr.mergeable == "UNKNOWN":
        time.sleep(2)   # GitHub computes mergeability lazily; ask once more
        data = gql(PR_QUERY, owner=owner, name=name, number=number)
        pr = _parse(repo, data["repository"])
    if pr.state == "OPEN" and pr.files_total > len(pr.files):
        pr.files = all_files(repo, number) or pr.files
    src = autofix_source(pr)
    if pr.state == "OPEN" and src:
        pr.autofix_source_state = gh(
            "pr", "view", str(src), "-R", repo, "--json", "state",
            "--jq", ".state", check=False).strip() or None
    return pr


# --------------------------------------------------------------------------
# classification (pure: no network, no clock of its own)
# --------------------------------------------------------------------------

AUTOFIX_HEAD = re.compile(r"^autofix/pr-(\d+)$")


def autofix_source(pr: PR) -> int | None:
    m = AUTOFIX_HEAD.match(pr.head)
    return int(m.group(1)) if m else None


def is_autofix(pr: PR) -> bool:
    return autofix_source(pr) is not None or pr.title.startswith("[autofix]")


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatchcase(path, p) for p in patterns)


def ships_nothing(pr: PR) -> bool:
    """True only when every changed path is provably outside the product."""
    if not pr.files or pr.files_total > len(pr.files):
        return False
    return all(_matches(p, SHIPS_NOTHING) for p in pr.files)


def is_sensitive(pr: PR) -> bool:
    if pr.files_total > len(pr.files):
        return True     # some paths were never seen: assume the worst
    return any(_matches(p.lower(), SENSITIVE) for p in pr.files
               if not _matches(p, SHIPS_NOTHING))


@dataclass
class Verdict:
    state: str
    reasons: list[str] = field(default_factory=list)
    stale: bool = False

    @property
    def label(self) -> str:
        return f"STALE({self.state})" if self.stale else self.state


NEXT_STEP = {
    "READY": "land it",
    "WAITING": "nothing yet; checks or review are still running",
    "THREADS": "fix or answer each thread, resolve it, then land",
    "FAILING": "fix the failing check, push, then land",
    "CONFLICT": "merge the base branch in, resolve, push, then land",
    "BLOCKED": "a branch rule blocks the merge; read `gh pr merge` output",
    "REVIEW": "run the adversarial review, add a line to the PR body "
              f"(`{EVIDENCE_FORMAT}`), land",
    "SUPERSEDED": "close it (sweep --apply does)",
    "AUTOFIX": "fold the fix into its source PR, or close it",
    "DRAFT": "finish it or close it",
    "STACKED": "land the PR it is based on first; GitHub then retargets this "
               "one to the default branch and it can land",
    "EXTERNAL": "outside contributor: the owner decides",
    "ELSEWHERE": "your PR in someone else's repo: its owner merges",
}
STALE_STEP = "no movement: the owner decides, close or revive"


def classify(pr: PR, now: datetime, trusted: set[str],
             owners: list[str] | None = None,
             accept_missing: bool = False,
             ignore_conflict: bool = False) -> Verdict:
    if pr.state != "OPEN":
        return Verdict(pr.state)
    idle_days = (now - pr.updated).days

    def verdict(state: str, *reasons: str) -> Verdict:
        # A READY PR nobody has touched for weeks was parked on purpose or
        # forgotten; either way a person decides. `land` still takes it when
        # asked by name; `sweep` does not.
        stale = state not in ("WAITING", "SUPERSEDED", "EXTERNAL", "ELSEWHERE") \
            and idle_days >= STALE_DAYS
        return Verdict(state, list(reasons), stale)

    if not pr.author_is_bot and pr.author.lower() not in trusted:
        return verdict("EXTERNAL", f"author {pr.author or 'unknown'}")
    # No explicit list means "whatever this run is configured for", so the
    # PR_TOOL_OWNERS override reaches every caller, not just the survey query.
    home = {o.lower() for o in (owners if owners is not None else _owners(None))}
    if pr.repo.split("/", 1)[0].lower() not in home:
        return verdict("ELSEWHERE", "someone else's repository")
    if is_autofix(pr):
        src = autofix_source(pr)
        if pr.autofix_source_state in ("MERGED", "CLOSED"):
            return verdict("SUPERSEDED",
                           f"source #{src} is {pr.autofix_source_state.lower()}")
        return verdict("AUTOFIX", f"source #{src} still open" if src
                       else "autofix PR with no source in its branch name")
    if pr.draft:
        return verdict("DRAFT")
    if pr.unverifiable:
        return verdict("BLOCKED", *(f"cannot verify: {u}" for u in pr.unverifiable))
    if pr.default_branch and pr.base != pr.default_branch:
        # Landing means reaching the default branch. Merging this one would
        # only fold it into another PR's branch, behind that PR's back, and
        # version or tag nothing real. It waits for the PR underneath it.
        return verdict("STACKED", f"based on {pr.base}, not {pr.default_branch}")
    if pr.mergeable == "CONFLICTING" and not ignore_conflict:
        return verdict("CONFLICT", f"conflicts with {pr.base}")
    failing = [n for n, b in pr.checks if b == "fail"]
    if failing:
        return verdict("FAILING", *failing)
    # From here on a missing signal must never read as a good one. Right after
    # a push the head's check list is empty or partial, and "nothing failed,
    # nothing pending" is true of an empty list.
    since_push = (now - pr.head_pushed).total_seconds() / 60
    if since_push < SETTLE_MIN:
        return verdict("WAITING", f"head pushed {max(0, int(since_push * 60))}s "
                       "ago; checks and review may not have registered yet")
    pending = [n for n, b in pr.checks if b == "pending"]
    if pending:
        if since_push >= STALLED_CHECK_MIN:
            return verdict("FAILING", *(f"{n} still running "
                                        f"{int(since_push // 60)} h after the "
                                        "push: stuck, re-run it" for n in pending))
        return verdict("WAITING", *(f"{n} running" for n in pending))
    have = {n for n, _ in pr.checks}
    missing = [n for n in pr.expected_checks if n not in have]
    # A workflow run that exists and has not finished always blocks. No flag
    # skips it: these are the scans, and a run that will not start is fixed
    # by re-running it, not by merging without it.
    if pr.running_workflows:
        late = since_push >= MISSING_CHECK_MIN
        return verdict("FAILING" if late else "WAITING",
                       *(f"workflow {w} "
                         f"{'never finished' if late else 'has not finished'} "
                         "on this head" for w in pr.running_workflows))
    if missing and not accept_missing:
        if since_push < MISSING_CHECK_MIN:
            return verdict("WAITING", *(f"{n} has not started on this head"
                                        for n in missing))
        return verdict("FAILING", *(f"{n} ran on an earlier commit but never "
                                    "started on this head" for n in missing))
    if pr.threads:
        return verdict("THREADS", f"{len(pr.threads)} unresolved review "
                       f"thread{'s' if len(pr.threads) != 1 else ''}")
    if pr.mergeable == "UNKNOWN":
        return verdict("WAITING", "GitHub is still computing mergeability")
    if pr.merge_state == "BLOCKED":
        return verdict("BLOCKED", "mergeStateStatus BLOCKED")
    if is_sensitive(pr) and not adversarial_review_recorded(pr.body):
        what = (f"{pr.files_total - len(pr.files)} changed files could not be "
                "read, so they count as sensitive"
                if pr.files_total > len(pr.files)
                else "auth/billing/migration paths")
        return verdict("REVIEW", f"{what}, and the PR body has no "
                       f"`{EVIDENCE_FORMAT}` line")
    since_review = (now - pr.review_clock).total_seconds() / 60
    if not pr.reviewed_head:
        # Bot authors (Dependabot) skip only the wait for a reviewer that has
        # never shown up; one that HAS acted on the PR is owed for them too.
        if pr.reviewer_active and not accept_missing:
            # A reviewer works on this PR, so its silence on the head is not
            # "this repo has no reviewer": it never becomes READY by waiting.
            if since_review < MISSING_CHECK_MIN:
                return verdict("WAITING", "no automated review of this head "
                               "yet (a reviewer acted on this PR earlier)")
            return verdict("FAILING", "a reviewer acted on this PR earlier but "
                           "has not reviewed this head: re-trigger it")
        if not pr.reviewer_active and not pr.author_is_bot \
                and since_review < REVIEW_GRACE_MIN:
            return verdict("WAITING", "no automated review of this head yet")
    return verdict("READY")


# --------------------------------------------------------------------------
# release plan: what the PR says about its own version bump
# --------------------------------------------------------------------------

RELEASE_LINE = re.compile(
    r"^[ \t>*-]*\**Release\**[ \t]*:[ \t]*\**[ \t]*`?"
    r"(major|minor|patch|none)\b", re.I | re.M)
NOTES_HEADING = re.compile(r"^(#{2,4})[ \t]*Release notes[ \t]*$", re.I | re.M)
# the section also ends at a heading of its own level or higher (built per PR,
# so `### Added` inside `## Release notes` stays part of the notes)
NOTES_END = r"<!--|---[ \t]*$|\U0001F916"
BREAKING = re.compile(r"^\w+(\([^)]*\))?!:|BREAKING[ -]CHANGE", re.M)
FEAT = re.compile(r"^feat(\(|!|:)")


@dataclass
class ReleasePlan:
    level: str           # major | minor | patch | none
    notes: str | None    # curated changelog body, when the PR supplies one
    source: str          # where the level came from, for the printed plan


def release_notes(body: str) -> str | None:
    m = NOTES_HEADING.search(body)
    if not m:
        return None
    rest = body[m.end():].replace("\r\n", "\n")
    depth = len(m.group(1))
    end = re.search(rf"^(?:#{{1,{depth}}}[ \t]|{NOTES_END})", rest, re.M)
    text = rest[:end.start()] if end else rest
    lines = [ln.rstrip() for ln in text.split("\n")
             if not RELEASE_LINE.match(ln)]
    return "\n".join(lines).strip() or None


def release_plan(pr: PR, override: str | None = None,
                 no_bump: bool = False) -> ReleasePlan:
    notes = release_notes(pr.body)
    if no_bump:
        return ReleasePlan("none", None, "--no-bump")
    if override:
        return ReleasePlan(override, notes, "--level")
    m = RELEASE_LINE.search(pr.body)
    if m:
        return ReleasePlan(m.group(1).lower(), notes, "PR body `Release:` line")
    if pr.author_is_bot:
        return ReleasePlan("none", None, "bot PR: lands without a bump")
    if ships_nothing(pr):
        return ReleasePlan("none", None, "every changed path ships nothing")
    blob = "\n".join(pr.subjects)
    if BREAKING.search(blob):
        return ReleasePlan("major", notes, "commit subjects (breaking)")
    if any(FEAT.match(s) for s in pr.subjects):
        return ReleasePlan("minor", notes, "commit subjects (feat)")
    return ReleasePlan("patch", notes, "commit subjects")


TITLE_VERSION = re.compile(r"\s*\(v?\d+\.\d+\.\d+\)|\s+[\u2014-]\s+v\d+\.\d+\.\d+\s*$")


def squash_subject(title: str, number: int, version: str | None) -> str:
    """`title (vX.Y.Z) (#N)`: the version comes from the landing, not the title."""
    clean = TITLE_VERSION.sub("", title).strip()
    return f"{clean} (v{version}) (#{number})" if version else f"{clean} (#{number})"


# --------------------------------------------------------------------------
# git mechanics for the bump (operate on a working tree; no network but push)
# --------------------------------------------------------------------------

ANY_H2 = re.compile(r"^##\s", re.M)


def strip_sections(text: str, known: set[str], heading_re: re.Pattern[str]
                   ) -> tuple[str, list[str]]:
    """Remove changelog sections whose version is not in `known`.

    Returns the new text and the bodies removed, oldest heading last, so a
    hand-written section survives as the notes for the re-cut release.
    """
    out, removed = text, []
    for m in reversed(list(heading_re.finditer(text))):
        if m.group("v") in known:
            continue
        nxt = ANY_H2.search(text, m.end())
        end = nxt.start() if nxt else len(text)
        tail = text[m.end():end]
        body = tail.split("\n", 1)[1] if "\n" in tail else ""
        if body.strip():
            removed.insert(0, body.strip())
        out = out[:m.start()] + out[end:]
    return out, removed


def _show(wt: Path, rev: str, rel: Path) -> str | None:
    proc = run(["git", "-C", str(wt), "show", f"{rev}:{rel.as_posix()}"],
               check=False)
    return proc.stdout if proc.returncode == 0 else None


def version_at(vt, wt: Path, rev: str, loc) -> str | None:
    text = _show(wt, rev, loc.path)
    return vt._extract(text, loc.kind) if text else None


def remote_tag_exists(repo: str, tag: str) -> bool:
    proc = run(["gh", "api", f"repos/{repo}/git/ref/tags/{tag}"],
               cwd=tempfile.gettempdir(), check=False)
    return proc.returncode == 0


def bump_state(vt, wt: Path, base_ref: str, tag_taken) -> tuple[str, str | None]:
    """How the branch stands against the base: (state, branch version).

    noversion  the repo has no version location: land without a bump
    absent     the branch carries no bump: cut one
    current    the branch's bump is still the next version: merge as it is
    stale      the base moved past it, or its tag is taken: drop and re-cut
    """
    canonical, _, _ = vt.detect(wt)
    if canonical is None or vt.parse_version(canonical.value or "") is None:
        return "noversion", None
    head_v = canonical.value
    mb = git(wt, "merge-base", "HEAD", base_ref).strip()
    mb_v = version_at(vt, wt, mb, canonical)
    if mb_v is None or head_v == mb_v:
        return "absent", head_v
    base_v = version_at(vt, wt, base_ref, canonical) or "0.0.0"
    if vt.parse_version(head_v) > (vt.parse_version(base_v) or (0, 0, 0)) \
            and not tag_taken(f"v{head_v}"):
        return "current", head_v
    return "stale", head_v


def drop_stale_bump(vt, wt: Path, base_ref: str) -> str | None:
    """Undo a bump cut before landing, surgically, and return its notes.

    Version fields go back to their merge-base values and the changelog
    sections the branch added come out. Nothing else in those files moves,
    so dependency edits sharing package.json with the version are untouched.
    """
    canonical, mirrors, _ = vt.detect(wt)
    if canonical is None:
        return None
    mb = git(wt, "merge-base", "HEAD", base_ref).strip()
    mb_v = version_at(vt, wt, mb, canonical)
    if mb_v is None or mb_v == canonical.value:
        return None
    for loc in [canonical, *mirrors]:
        old = version_at(vt, wt, mb, loc)
        if old and old != loc.value:
            vt.write_version(wt, loc, old)
    removed: list[str] = []
    rel = vt.changelog_path(wt)
    mb_changelog = _show(wt, mb, rel)
    if mb_changelog is not None and (wt / rel).exists():
        known = {m.group("v") for m in vt.CHANGELOG_HEADING.finditer(mb_changelog)}
        with open(wt / rel, encoding="utf-8", newline="") as fh:
            text = fh.read()
        updated, removed = strip_sections(text, known, vt.CHANGELOG_HEADING)
        if updated != text:
            with open(wt / rel, "w", encoding="utf-8", newline="") as fh:
                fh.write(updated)
    git(wt, "add", "-A")
    if run(["git", "-C", str(wt), "diff", "--cached", "--quiet"],
           check=False).returncode != 0:
        git(wt, "commit", "-m",
            "chore(release): drop pre-landing bump (re-cut at landing)")
    return "\n\n".join(removed).strip() or None


def prepare_branch(vt, vt_path: Path, wt: Path, base_ref: str, level: str,
                   notes: str | None, tag_taken, scratch: Path) -> str:
    """Bring the branch to 'base + one fresh bump commit'. Returns the version."""
    carried = drop_stale_bump(vt, wt, base_ref)
    if int(git(wt, "rev-list", "--count", f"HEAD..{base_ref}").strip() or 0):
        merge = run(["git", "-C", str(wt), "merge", "--no-edit", base_ref],
                    check=False)
        if merge.returncode != 0:
            conflicted = git(wt, "diff", "--name-only", "--diff-filter=U",
                             check=False).split()
            run(["git", "-C", str(wt), "merge", "--abort"], check=False)
            raise ToolError("merging the base branch conflicts in: "
                            + (", ".join(conflicted) or "unknown paths"))
    canonical, _, _ = vt.detect(wt)
    current = vt.parse_version((canonical.value if canonical else "") or "")
    if current is None:
        raise ToolError("no parseable version after merging the base branch")
    target = vt.fmt_version(vt.bump(current, level))
    tag = f"v{target}"
    if tag_taken(tag):
        raise ToolError(f"tag {tag} already exists on the remote but the base "
                        f"branch is still at {canonical.value}; run "
                        "version_tool.py check on the base branch")
    if tag in git(wt, "tag", "--list", tag).split():
        # a local-only draft from an earlier cut: move it aside, never delete
        sha = git(wt, "rev-parse", "--short", f"{tag}^{{commit}}").strip()
        git(wt, "tag", f"{tag}-draft-{sha}", f"{tag}^{{commit}}", check=False)
        git(wt, "tag", "-d", tag)
    cmd = [sys.executable, str(vt_path), "--repo", str(wt),
           "release", level, "--apply", "--no-tag"]
    body = notes or carried
    if body:
        notes_file = scratch / "release-notes.md"
        notes_file.write_text(body.rstrip() + "\n", encoding="utf-8")
        cmd += ["--notes", str(notes_file)]
    out = run(cmd, check=False)
    if out.returncode != 0:
        raise ToolError("version tool refused the release:\n"
                        + (out.stdout + out.stderr).strip())
    canonical, _, _ = vt.detect(wt)
    if canonical is None or canonical.value != target:
        raise ToolError(f"expected version {target} after the release, found "
                        f"{canonical.value if canonical else 'none'}")
    return target


# --------------------------------------------------------------------------
# workspace: a detached worktree off a local clone, or a throwaway clone
# --------------------------------------------------------------------------

def find_clone(repo: str, hint: str | None = None) -> Path | None:
    name = repo.split("/", 1)[1]
    here = Path.cwd()
    roots = [r for r in os.environ.get("PR_TOOL_CODE_ROOT", "").split(os.pathsep)
             if r] + _names(config().get("code_roots")) + list(CODE_ROOTS) \
        + [str(here), str(here.parent)]
    # The current directory may itself be the clone. Every candidate is still
    # checked below: only a clone whose origin is this repository is used.
    candidates = ([Path(hint)] if hint else []) + [here]
    for root in roots:
        base = Path(root).expanduser()
        candidates += [base / name, base / "Web" / name]
    want = repo.lower()
    for cand in candidates:
        if not (cand / ".git").exists():
            continue
        url = run(["git", "-C", str(cand), "remote", "get-url", "origin"],
                  check=False).stdout.strip().lower()
        url = url[:-4] if url.endswith(".git") else url
        if url.endswith("/" + want) or url.endswith(":" + want):
            return cand
    if hint:
        raise ToolError(f"--clone {hint} is not a clone of {repo}")
    return None


class Workspace:
    def __init__(self, pr: PR, hint: str | None = None):
        self.clone = find_clone(pr.repo, hint)
        self.tmp = Path(tempfile.mkdtemp(prefix="land-pr-"))
        self.wt = self.tmp / "wt"
        try:
            if self.clone is None:
                self.clone = self.tmp / "clone"
                gh("repo", "clone", pr.repo, str(self.clone))
            git(self.clone, "fetch", "origin",
                f"+refs/heads/{pr.head}:refs/remotes/origin/{pr.head}",
                f"+refs/heads/{pr.base}:refs/remotes/origin/{pr.base}")
            git(self.clone, "worktree", "add", "--detach", str(self.wt),
                f"origin/{pr.head}")
            if git(self.wt, "rev-parse", "HEAD").strip() != pr.head_oid:
                raise ToolError("the branch moved while landing started; "
                                "run again")
        except ToolError:
            self.close()
            raise

    def close(self) -> None:
        run(["git", "-C", str(self.clone), "worktree", "remove", "--force",
             str(self.wt)], check=False)
        shutil.rmtree(self.tmp, ignore_errors=True)
        run(["git", "-C", str(self.clone), "worktree", "prune"], check=False)


class Lock:
    """One landing per repo per machine; the remote check covers the rest."""

    def __init__(self, repo: str):
        root = Path.home() / ".claude" / "state" / "land-pr"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / (repo.replace("/", "__") + ".lock")

    def __enter__(self) -> "Lock":
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {datetime.now(timezone.utc)}".encode())
                os.close(fd)
                return self
            except FileExistsError:
                if time.time() - self.path.stat().st_mtime > 45 * 60:
                    self.path.unlink(missing_ok=True)   # abandoned
                    continue
                raise ToolError(f"another landing holds {self.path}; "
                                "wait for it or delete the file if it died")
        raise ToolError(f"could not take {self.path}")

    def __exit__(self, *_: object) -> None:
        self.path.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# GitHub actions
# --------------------------------------------------------------------------

def signed_in() -> str:
    """The login `gh` is signed in as ('' when it is not), asked once."""
    if "me" not in _CACHE:
        _CACHE["me"] = gh("api", "user", "--jq", ".login", check=False).strip()
    return str(_CACHE["me"])


def trusted_authors() -> set[str]:
    me = signed_in().lower()
    return {me} if me else set()


def detect_method(pr: PR) -> str:
    """The repo's merge style, read from how its last merges actually landed."""
    out = gh("api", f"repos/{pr.repo}/commits?sha={pr.base}&per_page=20",
             "--jq", '.[] | "\\(.parents|length)\\t\\(.commit.message|split("\\n")[0])"',
             check=False)
    squash = merge = 0
    for line in out.splitlines():
        parents, _, subject = line.partition("\t")
        if parents == "2" and subject.startswith("Merge pull request"):
            merge += 1
        elif parents == "1" and re.search(r"\(#\d+\)$", subject):
            squash += 1
    want = "merge" if merge > squash else "squash"
    return want if want in pr.methods else pr.methods[0]


def tag_commit(repo: str, tag: str) -> str | None:
    """The commit a remote tag points at (annotated tags peeled), or None."""
    out = gh("api", f"repos/{repo}/git/ref/tags/{tag}",
             "--jq", '"\\(.object.type) \\(.object.sha)"', check=False).split()
    if len(out) != 2 or not re.fullmatch(r"[0-9a-f]{40}", out[1]):
        return None
    kind, sha = out
    if kind == "tag":
        sha = gh("api", f"repos/{repo}/git/tags/{sha}", "--jq", ".object.sha",
                 check=False).strip()
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def create_tag(repo: str, version: str, oid: str) -> str:
    tag = f"v{version}"
    if remote_tag_exists(repo, tag):
        # Someone got there first (another machine: the lock is per machine).
        # That is only fine if it is this very release.
        at = tag_commit(repo, tag)
        if at != oid:
            raise ToolError(f"tag {tag} already exists at "
                            f"{(at or 'an unreadable ref')[:9]}, not at the "
                            f"merge commit {oid[:9]}; it is protected, so "
                            "this needs a person")
        return f"tag {tag} already on the merge commit"
    sha = gh("api", f"repos/{repo}/git/tags", "-f", f"tag={tag}",
             "-f", f"message=Version {version}", "-f", f"object={oid}",
             "-f", "type=commit", "--jq", ".sha").strip()
    gh("api", f"repos/{repo}/git/refs", "-f", f"ref=refs/tags/{tag}",
       "-f", f"sha={sha}")
    return f"tagged {tag} at {oid[:9]}"


def close_superseded(repo: str, number: int, why: str) -> None:
    gh("pr", "close", str(number), "-R", repo, "--delete-branch",
       "--comment", why)


def wait_ready(repo: str, number: int, oid: str, minutes: float,
               trusted: set[str], had_checks: bool,
               owners: list[str] | None = None,
               accept_missing: bool = False) -> tuple[bool, PR]:
    """Poll until the PR is READY at `oid` twice running, or time runs out."""
    deadline = time.time() + minutes * 60
    streak = 0
    time.sleep(min(20, max(0, minutes * 60)))   # let the push register
    while True:
        pr = fetch_pr(repo, number)
        if pr.state != "OPEN":
            raise ToolError(f"{pr.ref} is {pr.state.lower()} now")
        if pr.head_oid != oid:
            raise ToolError("someone else pushed to the branch; run again")
        v = classify(pr, datetime.now(timezone.utc), trusted, owners,
                     accept_missing)
        settled = v.state == "READY" and (pr.checks or not had_checks)
        if v.state not in ("READY", "WAITING"):
            raise ToolError(f"{pr.ref} is {v.label}: {'; '.join(v.reasons)}")
        streak = streak + 1 if settled else 0
        if streak >= 2:
            return True, pr
        if time.time() >= deadline:
            return False, pr
        time.sleep(20)


# --------------------------------------------------------------------------
# verbs
# --------------------------------------------------------------------------

def print_threads(pr: PR) -> None:
    for t in pr.threads:
        where = f"{t['path']}:{t['line']}" if t.get("line") else (t.get("path") or "")
        mark = " (outdated)" if t["outdated"] else ""
        text = re.sub(r"<!--.*?-->|<[^>]+>", " ", t["body"], flags=re.S)
        first = " ".join(text.split())[:160]
        print(f"    {t['id']}  {where}{mark}  @{t['author']}")
        print(f"      {first}")
        if t["url"]:
            print(f"      {t['url']}")


def cmd_land(ref: str, apply: bool = False, level: str | None = None,
             no_bump: bool = False, method: str | None = None,
             clone: str | None = None, wait: float = 8.0,
             trusted: set[str] | None = None,
             owners: list[str] | None = None,
             accept_missing: bool = False, **_: object) -> int:
    repo, number = parse_ref(ref)
    trusted = trusted if trusted is not None else trusted_authors()
    owners = owners if owners is not None else _owners(None)
    _CACHE["clone_hint"] = clone      # so proofs can use the same clone
    pr = fetch_pr(repo, number)
    print(f"{pr.ref}  {pr.title}")
    if pr.state == "MERGED":
        return finish_merged(pr, apply, trusted, owners)
    if pr.state != "OPEN":
        print(f"  already {pr.state.lower()}; nothing to land")
        return 0

    v = classify(pr, datetime.now(timezone.utc), trusted, owners, accept_missing)
    if v.state == "WAITING" and apply and wait > 0:
        print(f"  waiting up to {wait:g} min: {'; '.join(v.reasons)}")
        ok, pr = wait_ready(repo, number, pr.head_oid, wait, trusted,
                            bool(pr.checks), owners, accept_missing)
        if not ok:
            print("  WAITING: still running. Run the same command again.")
            return 3
        v = classify(pr, datetime.now(timezone.utc), trusted, owners,
                     accept_missing)
    plan = release_plan(pr, level, no_bump)
    if pr.cross_repo and plan.level != "none":
        plan = ReleasePlan("none", None, "fork PR: its branch cannot take a bump")
    # A CONFLICT can be nothing more than a pre-landing bump gone stale: each
    # merge to the base moves the version and changelog lines it touched.
    # That one the lander repairs itself, so it gets as far as looking.
    repair = v.state == "CONFLICT" and plan.level != "none" and not pr.cross_repo
    if v.state != "READY" and not repair:
        return refuse(pr, v)
    if repair:
        # Every other gate first. The repair pushes to the branch, and nothing
        # is pushed to a PR that would be refused anyway (open threads, no
        # review of the head, a failing check).
        rest = classify(pr, datetime.now(timezone.utc), trusted, owners,
                        accept_missing, ignore_conflict=True)
        if rest.state != "READY":
            print(f"  CONFLICT with {pr.base}; and apart from the conflict:")
            return refuse(pr, rest)
    method = method or detect_method(pr)
    print(f"  release: {plan.level}  ({plan.source})")
    if plan.level != "none":
        print("  notes:   " + ("from the PR body" if plan.notes
                               else "none in the PR body; drafted from commits"))
    print(f"  merge:   {method}, delete branch, tag after merge")
    if repair:
        print(f"  CONFLICT with {pr.base}: --apply checks whether a version "
              "bump already on the branch is the cause, drops it, merges the "
              "base and re-cuts. Any other conflict is refused, nothing pushed.")
    if not apply:
        print("  (dry run: pass --apply to land)")
        return 1 if repair else 0

    version: str | None = None
    with Lock(repo):
        if plan.level != "none":
            vt, vt_path = load_version_tool()
            ws = Workspace(pr, clone)
            try:
                base_ref = f"origin/{pr.base}"
                taken = lambda tag: remote_tag_exists(repo, tag)  # noqa: E731
                state, head_v = bump_state(vt, ws.wt, base_ref, taken)
                # A bump on the branch can conflict with the base even while
                # its number is still the right next one (branch 1.0.0->1.1.0,
                # base moved to 1.0.1): the version line and the changelog
                # were both touched on each side. So in a repair any bump on
                # the branch is dropped and re-cut, "current" included.
                if repair and state not in ("stale", "current"):
                    return refuse(pr, v)    # a real conflict: not ours to fix
                if state == "noversion":
                    print("  NOTE: no version location in this repo; landing "
                          "without a bump. Run version_tool.py backfill here.")
                elif state == "current" and not repair:
                    version = head_v
                    print(f"  bump v{version} on the branch is current")
                else:
                    if state in ("stale", "current"):
                        print(f"  bump v{head_v} on the branch "
                              f"{'conflicts with' if repair else 'is stale against'}"
                              f" {pr.base}; re-cutting")
                    version = prepare_branch(vt, vt_path, ws.wt, base_ref,
                                             plan.level, plan.notes, taken,
                                             ws.tmp)
                    made = git(ws.wt, "rev-list", f"{pr.head_oid}..HEAD").split()
                    _CACHE.setdefault("own_commits", set()).update(made)  # type: ignore[union-attr]
                    git(ws.wt, "push", "origin", f"HEAD:refs/heads/{pr.head}")
                    oid = git(ws.wt, "rev-parse", "HEAD").strip()
                    print(f"  pushed bump v{version} ({oid[:9]}); waiting on checks")
                    ok, pr = wait_ready(repo, number, oid, wait, trusted,
                                        bool(pr.checks), owners, accept_missing)
                    if not ok:
                        print("  WAITING: checks on the bump commit are still "
                              "running. Run the same command again.")
                        return 3
            finally:
                ws.close()

        # No --delete-branch here: the branch is deleted in after_merge, and
        # only once any PR stacked on it has been moved off it.
        args = ["pr", "merge", str(number), "-R", repo, f"--{method}",
                "--match-head-commit", pr.head_oid]
        if method == "squash":
            args += ["--subject", squash_subject(pr.title, number, version)]
        gh(*args)
        # `gh pr merge` succeeding is not the PR being merged: with a merge
        # queue it only enqueues. Tag and clean up only once GitHub says so.
        merged = fetch_pr(repo, number)
        for _ in range(MERGE_POLLS):
            if merged.state == "MERGED":
                break
            time.sleep(MERGE_POLL_SECONDS)
            merged = fetch_pr(repo, number)
        if merged.state != "MERGED":
            print(f"  NOT MERGED YET: GitHub took the request but the PR is still "
                  f"{merged.state.lower()} (a merge queue, or a rule still "
                  "pending). Nothing was tagged or closed. Run the same "
                  "command again once it merges.")
            return 3
        print(f"  merged ({method}) as {(merged.merge_commit or '?')[:9]}")
        return after_merge(merged, version)


MERGE_POLLS = 5
MERGE_POLL_SECONDS = 4
RELEASE_COMMIT = re.compile(r"^chore\(release\): v(\d+\.\d+\.\d+[\w.+-]*)$")


def refuse(pr: PR, v: Verdict) -> int:
    print(f"  {v.label}: {'; '.join(v.reasons) or 'not ready'}")
    print(f"  next: {STALE_STEP if v.stale else NEXT_STEP.get(v.state, '')}")
    if v.state == "THREADS":
        print_threads(pr)
    return 3 if v.state == "WAITING" else 1


def landed_version(pr: PR) -> str | None:
    """The version a PR carries: its last release commit, unless dropped."""
    for subject in reversed(pr.subjects):
        if subject.startswith("chore(release): drop pre-landing bump"):
            return None
        m = RELEASE_COMMIT.match(subject)
        if m:
            return m.group(1)
    return None


def after_merge(pr: PR, version: str | None) -> int:
    """Everything that follows the merge. Every step is safe to repeat, so a
    run that died here is finished by running `land` on the merged PR again."""
    tag_failed = False
    if version and pr.merge_commit:
        try:
            print("  " + create_tag(pr.repo, version, pr.merge_commit))
        except ToolError as exc:
            tag_failed = True
            print(f"  TAG FAILED: merged, but v{version} is not tagged: {exc}")
    if pr.head and pr.head != pr.base and not pr.cross_repo:
        # Only the branch as it was merged; one that has moved since is in use.
        tip = gh("api", f"repos/{pr.repo}/git/ref/heads/{pr.head}",
                 "--jq", ".object.sha", check=False).strip()
        if tip and tip == pr.head_oid:
            # GitHub retargets PRs stacked on a branch only when IT deletes
            # the branch (the merge button). A deletion through the API
            # CLOSES them instead (plugins#10, 2026-11-11). So move every
            # dependent to this PR's base first, and keep the branch if any
            # of them could not be moved.
            dependents = gh("pr", "list", "-R", pr.repo, "--state", "open",
                            "--base", pr.head, "--json", "number",
                            "--jq", ".[].number", check=False).split()
            stranded = []
            for n in dependents:
                try:
                    gh("pr", "edit", n, "-R", pr.repo, "--base", pr.base)
                    print(f"  retargeted #{n} from {pr.head} to {pr.base}")
                except ToolError as exc:
                    stranded.append(n)
                    print(f"  could not retarget #{n} to {pr.base}: {exc}")
            if stranded:
                print(f"  kept branch {pr.head}: #{', #'.join(stranded)} "
                      "still based on it; deleting it would close them")
            else:
                gh("api", "-X", "DELETE",
                   f"repos/{pr.repo}/git/refs/heads/{pr.head}", check=False)
                print(f"  deleted branch {pr.head}")
    leftovers = gh("pr", "list", "-R", pr.repo, "--state", "open", "--head",
                   f"autofix/pr-{pr.number}", "--json", "number",
                   "--jq", ".[].number", check=False).split()
    for n in leftovers:
        try:
            close_superseded(pr.repo, int(n), f"Closing: source PR #{pr.number} "
                             "merged, so this autofix draft is superseded.")
            print(f"  closed superseded autofix #{n}")
        except ToolError as exc:
            print(f"  could not close autofix #{n}: {exc}")
    if tag_failed:
        print("  Run the same command again to retry the tag.")
        return 1
    print(f"  LANDED {pr.ref}" + (f" as v{version}" if version else ""))
    return 0


def commit_files(repo: str, oid: str) -> list[dict]:
    raw = gh("api", f"repos/{repo}/commits/{oid}", "--jq", ".files", check=False)
    try:
        files = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError:
        return []
    return files if isinstance(files, list) else []


def confirmed_version(pr: PR) -> tuple[str | None, str]:
    """(version, why not) for a merged PR whose commits name a release.

    A commit subject is only a claim, and a tag cannot be taken back, so the
    claim is checked twice before anything is tagged: the release commit must
    be a pure version bump, and a file it bumped must declare that version
    at the merge commit.
    """
    version = landed_version(pr)
    if not version or not pr.merge_commit:
        return None, ""
    wanted = f"chore(release): v{version}"
    at = max((i for i, s in enumerate(pr.subjects) if s == wanted), default=-1)
    oid = pr.commit_oids[at] if 0 <= at < len(pr.commit_oids) else ""
    files = commit_files(pr.repo, oid) if oid else []
    if not release_diff_is_mechanical(files):
        return None, "its release commit changes more than version lines"
    for f in files:
        name = f.get("filename") or ""
        base = name.rsplit("/", 1)[-1]
        if base.upper().startswith("CHANGELOG"):
            continue
        text = gh("api", f"repos/{pr.repo}/contents/{name}?ref={pr.merge_commit}",
                  "-H", "Accept: application/vnd.github.raw", check=False)
        if any(_version_line(base, line) and version in SEMVER.findall(line)
               for line in text.splitlines()):
            return version, ""
    return None, f"no version file declares {version} at the merge commit"


def finish_merged(pr: PR, apply: bool, trusted: set[str],
                  owners: list[str]) -> int:
    """`land` on a PR that is already merged: finish a landing that stopped
    after the merge (tag refused, process killed) instead of calling it done."""
    # The same trust an open PR needs: your PR, in a repository that is yours.
    home = {o.lower() for o in owners}
    if (not pr.author_is_bot and pr.author.lower() not in trusted) \
            or pr.repo.split("/", 1)[0].lower() not in home:
        print("  already merged; not your PR or not your repository, so "
              "nothing is tagged or cleaned up from here")
        return 0
    claimed = landed_version(pr)
    version: str | None = None
    untagged = bool(claimed and pr.merge_commit
                    and not remote_tag_exists(pr.repo, f"v{claimed}"))
    if untagged:
        version, why = confirmed_version(pr)
        if version is None:
            print(f"  already merged. A commit names v{claimed} and it is not "
                  f"tagged, but that could not be confirmed: {why}. Nothing "
                  "is tagged; if the version is right, tag it by hand.")
            return 1
    elif claimed and pr.merge_commit:
        # Tagged, but is it THIS release? A run that failed because the tag
        # sits on another commit must not be reported as finished by the
        # next run just because "a tag of that name exists".
        at = tag_commit(pr.repo, f"v{claimed}")
        if at != pr.merge_commit:
            print(f"  already merged, and v{claimed} is tagged, but at "
                  f"{(at or 'an unreadable ref')[:9]}, not at this PR's merge "
                  f"commit {pr.merge_commit[:9]}. Tags are protected, so "
                  "this needs a person.")
            return 1
    if not apply:
        if untagged:
            print(f"  already merged, but v{version} is not tagged: --apply "
                  f"tags {pr.merge_commit[:9]}")
            return 10
        print("  already merged; nothing to land")
        return 0
    print("  already merged; finishing what is left")
    return after_merge(pr, version)


def collect(owners: list[str], repo: str | None) -> list[tuple[str, int]]:
    refs: set[tuple[str, int]] = set()
    queries = [["--owner", o] for o in owners] + [["--author", "@me"]]
    if repo:
        queries = [["--repo", repo]]
    for q in queries:
        out = gh("search", "prs", "--state", "open", "--archived=false",
                 "--limit", "300", *q, "--json", "repository,number",
                 "--jq", '.[] | "\\(.repository.nameWithOwner)\\t\\(.number)"')
        for line in out.splitlines():
            name, _, num = line.partition("\t")
            if name and num:
                refs.add((name, int(num)))
    return sorted(refs)


ORDER = ["READY", "SUPERSEDED", "THREADS", "FAILING", "CONFLICT", "REVIEW",
         "BLOCKED", "WAITING", "STACKED", "AUTOFIX", "DRAFT", "EXTERNAL",
         "ELSEWHERE"]


def survey(owners: list[str], repo: str | None, trusted: set[str]
           ) -> list[tuple[PR, Verdict]]:
    refs = collect(owners, repo)
    with ThreadPoolExecutor(max_workers=6) as pool:
        prs = list(pool.map(lambda r: fetch_pr(*r), refs))
    now = datetime.now(timezone.utc)
    rows = [(pr, classify(pr, now, trusted, owners)) for pr in prs]
    rows.sort(key=lambda row: (row[1].stale, ORDER.index(row[1].state)
                               if row[1].state in ORDER else 99,
                               row[0].repo.lower(), row[0].number))
    return rows


def print_survey(rows: list[tuple[PR, Verdict]]) -> None:
    now = datetime.now(timezone.utc)
    last = None
    for pr, v in rows:
        if v.label != last:
            step = STALE_STEP if v.stale else NEXT_STEP.get(v.state, "")
            print(f"\n{v.label}  ({step})")
            last = v.label
        idle = (now - pr.updated).days
        why = f"  [{'; '.join(v.reasons)}]" if v.reasons else ""
        print(f"  {pr.ref:<46} {idle:>3}d  {pr.title[:60]}{why}")
    counts: dict[str, int] = {}
    for _, v in rows:
        counts[v.label] = counts.get(v.label, 0) + 1
    print(f"\n{len(rows)} open: "
          + ", ".join(f"{k} {n}" for k, n in sorted(counts.items())))


def _configured_owners(args_owner: list[str] | None) -> list[str]:
    env = [o for o in os.environ.get("PR_TOOL_OWNERS", "").split(",") if o]
    return args_owner or env or _names(config().get("owners")) or list(OWNERS)


def _owners(args_owner: list[str] | None) -> list[str]:
    """Whose repositories count as yours; see the POLICY note on OWNERS."""
    chosen = _configured_owners(args_owner)
    if chosen:
        return chosen
    me = signed_in()
    return [me] if me else []


def _owner_hint(args_owner: list[str] | None, repo: str | None) -> None:
    """Say so when only the signed-in account is being surveyed: PRs in an
    organization's repositories are then missing, not absent."""
    if repo or _configured_owners(args_owner):
        return
    print(f"note: surveying {signed_in() or 'no account (gh is not signed in)'} "
          f"only. To add organizations set \"owners\" in {CONFIG_PATH} or "
          "PR_TOOL_OWNERS=a,b.", file=sys.stderr)


def cmd_status(owner: list[str] | None = None, repo: str | None = None,
               as_json: bool = False, **_: object) -> int:
    trusted = trusted_authors()
    _owner_hint(owner, repo)
    rows = survey(_owners(owner), repo, trusted)
    if as_json:
        print(json.dumps([{"ref": pr.ref, "state": v.state, "stale": v.stale,
                           "reasons": v.reasons, "title": pr.title,
                           "url": pr.url, "author": pr.author,
                           "updated": pr.updated.isoformat()}
                          for pr, v in rows], indent=2))
    else:
        print_survey(rows)
    actionable = any(v.state == "SUPERSEDED" or (v.state == "READY" and not v.stale)
                     for _, v in rows)
    return 10 if actionable else 0


def cmd_sweep(owner: list[str] | None = None, repo: str | None = None,
              apply: bool = False, limit: int = 25, wait: float = 8.0,
              **_: object) -> int:
    trusted = trusted_authors()
    _owner_hint(owner, repo)
    owners = _owners(owner)
    rows = survey(owners, repo, trusted)
    print_survey(rows)
    ready = [pr for pr, v in rows if v.state == "READY" and not v.stale]
    dead = [pr for pr, v in rows if v.state == "SUPERSEDED"]
    if not apply:
        print(f"\nsweep would close {len(dead)} superseded and land "
              f"{min(len(ready), limit)} ready (dry run: pass --apply)")
        return 10 if (ready or dead) else 0

    failures = waiting = 0
    for pr in dead:
        src = autofix_source(pr)
        try:
            close_superseded(pr.repo, pr.number, f"Closing: source PR #{src} is "
                             f"{(pr.autofix_source_state or 'done').lower()}, "
                             "so this autofix draft is superseded.")
            print(f"closed superseded {pr.ref}")
        except ToolError as exc:
            failures += 1
            print(f"FAILED to close {pr.ref}: {exc}")
    for pr in ready[:limit]:
        print()
        try:
            code = cmd_land(pr.ref, apply=True, wait=wait, trusted=trusted,
                            owners=owners)
        except ToolError as exc:
            code = 1
            print(f"  FAILED: {exc}")
        failures += code == 1
        waiting += code == 3
    print(f"\nsweep done: {failures} failed, {waiting} still waiting on checks")
    return 1 if failures else (3 if waiting else 0)


RESOLVE = ("mutation($id:ID!){resolveReviewThread(input:{threadId:$id})"
           "{thread{isResolved}}}")


def cmd_threads(ref: str, resolve: list[str] | None = None, **_: object) -> int:
    repo, number = parse_ref(ref)
    for thread_id in resolve or []:
        gql(RESOLVE, id=thread_id)
        print(f"resolved {thread_id}")
    pr = fetch_pr(repo, number)
    print(f"{pr.ref}: {len(pr.threads)} unresolved thread(s)")
    print_threads(pr)
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="pr_tool.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)

    def scope(p: argparse.ArgumentParser) -> None:
        p.add_argument("--owner", action="append", help="account to survey (repeatable)")
        p.add_argument("--repo", help="limit to one OWNER/NAME")

    s = sub.add_parser("status", help="classify every open PR; never writes")
    scope(s)
    s.add_argument("--json", dest="as_json", action="store_true")

    la = sub.add_parser("land", help="bump, wait for checks, merge, tag")
    la.add_argument("ref", help="OWNER/NAME#N or a PR URL")
    la.add_argument("--apply", action="store_true")
    la.add_argument("--level", choices=["major", "minor", "patch"])
    la.add_argument("--no-bump", action="store_true")
    la.add_argument("--method", choices=["squash", "merge", "rebase"])
    la.add_argument("--clone", help="local clone to work from")
    la.add_argument("--wait", type=float, default=8.0,
                    help="minutes to wait on checks before exiting 3 (default 8)")
    la.add_argument("--accept-missing-review", dest="accept_missing",
                    action="store_true",
                    help="land although the automated reviewer that acted on "
                         "this PR earlier has not reviewed the head (it is "
                         "gone, or will not re-review). Never skips a check "
                         "or a running workflow; never implied; never in sweep")

    sw = sub.add_parser("sweep", help="close superseded, land everything READY")
    scope(sw)
    sw.add_argument("--apply", action="store_true")
    sw.add_argument("--max", dest="limit", type=int, default=25)
    sw.add_argument("--wait", type=float, default=8.0)

    th = sub.add_parser("threads", help="list (and resolve) review threads")
    th.add_argument("ref")
    th.add_argument("--resolve", nargs="+", metavar="ID")

    args = ap.parse_args(argv)
    verbs = {"status": cmd_status, "land": cmd_land, "sweep": cmd_sweep,
             "threads": cmd_threads}
    try:
        return verbs[args.verb](**{k: v for k, v in vars(args).items()
                                   if k != "verb"})
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
