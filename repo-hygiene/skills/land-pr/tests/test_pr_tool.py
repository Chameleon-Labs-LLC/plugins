"""Tests for pr_tool.py.

Classification and release-plan tests are pure. The bump tests build real git
repositories (a bare origin plus a clone) and run the real version tool, so a
failure there means a real branch would be mishandled at landing.

    python -m pytest ${CLAUDE_PLUGIN_ROOT}/skills/land-pr/tests/ -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pr_tool as pt  # noqa: E402

NOW = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)
ME = {"octo-user"}


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    """No test may depend on this machine's config, environment or sign-in:
    whose repositories count as "yours" is fixed here for every test."""
    monkeypatch.setenv("PR_TOOL_CONFIG", str(tmp_path / "no-such-config.json"))
    monkeypatch.delenv("PR_TOOL_OWNERS", raising=False)
    monkeypatch.delenv("PR_TOOL_CODE_ROOT", raising=False)
    monkeypatch.setattr(pt, "OWNERS", ["octo-user", "Octo-Org"])
    monkeypatch.setattr(pt, "_CACHE", {"me": "octo-user"})


def test_owners_come_from_flag_then_env_then_config_then_sign_in(monkeypatch, tmp_path):
    monkeypatch.setattr(pt, "OWNERS", [])            # as the tool ships
    assert pt._owners(None) == ["octo-user"]           # the signed-in account
    cfg = tmp_path / "land-pr.json"
    cfg.write_text('{"owners": ["me", "my-org"], "code_roots": ["~/code"]}',
                   encoding="utf-8")
    monkeypatch.setenv("PR_TOOL_CONFIG", str(cfg))
    assert pt._owners(None) == ["me", "my-org"]
    monkeypatch.setenv("PR_TOOL_OWNERS", "acme,beta")
    assert pt._owners(None) == ["acme", "beta"]
    assert pt._owners(["flag"]) == ["flag"]
    # Not signed in and nothing configured: nobody's repositories are "yours",
    # so nothing can be classified READY.
    monkeypatch.delenv("PR_TOOL_OWNERS")
    monkeypatch.setenv("PR_TOOL_CONFIG", str(tmp_path / "absent.json"))
    monkeypatch.setattr(pt, "_CACHE", {"me": ""})
    assert pt._owners(None) == []
    assert pt.classify(make(), NOW, ME).label == "ELSEWHERE"


def test_a_broken_config_file_is_an_error_not_a_silent_default(monkeypatch, tmp_path):
    cfg = tmp_path / "land-pr.json"
    cfg.write_text('{"owners": ["me",', encoding="utf-8")
    monkeypatch.setenv("PR_TOOL_CONFIG", str(cfg))
    with pytest.raises(pt.ToolError):
        pt._owners(None)
    cfg.write_text('["me"]', encoding="utf-8")
    monkeypatch.setattr(pt, "_CACHE", {"me": "octo-user"})
    with pytest.raises(pt.ToolError):
        pt.config()


def make(**kw) -> pt.PR:
    base = dict(repo="octo-user/r", number=7, title="fix: thing", author="octo-user",
                head="fix/thing", head_oid="a" * 40,
                updated=NOW - timedelta(hours=2),
                head_committed=NOW - timedelta(hours=2),
                files=["src/app.py"], files_total=1,
                subjects=["fix: thing"], checks=[("ci", "pass")],
                reviewed_head=True)
    base.update(kw)
    return pt.PR(**base)


def state(**kw) -> str:
    return pt.classify(make(**kw), NOW, ME).label


# ---- classification -------------------------------------------------------

def test_green_reviewed_pr_is_ready():
    assert state() == "READY"


def test_pending_check_waits_and_failing_check_fails():
    assert state(checks=[("ci", "pass"), ("CodeRabbit", "pending")]) == "WAITING"
    assert state(checks=[("ci", "fail"), ("x", "pending")]) == "FAILING"


def test_unresolved_thread_blocks_even_when_outdated():
    thread = {"id": "T1", "path": "a.py", "line": 3, "outdated": True,
              "author": "coderabbitai", "body": "x", "url": ""}
    assert state(threads=[thread]) == "THREADS"


def test_conflict_and_blocked():
    assert state(mergeable="CONFLICTING") == "CONFLICT"
    assert state(merge_state="BLOCKED") == "BLOCKED"


def test_review_grace_only_while_no_reviewer_and_fresh_push():
    fresh = NOW - timedelta(minutes=6)
    assert state(reviewed_head=False, head_committed=fresh) == "WAITING"
    assert state(reviewed_head=False) == "READY"          # grace expired
    assert state(reviewed_head=False, head_committed=fresh,
                 author="dependabot", author_is_bot=True) == "READY"


# ---- the verdict is about the current head --------------------------------
# Regression: seconds after a push to lelandg/.claude_code#13 (2026-11-11) the
# head's rollup held one check and the only reviewer activity was on the
# previous head, and `land` called it READY.

def test_just_pushed_head_is_never_ready_even_with_green_checks():
    just = NOW - timedelta(seconds=40)
    v = pt.classify(make(head_committed=just), NOW, ME)
    assert v.state == "WAITING" and "40s ago" in v.reasons[0]
    assert state(head_committed=just, author="dependabot",
                 author_is_bot=True) == "WAITING"        # bots too
    assert state(head_committed=just, checks=[]) == "WAITING"   # empty != green
    assert state(head_committed=just, checks=[("ci", "fail")]) == "FAILING"


def test_check_seen_on_an_earlier_commit_must_report_on_the_head():
    ran_before = ["gitleaks", "osv-scanner", "CodeRabbit", "GitGuardian"]
    partial = [("GitGuardian", "pass")]
    ten = NOW - timedelta(minutes=10)
    v = pt.classify(make(head_committed=ten, checks=partial,
                         expected_checks=ran_before), NOW, ME)
    assert v.state == "WAITING"
    assert v.reasons == ["gitleaks has not started on this head",
                         "osv-scanner has not started on this head",
                         "CodeRabbit has not started on this head"]
    # Long after the push it is a failure to act on, never READY.
    old = pt.classify(make(checks=partial, expected_checks=ran_before), NOW, ME)
    assert old.state == "FAILING" and "never started" in old.reasons[0]
    # Every expected check present: ready again.
    full = [(n, "pass") for n in ran_before]
    assert state(checks=full, expected_checks=ran_before) == "READY"
    # The explicit override is per call, for a reviewer that will not return.
    assert pt.classify(make(checks=partial, expected_checks=ran_before),
                       NOW, ME, accept_missing=True).state == "READY"
    # It never skips a workflow run that exists and has not finished.
    for age in (timedelta(minutes=10), timedelta(hours=2)):
        v = pt.classify(make(head_committed=NOW - age,
                             running_workflows=["security"]),
                        NOW, ME, accept_missing=True)
        assert v.state in ("WAITING", "FAILING") and "security" in v.reasons[0]


def test_a_pr_based_on_another_prs_branch_is_never_landed_by_itself():
    # plugins#10, 2026-11-11: green, reviewed, and based on #9's branch.
    # Merging it would fold it into #9 behind that PR's back.
    stacked = make(base="fix/version-manager-sync", default_branch="main")
    v = pt.classify(stacked, NOW, ME)
    assert v.state == "STACKED"
    assert v.reasons == ["based on fix/version-manager-sync, not main"]
    assert pt.classify(make(base="main", default_branch="main"), NOW, ME).state == "READY"
    assert pt.classify(make(base="master", default_branch="master"), NOW, ME).state == "READY"
    # The default branch is read from the repository node.
    t0 = NOW - timedelta(hours=3)
    node = _node([("a1", "fix: thing", t0)], rollup=["ci", "CodeRabbit"],
                 tail=[("a1", t0, ["ci", "CodeRabbit"])])
    node["pullRequest"]["baseRefName"] = "feat/parent"
    pr = pt.pr_from_node("octo-user/r", {"pullRequest": node["pullRequest"],
                                       "defaultBranchRef": {"name": "main"}})
    assert pr.default_branch == "main" and pt.classify(pr, NOW, ME).state == "STACKED"


def test_land_refuses_a_stacked_pr(monkeypatch, capsys):
    calls = _land_env(monkeypatch, [make(base="feat/parent", default_branch="main",
                                         files=CI_ONLY)])
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 1
    assert calls == [] and "STACKED" in capsys.readouterr().out


def test_a_newer_run_of_the_same_workflow_replaces_a_dead_one():
    # plugins#9, 2026-11-11: runs created during an Actions outage stayed
    # queued for good and could not be cancelled; re-firing the event gave
    # the same commit a second, successful run of each workflow.
    t0 = NOW - timedelta(hours=2)

    def suite(minutes_ago, workflow, status, conclusion=None, event="pull_request"):
        return {"createdAt": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
                "status": status, "conclusion": conclusion,
                "workflowRun": {"event": event, "workflow": {"name": workflow}}}

    def running(*suites):
        node = _node([("a1", "fix: thing", t0)], rollup=["ci", "CodeRabbit"],
                     tail=[("a1", t0, ["ci", "CodeRabbit"])])
        node["pullRequest"]["tail"]["nodes"][-1]["commit"]["checkSuites"] = {
            "nodes": list(suites)}
        return _pr(node).running_workflows

    dead = [suite(60, "security", "QUEUED"), suite(60, "validate", "QUEUED")]
    assert running(*dead) == ["security", "validate"]
    rerun = [suite(20, "security", "COMPLETED", "SUCCESS"),
             suite(20, "validate", "COMPLETED", "SUCCESS")]
    assert running(*dead, *rerun) == []
    assert running(*rerun, *dead) == []                  # order does not matter
    # Only the workflow that was re-run is cleared.
    assert running(*dead, rerun[0]) == ["validate"]
    # The newest run being the unfinished one still blocks: that is a re-run
    # in progress, not a ghost.
    assert running(suite(60, "security", "COMPLETED", "SUCCESS"),
                   suite(5, "security", "IN_PROGRESS")) == ["security"]
    # A run for a different event does not vouch for this one.
    assert running(suite(60, "security", "QUEUED", event="pull_request"),
                   suite(20, "security", "COMPLETED", "SUCCESS", event="push")) \
        == ["security"]
    # Same instant: the unfinished one is believed.
    assert running(suite(20, "security", "COMPLETED", "SUCCESS"),
                   suite(20, "security", "QUEUED")) == ["security"]


def _node(commits, *, reviews=(), comments=(), rollup=(), tail=None):
    """A minimal GraphQL pullRequest node; commits are (oid, subject, when)."""
    def run(name, conclusion="SUCCESS"):
        return {"__typename": "CheckRun", "name": name, "status": "COMPLETED",
                "conclusion": conclusion}
    cs = [{"commit": {"oid": o, "messageHeadline": s,
                      "committedDate": w.isoformat()}} for o, s, w in commits]
    def suites(pushed, queued):
        if not pushed:
            return []
        at = pushed.isoformat()
        # An app that never reports leaves a suite queued forever; a workflow
        # run is a suite too, and is queued before any of its jobs exist.
        return ([{"createdAt": at, "status": "QUEUED", "conclusion": None,
                  "workflowRun": None}]
                + [{"createdAt": at, "status": "QUEUED", "conclusion": None,
                    "workflowRun": {"workflow": {"name": w}}} for w in queued])

    tl = [{"commit": {"oid": t[0],
                      "checkSuites": {"nodes": suites(t[1], t[3] if len(t) > 3 else ())},
                      "statusCheckRollup": {"contexts": {"nodes":
                                                         [run(n) for n in t[2]]}}}}
          for t in (tail or [])]
    return {"repository": None, "pullRequest": {
        "number": 7, "title": "fix: thing", "state": "OPEN",
        "author": {"login": "octo-user", "__typename": "User"},
        "headRefName": "fix/thing", "headRefOid": commits[-1][0],
        "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
        "updatedAt": NOW.isoformat(), "createdAt": NOW.isoformat(),
        "commits": {"nodes": cs}, "tail": {"nodes": tl},
        "statusCheckRollup": {"contexts": {"nodes": [run(n) for n in rollup]}},
        "reviews": {"nodes": [{"author": {"login": a}, "commit": {"oid": o}}
                              for a, o in reviews]},
        "comments": {"nodes": [{"author": {"login": a},
                                "createdAt": w.isoformat()}
                               for a, w in comments]},
    }}


def _pr(node, mechanical=None) -> pt.PR:
    return pt.pr_from_node("octo-user/r", {"pullRequest": node["pullRequest"],
                                         "squashMergeAllowed": True}, mechanical)


def test_review_of_an_earlier_head_does_not_cover_the_new_one():
    t0, t1 = NOW - timedelta(minutes=30), NOW - timedelta(minutes=5)
    pr = _pr(_node(
        [("a1", "fix: thing", t0), ("b2", "fix: address review", t1)],
        reviews=[("coderabbitai", "a1")],
        comments=[("coderabbitai", t0 + timedelta(minutes=3))],
        rollup=["GitGuardian"],
        tail=[("a1", t0, ["gitleaks", "CodeRabbit", "GitGuardian",
                          ".github/dependabot.yml"]),
              ("b2", t1, ["GitGuardian"], ["security"])]))
    assert pr.reviewed_head is False
    # Only the reviewer check is expected by name: Dependabot's config check
    # ran earlier because that commit touched its file, not because it must.
    assert pr.expected_checks == ["CodeRabbit"]
    # The workflow run exists on the head but none of its jobs do yet.
    assert pr.running_workflows == ["security"]
    v = pt.classify(pr, NOW, ME)
    assert v.state == "WAITING"
    assert v.reasons == ["workflow security has not finished on this head"]
    # Once the workflow is done, the missing reviewer check is what holds it.
    pr.running_workflows = []
    assert pt.classify(pr, NOW, ME).reasons == [
        "CodeRabbit has not started on this head"]


def test_queued_suite_of_an_app_that_never_reports_does_not_block():
    t0 = NOW - timedelta(hours=3)
    pr = _pr(_node([("a1", "fix: thing", t0)], rollup=["ci", "CodeRabbit"],
                   tail=[("a1", t0, ["ci", "CodeRabbit"])]))
    assert pr.running_workflows == [] and pr.expected_checks == []
    assert pt.classify(pr, NOW, ME).state == "READY"
    # A workflow run still unfinished long after the push is a failure to act on.
    stuck = _pr(_node([("a1", "fix: thing", t0)], rollup=["CodeRabbit"],
                      tail=[("a1", t0, ["CodeRabbit"], ["security"])]))
    v = pt.classify(stuck, NOW, ME)
    assert v.state == "FAILING"
    assert v.reasons == ["workflow security never finished on this head"]


def test_push_time_comes_from_the_heads_first_check_suite():
    # Committed an hour ago, pushed 30 seconds ago: the push is what counts.
    committed, pushed = NOW - timedelta(hours=1), NOW - timedelta(seconds=30)
    pr = _pr(_node([("a1", "fix: thing", committed)], rollup=["ci"],
                   tail=[("a1", pushed, ["ci"])]))
    assert pr.head_pushed == pushed
    assert pt.classify(pr, NOW, ME).state == "WAITING"


def test_review_evidence_must_name_the_head_commit():
    t0, t1 = NOW - timedelta(minutes=40), NOW - timedelta(minutes=20)
    commits = [("a1", "fix: thing", t0), ("b2", "fix: more", t1)]
    tail = [("a1", t0, ["ci"]), ("b2", t1, ["ci"])]
    by_review = _pr(_node(commits, reviews=[("greptile-apps", "b2")],
                          rollup=["ci"], tail=tail))
    by_check = _pr(_node(commits, rollup=["ci", "CodeRabbit"], tail=tail))
    # A bot comment has no commit. One posted after the push may be the bot
    # finishing its review of the commit BEFORE: it is not evidence.
    by_comment = _pr(_node(commits, comments=[("claude", t1 + timedelta(minutes=4))],
                           rollup=["ci"], tail=tail))
    earlier = _pr(_node(commits, reviews=[("greptile-apps", "a1")],
                        rollup=["ci"], tail=tail))
    assert [p.reviewed_head for p in (by_review, by_check, by_comment, earlier)] \
        == [True, True, False, False]
    assert [p.reviewer_active for p in (by_review, by_check, by_comment, earlier)] \
        == [True, True, False, True]


def test_an_active_reviewer_silent_on_the_head_never_times_out_to_ready():
    def verdict(minutes, **kw):
        t = NOW - timedelta(minutes=minutes)
        return pt.classify(make(head_committed=t, reviewed_head=False, **kw),
                           NOW, ME)
    # No reviewer has ever acted here: the grace runs out and it is ready.
    assert verdict(10).state == "WAITING" and verdict(20).state == "READY"
    # One has: 20 minutes is still waiting, two hours is a failure to act on.
    assert verdict(20, reviewer_active=True).state == "WAITING"
    late = verdict(120, reviewer_active=True)
    assert late.state == "FAILING" and "re-trigger" in late.reasons[0]
    # Only the explicit, per-PR override gets past it.
    t = NOW - timedelta(hours=2)
    assert pt.classify(make(head_committed=t, reviewed_head=False,
                            reviewer_active=True), NOW, ME,
                       accept_missing=True).state == "READY"
    # Reviews past the page that was read: assume a reviewer is among them.
    node = _node([("a1", "fix: thing", t)], rollup=["ci"], tail=[("a1", t, ["ci"])])
    node["pullRequest"]["reviews"]["totalCount"] = 80
    assert _pr(node).reviewer_active is True


LANDER = [("m2", "Merge remote-tracking branch 'origin/main' into HEAD"),
          ("r3", "chore(release): v1.4.2")]


def test_landers_own_commits_keep_the_review_only_when_proven():
    t0, t1, t2 = (NOW - timedelta(minutes=m) for m in (60, 10, 9))
    commits = [("a1", "fix: thing", t0), (*LANDER[0], t1), (*LANDER[1], t2)]
    node = _node(commits, reviews=[("greptile-apps", "a1")], rollup=["ci"],
                 tail=[("a1", t0, ["ci", "Greptile Review"]),
                       ("m2", t1, []), ("r3", t2, ["ci"])])
    proven = _pr(node, mechanical={"m2", "r3"})
    assert proven.reviewed_head is True
    # The code was reviewed and the bump adds none: GrepTile, which never
    # re-reviews a push, is not expected again on it.
    assert proven.expected_checks == []
    assert pt.classify(proven, NOW, ME).state == "READY"
    # The same titles with no proof of what the commits contain: a title is
    # only a claim, so the head counts as unreviewed code.
    claimed = _pr(node)
    assert claimed.reviewed_head is False
    assert claimed.expected_checks == ["Greptile Review"]
    assert pt.classify(claimed, NOW, ME).state == "WAITING"
    # Proof stops at the first commit that fails it: r3 alone is not enough
    # to reach back past an unproven merge.
    assert _pr(node, mechanical={"r3"}).reviewed_head is False


def test_a_release_commit_is_mechanical_only_if_its_diff_is():
    def f(name, patch, status="modified"):
        return {"filename": name, "status": status, "patch": patch}
    bump = [f("package.json", '@@ -1,3 +1,3 @@\n {\n-  "version": "1.4.1",\n'
                              '+  "version": "1.4.2",\n   "private": true'),
            f("VERSION", "@@ -1 +1 @@\n-1.4.1\n+1.4.2"),
            f("src/App.csproj", "@@ -3 +3 @@\n-    <Version>1.4.1</Version>\n"
                                "+    <Version>1.4.2</Version>"),
            f("CHANGELOG.md", "@@ -1,2 +1,6 @@\n # Changelog\n+\n+## [1.4.2]\n"
                              "+- anything at all goes in a changelog")]
    assert pt.release_diff_is_mechanical(bump)
    code = f("src/app.py", "@@ -1 +1,2 @@\n x = 1\n+y = something_new()")
    assert not pt.release_diff_is_mechanical(bump + [code])
    # A dependency pin changes a version number too, but not a version line.
    dep = f("package.json", '@@ -9 +9 @@\n-    "left-pad": "1.3.0"\n'
                            '+    "left-pad": "1.3.1"')
    assert not pt.release_diff_is_mechanical([dep])
    # Same line count, different content beside the number.
    swapped = f("package.json", '@@ -2 +2 @@\n-  "version": "1.4.1",\n'
                                '+  "version": "1.4.2", "scripts": {"x": "y"},')
    assert not pt.release_diff_is_mechanical([swapped])
    # A dependency whose NAME contains "version" is still a dependency.
    named = f("package.json", '@@ -9 +9 @@\n-    "compare-versions": "6.1.0"\n'
                              '+    "compare-versions": "6.1.1"')
    assert not pt.release_diff_is_mechanical([named])
    # A lockfile is nothing but "version" lines for other packages.
    lock = f("package-lock.json", '@@ -40 +40 @@\n-      "version": "1.3.0",\n'
                                  '+      "version": "1.3.1",')
    assert not pt.release_diff_is_mechanical([lock])
    # One JSON file, two "version" lines moved: a bump moves one.
    two = f("package.json", '@@ -2 +2 @@\n-  "version": "1.4.1",\n'
                            '+  "version": "1.4.2",\n@@ -30 +30 @@\n'
                            '-      "version": "2.0.0"\n+      "version": "2.0.1"')
    assert not pt.release_diff_is_mechanical([two])
    # A product file renamed to CHANGELOG.md is not a changelog edit.
    renamed = {"filename": "CHANGELOG.md", "status": "renamed",
               "previous_filename": "src/app.py", "patch": ""}
    assert not pt.release_diff_is_mechanical(bump[:1] + [renamed])
    assert pt.release_diff_is_mechanical(
        bump[:1] + [f("CHANGELOG.md", "@@ -0,0 +1 @@\n+# Changelog", "added")])
    # What the patch does not show cannot be vouched for.
    assert not pt.release_diff_is_mechanical([f("logo.png", None)])
    assert not pt.release_diff_is_mechanical([f("new.py", "@@ +1 @@\n+x", "added")])
    assert not pt.release_diff_is_mechanical([])


def test_verified_mechanical_walks_back_and_stops_at_the_first_failure(monkeypatch):
    def c(oid, title, parents):
        return {"oid": oid, "messageHeadline": title,
                "parents": {"nodes": [{"oid": p} for p in parents]}}
    commits = [c("a1", "fix: thing", ["z0"]),
               c("m2", LANDER[0][1], ["a1", "base9"]),
               c("r3", LANDER[1][1], ["m2"])]
    good_bump = json.dumps([{"filename": "VERSION", "status": "modified",
                             "patch": "@@ -1 +1 @@\n-1.4.1\n+1.4.2"}])
    monkeypatch.setattr(pt, "gh", lambda *a, **k: good_bump)
    monkeypatch.setattr(pt, "merge_is_clean", lambda *a: True)
    assert pt.verified_mechanical("o/r", "main", commits) == {"m2", "r3"}
    monkeypatch.setattr(pt, "merge_is_clean", lambda *a: False)
    assert pt.verified_mechanical("o/r", "main", commits) == {"r3"}
    # A "release" commit that also changes code proves nothing, and nothing
    # behind it is reached.
    with_code = json.dumps([{"filename": "src/app.py", "status": "modified",
                             "patch": "@@ -1 +1 @@\n-x = 1\n+x = 2"}])
    monkeypatch.setattr(pt, "gh", lambda *a, **k: with_code)
    monkeypatch.setattr(pt, "merge_is_clean", lambda *a: True)
    assert pt.verified_mechanical("o/r", "main", commits) == set()
    # The PR's first commit is never mechanical, whatever it is called.
    only = [c("r1", "chore(release): v1.0.0", ["z0"])]
    monkeypatch.setattr(pt, "gh", lambda *a, **k: good_bump)
    assert pt.verified_mechanical("o/r", "main", only) == set()
    # Commits this run made and pushed itself need no proof, even with no
    # clone anywhere to check them in (a temporary clone, or --clone).
    monkeypatch.setattr(pt, "gh", lambda *a, **k: "")
    monkeypatch.setattr(pt, "merge_is_clean", lambda *a: False)
    assert pt.verified_mechanical("o/r", "main", commits) == set()
    monkeypatch.setitem(pt._CACHE, "own_commits", {"m2", "r3"})
    assert pt.verified_mechanical("o/r", "main", commits) == {"m2", "r3"}


def test_gates_added_by_the_third_review_round():
    # Unknown push time (no check suite on the head yet) means "just
    # pushed", never "as old as the commit": a 2-hour-old local commit that
    # has only now been pushed must wait.
    old = NOW - timedelta(hours=2)
    node = _node([("a1", "fix: thing", old)], rollup=[], tail=[("a1", None, [])])
    pr = _pr(node)
    assert pr.head_pushed == NOW                 # the PR's updatedAt
    assert pt.classify(pr, NOW, ME).state == "WAITING"

    # A reviewer that has acted on a bot's PR is owed for the bot too; only
    # the wait for a reviewer that never showed up is skipped for bots.
    bot = dict(author="dependabot", author_is_bot=True, reviewed_head=False,
               head_committed=NOW - timedelta(minutes=20))
    assert pt.classify(make(**bot), NOW, ME).state == "READY"
    assert pt.classify(make(**bot, reviewer_active=True), NOW, ME).state == "WAITING"

    # A check pending beyond any real job's lifetime is stuck, not slow.
    running = [("ci", "pending")]
    assert state(checks=running, head_committed=NOW - timedelta(hours=2)) == "WAITING"
    v = pt.classify(make(checks=running, head_committed=NOW - timedelta(hours=7)),
                    NOW, ME)
    assert v.state == "FAILING" and "still running 7 h" in v.reasons[0]

    # Punctuated and qualified negatives are still negatives.
    sensitive = ["lib/auth/session.ts"]
    for body in ("Adversarial review: No.", "Adversarial review: no!",
                 "Adversarial review: no, not run", "Adversarial review: NO"):
        assert state(files=sensitive, body=body) == "REVIEW", body
    for body in ("Adversarial review: no findings (codex)",
                 "Adversarial review: No issues."):
        assert state(files=sensitive, body=body) == "READY", body


def test_outside_contributor_is_never_ready():
    assert state(author="Mr-Neutr0n") == "EXTERNAL"


def test_autofix_follows_its_source():
    assert state(head="autofix/pr-3", draft=True,
                 autofix_source_state="MERGED") == "SUPERSEDED"
    assert state(head="autofix/pr-3", draft=True,
                 autofix_source_state="OPEN") == "AUTOFIX"


def test_stale_marks_only_stuck_states():
    old = NOW - timedelta(days=40)
    assert state(draft=True, updated=old) == "STALE(DRAFT)"
    assert state(mergeable="CONFLICTING", updated=old) == "STALE(CONFLICT)"
    assert state(updated=old) == "STALE(READY)"   # parked: sweep leaves it


def test_my_pr_in_someone_elses_repo_is_theirs_to_merge():
    assert state(repo="someone-else/their-repo") == "ELSEWHERE"
    assert state(repo="octo-org/x") == "READY"   # owner match ignores case


def test_owner_override_reaches_classification(monkeypatch):
    # PR_TOOL_OWNERS must change what counts as "home", not only which PRs
    # the survey query returns: otherwise every row comes back ELSEWHERE.
    theirs = make(repo="acme/widgets", author="pat")
    assert pt.classify(theirs, NOW, {"pat"}).label == "ELSEWHERE"
    monkeypatch.setenv("PR_TOOL_OWNERS", "acme")
    assert pt.classify(theirs, NOW, {"pat"}).label == "READY"
    assert pt.classify(make(), NOW, ME).label == "ELSEWHERE"   # octo-user is not home now


def test_survey_classifies_with_the_owners_it_was_given(monkeypatch):
    theirs = make(repo="acme/widgets", author="pat")
    monkeypatch.setattr(pt, "collect", lambda owners, repo: [("acme/widgets", 7)])
    monkeypatch.setattr(pt, "fetch_pr", lambda repo, number: theirs)
    assert [v.label for _, v in pt.survey(["acme"], None, {"pat"})] == ["READY"]
    assert [v.label for _, v in pt.survey(["octo-user"], None, {"pat"})] == ["ELSEWHERE"]


def test_sensitive_paths_need_recorded_adversarial_review():
    files = ["lib/auth/session.ts"]
    assert state(files=files) == "REVIEW"
    assert state(files=files, body="Adversarial Codex review: clean") == "READY"
    ok = ["Adversarial review: clean (codex, gpt-6-astra high)",
          "- **Adversarial review:** 2 findings, both fixed in abc1234",
          "## Checks\n\n> Adversarial Codex review: no findings\n\nmore text"]
    for body in ok:
        assert state(files=files, body=body) == "READY", body
    # The word is not the record. Neither is the line without a result.
    not_ok = ["No adversarial review was run for this change.",
              "We should do an adversarial review later",
              "Adversarial review: none",
              "Adversarial review: not run",
              "Adversarial review: N/A",
              "Adversarial review: pending",
              "Adversarial review:",
              "**Adversarial review:** TODO"]
    for body in not_ok:
        v = pt.classify(make(files=files, body=body), NOW, ME)
        assert v.state == "REVIEW", body
    assert "Adversarial review: <result" in v.reasons[0]
    # a test file with 'auth' in its name ships nothing and is not sensitive
    assert state(files=["tests/test_auth.py"]) == "READY"


# ---- findings from the Codex review, 2026-11-11 ---------------------------

def test_a_pr_too_big_to_read_in_one_page_is_refused_not_passed():
    t0 = NOW - timedelta(hours=3)
    node = _node([("a1", "fix: thing", t0)], rollup=["ci", "CodeRabbit"],
                 tail=[("a1", t0, ["ci", "CodeRabbit"])])
    assert pt.classify(_pr(node), NOW, ME).state == "READY"
    node["pullRequest"]["reviewThreads"] = {"totalCount": 140, "nodes": []}
    v = pt.classify(_pr(node), NOW, ME)
    assert v.state == "BLOCKED" and "140 review threads" in v.reasons[0]
    node["pullRequest"]["reviewThreads"] = {"totalCount": 0, "nodes": []}
    node["pullRequest"]["statusCheckRollup"]["contexts"]["totalCount"] = 250
    assert pt.classify(_pr(node), NOW, ME).state == "BLOCKED"


def test_unseen_files_count_as_sensitive():
    # 100 harmless paths read out of 180: the other 80 are unknown.
    partial = make(files=[f"src/f{i}.py" for i in range(100)], files_total=180)
    assert pt.classify(partial, NOW, ME).state == "REVIEW"
    whole = make(files=[f"src/f{i}.py" for i in range(180)], files_total=180)
    assert pt.classify(whole, NOW, ME).state == "READY"


def test_landed_version_reads_the_last_release_commit():
    lv = lambda *s: pt.landed_version(make(subjects=list(s)))  # noqa: E731
    assert lv("fix: a", "chore(release): v1.2.3") == "1.2.3"
    assert lv("chore(release): v1.2.3", "fix: review") == "1.2.3"
    assert lv("chore(release): v1.2.3",
              "chore(release): drop pre-landing bump (re-cut at landing)") is None
    assert lv("fix: a") is None


class _Calls(list):
    def __call__(self, *args, **kw):
        self.append(args)
        return ""


def _land_env(monkeypatch, prs):
    """Stub the network. fetch_pr hands out `prs` in turn; the last repeats."""
    seq = list(prs)
    monkeypatch.setattr(pt, "fetch_pr",
                        lambda repo, n: seq.pop(0) if len(seq) > 1 else seq[0])
    calls = _Calls()
    monkeypatch.setattr(pt, "gh", calls)
    monkeypatch.setattr(pt, "detect_method", lambda pr: "squash")
    monkeypatch.setattr(pt, "MERGE_POLL_SECONDS", 0)
    monkeypatch.setattr(pt.Lock, "__init__", lambda self, repo: None)
    monkeypatch.setattr(pt.Lock, "__enter__", lambda self: self)
    monkeypatch.setattr(pt.Lock, "__exit__", lambda self, *a: None)
    return calls


CI_ONLY = [".github/workflows/x.yml"]      # Release: none, so no worktree


def test_land_does_not_tag_or_clean_up_until_github_says_merged(monkeypatch, capsys):
    # A merge queue: `gh pr merge` succeeds and the PR stays open.
    calls = _land_env(monkeypatch, [make(files=CI_ONLY)])
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 3
    assert [c[:2] for c in calls] == [("pr", "merge")]
    assert "NOT MERGED YET" in capsys.readouterr().out
    # Merged for real: cleanup runs and it reports LANDED.
    merged = make(files=CI_ONLY, state="MERGED", merge_commit="c" * 40)
    calls = _land_env(monkeypatch, [make(files=CI_ONLY), merged])
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 0
    assert ("pr", "list") in [c[:2] for c in calls]
    assert "LANDED octo-user/r#7" in capsys.readouterr().out


VERSION_BUMP = json.dumps([{"filename": "VERSION", "status": "modified",
                            "patch": "@@ -1 +1 @@\n-1.4.1\n+1.4.2"}])
TAGS = ("api", "repos/octo-user/r/git/tags")


def _merged_env(monkeypatch, merged, *, release_commit=VERSION_BUMP,
                version_file="1.4.2\n", tag_refused=False):
    """A merged PR whose release commit is r3; gh answers by endpoint."""
    _land_env(monkeypatch, [merged])
    calls = []

    def gh(*args, **kw):
        calls.append(args)
        if args[:2] == ("api", "repos/octo-user/r/commits/r3"):
            return release_commit
        if len(args) > 1 and args[1].startswith("repos/octo-user/r/contents/VERSION"):
            return version_file
        if args[:2] == TAGS and tag_refused:
            raise pt.ToolError("protected tag")
        return ""
    monkeypatch.setattr(pt, "gh", gh)
    monkeypatch.setattr(pt, "remote_tag_exists", lambda repo, tag: False)
    return calls


def test_land_on_a_merged_pr_finishes_the_tag_it_missed(monkeypatch, capsys):
    merged = make(state="MERGED", merge_commit="c" * 40,
                  subjects=["fix: thing", "chore(release): v1.4.2"],
                  commit_oids=["a1", "r3"])
    calls = _merged_env(monkeypatch, merged)
    assert pt.cmd_land("octo-user/r#7", trusted=ME) == 10       # dry run: work pending
    assert TAGS not in [c[:2] for c in calls]
    assert "v1.4.2 is not tagged" in capsys.readouterr().out
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 0
    assert TAGS in [c[:2] for c in calls]

    # The tag is refused again: say so and exit non-zero, never "LANDED".
    _merged_env(monkeypatch, merged, tag_refused=True)
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 1
    out = capsys.readouterr().out
    assert "TAG FAILED" in out and "LANDED" not in out.split("TAG FAILED")[1]

    # Already tagged: nothing to do.
    calls = _merged_env(monkeypatch, merged)
    monkeypatch.setattr(pt, "remote_tag_exists", lambda repo, tag: True)
    assert pt.cmd_land("octo-user/r#7", trusted=ME) == 0
    assert calls == []


def test_a_merged_pr_is_tagged_only_when_the_version_is_confirmed(monkeypatch, capsys):
    merged = make(state="MERGED", merge_commit="c" * 40,
                  subjects=["fix: thing", "chore(release): v1.4.2"],
                  commit_oids=["a1", "r3"])
    # The subject says 1.4.2 but the merge commit's VERSION file says 1.4.1.
    calls = _merged_env(monkeypatch, merged, version_file="1.4.1\n")
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 1
    assert TAGS not in [c[:2] for c in calls]
    assert "no version file declares 1.4.2" in capsys.readouterr().out
    # A "release" commit that also changed code is not a release commit.
    code = json.dumps([{"filename": "src/app.py", "status": "modified",
                        "patch": "@@ -1 +1 @@\n-x = 1\n+x = 2"}])
    calls = _merged_env(monkeypatch, merged, release_commit=code)
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 1
    assert TAGS not in [c[:2] for c in calls]
    # Someone else's PR, or someone else's repository: nothing at all.
    for other in (make(state="MERGED", merge_commit="c" * 40, author="Mr-Neutr0n",
                       subjects=["chore(release): v1.4.2"], commit_oids=["r3"]),
                  make(state="MERGED", merge_commit="c" * 40, repo="acme/widgets",
                       subjects=["chore(release): v1.4.2"], commit_oids=["r3"])):
        calls = _merged_env(monkeypatch, other)
        assert pt.cmd_land(other.ref, apply=True, trusted=ME) == 0
        assert calls == []


def test_an_existing_tag_must_point_at_the_merge_commit(monkeypatch):
    merge, other = "c" * 40, "d" * 40
    monkeypatch.setattr(pt, "remote_tag_exists", lambda repo, tag: True)
    monkeypatch.setattr(pt, "tag_commit", lambda repo, tag: merge)
    assert "already on the merge commit" in pt.create_tag("o/r", "1.4.2", merge)
    monkeypatch.setattr(pt, "tag_commit", lambda repo, tag: other)
    with pytest.raises(pt.ToolError, match="not at the merge commit"):
        pt.create_tag("o/r", "1.4.2", merge)
    # tag_commit peels an annotated tag to its commit.
    answers = {"repos/o/r/git/ref/tags/v1.4.2": f"tag {'e' * 40}\n",
               f"repos/o/r/git/tags/{'e' * 40}": merge + "\n"}
    monkeypatch.undo()
    monkeypatch.setattr(pt, "gh", lambda *a, **k: answers.get(a[1], ""))
    assert pt.tag_commit("o/r", "v1.4.2") == merge
    assert pt.tag_commit("o/r", "v9.9.9") is None


def test_conflict_is_refused_unless_a_stale_bump_explains_it(monkeypatch, capsys):
    # Release: none means no bump on the branch to blame.
    calls = _land_env(monkeypatch, [make(mergeable="CONFLICTING", files=CI_ONLY)])
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 1
    assert calls == []
    # A PR that ships something might carry one; a dry run promises nothing.
    shipping = make(mergeable="CONFLICTING")
    _land_env(monkeypatch, [shipping])
    assert pt.cmd_land("octo-user/r#7", trusted=ME) == 1
    assert "version bump already on the branch" in capsys.readouterr().out
    # Every other gate is checked BEFORE any repair: a conflicted PR with an
    # open thread is refused without a worktree, a push or a merge.
    thread = {"id": "T1", "path": "a.py", "line": 3, "outdated": False,
              "author": "coderabbitai", "body": "x", "url": ""}
    calls = _land_env(monkeypatch, [make(mergeable="CONFLICTING", threads=[thread])])
    opened = []
    monkeypatch.setattr(pt, "Workspace", lambda *a: opened.append(a))
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 1
    assert calls == [] and opened == []
    out = capsys.readouterr().out
    assert "apart from the conflict" in out and "THREADS" in out

    # --apply looks, finds no stale bump, and refuses without pushing or merging.
    class NoWorktree:
        def __init__(self, pr, clone):
            self.wt = self.tmp = Path(".")

        def close(self):
            pass
    calls = _land_env(monkeypatch, [shipping])
    monkeypatch.setattr(pt, "Workspace", NoWorktree)
    monkeypatch.setattr(pt, "load_version_tool", lambda: (None, None))
    monkeypatch.setattr(pt, "bump_state", lambda *a: ("absent", None))
    pushed = []
    monkeypatch.setattr(pt, "git", lambda *a, **k: pushed.append(a) or "")
    assert pt.cmd_land("octo-user/r#7", apply=True, trusted=ME) == 1
    assert calls == [] and pushed == []
    assert "CONFLICT: conflicts with main" in capsys.readouterr().out

    # A bump whose NUMBER is still right can conflict all the same (branch
    # 1.0.0 -> 1.1.0, base moved to 1.0.1): in a repair it is re-cut too,
    # not kept as "current" and left stuck.
    for state in ("current", "stale"):
        recut = []
        monkeypatch.setattr(pt, "bump_state", lambda *a, s=state: (s, "1.1.0"))

        def prepare(*a, **k):
            recut.append(a)
            raise pt.ToolError("merging the base branch conflicts in: app.js")
        monkeypatch.setattr(pt, "prepare_branch", prepare)
        with pytest.raises(pt.ToolError, match="conflicts in: app.js"):
            pt.cmd_land("octo-user/r#7", apply=True, trusted=ME)
        assert len(recut) == 1 and calls == [] and pushed == []


def test_check_bucket_maps_rollup_nodes():
    run = lambda **k: pt.check_bucket({"__typename": "CheckRun", **k})[1]  # noqa: E731
    assert run(status="IN_PROGRESS", conclusion=None) == "pending"
    assert run(status="COMPLETED", conclusion="SUCCESS") == "pass"
    assert run(status="COMPLETED", conclusion="NEUTRAL") == "skip"
    assert run(status="COMPLETED", conclusion="TIMED_OUT") == "fail"
    # GitHub can report a stale status beside a real conclusion: the
    # conclusion wins, in both directions.
    assert run(status="IN_PROGRESS", conclusion="SUCCESS") == "pass"
    assert run(status="IN_PROGRESS", conclusion="FAILURE") == "fail"
    assert run(status="QUEUED", conclusion=None) == "pending"
    ctx = lambda s: pt.check_bucket({"__typename": "StatusContext",  # noqa: E731
                                     "context": "CodeRabbit", "state": s})[1]
    assert (ctx("SUCCESS"), ctx("PENDING"), ctx("ERROR")) == ("pass", "pending", "fail")


# ---- release plan ---------------------------------------------------------

BODY = """## What

