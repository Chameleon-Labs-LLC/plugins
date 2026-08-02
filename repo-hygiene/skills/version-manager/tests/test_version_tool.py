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
