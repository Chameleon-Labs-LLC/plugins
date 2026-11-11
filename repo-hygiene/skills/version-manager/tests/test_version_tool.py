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


def test_marketplace_with_many_plugins_is_noted_not_tracked(tmp_path):
    """Chameleon-Labs-LLC/plugins: seven plugins, each with its own version —
    no single repo version exists, so the tool must not pick plugins[0]."""
    repo = new_repo(tmp_path)
    market = json.loads(MARKETPLACE)
    market["plugins"].append(dict(market["plugins"][0],
                                  name="second-plugin", version="1.4.0"))
    commit(repo, "init",
           {".claude-plugin/marketplace.json": json.dumps(market, indent=2)})
    canonical, _mirrors, notes = vt.detect(repo)
    assert canonical is None
    assert any("2 plugins" in n for n in notes)


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


# A plugin entry whose npm-style source carries its own version pin, placed
# BEFORE the entry's own version. "The first version after plugins" is the pin.
MARKETPLACE_NPM = """{
  "name": "example-marketplace",
  "metadata": { "version": "0.2.0" },
  "plugins": [
    {
      "name": "example-plugin",
      "source": { "source": "npm", "package": "@example/plugin", "version": "%s" },
      "description": "one plugin, \\"quoted\\" { braces ] in a string",
      "version": "0.3.0"
    }
  ]
}
"""


def test_release_bumps_the_plugin_entry_not_its_nested_source_pin(tmp_path):
    """plugins#9 review: with source.version equal to the entry's version the
    old first-match pattern passed detect()'s equality check and a release
    rewrote the source pin, leaving the entry's own version behind."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        ".claude-plugin/marketplace.json": MARKETPLACE_NPM % "0.3.0",
        "CHANGELOG.md": CHANGELOG.format(v="0.3.0", d="2026-08-01"),
    }, when="2026-08-01T10:00:00")
    commit(repo, "feat: new skill", when="2026-08-06T10:00:00")

    assert vt.main(["--repo", str(repo), "release", "minor", "--apply"]) == 0

    text = (repo / ".claude-plugin/marketplace.json").read_text()
    entry = json.loads(text)["plugins"][0]
    assert entry["version"] == "0.4.0"
    assert entry["source"]["version"] == "0.3.0", "source pin was rewritten"
    assert json.loads(text)["metadata"]["version"] == "0.2.0"
    # Surgical: only the three digits groups moved.
    assert text == (MARKETPLACE_NPM % "0.3.0").replace(
        '"version": "0.3.0"\n    }', '"version": "0.4.0"\n    }')


def test_marketplace_with_a_different_source_pin_is_still_tracked(tmp_path):
    """A source pin that differs from the entry used to read as a 'pattern
    mismatch' and the repo lost its only version home."""
    repo = new_repo(tmp_path)
    commit(repo, "init",
           {".claude-plugin/marketplace.json": MARKETPLACE_NPM % "7.1.2"})
    canonical, _mirrors, notes = vt.detect(repo)
    assert canonical is not None and canonical.value == "0.3.0"
    assert not any("mismatch" in n for n in notes)


def test_version_span_reads_only_the_owned_key():
    span = vt._version_span(MARKETPLACE_NPM % "9.9.9", "marketplace")
    assert span is not None
    assert (MARKETPLACE_NPM % "9.9.9")[span[0]:span[1]] == "0.3.0"
    # plugin.json: the top-level key, never a nested one that comes first.
    manifest = '{"author": {"version": "5.5.5"}, "name": "p", "version": "1.2.3"}'
    a, b = vt._version_span(manifest, "plugin_json")
    assert manifest[a:b] == "1.2.3"
    assert vt._version_span('{"name": "p"}', "plugin_json") is None
    assert vt._version_span('{"plugins": [], "version": "1.0.0"}', "marketplace") is None
    assert vt._version_span('{"plugins": [{"version": 3}]}', "marketplace") is None
    assert vt._version_span('{"plugins": [{"version": "1.0.0"', "marketplace") is None
    assert vt._version_span("not json", "marketplace") is None