Fixes the thing.

## Release notes

Release: minor

### Added
- A new thing users can see.

### Fixed
- The old thing.

## Verification

- tests pass

<!-- coderabbit summary -->
"""


def test_release_line_and_notes_come_from_the_body():
    plan = pt.release_plan(make(body=BODY))
    assert plan.level == "minor"
    assert plan.notes.startswith("### Added")
    assert "The old thing." in plan.notes
    assert "Verification" not in plan.notes and "Release:" not in plan.notes


def test_notes_stop_at_reviewer_markers():
    body = "## Release notes\n- one\n\n<!-- bot -->\n## Summary by CodeRabbit\n- x"
    assert pt.release_notes(body) == "- one"


def test_ci_only_pr_lands_without_a_bump():
    plan = pt.release_plan(make(files=[".github/workflows/security.yml"]))
    assert plan.level == "none"


def test_level_falls_back_to_commit_subjects():
    assert pt.release_plan(make()).level == "patch"
    assert pt.release_plan(make(subjects=["feat(x): y", "fix: z"])).level == "minor"
    assert pt.release_plan(make(subjects=["feat!: drop v1"])).level == "major"


def test_truncated_file_list_never_proves_ships_nothing():
    pr = make(files=[".github/a.yml"], files_total=250)
    assert pt.release_plan(pr).level == "patch"


def test_explicit_release_line_beats_the_path_heuristic():
    pr = make(files=[".github/a.yml"], body="Release: patch")
    assert pt.release_plan(pr).level == "patch"
    assert pt.release_plan(make(body="**Release:** none")).level == "none"


def test_bot_and_no_bump():
    assert pt.release_plan(make(author_is_bot=True)).level == "none"
    assert pt.release_plan(make(), no_bump=True).level == "none"


def test_squash_subject_replaces_a_stale_title_version():
    assert pt.squash_subject("fix(admin): lint (v0.22.5)", 449, "0.22.7") \
        == "fix(admin): lint (v0.22.7) (#449)"
    assert pt.squash_subject("ci: template", 3, None) == "ci: template (#3)"


def test_parse_ref():
    assert pt.parse_ref("octo-user/example#63") == ("octo-user/example", 63)
    assert pt.parse_ref("https://github.com/a/b.c/pull/9") == ("a/b.c", 9)
    with pytest.raises(pt.ToolError):
        pt.parse_ref("nope")


# ---- changelog surgery ----------------------------------------------------

def test_strip_sections_removes_only_unknown_versions():
    vt, _ = pt.load_version_tool()
    text = ("# Changelog\n\n## [1.1.0] - 2026-11-01\n\n- branch notes\n\n"
            "## [1.0.0] - 2026-10-01\n\n- old\n")
    out, removed = pt.strip_sections(text, {"1.0.0"}, vt.CHANGELOG_HEADING)
    assert "1.1.0" not in out and "## [1.0.0]" in out and "- old" in out
    assert removed == ["- branch notes"]


# ---- real git: the bump at landing ---------------------------------------

def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


CHANGELOG = "# Changelog\n\n## [1.0.0] - 2026-10-01\n\n- first\n"


@pytest.fixture
def repo(tmp_path: Path):
    """A clone on branch `feature` of an origin whose main is at 1.0.0."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)],
                   check=True, capture_output=True)
    nohooks = tmp_path / "nohooks"
    nohooks.mkdir()
    for key, value in (("user.name", "t"), ("user.email", "t@example.invalid"),
                       ("core.hooksPath", str(nohooks)),
                       ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        sh(work, "config", key, value)
    (work / "package.json").write_bytes(
        b'{\n  "name": "x",\n  "version": "1.0.0",\n  "private": true,\n'
        b'  "description": "fixture",\n  "scripts": {\n    "test": "true"\n  },\n'
        b'  "dependencies": {}\n}\n')
    (work / "CHANGELOG.md").write_bytes(CHANGELOG.encode())
    (work / "app.js").write_bytes(b"1\n")
    sh(work, "add", "-A")
    sh(work, "commit", "-m", "chore(release): v1.0.0")
    sh(work, "push", "origin", "HEAD:main")
    sh(work, "checkout", "-b", "feature")
    return work


def test_find_clone_uses_config_roots_and_the_current_directory(repo, monkeypatch, tmp_path):
    # `repo` is tmp_path/work with origin tmp_path/origin.git; give it a
    # GitHub-shaped origin URL so it reads as a clone of o/work.
    sh(repo, "remote", "set-url", "origin", "https://github.com/o/work.git")
    elsewhere = tmp_path / "far" / "away"      # not beside the clone
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)
    assert pt.find_clone("o/work") is None           # nothing points at it
    cfg = tmp_path / "land-pr.json"
    cfg.write_text(json.dumps({"code_roots": [str(tmp_path)]}), encoding="utf-8")
    monkeypatch.setenv("PR_TOOL_CONFIG", str(cfg))
    monkeypatch.setattr(pt, "_CACHE", {"me": "octo-user"})
    assert pt.find_clone("o/work") == tmp_path / "work"
    # With no config: found from inside the clone, and from beside it.
    monkeypatch.setenv("PR_TOOL_CONFIG", str(tmp_path / "absent.json"))
    monkeypatch.chdir(repo)
    assert pt.find_clone("o/work").resolve() == repo.resolve()
    monkeypatch.chdir(tmp_path)
    assert pt.find_clone("o/work").resolve() == repo.resolve()
    # A clone of something else in the same place is never used.
    assert pt.find_clone("o/other") is None


