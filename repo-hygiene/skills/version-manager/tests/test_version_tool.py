"""Tests for version_tool, one fixture per real-world shape found in the
eight-repo survey (design §10).

Each synthetic repo reproduces a failure actually present in the surveyed projects,
so a regression here means the tool would mishandle a real repository.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import version_tool as vt  # noqa: E402


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def new_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True)
    run_git(repo, "init", "-q", "-b", "main")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test")
    run_git(repo, "config", "commit.gpgsign", "false")
    return repo


def commit(repo: Path, message: str, files: dict[str, str] | None = None,
           when: str = "2026-01-01T12:00:00") -> str:
    for rel, content in (files or {}).items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q",
                    "--allow-empty", "-m", message],
                   check=True, capture_output=True, env=env)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


CHANGELOG = """# Changelog

## [Unreleased]

## [{v}] - {d}

### Added
- something
"""


# --------------------------------------------------------------------------
# detection (§4)
# --------------------------------------------------------------------------

def test_pointer_comment_wins_over_packaging_metadata(tmp_path):
    """A Python service: pyproject and setup.py both name src/version.py canonical,
    and src/version.py (0.9.0) disagrees with everything else (0.2.0)."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "pyproject.toml": '[project]\nversion = "0.2.0"  # See src/version.py '
                          'for centralized version management\n',
        "setup.py": "# The actual version is managed in src/version.py\n",
        "VERSION": "0.2.0\n",
        "src/version.py": '__version__ = "0.9.0"\n',
    })
    canonical, mirrors, notes = vt.detect(repo)
    assert canonical is not None
    assert canonical.path == Path("src/version.py")
    assert canonical.value == "0.9.0"
    assert any("canonical source" in n for n in notes)
    assert {m.value for m in mirrors} == {"0.2.0"}


def test_empty_package_json_is_skipped_not_filled(tmp_path):
    """A CLI tool: package.json is `{}` — a stub, not a version location."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {"package.json": "{}\n", "VERSION": "0.2.0\n"})
    canonical, _mirrors, notes = vt.detect(repo)
    assert canonical is not None
    assert canonical.path == Path("VERSION")
    assert canonical.value == "0.2.0"
    assert any("empty stub" in n for n in notes)


MARKETPLACE = """{
  "name": "example-marketplace",
  "owner": { "name": "Example" },
  "metadata": {
    "description": "catalog of plugins",
    "version": "0.2.0"
  },
  "plugins": [
    {
      "name": "example-plugin",
      "source": "./",
      "skills": ["./claude/skills/version-manager"],
      "description": "one plugin",
      "version": "0.3.0"
    }
  ]
}
"""


def test_marketplace_plugin_version_is_detected(tmp_path):
    """.claude_code: the only version home is the plugin entry in
    .claude-plugin/marketplace.json — metadata.version is the catalog's own
    series and must not be picked (or later overwritten) as the repo version."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {".claude-plugin/marketplace.json": MARKETPLACE})
    canonical, mirrors, notes = vt.detect(repo)
    assert canonical is not None
    assert canonical.path == Path(".claude-plugin/marketplace.json")
    assert canonical.kind == "marketplace"
    assert canonical.value == "0.3.0"
    assert not mirrors
    assert any("metadata.version" in n for n in notes)


def test_marketplace_with_many_plugins_and_no_catalog_version_is_noted(tmp_path):
    """Several plugins, each with its own version, and no metadata.version —
    no single repo version exists, so the tool must not pick plugins[0]."""
    repo = new_repo(tmp_path)
    market = json.loads(MARKETPLACE)
    del market["metadata"]["version"]
    market["plugins"].append(dict(market["plugins"][0],
                                  name="second-plugin", version="1.4.0"))
    commit(repo, "init",
           {".claude-plugin/marketplace.json": json.dumps(market, indent=2)})
    canonical, _mirrors, notes = vt.detect(repo)
    assert canonical is None
    assert any("2 plugins" in n for n in notes)


# Chameleon-Labs-LLC/plugins shape: many bundled plugins, a catalog series in
# metadata.version, and a changelog with unbracketed "## 0.3.0 — date" headings.
MULTI_CHANGELOG = """# Changelog

Marketplace releases, newest first.

## 0.3.0 — 2026-08-02

- three plugins
"""