def test_a_repeated_version_key_blocks_release_instead_of_being_skipped(tmp_path, capsys):
    """plugins#9 review: with two "version" keys in the plugin entry the tool
    wrote the first while every JSON reader uses the last, so a release could
    tag a version the manifest does not declare."""
    twice = MARKETPLACE.replace('"version": "0.3.0"',
                                '"version": "0.3.0",\n      "version": "0.3.0"', 1)
    assert json.loads(twice)["plugins"][0]["version"] == "0.3.0"   # valid to a reader
    assert vt._version_span(twice, "marketplace") is None
    assert vt._duplicate_key(twice, "marketplace") == "version"
    assert vt._duplicate_key(MARKETPLACE, "marketplace") is None
    assert vt._duplicate_key("not json", "marketplace") is None

    repo = new_repo(tmp_path)
    commit(repo, "init", {
        ".claude-plugin/marketplace.json": twice,
        "CHANGELOG.md": CHANGELOG.format(v="0.3.0", d="2026-08-01"),
    }, when="2026-08-01T10:00:00")
    commit(repo, "fix: thing", when="2026-08-06T10:00:00")
    before = (repo / ".claude-plugin/marketplace.json").read_text()

    assert vt.main(["--repo", str(repo), "check"]) == 0            # reports, never writes
    assert "BLOCKING: " in capsys.readouterr().out
    for verb in (["release", "patch", "--apply"], ["backfill", "--apply"]):
        assert vt.main(["--repo", str(repo), *verb]) == 1, verb
        assert "REFUSED: a version file cannot be written safely" in capsys.readouterr().out
    assert (repo / ".claude-plugin/marketplace.json").read_text() == before
    assert not (repo / "VERSION").exists()        # no second home was created
    assert vt.git(repo, "tag", "--list").strip() == ""

    # The plugin's own manifest is held to the same rule.
    manifest = '{"name": "p", "version": "0.3.0", "version": "0.3.0"}'
    assert vt._duplicate_key(manifest, "plugin_json") == "version"
    # A key of the same name in a NESTED object is not a repeat.
    nested = '{"author": {"version": "5.5.5"}, "name": "p", "version": "1.2.3"}'
    assert vt._duplicate_key(nested, "plugin_json") is None


def _symlink(link: Path, target: Path, is_dir: bool) -> bool:
    try:
        os.symlink(target, link, target_is_directory=is_dir)
        return True
    except (OSError, NotImplementedError):
        return False        # Windows without the privilege


def test_a_version_is_never_written_outside_the_repository(tmp_path, capsys):
    """plugins#9 review (CWE-61): a marketplace `source` that is a symlink
    out of the repo passed the relative-path checks, and a release rewrote
    the plugin.json it reached."""
    outside = tmp_path / "someone-elses-plugin"
    (outside / ".claude-plugin").mkdir(parents=True)
    theirs = outside / ".claude-plugin" / "plugin.json"
    theirs.write_text(PLUGIN_JSON % "0.3.0", encoding="utf-8")

    repo = new_repo(tmp_path)
    commit(repo, "init", {
        ".claude-plugin/marketplace.json":
            MARKETPLACE.replace('"source": "./"', '"source": "./linked"'),
        "CHANGELOG.md": CHANGELOG.format(v="0.3.0", d="2026-08-01"),
    }, when="2026-08-01T10:00:00")

    # The write guard needs no symlink to test: a location that resolves
    # outside the repo is refused whatever led to it.
    escape = vt.Location(Path("..") / outside.name / ".claude-plugin" / "plugin.json",
                         "plugin_json", "0.3.0")
    assert vt._inside(repo, Path("CHANGELOG.md"))
    assert not vt._inside(repo, escape.path)
    with pytest.raises(vt.GitError, match="outside the repository"):
        vt.write_version(repo, escape, "9.9.9")
    assert theirs.read_text(encoding="utf-8") == PLUGIN_JSON % "0.3.0"

    if not _symlink(repo / "linked", outside, is_dir=True):
        pytest.skip("cannot create symlinks here; the guard itself is tested above")
    vt.git(repo, "add", "-A")
    vt.git(repo, "commit", "-q", "-m", "chore: link the plugin source")
    assert vt._plugin_manifest_for(repo, {"source": "./linked"}) is None
    _canonical, mirrors, _notes = vt.detect(repo)
    assert all(m.kind != "plugin_json" for m in mirrors)
    assert vt.main(["--repo", str(repo), "release", "patch", "--apply"]) == 0
    assert theirs.read_text(encoding="utf-8") == PLUGIN_JSON % "0.3.0"