def test_merge_is_clean_only_for_an_untouched_merge_of_the_base(repo, monkeypatch):
    commit(repo, "feat.js", "feature\n", "feat: a")
    sh(repo, "checkout", "-q", "--detach", "origin/main")
    commit(repo, "other.js", "other\n", "fix: something else lands on main")
    sh(repo, "push", "-q", "origin", "HEAD:main")
    sh(repo, "checkout", "-q", "feature")
    sh(repo, "fetch", "-q", "origin")
    sh(repo, "merge", "-q", "--no-edit", "origin/main")
    merge = sh(repo, "rev-parse", "HEAD")
    parents = [sh(repo, "rev-parse", "HEAD^1"), sh(repo, "rev-parse", "HEAD^2")]
    monkeypatch.setattr(pt, "find_clone", lambda r, hint=None: repo)
    monkeypatch.setattr(pt, "gh", lambda *a, **k: "behind\n")
    assert pt.merge_is_clean("o/r", "main", merge, parents) is True
    # The merged-in side is not on the base branch: it could carry anything.
    monkeypatch.setattr(pt, "gh", lambda *a, **k: "diverged\n")
    assert pt.merge_is_clean("o/r", "main", merge, parents) is False
    # Same two parents, but an edit was slipped into the merge commit.
    monkeypatch.setattr(pt, "gh", lambda *a, **k: "behind\n")
    (repo / "feat.js").write_bytes(b"feature\nplus something nobody reviewed\n")
    sh(repo, "commit", "-q", "-a", "--amend", "--no-edit")
    evil = sh(repo, "rev-parse", "HEAD")
    assert [sh(repo, "rev-parse", "HEAD^1"), sh(repo, "rev-parse", "HEAD^2")] == parents
    assert pt.merge_is_clean("o/r", "main", evil, parents) is False
    # No local clone to check against: the answer is no.
    monkeypatch.setattr(pt, "find_clone", lambda r, hint=None: None)
    assert pt.merge_is_clean("o/r", "main", merge, parents) is False