def _multi_market(meta: str | None = "0.3.0") -> str:
    market = json.loads(MARKETPLACE)
    if meta is None:
        del market["metadata"]["version"]
    else:
        market["metadata"]["version"] = meta
    market["plugins"] = [
        {"name": "alpha", "source": "./alpha", "description": "a",
         "author": {"name": "Ex"}, "version": "0.1.0"},
        {"name": "beta", "source": "./beta", "description": "b",
         "version": "1.4.0"},
        {"name": "remote", "source": {"source": "github", "repo": "x/y"},
         "description": "r", "version": "2.0.0"},
    ]
    return json.dumps(market, indent=2) + "\n"


def _plugin_json(name: str, version: str) -> str:
    return json.dumps({"name": name, "version": version,
                       "description": "d"}, indent=2) + "\n"


def _multi_repo(tmp_path: Path, meta: str | None = "0.3.0",
                beta_json: str = "1.4.0") -> Path:
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        ".claude-plugin/marketplace.json": _multi_market(meta),
        "alpha/.claude-plugin/plugin.json": _plugin_json("alpha", "0.1.0"),
        "beta/.claude-plugin/plugin.json": _plugin_json("beta", beta_json),
        "CHANGELOG.md": MULTI_CHANGELOG,
    }, when="2026-08-02T10:00:00")
    commit(repo, "feat(alpha): new skill", {"alpha/skill.md": "x\n"},
           when="2026-09-01T10:00:00")
    return repo


def _versions(repo: Path) -> dict[str, str]:
    data = json.loads((repo / ".claude-plugin/marketplace.json").read_text())
    out = {"metadata": data["metadata"]["version"]}
    out.update({p["name"]: p["version"] for p in data["plugins"]})
    for name in ("alpha", "beta"):
        pj = json.loads((repo / name / ".claude-plugin/plugin.json").read_text())
        out[f"{name}/plugin.json"] = pj["version"]
    return out


def test_multi_plugin_marketplace_tracks_the_catalog_series(tmp_path):
    repo = _multi_repo(tmp_path)
    canonical, mirrors, notes = vt.detect(repo)
    assert canonical is not None
    assert canonical.kind == "marketplace_meta"
    assert canonical.value == "0.3.0"
    assert not mirrors
    assert any("--plugin" in n for n in notes)


def test_unbracketed_changelog_headings_are_parsed(tmp_path):
    repo = _multi_repo(tmp_path)
    assert vt.changelog_ledger(repo) == {"0.3.0": "2026-08-02"}


def test_release_bumps_named_plugins_and_the_catalog(tmp_path):
    repo = _multi_repo(tmp_path)
    before = (repo / ".claude-plugin/marketplace.json").read_text()

    assert vt.main(["--repo", str(repo), "release", "minor",
                    "--plugin", "alpha", "--plugin", "beta=patch", "--apply"]) == 0

    assert _versions(repo) == {
        "metadata": "0.4.0",
        "alpha": "0.2.0", "alpha/plugin.json": "0.2.0",
        "beta": "1.4.1", "beta/plugin.json": "1.4.1",
        "remote": "2.0.0",
    }
    after = (repo / ".claude-plugin/marketplace.json").read_text()
    assert after.count("\n") == before.count("\n"), "file was reserialised"
    assert '"author": {\n        "name": "Ex"\n      }' in after
    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## 0.4.0 — {date.today()}" in changelog, "heading style not kept"
    assert "## [0.4.0]" not in changelog
    assert changelog.index("## 0.4.0") < changelog.index("## 0.3.0")
    assert "v0.4.0" in vt.existing_tags(repo)
    assert not vt.is_dirty(repo)


def test_release_plugin_refuses_when_plugin_json_disagrees(tmp_path, capsys):
    repo = _multi_repo(tmp_path, beta_json="1.3.0")
    before = _versions(repo)
    assert vt.main(["--repo", str(repo), "release", "minor",
                    "--plugin", "beta", "--apply"]) == 1
    assert "beta" in capsys.readouterr().out
    assert _versions(repo) == before