def test_a_version_file_linked_out_of_the_repo_blocks_release(tmp_path, capsys):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    repo = new_repo(tmp_path)
    commit(repo, "init", {"README.md": "x\n"})
    if not _symlink(repo / "VERSION", outside / "VERSION", is_dir=False):
        pytest.skip("cannot create symlinks here")
    vt.git(repo, "add", "-A")
    vt.git(repo, "commit", "-q", "-m", "chore: link VERSION")
    assert vt.main(["--repo", str(repo), "release", "patch", "--apply"]) == 1
    assert "BLOCKING: " in capsys.readouterr().out
    assert (outside / "VERSION").read_text(encoding="utf-8") == "1.2.3\n"


CSPROJ_SPLIT = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <Version>
      %s
    </Version>
  </PropertyGroup>
</Project>
"""


def test_ledger_reads_a_csproj_version_split_across_lines(tmp_path):
    """plugins#9 review: detect() accepts <Version> split across lines, but
    the history ledger matched one diff line at a time and saw none of them,
    so backfill could call a real release history a placeholder."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {"App.csproj": CSPROJ_SPLIT % "0.2.0"},
           when="2026-08-01T10:00:00")
    commit(repo, "release 0.3.0", {"App.csproj": CSPROJ_SPLIT % "0.3.0"},
           when="2026-08-05T10:00:00")
    commit(repo, "release 0.4.0", {"App.csproj": CSPROJ_SPLIT % "0.4.0"},
           when="2026-08-09T10:00:00")
    canonical, _mirrors, _notes = vt.detect(repo)
    assert canonical is not None and canonical.value == "0.4.0"
    assert [e.version for e in vt.git_ledger(repo, canonical)] \
        == ["0.2.0", "0.3.0", "0.4.0"]


CSPROJ_COMMENTED = """<Project Sdk="Microsoft.NET.Sdk">
  <!-- Was <Version>0.1.0</Version> before the rename; kept for reference.
       <AssemblyVersion>0.1.0.0</AssemblyVersion> -->
  <PropertyGroup>
    <Version>%s</Version>
    <AssemblyVersion>%s.0</AssemblyVersion>
    <!-- <Version>9.9.9</Version> -->
  </PropertyGroup>
</Project>
"""


def test_a_version_inside_an_xml_comment_is_neither_read_nor_rewritten(tmp_path):
    """plugins#9 review: `<!-- <Version>1.0.0</Version> -->` was detected as
    a declaration and rewritten by a release."""
    text = CSPROJ_COMMENTED % ("0.3.0", "0.3.0")
    assert vt._extract(text, "csproj") == "0.3.0"          # not the commented 0.1.0
    assert vt._extract_all(text, "csproj") == ["0.3.0"]    # no false disagreement
    only_commented = "<Project><!-- <Version>1.0.0</Version> --></Project>"
    assert vt._extract(only_commented, "csproj") is None
    # CDATA is literal text too, however much it looks like markup.
    cdata = ("<Project><Description><![CDATA[Set <Version>9.9.9</Version> in "
             "your own project]]></Description>\n"
             "<PropertyGroup><Version>0.3.0</Version></PropertyGroup></Project>")
    assert vt._extract_all(cdata, "csproj") == ["0.3.0"]
    assert vt._sub_outside_comments(
        vt.PATTERNS["csproj"], lambda m: m.group("pre") + "0.3.1" + m.group("post"),
        cdata) == cdata.replace("<Version>0.3.0", "<Version>0.3.1")

    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "App.csproj": text,
        "CHANGELOG.md": CHANGELOG.format(v="0.3.0", d="2026-08-01"),
    }, when="2026-08-01T10:00:00")
    commit(repo, "fix: thing", when="2026-08-06T10:00:00")
    canonical, mirrors, _notes = vt.detect(repo)
    assert canonical.value == "0.3.0" and mirrors == []
    assert vt.main(["--repo", str(repo), "release", "patch", "--apply"]) == 0
    # Only the live declarations moved; both comments are byte-for-byte intact.
    assert (repo / "App.csproj").read_text() == CSPROJ_COMMENTED % ("0.3.1", "0.3.1")