def commit(work: Path, name: str, data: str, msg: str) -> None:
    (work / name).write_bytes(data.encode())
    sh(work, "add", "-A")
    sh(work, "commit", "-m", msg)


def advance_main(work: Path, version: str) -> None:
    """Simulate another PR landing on origin/main with its own bump."""
    sh(work, "checkout", "-q", "--detach", "origin/main")
    pkg = (work / "package.json").read_bytes().decode()
    old = pkg.split('"version": "')[1].split('"')[0]
    (work / "package.json").write_bytes(pkg.replace(old, version).encode())
    log = (work / "CHANGELOG.md").read_bytes().decode()
    (work / "CHANGELOG.md").write_bytes(log.replace(
        "## [", f"## [{version}] - 2026-11-10\n\n- other PR\n\n## [", 1).encode())
    (work / "other.js").write_bytes(b"other\n")
    sh(work, "add", "-A")
    sh(work, "commit", "-m", f"fix: other (v{version})")
    sh(work, "push", "origin", "HEAD:main")
    sh(work, "fetch", "origin")
    sh(work, "checkout", "-q", "feature")


def never(_tag: str) -> bool:
    return False


def prepare(work: Path, tmp_path: Path, level="patch", notes=None, taken=never):
    vt, vt_path = pt.load_version_tool()
    scratch = tmp_path / "scratch"
    scratch.mkdir(exist_ok=True)
    return pt.prepare_branch(vt, vt_path, work, "origin/main", level, notes,
                             taken, scratch)