def test_release_plugin_refuses_unknown_external_or_bad_level(tmp_path):
    repo = _multi_repo(tmp_path)
    before = _versions(repo)
    for spec in ("gamma", "remote", "alpha=huge", "alpha,beta"):
        assert vt.main(["--repo", str(repo), "release", "minor",
                        "--plugin", spec, "--apply"]) == 1, spec
    assert vt.main(["--repo", str(repo), "release", "minor",
                    "--plugin", "alpha", "--plugin", "alpha", "--apply"]) == 1
    assert _versions(repo) == before
    assert "v0.4.0" not in vt.existing_tags(repo)


def test_release_plugin_flag_needs_a_multi_plugin_marketplace(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "1.0.0\n"})
    assert vt.main(["--repo", str(repo), "release", "patch",
                    "--plugin", "alpha", "--apply"]) == 1
    assert (repo / "VERSION").read_text() == "1.0.0\n"


def test_release_names_changed_plugins_left_unbumped(tmp_path, capsys):
    repo = _multi_repo(tmp_path)
    assert vt.main(["--repo", str(repo), "release", "minor"]) == 0
    out = capsys.readouterr().out
    assert "alpha" in out and "--plugin alpha" in out
    assert "--plugin beta" not in out, "beta has no commits of its own"


def test_check_lists_plugin_versions_and_flags_drift(tmp_path, capsys):
    repo = _multi_repo(tmp_path, beta_json="1.3.0")
    assert vt.main(["--repo", str(repo), "check"]) == 0
    out = capsys.readouterr().out
    assert "plugin: alpha = 0.1.0" in out
    assert "plugin: beta = 1.4.0" in out and "DISAGREES" in out


def test_release_bumps_marketplace_plugin_not_metadata(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        ".claude-plugin/marketplace.json": MARKETPLACE,
        "CHANGELOG.md": CHANGELOG.format(v="0.3.0", d="2026-08-01"),
    }, when="2026-08-01T10:00:00")
    commit(repo, "feat: new skill", when="2026-08-06T10:00:00")

    assert vt.main(["--repo", str(repo), "release", "minor", "--apply"]) == 0

    text = (repo / ".claude-plugin/marketplace.json").read_text()
    data = json.loads(text)
    assert data["plugins"][0]["version"] == "0.4.0"
    assert data["metadata"]["version"] == "0.2.0", "metadata.version overwritten"
    assert '"description": "catalog of plugins"' in text, "file was reserialised"
    assert "## [0.4.0]" in (repo / "CHANGELOG.md").read_text()
    assert "v0.4.0" in vt.existing_tags(repo)


def test_version_file_with_trailing_comments_is_detected(tmp_path):
    """A Python service's VERSION has explanatory comments under the number;
    requiring a bare file left it undetected and it would go stale."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "VERSION": "0.2.0\n# This file is maintained for backward compatibility\n",
        "README.md": "# App\n",
    })
    canonical, _, _ = vt.detect(repo)
    assert canonical is not None
    assert canonical.path == Path("VERSION")
    assert canonical.value == "0.2.0"

    vt.main(["--repo", str(repo), "release", "patch", "--apply"])
    text = (repo / "VERSION").read_text()
    assert text.startswith("0.2.1")
    assert "backward compatibility" in text, "comments must survive the bump"


def test_readme_display_is_a_mirror_never_canonical(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "core/constants.py": 'VERSION = "0.40.0"\n',
        "README.md": "# App\n\n**Version 0.40.0**\n",
    })
    canonical, mirrors, _ = vt.detect(repo)
    assert canonical is not None and canonical.path == Path("core/constants.py")
    readme = [m for m in mirrors if m.path == Path("README.md")]
    assert readme and readme[0].mirror_only


def test_detection_prunes_heavy_directories(tmp_path):
    """A bare **/ glob would descend into node_modules; the walk must not."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "VERSION": "1.0.0\n",
        "node_modules/pkg/version.py": '__version__ = "9.9.9"\n',
        ".venv/lib/constants.py": 'VERSION = "8.8.8"\n',
    })
    canonical, mirrors, _ = vt.detect(repo)
    assert canonical is not None and canonical.value == "1.0.0"
    assert all("node_modules" not in str(m.path) for m in mirrors)
    assert all(".venv" not in str(m.path) for m in mirrors)