def test_marketplace_of_the_wrong_shape_is_skipped_not_crashed_on(tmp_path):
    repo = new_repo(tmp_path)
    for body in ('[]', '"just a string"', '{"plugins": {"a": 1}}',
                 '{"plugins": "nope"}', '{"plugins": [{"version": "1.0.0"}], '
                 '"metadata": "not an object"}'):
        commit(repo, "shape", {".claude-plugin/marketplace.json": body})
        vt.detect(repo)                       # must not raise


PLUGIN_JSON = """{
  "name": "example-plugin",
  "description": "the plugin's own manifest",
  "version": "%s",
  "author": { "name": "Example" }
}
"""


def test_single_plugin_manifest_is_a_mirror_and_is_bumped(tmp_path):
    """plugins#9 review / Codex: a single-plugin marketplace with source "./"
    and its own .claude-plugin/plugin.json got only the marketplace bumped."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        ".claude-plugin/marketplace.json": MARKETPLACE,
        ".claude-plugin/plugin.json": PLUGIN_JSON % "0.3.0",
        "CHANGELOG.md": CHANGELOG.format(v="0.3.0", d="2026-08-01"),
    }, when="2026-08-01T10:00:00")
    commit(repo, "fix: thing", when="2026-08-06T10:00:00")

    canonical, mirrors, _notes = vt.detect(repo)
    assert canonical.kind == "marketplace"
    assert [(m.path, m.kind, m.value) for m in mirrors] == [
        (Path(".claude-plugin/plugin.json"), "plugin_json", "0.3.0")]

    assert vt.main(["--repo", str(repo), "release", "patch", "--apply"]) == 0
    assert json.loads((repo / ".claude-plugin/marketplace.json").read_text()
                      )["plugins"][0]["version"] == "0.3.1"
    assert (repo / ".claude-plugin/plugin.json").read_text() == PLUGIN_JSON % "0.3.1"


def test_plugin_manifest_drift_is_reported_and_blocks_release(tmp_path, capsys):
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        ".claude-plugin/marketplace.json": MARKETPLACE,
        ".claude-plugin/plugin.json": PLUGIN_JSON % "0.2.9",
    })
    assert vt.main(["--repo", str(repo), "check"]) == 0
    out = capsys.readouterr().out
    assert "plugin.json (plugin_json) = 0.2.9  <-- DISAGREES" in out
    assert vt.main(["--repo", str(repo), "release", "patch", "--apply"]) == 1
    assert "version locations disagree" in capsys.readouterr().out


def test_plugin_manifest_follows_the_entrys_source_folder(tmp_path):
    """The manifest lives where the entry's source points; a manifest with no
    version key, or a source outside the repo, adds no location."""
    repo = new_repo(tmp_path)
    market = json.loads(MARKETPLACE)
    market["plugins"][0]["source"] = "./plugins/example"
    commit(repo, "init", {
        ".claude-plugin/marketplace.json": json.dumps(market, indent=2),
        "plugins/example/.claude-plugin/plugin.json": PLUGIN_JSON % "0.3.0",
        ".claude-plugin/plugin.json": '{"name": "root has no version"}\n',
    })
    _canonical, mirrors, _notes = vt.detect(repo)
    assert [m.path for m in mirrors] == [
        Path("plugins/example/.claude-plugin/plugin.json")]

    market["plugins"][0]["source"] = "../elsewhere"
    commit(repo, "move", {
        ".claude-plugin/marketplace.json": json.dumps(market, indent=2)})
    assert vt.detect(repo)[1] == []
    market["plugins"][0]["source"] = "./"
    commit(repo, "root", {
        ".claude-plugin/marketplace.json": json.dumps(market, indent=2)})
    assert vt.detect(repo)[1] == [], "a manifest without a version is no location"


def test_ledger_reads_marketplace_versions_from_history(tmp_path, capsys):
    """.claude_code: 16 tags, yet `check` said '0 bumps in history' because
    marketplace.json was read as a Python constant file. A real history must
    never be classified as a placeholder."""
    repo = new_repo(tmp_path)
    for i, v in enumerate(("0.1.0", "0.2.0", "0.3.0")):
        commit(repo, f"chore(release): v{v}", {
            ".claude-plugin/marketplace.json": MARKETPLACE.replace("0.3.0", v),
        }, when=f"2026-08-0{i + 1}T10:00:00")
    # metadata.version moving on its own is not a release of the repo.
    commit(repo, "chore: catalog series", {
        ".claude-plugin/marketplace.json":
            MARKETPLACE.replace('"version": "0.2.0"', '"version": "0.9.0"'),
    }, when="2026-08-04T10:00:00")

    canonical, _mirrors, _notes = vt.detect(repo)
    ledger = vt.git_ledger(repo, canonical)
    assert [e.version for e in ledger] == ["0.1.0", "0.2.0", "0.3.0"]
    assert [e.date for e in ledger] == ["2026-08-01", "2026-08-02", "2026-08-03"]
    assert not vt.is_placeholder(ledger, 0)

    assert vt.main(["--repo", str(repo), "check"]) == 0
    assert "real record — 3 bumps in history" in capsys.readouterr().out


def test_ledger_skips_commits_where_the_marketplace_listed_several_plugins(tmp_path):
    repo = new_repo(tmp_path)
    market = json.loads(MARKETPLACE)
    two = dict(market, plugins=market["plugins"] + [
        dict(market["plugins"][0], name="second", version="4.0.0")])
    commit(repo, "two plugins", {
        ".claude-plugin/marketplace.json": json.dumps(two, indent=2)},
        when="2026-08-01T10:00:00")
    commit(repo, "one plugin", {
        ".claude-plugin/marketplace.json": MARKETPLACE},
        when="2026-08-02T10:00:00")
    canonical, _mirrors, _notes = vt.detect(repo)
    assert [e.version for e in vt.git_ledger(repo, canonical)] == ["0.3.0"]


CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Version>%s</Version>
    <AssemblyVersion>%s.0</AssemblyVersion>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)'=='Release'">
    <Version>%s</Version>
    <FileVersion>%s.0</FileVersion>
  </PropertyGroup>
</Project>
"""