def test_fresh_branch_gets_one_bump_and_no_tag(repo, tmp_path):
    commit(repo, "app.js", "2\n", "fix: app")
    vt, _ = pt.load_version_tool()
    assert pt.bump_state(vt, repo, "origin/main", never) == ("absent", "1.0.0")
    assert prepare(repo, tmp_path, notes="### Fixed\n- The app.") == "1.0.1"
    assert '"version": "1.0.1"' in (repo / "package.json").read_text()
    log = (repo / "CHANGELOG.md").read_text()
    assert "## [1.0.1]" in log and "- The app." in log
    assert sh(repo, "log", "-1", "--format=%s") == "chore(release): v1.0.1"
    assert sh(repo, "tag") == ""                     # the lander tags after merge
    assert pt.bump_state(vt, repo, "origin/main", never) == ("current", "1.0.1")


def test_stale_bump_is_dropped_and_recut_after_main_moves(repo, tmp_path):
    commit(repo, "app.js", "2\n", "fix: app")
    assert prepare(repo, tmp_path, notes="- Hand-written branch notes.") == "1.0.1"
    advance_main(repo, "1.0.1")                      # someone else took 1.0.1
    vt, _ = pt.load_version_tool()
    assert pt.bump_state(vt, repo, "origin/main", never)[0] == "stale"

    assert prepare(repo, tmp_path) == "1.0.2"        # no notes passed this time
    log = (repo / "CHANGELOG.md").read_text()
    assert log.count("## [1.0.1]") == 1 and "- other PR" in log
    assert "## [1.0.2]" in log
    # the branch's own notes were carried over from the dropped section
    section = log.split("## [1.0.2]")[1].split("## [1.0.1]")[0]
    assert "Hand-written branch notes." in section
    assert (repo / "other.js").exists()              # main was merged in
    assert sh(repo, "status", "--porcelain") == ""