# --------------------------------------------------------------------------
# ledger (§5)
# --------------------------------------------------------------------------

def test_ledger_recovers_relocated_version_home(tmp_path):
    """ImageAI: __version__ lived in main.py before moving to core/constants.py.
    Without walking the old home, 0.2.0 is unrecoverable."""
    repo = new_repo(tmp_path)
    commit(repo, "start", {"main.py": '__version__ = "0.2.0"\n'},
           when="2025-08-29T10:00:00")
    commit(repo, "move version into core", {
        "main.py": "pass\n",
        "core/constants.py": 'VERSION = "0.8.0"\n',
    }, when="2025-09-07T10:00:00")
    commit(repo, "feat: bump", {"core/constants.py": 'VERSION = "0.9.0"\n'},
           when="2025-09-08T10:00:00")

    canonical, _, _ = vt.detect(repo)
    versions = [e.version for e in vt.git_ledger(repo, canonical)]
    assert "0.2.0" in versions, "relocated home not walked"
    assert versions == ["0.2.0", "0.8.0", "0.9.0"]


def test_generated_client_version_never_enters_the_ledger(tmp_path):
    """A Next.js app tracked a generated Prisma client; its bundled package.json
    says "version": "6.19.0", which surfaced as a release of the app itself."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {"package.json": json.dumps({"version": "1.0.0"})},
           when="2025-11-20T10:00:00")
    commit(repo, "feat: add prisma", {
        "src/generated/prisma/package.json": json.dumps({"version": "6.19.0"}),
        "package.json": json.dumps({"version": "1.1.0"}),
    }, when="2025-11-26T10:00:00")

    canonical, _, _ = vt.detect(repo)
    versions = [e.version for e in vt.git_ledger(repo, canonical)]
    assert "6.19.0" not in versions, "vendored dependency version leaked in"
    assert versions == ["1.0.0", "1.1.0"]


def test_reconcile_finds_gaps_mismatches_and_unlocatable(tmp_path):
    """ImageAI's three real changelog defects at once."""
    repo = new_repo(tmp_path)
    commit(repo, "v1", {"VERSION": "0.1.0\n"}, when="2025-12-01T10:00:00")
    commit(repo, "feat: gap release", {"VERSION": "0.2.0\n"},
           when="2025-12-02T10:00:00")
    changelog = (
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [0.3.0] - 2025-12-10\n\n### Added\n- never bumped the file\n\n"
        "## [0.1.0] - 2025-11-06\n\n### Added\n- wrong month\n"
    )
    commit(repo, "docs: changelog", {"CHANGELOG.md": changelog},
           when="2025-12-11T10:00:00")

    canonical, _, _ = vt.detect(repo)
    rec = vt.reconcile(repo, canonical)
    assert "0.2.0" in rec.git_only          # in git, missing from changelog
    assert "0.3.0" in rec.changelog_only    # no locatable bump commit
    assert "0.1.0" in rec.date_mismatch     # 2025-11-06 vs git 2025-12-01
    assert rec.entries["0.1.0"].date == "2025-12-01"
    assert rec.entries["0.1.0"].changelog_date == "2025-11-06"


# --------------------------------------------------------------------------
# real record vs placeholder (§5.1)
# --------------------------------------------------------------------------