def test_csproj_release_moves_every_version_declaration(tmp_path):
    """plugins#9 review: with <Version> in two property groups only the first
    was written, so a release tagged 0.4.0 while the later group built 0.3.0."""
    repo = new_repo(tmp_path)
    commit(repo, "init", {
        "App/App.csproj": CSPROJ % (("0.3.0",) * 4),
        "CHANGELOG.md": CHANGELOG.format(v="0.3.0", d="2026-08-01"),
    }, when="2026-08-01T10:00:00")
    commit(repo, "feat: thing", when="2026-08-06T10:00:00")

    canonical, mirrors, notes = vt.detect(repo)
    assert canonical.kind == "csproj" and canonical.value == "0.3.0"
    assert not mirrors and not any("disagree" in n for n in notes)

    assert vt.main(["--repo", str(repo), "release", "minor", "--apply"]) == 0
    assert (repo / "App/App.csproj").read_text() == CSPROJ % (("0.4.0",) * 4)


def test_csproj_with_disagreeing_declarations_is_refused(tmp_path, capsys):
    repo = new_repo(tmp_path)
    before = CSPROJ % ("0.3.0", "0.3.0", "0.2.0", "0.2.0")
    commit(repo, "init", {"App/App.csproj": before})

    canonical, mirrors, notes = vt.detect(repo)
    assert canonical.value == "0.3.0"
    assert [(m.kind, m.value) for m in mirrors] == [("csproj", "0.2.0")]
    assert any("declares 2 versions that disagree (0.3.0, 0.2.0)" in n
               for n in notes)

    assert vt.main(["--repo", str(repo), "check"]) == 0
    assert "= 0.2.0  <-- DISAGREES" in capsys.readouterr().out
    assert vt.main(["--repo", str(repo), "release", "patch", "--apply"]) == 1
    assert "version locations disagree" in capsys.readouterr().out
    assert (repo / "App/App.csproj").read_text() == before, "refusal wrote"


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