def test_dropping_a_bump_keeps_other_edits_to_the_version_file(repo, tmp_path):
    pkg = (repo / "package.json").read_text().replace(
        '"dependencies": {}', '"dependencies": {"left-pad": "1.3.0"}')
    commit(repo, "package.json", pkg, "feat: add left-pad")
    assert prepare(repo, tmp_path, level="minor") == "1.1.0"
    advance_main(repo, "1.0.1")
    assert prepare(repo, tmp_path, level="minor") == "1.1.0"   # 1.0.1 -> 1.1.0
    text = (repo / "package.json").read_text()
    assert '"left-pad": "1.3.0"' in text and '"version": "1.1.0"' in text


def test_taken_tag_makes_a_bump_stale(repo, tmp_path):
    commit(repo, "app.js", "2\n", "fix: app")
    prepare(repo, tmp_path)
    vt, _ = pt.load_version_tool()
    taken = lambda tag: tag == "v1.0.1"  # noqa: E731
    assert pt.bump_state(vt, repo, "origin/main", taken)[0] == "stale"


def test_real_conflict_with_main_is_refused_and_left_clean(repo, tmp_path):
    commit(repo, "other.js", "mine\n", "feat: other")
    advance_main(repo, "1.0.1")                      # also writes other.js
    with pytest.raises(pt.ToolError, match="conflicts in: other.js"):
        prepare(repo, tmp_path)
    assert sh(repo, "status", "--porcelain") == ""


def test_bump_keeps_lf_line_endings(repo, tmp_path):
    commit(repo, "app.js", "2\n", "fix: app")
    prepare(repo, tmp_path)
    assert b"\r\n" not in (repo / "package.json").read_bytes()
    assert b"\r\n" not in (repo / "CHANGELOG.md").read_bytes()


def test_local_draft_tag_is_moved_aside_not_deleted(repo, tmp_path):
    commit(repo, "app.js", "2\n", "fix: app")
    sh(repo, "tag", "v1.0.1")                        # left by an older flow
    assert prepare(repo, tmp_path) == "1.0.1"
    tags = sh(repo, "tag").split()
    assert "v1.0.1" not in tags
    assert any(t.startswith("v1.0.1-draft-") for t in tags)