def test_sparse_real_record_invents_nothing(tmp_path):
    """A Next.js app: 3 real bumps across many commits stays 3 versions."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {"package.json": json.dumps({"version": "0.0.0"})},
           when="2025-11-20T10:00:00")
    for _ in range(8):
        commit(repo, "chore: filler", when="2025-11-22T10:00:00")
    commit(repo, "feat: first", {"package.json": json.dumps({"version": "0.1.0"})},
           when="2025-11-25T10:00:00")
    for _ in range(8):
        commit(repo, "chore: filler", when="2026-01-10T10:00:00")
    commit(repo, "feat: big", {"package.json": json.dumps({"version": "1.1.0"})},
           when="2026-02-10T10:00:00")

    canonical, _, _ = vt.detect(repo)
    entries = vt.git_ledger(repo, canonical)
    assert not vt.is_placeholder(entries)
    assert [e.version for e in entries] == ["0.0.0", "0.1.0", "1.1.0"]


def test_placeholder_version_is_classified_and_synthesized(tmp_path):
    """A busy web app: 0.1.0 set once and never moved is a default, not a record."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {"package.json": json.dumps({"version": "0.1.0"})},
           when="2025-11-10T10:00:00")
    for i in range(6):
        commit(repo, f"feat: thing {i} (#{i + 1})", when="2025-12-01T10:00:00")

    canonical, _, _ = vt.detect(repo)
    entries = vt.git_ledger(repo, canonical)
    assert vt.is_placeholder(entries)

    series, note = vt.synthesize(repo)
    assert "PR merge references" in note
    assert len(series) > 1
    assert vt.version_key(series[-1].version) > vt.version_key(series[0].version)


def test_synthesis_is_per_boundary_never_per_commit(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"}, when="2025-11-10T10:00:00")
    for i in range(3):
        commit(repo, "chore: work", when="2025-11-11T10:00:00")
        commit(repo, "chore: more work", when="2025-11-11T10:00:00")
        commit(repo, f"feat: shipped (#{i + 1})", when="2025-11-12T10:00:00")

    series, _ = vt.synthesize(repo)
    assert len(series) == 3, "one version per PR boundary, not per commit"


def test_boundary_guard_groups_by_month(tmp_path):
    """A busy web app' 348 PRs must not become 0.348.0."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"}, when="2025-11-10T10:00:00")
    n = vt.BOUNDARY_GUARD + 20
    for i in range(n):
        month = 11 if i < n // 2 else 12
        commit(repo, f"feat: change {i} (#{i + 1})",
               when=f"2025-{month:02d}-15T10:00:00")

    series, note = vt.synthesize(repo)
    assert "grouped by month" in note
    assert len(series) <= 3, f"expected month grouping, got {len(series)} versions"


def test_changelog_record_is_not_a_placeholder(tmp_path):
    """A small service: app/__init__.py never moved off 0.1.0, but the changelog
    shipped 0.1.0 and 0.2.0. Synthesizing here produced 0.0.1 — below what
    already shipped."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "app/__init__.py": '__version__ = "0.1.0"\n',
        "CHANGELOG.md": "# Changelog\n\n## [0.2.0] - 2025-12-07\n\n### Added\n- b\n"
                        "\n## [0.1.0] - 2025-12-06\n\n### Added\n- a\n",
    }, when="2025-12-06T10:00:00")

    canonical, _, _ = vt.detect(repo)
    entries = vt.git_ledger(repo, canonical)
    cl = vt.changelog_ledger(repo)
    assert not vt.is_placeholder(entries, len(cl)), \
        "a changelog with several versions IS a record"


def test_synthesized_series_never_regresses_below_known_versions(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "VERSION": "2.3.0\n",
        "CHANGELOG.md": "# Changelog\n\n## [2.3.0] - 2025-12-06\n\n### Added\n- a\n",
    }, when="2025-12-06T10:00:00")
    for i in range(3):
        commit(repo, f"feat: later work (#{i + 1})", when="2025-12-10T10:00:00")

    canonical, _, _ = vt.detect(repo)
    rec = vt.reconcile(repo, canonical)
    floor = vt.known_floor(canonical, rec.entries)
    series, _ = vt.synthesize(repo, floor)
    assert series
    assert vt.version_key(series[0].version) > vt.version_key("2.3.0"), \
        f"series regressed to {series[0].version}"


def test_version_behind_changelog_is_called_out(tmp_path, capsys):
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "app/__init__.py": '__version__ = "0.1.0"\n',
        "CHANGELOG.md": "# Changelog\n\n## [0.2.0] - 2025-12-07\n\n### Added\n- b\n"
                        "\n## [0.1.0] - 2025-12-06\n\n### Added\n- a\n",
    })
    vt.main(["--repo", str(repo), "check"])
    assert "VERSION BEHIND CHANGELOG" in capsys.readouterr().out


def test_level_derived_from_conventional_commits(tmp_path):
    assert vt.level_for(["fix: a", "chore: b"]) == "patch"
    assert vt.level_for(["fix: a", "feat: b"]) == "minor"
    assert vt.level_for(["feat!: breaking"]) == "major"
    assert vt.level_for(["feat: x", "BREAKING CHANGE: y"]) == "major"


# --------------------------------------------------------------------------
# backfill (§6)
# --------------------------------------------------------------------------

def test_backfill_is_dry_by_default_then_tags_and_fills(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"}, when="2025-12-01T10:00:00")
    commit(repo, "feat: two", {"VERSION": "0.2.0\n"}, when="2025-12-02T10:00:00")
    commit(repo, "docs: changelog", {"CHANGELOG.md": CHANGELOG.format(
        v="0.1.0", d="2025-12-01")}, when="2025-12-03T10:00:00")

    assert vt.main(["--repo", str(repo), "backfill"]) == 0
    assert vt.existing_tags(repo) == set(), "dry run must not write"

    assert vt.main(["--repo", str(repo), "backfill", "--apply"]) == 0
    assert {"v0.1.0", "v0.2.0"} <= vt.existing_tags(repo)
    text = (repo / "CHANGELOG.md").read_text()
    assert "## [0.2.0] - 2025-12-02" in text, "gap not filled"
    assert "## [0.1.0] - 2025-12-01" in text, "existing entry disturbed"


def test_backfill_never_tags_unlocatable_versions(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"}, when="2025-12-01T10:00:00")
    commit(repo, "docs", {"CHANGELOG.md":
                          "# Changelog\n\n## [0.5.0] - 2025-12-09\n\n### Added\n- ghost\n"},
           when="2025-12-09T10:00:00")

    vt.main(["--repo", str(repo), "backfill", "--apply"])
    assert "v0.5.0" not in vt.existing_tags(repo), "tagged a guessed commit"


def test_backfill_leaves_dates_alone_without_fix_dates(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"}, when="2025-12-01T10:00:00")
    commit(repo, "docs", {"CHANGELOG.md": CHANGELOG.format(
        v="0.1.0", d="2025-11-06")}, when="2025-12-02T10:00:00")

    vt.main(["--repo", str(repo), "backfill", "--apply"])
    assert "## [0.1.0] - 2025-11-06" in (repo / "CHANGELOG.md").read_text()

    vt.main(["--repo", str(repo), "backfill", "--apply", "--fix-dates"])
    assert "## [0.1.0] - 2025-12-01" in (repo / "CHANGELOG.md").read_text()


def test_backfill_replaces_placeholder_with_derived_head(tmp_path):
    """Never resets to a hardcoded 0.1.0 — the head comes from history."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"}, when="2025-11-10T10:00:00")
    for i in range(5):
        commit(repo, f"feat: thing {i} (#{i + 1})", when="2025-11-11T10:00:00")

    vt.main(["--repo", str(repo), "backfill", "--apply"])
    written = (repo / "VERSION").read_text().strip()
    assert vt.version_key(written) > vt.version_key("0.1.0"), (
        f"placeholder not advanced (got {written})")


def test_backfill_is_idempotent(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"}, when="2025-12-01T10:00:00")
    commit(repo, "feat: two", {"VERSION": "0.2.0\n"}, when="2025-12-02T10:00:00")

    vt.main(["--repo", str(repo), "backfill", "--apply"])
    first = (repo / "CHANGELOG.md").read_text()
    tags = vt.existing_tags(repo)
    vt.main(["--repo", str(repo), "backfill", "--apply"])
    assert (repo / "CHANGELOG.md").read_text() == first
    assert vt.existing_tags(repo) == tags


# --------------------------------------------------------------------------
# release (§7)
# --------------------------------------------------------------------------

def test_release_round_trip_updates_every_location(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "core/constants.py": 'VERSION = "0.40.0"\n',
        "README.md": "# App\n\n**Version 0.40.0**\n",
        "CHANGELOG.md": CHANGELOG.format(v="0.40.0", d="2026-07-01"),
    }, when="2026-07-01T10:00:00")
    commit(repo, "feat: something new", when="2026-07-20T10:00:00")

    assert vt.main(["--repo", str(repo), "release", "minor", "--apply"]) == 0

    assert 'VERSION = "0.41.0"' in (repo / "core/constants.py").read_text()
    assert "**Version 0.41.0**" in (repo / "README.md").read_text(), \
        "README display not synced"
    assert "## [0.41.0]" in (repo / "CHANGELOG.md").read_text()
    assert "v0.41.0" in vt.existing_tags(repo)
    assert not vt.is_dirty(repo)


def test_release_levels_cover_major_minor_patch(tmp_path):
    for level, expected in (("major", "1.0.0"), ("minor", "0.41.0"),
                            ("patch", "0.40.1")):
        repo = new_repo(tmp_path, name=f"r_{level}")
        commit(repo, "init", {"VERSION": "0.40.0\n"}, when="2026-07-01T10:00:00")
        vt.main(["--repo", str(repo), "release", level, "--apply"])
        assert (repo / "VERSION").read_text().strip() == expected


def test_release_refuses_on_dirty_tree(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"})
    (repo / "scratch.txt").write_text("wip")
    assert vt.main(["--repo", str(repo), "release", "minor", "--apply"]) == 1
    assert (repo / "VERSION").read_text().strip() == "0.1.0"


def test_release_refuses_when_locations_disagree(tmp_path):
    """A Python service today: 0.9.0 vs 0.2.0 must block, not silently pick one."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "pyproject.toml": '[project]\nversion = "0.2.0"\n',
        "src/version.py": '__version__ = "0.9.0"\n',
    })
    assert vt.main(["--repo", str(repo), "release", "minor", "--apply"]) == 1
    assert '"0.2.0"' in (repo / "pyproject.toml").read_text()


def test_release_refuses_existing_tag(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"})
    run_git(repo, "tag", "-a", "v0.2.0", "-m", "Version 0.2.0")
    assert vt.main(["--repo", str(repo), "release", "minor", "--apply"]) == 1


def test_release_dry_run_writes_nothing(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n",
                          "CHANGELOG.md": CHANGELOG.format(v="0.1.0", d="2026-01-01")})
    assert vt.main(["--repo", str(repo), "release", "minor"]) == 0
    assert (repo / "VERSION").read_text().strip() == "0.1.0"
    assert vt.existing_tags(repo) == set()


def test_release_preserves_package_json_formatting(tmp_path):
    """Surgical rewrite, not reserialisation — key order and indent survive."""
    repo = new_repo(tmp_path)
    original = '{\n  "name": "app",\n  "version": "1.1.0",\n  "private": true\n}\n'
    commit(repo, "init", {"package.json": original})
    vt.main(["--repo", str(repo), "release", "patch", "--apply"])
    updated = (repo / "package.json").read_text()
    assert updated == original.replace("1.1.0", "1.1.1")


def test_check_never_writes(tmp_path):
    repo = new_repo(tmp_path)
    commit(repo, "init", {"VERSION": "0.1.0\n"})
    before = vt.is_dirty(repo)
    assert vt.main(["--repo", str(repo), "check"]) == 0
    assert vt.is_dirty(repo) == before
    assert vt.existing_tags(repo) == set()


def test_version_behind_changelog_is_reported(tmp_path, capsys):
    """A small service: code says 0.1.0, changelog shipped 0.2.0."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "app/__init__.py": '__version__ = "0.1.0"\n',
        "CHANGELOG.md": "# Changelog\n\n## [0.2.0] - 2025-12-07\n\n### Added\n- x\n"
                        "\n## [0.1.0] - 2025-12-06\n\n### Added\n- y\n",
    })
    vt.main(["--repo", str(repo), "check"])
    out = capsys.readouterr().out
    assert "0.2.0" in out
    assert "NO LOCATABLE BUMP COMMIT" in out


def test_not_a_git_repo_exits_cleanly(tmp_path):
    assert vt.main(["--repo", str(tmp_path), "check"]) == 2
