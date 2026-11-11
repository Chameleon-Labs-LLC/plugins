#!/usr/bin/env python3
"""Version Manager — cross-project version bumping and changelog currency.


Standard library only. Operates on a repository from the outside; adds no
per-repository config file. Every verb is read-only until it prints its plan;
`backfill` and `release` require --apply to write.

    version_tool.py check    [--repo PATH]
    version_tool.py backfill [--repo PATH] [--apply] [--fix-dates]
    version_tool.py release  <major|minor|patch> [--repo PATH] [--apply]
                             [--notes FILE] [--no-tag]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# --------------------------------------------------------------------------
# git plumbing
# --------------------------------------------------------------------------

NUL = "\x00"


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> str:
    """Run git with an explicit -C; never changes the process working dir."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def is_repo(repo: Path) -> bool:
    try:
        return git(repo, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except GitError:
        return False


def is_dirty(repo: Path) -> bool:
    # untracked files inside a submodule are not this repo's dirt; a changed
    # submodule pointer or modified content still counts
    return bool(git(repo, "status", "--porcelain",
                    "--ignore-submodules=untracked").strip())


def existing_tags(repo: Path) -> set[str]:
    return {t for t in git(repo, "tag").split() if t}


# --------------------------------------------------------------------------
# semantic versions
# --------------------------------------------------------------------------

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = SEMVER_RE.match(text.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def fmt_version(v: tuple[int, int, int]) -> str:
    return "{}.{}.{}".format(*v)


def bump(v: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    major, minor, patch = v
    if level == "major":
        return (major + 1, 0, 0)
    if level == "minor":
        return (major, minor + 1, 0)
    if level == "patch":
        return (major, minor, patch + 1)
    raise ValueError(f"unknown bump level: {level}")


def version_key(text: str) -> tuple[int, int, int]:
    return parse_version(text) or (0, 0, 0)


# --------------------------------------------------------------------------
# version locations (§4 — detection ladder, no manifest)
# --------------------------------------------------------------------------

# Each pattern captures the version in group 'v' and preserves surrounding text
# so writes are surgical: package.json is never reserialised and reformatted.
PATTERNS: dict[str, re.Pattern[str]] = {
    "pyproject": re.compile(
        r"(?P<pre>^version\s*=\s*[\"'])(?P<v>\d+\.\d+\.\d+)(?P<post>[\"'])", re.M),
    "package_json": re.compile(
        r"(?P<pre>\"version\"\s*:\s*\")(?P<v>\d+\.\d+\.\d+)(?P<post>\")"),
    "py_const": re.compile(
        r"(?P<pre>^(?:__version__|VERSION)\s*=\s*[\"'])(?P<v>\d+\.\d+\.\d+)(?P<post>[\"'])", re.M),
    # First line only — some projects put explanatory comments
    # beneath the number, so demanding a bare file misses it entirely.
    "version_file": re.compile(
        r"(?P<pre>\A[ \t]*)(?P<v>\d+\.\d+\.\d+)(?P<post>[ \t]*(?:\r?\n|\Z))"),
    "readme": re.compile(
        r"(?P<pre>\*\*Version\s+)(?P<v>\d+\.\d+\.\d+)(?P<post>\*\*)"),
    # .NET SDK-style project: <Version> is canonical; write_version also syncs
    # the 4-part <AssemblyVersion>/<FileVersion> siblings when present. A
    # project may declare <Version> in more than one PropertyGroup: detect()
    # reads every one and write_version() replaces every one.
    "csproj": re.compile(
        r"(?P<pre><Version>\s*)(?P<v>\d+\.\d+\.\d+)(?P<post>\s*</Version>)"),
}

# JSON manifests whose version is ONE specific key, found by walking the JSON
# structure rather than by pattern. A pattern cannot tell a plugin entry's own
# "version" from a nested one: an npm-style `source` object carries a version
# pin of its own, and "the first version after plugins" would rewrite that pin.
#   marketplace  .claude-plugin/marketplace.json -> plugins[0].version. NOT
#                metadata.version (the catalog's own series).
#   plugin_json  <plugin root>/.claude-plugin/plugin.json -> top-level version
SPAN_KINDS = {"marketplace", "plugin_json"}
MARKETPLACE_PATH = ".claude-plugin/marketplace.json"
PLUGIN_MANIFEST = ".claude-plugin/plugin.json"


def _json_ws(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def _json_string(s: str, i: int) -> int:
    """Index just past the string that opens at s[i] == '"'."""
    i += 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
        elif s[i] == '"':
            return i + 1
        else:
            i += 1
    raise ValueError("unterminated string")


def _json_value(s: str, i: int) -> int:
    """Index just past the JSON value that starts at s[i]."""
    if s[i] == '"':
        return _json_string(s, i)
    if s[i] in "{[":
        depth = 0
        while i < len(s):
            if s[i] == '"':
                i = _json_string(s, i)
                continue
            if s[i] in "{[":
                depth += 1
            elif s[i] in "}]":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise ValueError("unterminated container")
    while i < len(s) and s[i] not in ",}] \t\r\n":
        i += 1
    return i


class DuplicateKey(ValueError):
    """One JSON object names the same key twice. Readers keep the LAST value,
    so no single span is "the" value: writing the first would change a value
    nothing reads, and a release would tag a version the file does not
    declare."""


# Prefix of a detect() note that makes backfill and release refuse.
BLOCKING = "BLOCKING: "


def _json_member(s: str, obj: int, key: str) -> tuple[int, int] | None:
    """(start, end) of `key`'s value in the object opening at s[obj] == '{'.

    Only the object's own keys are considered; nested objects are skipped
    whole, so a key of the same name deeper down never matches. The whole
    object is read: a key that appears twice raises DuplicateKey.
    """
    found: tuple[int, int] | None = None
    i = _json_ws(s, obj + 1)
    while s[i] != "}":
        if s[i] != '"':
            raise ValueError("expected a key")
        end = _json_string(s, i)
        name = json.loads(s[i:end])
        i = _json_ws(s, end)
        if s[i] != ":":
            raise ValueError("expected ':'")
        start = _json_ws(s, i + 1)
        stop = _json_value(s, start)
        if name == key:
            if found is not None:
                raise DuplicateKey(key)
            found = (start, stop)
        i = _json_ws(s, stop)
        if s[i] == ",":
            i = _json_ws(s, i + 1)
    return found


def _owned_span(text: str, kind: str) -> tuple[int, int] | None:
    """_version_span without the safety net: malformed JSON raises ValueError
    or IndexError, a repeated key on the path raises DuplicateKey."""
    obj = _json_ws(text, 1 if text.startswith("﻿") else 0)
    if text[obj] != "{":
        return None
    if kind == "marketplace":
        plugins = _json_member(text, obj, "plugins")
        if plugins is None or text[plugins[0]] != "[":
            return None
        obj = _json_ws(text, plugins[0] + 1)
        if text[obj] != "{":
            return None
    span = _json_member(text, obj, "version")
    if span is None or text[span[0]] != '"':
        return None
    start, end = span[0] + 1, span[1] - 1
    if not re.fullmatch(r"\d+\.\d+\.\d+", text[start:end]):
        return None
    return start, end


def _version_span(text: str, kind: str) -> tuple[int, int] | None:
    """Span of the X.Y.Z digits of the one version key a SPAN_KINDS file owns.
    None when there is no such single key, a repeated one included."""
    try:
        return _owned_span(text, kind)
    except (ValueError, IndexError):
        return None


def _duplicate_key(text: str, kind: str) -> str | None:
    """The key a SPAN_KINDS file repeats on the way to its version, if any."""
    try:
        _owned_span(text, kind)
    except DuplicateKey as exc:
        return str(exc)
    except (ValueError, IndexError):
        return None
    return None


def _duplicate_note(rel: Path, key: str) -> str:
    return (f"{BLOCKING}{rel}: \"{key}\" appears twice in one JSON object. "
            "Readers use the last, so no version can be written safely. "
            "Remove the duplicate.")

# Some projects' own files name their canonical source; reading it beats
# guessing. Two phrasings occur in that repo alone, so match both:
#   "The actual version is managed in src/version.py"
#   'version = "0.2.0"  # See src/version.py for centralized version management'
POINTER_RE = re.compile(
    r"version\s+is\s+(?:managed|maintained|centraliz|centralis)\w*\s+in\s+"
    r"[`'\"]?(?P<managed>[\w./\\-]+\.\w+)"
    r"|see\s+[`'\"]?(?P<see>[\w./\\-]+\.\w+)[`'\"]?\s+for\s+(?:the\s+)?"
    r"(?:centraliz|centralis|canonical)\w*\s+version",
    re.I)


def _pointer_target(text: str) -> str | None:
    m = POINTER_RE.search(text)
    if not m:
        return None
    return m.group("managed") or m.group("see")

# Vendored and generated trees carry their own package.json/version files.
# a Next.js app tracked a generated Prisma client whose bundled package.json says
# "version": "6.19.0" — without this, Prisma's version enters the ledger as a
# a Next.js app release.
SKIP_DIRS = {".git", ".venv", ".venv_linux", "node_modules", "__pycache__",
             "dist", "build", ".next", "venv", "site-packages",
             "generated", "vendor", ".prisma", "out", "coverage", "target",
             "obj", "bin"}

MAX_DEPTH = 3   # project version files live near the root; deeper is vendored


@dataclass
class Location:
    path: Path          # relative to repo root
    kind: str
    value: str | None
    mirror_only: bool = False   # display string, never canonical (README)

    @property
    def label(self) -> str:
        return f"{self.path} ({self.kind})"


def _read(repo: Path, rel: Path) -> str | None:
    try:
        return (repo / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _inside(repo: Path, rel: Path) -> bool:
    """True when repo/rel, with every symlink followed, is still in the repo.

    A tracked symlink can point anywhere. Reading through one is harmless;
    WRITING a version through one changes a file outside the repository, so
    every version location is checked before it is trusted or written.
    """
    try:
        root = repo.resolve()
        target = (repo / rel).resolve()
    except (OSError, RuntimeError):
        return False
    return target == root or root in target.parents


def _write(path: Path, text: str) -> None:
    """Write text keeping the file's existing line endings.

    Path.write_text translates newlines to os.linesep, so on native Windows a
    bump would rewrite an LF file as CRLF from end to end.
    """
    newline = "\n"
    try:
        if b"\r\n" in path.read_bytes():
            newline = "\r\n"
    except OSError:
        pass
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def _extract(text: str, kind: str) -> str | None:
    if kind in SPAN_KINDS:
        span = _version_span(text, kind)
        return text[span[0]:span[1]] if span else None
    if kind == "csproj":
        live = _outside_comments(PATTERNS[kind], text)
        return live[0].group("v") if live else None
    m = PATTERNS[kind].search(text)
    return m.group("v") if m else None


# Text in an XML file that is not markup: a comment, or a CDATA section
# (literal characters, whatever they look like).
XML_DEAD_SPAN = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>", re.S)


def _outside_comments(pattern: re.Pattern[str], text: str) -> list[re.Match[str]]:
    """Matches of `pattern` in an XML file that are real markup.

    `<!-- <Version>1.0.0</Version> -->` is a note to a person, and
    `<![CDATA[<Version>1.0.0</Version>]]>` is literal text. Neither is a
    declaration: it must be neither read as the project's version nor
    rewritten by a release.
    """
    dead = [m.span() for m in XML_DEAD_SPAN.finditer(text)]
    return [m for m in pattern.finditer(text)
            if not any(a <= m.start() < b for a, b in dead)]


def _sub_outside_comments(pattern: re.Pattern[str], repl, text: str) -> str:
    """pattern.sub(repl, text) that leaves matches inside XML comments alone."""
    live = {m.start() for m in _outside_comments(pattern, text)}
    return pattern.sub(lambda m: repl(m) if m.start() in live else m.group(0),
                       text)


def _extract_all(text: str, kind: str) -> list[str]:
    """Every version a file declares. More than one only for csproj, where
    each PropertyGroup may carry its own <Version>."""
    if kind == "csproj":
        return [m.group("v") for m in _outside_comments(PATTERNS[kind], text)]
    value = _extract(text, kind)
    return [value] if value is not None else []


def _single_plugin(text: str) -> dict | None:
    """The one plugin entry of a marketplace file, or None when the file is
    unparseable or lists zero or several plugins (no single repo version)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, list) or len(plugins) != 1 \
            or not isinstance(plugins[0], dict):
        return None
    return plugins[0]


def _manifest_version(text: str, kind: str) -> str | None:
    """The version a SPAN_KINDS file declares, by the rules detect() applies."""
    if kind == "marketplace" and _single_plugin(text) is None:
        return None
    return _extract(text, kind)


def _plugin_manifest_for(repo: Path, plugin: dict) -> Path | None:
    """The plugin's own manifest, when its source is a folder in this repo.

    A single-plugin marketplace whose source is "./" keeps a second copy of
    the version in .claude-plugin/plugin.json; bumping only the marketplace
    entry leaves the two disagreeing about what was released.
    """
    source = plugin.get("source")
    if not isinstance(source, str):
        return None     # npm / git / url source: the plugin lives elsewhere
    rel = Path(os.path.normpath((Path(source) / PLUGIN_MANIFEST).as_posix()))
    if rel.is_absolute() or ".." in rel.parts:
        return None
    # A `source` that is a symlink out of the repo passes both tests above
    # and is_file() follows it: the manifest it reaches is someone else's.
    if not _inside(repo, rel):
        return None
    return rel if (repo / rel).is_file() else None


MODULE_FILES = {"version.py", "constants.py", "__init__.py", "main.py", "setup.py"}


def _candidate_files(repo: Path) -> list[tuple[Path, str]]:
    """(relative path, kind) for every plausible version location.

    Walks with pruning rather than globbing `**/` — a bare glob descends into
    node_modules and .venv, which on the web repos is minutes of pointless IO.
    """
    out: list[tuple[Path, str]] = []
    for name, kind in (("pyproject.toml", "pyproject"),
                       ("package.json", "package_json"),
                       ("VERSION", "version_file"),
                       ("README.md", "readme"),
                       # dot-dir, so the pruned walk below never reaches it
                       (".claude-plugin/marketplace.json", "marketplace")):
        if (repo / name).exists():
            out.append((Path(name), kind))

    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        rel_root = Path(root).relative_to(repo)
        if len(rel_root.parts) >= MAX_DEPTH:
            dirs[:] = []
        for name in files:
            if name in MODULE_FILES:
                out.append((rel_root / name if rel_root.parts else Path(name),
                            "py_const"))
            elif name.endswith(".csproj"):
                out.append((rel_root / name if rel_root.parts else Path(name),
                            "csproj"))
    return out


def detect(repo: Path) -> tuple[Location | None, list[Location], list[str]]:
    """Return (canonical, mirrors, notes) per the §4 ladder."""
    notes: list[str] = []
    found: list[Location] = []
    candidates = _candidate_files(repo)

    for rel, kind in candidates:
        if not _inside(repo, rel):
            # A version file that is a link out of the repository: releasing
            # would rewrite someone else's file. Refuse, loudly.
            notes.append(f"{BLOCKING}{rel} is a link to a file outside the "
                         "repository; a release would write through it. "
                         "Replace the link with a real file.")
            continue
        text = _read(repo, rel)
        if text is None:
            continue
        manifest: Path | None = None
        if kind == "package_json":
            # `{}` is a stub, not a version location — do not fill it.
            try:
                if not json.loads(text):
                    notes.append(f"{rel}: empty stub, skipped")
                    continue
            except json.JSONDecodeError:
                notes.append(f"{rel}: unparseable, skipped")
                continue
        if kind == "marketplace":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                notes.append(f"{rel}: unparseable, skipped")
                continue
            plugins = data.get("plugins") if isinstance(data, dict) else None
            if not isinstance(plugins, list):
                notes.append(f"{rel}: no \"plugins\" list; skipped")
                continue
            if len(plugins) != 1:
                notes.append(f"{rel}: {len(plugins)} plugins — per-plugin "
                             "versions, no single repo version; skipped")
                continue
            repeated = _duplicate_key(text, kind)
            if repeated:
                notes.append(_duplicate_note(rel, repeated))
                continue
            declared = str(plugins[0].get("version") or "") \
                if isinstance(plugins[0], dict) else ""
            if parse_version(declared) is None or \
                    _extract(text, kind) != declared:
                notes.append(f"{rel}: plugin version missing or pattern "
                             "mismatch; skipped")
                continue
            metadata = data.get("metadata")
            if isinstance(metadata, dict) and metadata.get("version"):
                notes.append(f"{rel}: metadata.version is the catalog's own "
                             "series — left unmanaged")
            manifest = _plugin_manifest_for(repo, plugins[0])
        values = _extract_all(text, kind)
        if not values:
            continue
        found.append(Location(rel, kind, values[0],
                              mirror_only=(kind == "readme")))
        # One file, several declarations that disagree: each extra value is a
        # location of its own, so `check` flags it and `release` refuses,
        # exactly as for two files that disagree.
        extra = [v for v in dict.fromkeys(values[1:]) if v != values[0]]
        for v in extra:
            found.append(Location(rel, kind, v))
        if extra:
            notes.append(f"{rel}: declares {len(values)} versions that "
                         f"disagree ({', '.join(dict.fromkeys(values))})")
        if manifest is not None:
            # The plugin's own manifest mirrors the marketplace entry. A
            # manifest with no version key is fine: the entry is then the
            # only home.
            manifest_text = _read(repo, manifest) or ""
            repeated = _duplicate_key(manifest_text, "plugin_json")
            if repeated:
                notes.append(_duplicate_note(manifest, repeated))
            own = _extract(manifest_text, "plugin_json")
            if own is not None:
                found.append(Location(manifest, "plugin_json", own))

    # Ladder rung 1 — an explicit pointer comment wins outright.
    pointer: Path | None = None
    for rel, _ in candidates:
        text = _read(repo, rel)
        if not text:
            continue
        hit = _pointer_target(text)
        if hit:
            target = Path(hit)
            if (repo / target).exists():
                pointer = target
                notes.append(f"{rel} names {target} as the canonical source")
                break

    def rank(loc: Location) -> int:
        if pointer is not None and loc.path == pointer:
            return 0
        if loc.mirror_only:
            return 90
        return {"pyproject": 10, "package_json": 11, "marketplace": 12,
                "plugin_json": 13, "csproj": 14,
                "py_const": 20, "version_file": 30}.get(loc.kind, 50)

    real = [loc for loc in found if not loc.mirror_only]
    if not real:
        return None, [loc for loc in found if loc.mirror_only], notes

    ordered = sorted(found, key=rank)
    canonical = ordered[0]
    mirrors = [loc for loc in ordered[1:]]
    return canonical, mirrors, notes


def write_version(repo: Path, loc: Location, new: str) -> None:
    if not _inside(repo, loc.path):
        raise GitError(f"{loc.path} resolves to a file outside the "
                       "repository; refusing to write it")
    text = _read(repo, loc.path)
    if text is None:
        raise GitError(f"cannot read {loc.path}")
    if loc.kind in SPAN_KINDS:
        # Replace exactly the digits of the one key this file owns; nothing
        # else in the file moves, so key order and indentation survive.
        span = _version_span(text, loc.kind)
        if span is None:
            raise GitError(f"no version key in {loc.path}")
        _write(repo / loc.path, text[:span[0]] + new + text[span[1]:])
        return
    pattern = PATTERNS[loc.kind]
    if loc.kind == "csproj":
        # Every PropertyGroup's declaration moves together, or a release
        # would tag the new version while a later group still builds the old
        # one. Declarations inside XML comments are left exactly as written.
        if not _outside_comments(pattern, text):
            raise GitError(f"no version pattern in {loc.path}")
        updated = _sub_outside_comments(
            pattern, lambda m: m.group("pre") + new + m.group("post"), text)
        # Keep the 4-part assembly metadata in step with <Version>.
        for tag in ("AssemblyVersion", "FileVersion"):
            updated = _sub_outside_comments(
                re.compile(rf"(<{tag}>\s*)\d+\.\d+\.\d+(?:\.\d+)?(\s*</{tag}>)"),
                lambda m: f"{m.group(1)}{new}.0{m.group(2)}", updated)
        _write(repo / loc.path, updated)
        return
    if not pattern.search(text):
        raise GitError(f"no version pattern in {loc.path}")
    updated = pattern.sub(lambda m: m.group("pre") + new + m.group("post"),
                          text, count=1)
    _write(repo / loc.path, updated)


# --------------------------------------------------------------------------
# the ledger (§5) — union of git-derived and changelog-declared
# --------------------------------------------------------------------------

@dataclass
class Entry:
    version: str
    commit: str | None = None
    date: str | None = None
    sources: set[str] = field(default_factory=set)
    changelog_date: str | None = None


def _history_paths(repo: Path, canonical: Location | None) -> list[Path]:
    """Paths that ever plausibly held a version, including relocated homes.

    Some projects keep __version__ in a main module before it moves to a constants file;
    without walking the old home its 0.3.0-0.6.0 releases are unrecoverable.
    """
    names = {"VERSION", "version.py", "constants.py", "__init__.py",
             "main.py", "pyproject.toml", "package.json", "setup.py"}
    seen = git(repo, "log", "--all", "--format=", "--name-only")
    paths: list[Path] = []
    for line in dict.fromkeys(seen.splitlines()):
        line = line.strip()
        if not line:
            continue
        p = Path(line)
        # marketplace.json is deliberately not in `names`: its history counts
        # only while it is the canonical location (appended below). A
        # multi-plugin marketplace has no single repo version, and a commit
        # from when it listed one plugin must not seed one.
        if ((p.name in names or p.suffix == ".csproj")
                and not any(d in p.parts for d in SKIP_DIRS)
                and len(p.parts) <= MAX_DEPTH):
            paths.append(p)
    if canonical and canonical.path not in paths:
        paths.append(canonical.path)
    return paths[:30]


def _kind_for(path: Path) -> str:
    if path.name == "pyproject.toml":
        return "pyproject"
    if path.name == "package.json":
        return "package_json"
    if path.name == "VERSION":
        return "version_file"
    if path.suffix == ".csproj":
        return "csproj"
    if path.as_posix() == MARKETPLACE_PATH:
        return "marketplace"
    if path.as_posix().endswith(PLUGIN_MANIFEST):
        return "plugin_json"
    return "py_const"


def _file_at(repo: Path, sha: str, path: Path) -> str | None:
    """A file's content at a commit. Bytes are decoded here rather than by
    subprocess, whose locale codec can reject UTF-8 on Windows."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{sha}:{path.as_posix()}"],
        capture_output=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def git_ledger(repo: Path, canonical: Location | None) -> list[Entry]:
    """Chronological version changes derived from git history.

    One `git log -p` pass over every candidate path at once. Walking each path
    separately with --follow took over two minutes on a Python service; --follow's
    rename detection is redundant anyway, since relocated homes are probed
    explicitly by _history_paths.
    """
    paths = _history_paths(repo, canonical)
    if not paths:
        return []

    hits: dict[str, Entry] = {}
    order: list[tuple[int, str]] = []

    log = git(repo, "log", "--reverse", "--format=%x00%H|%ct|%cs",
              "-p", "--unified=0", "--", *[str(p) for p in paths], check=False)

    for chunk in log.split(NUL):
        if not chunk.strip():
            continue
        header, _, body = chunk.partition("\n")
        try:
            sha, ts, when = header.split("|")
        except ValueError:
            continue
        current_kind: str | None = None

        def record(value: str | None) -> None:
            if value is not None and value not in hits:
                hits[value] = Entry(value, sha[:8], when, {"git"})
                order.append((int(ts), value))

        for line in body.splitlines():
            if line.startswith("+++ b/"):
                path = Path(line[6:].strip())
                current_kind = _kind_for(path)
                if current_kind in SPAN_KINDS:
                    # One added line cannot say WHICH "version" key it is
                    # (metadata's, a source pin's, the plugin entry's), so
                    # read the whole file as it stood at this commit.
                    text = _file_at(repo, sha, path)
                    record(_manifest_version(text, current_kind)
                           if text else None)
                    current_kind = None
                elif current_kind == "csproj":
                    # detect() accepts <Version> split across lines; a diff
                    # line never holds a split tag whole. Read the file as it
                    # stood, and count it only when its declarations agree.
                    declared = list(dict.fromkeys(_extract_all(
                        _file_at(repo, sha, path) or "", "csproj")))
                    record(declared[0] if len(declared) == 1 else None)
                    current_kind = None
                continue
            if current_kind is None or not line.startswith("+"):
                continue
            record(_extract(line[1:], current_kind))

    order.sort()
    return [hits[v] for _ts, v in order]


CHANGELOG_HEADING = re.compile(
    r"^##\s*\[(?P<v>\d+\.\d+\.\d+)\]\s*(?:-\s*(?P<d>\d{4}-\d{2}-\d{2}))?", re.M)


def changelog_path(repo: Path) -> Path:
    for name in ("CHANGELOG.md", "Docs/CHANGELOG.md", "docs/CHANGELOG.md"):
        if (repo / name).exists():
            return Path(name)
    return Path("CHANGELOG.md")


def changelog_ledger(repo: Path) -> dict[str, str | None]:
    text = _read(repo, changelog_path(repo)) or ""
    return {m.group("v"): m.group("d") for m in CHANGELOG_HEADING.finditer(text)}


@dataclass
class Reconciliation:
    entries: dict[str, Entry]
    both_ok: list[str]
    date_mismatch: list[str]
    git_only: list[str]      # missing from the changelog — gaps to fill
    changelog_only: list[str]  # no locatable bump commit — reported, never tagged


def reconcile(repo: Path, canonical: Location | None) -> Reconciliation:
    entries: dict[str, Entry] = {}
    for e in git_ledger(repo, canonical):
        entries[e.version] = e
    for v, d in changelog_ledger(repo).items():
        e = entries.setdefault(v, Entry(v))
        e.sources.add("changelog")
        e.changelog_date = d

    both_ok, mismatch, git_only, cl_only = [], [], [], []
    for v, e in entries.items():
        has_git = "git" in e.sources
        has_cl = "changelog" in e.sources
        if has_git and has_cl:
            (both_ok if e.date == e.changelog_date else mismatch).append(v)
        elif has_git:
            git_only.append(v)
        else:
            cl_only.append(v)
    key = version_key
    return Reconciliation(entries, sorted(both_ok, key=key),
                          sorted(mismatch, key=key), sorted(git_only, key=key),
                          sorted(cl_only, key=key))


# --------------------------------------------------------------------------
# synthesized ledgers for placeholder repos (§5.1, §5.2)
# --------------------------------------------------------------------------

PR_REF = re.compile(r"\(#\d+\)\s*$")
FEAT = re.compile(r"^feat(\(|!|:)")
BREAKING = re.compile(r"^[a-z]+(\([^)]*\))?!:|^BREAKING CHANGE", re.M)
BOUNDARY_GUARD = 60   # §5.2 — above this, group boundaries by calendar month


@dataclass
class Boundary:
    commit: str
    date: str
    subjects: list[str]


def _commits(repo: Path) -> list[tuple[str, str, str]]:
    out = git(repo, "log", "--reverse", "--format=%H|%cs|%s")
    rows = []
    for line in out.splitlines():
        sha, _, rest = line.partition("|")
        when, _, subject = rest.partition("|")
        if sha:
            rows.append((sha, when, subject))
    return rows


def boundary_signal(repo: Path) -> tuple[str, list[Boundary]]:
    """Pick the first signal that yields boundaries (§5.2). Never per commit."""
    rows = _commits(repo)
    if not rows:
        return "none", []

    def collect(is_boundary) -> list[Boundary]:
        """Close a version at each boundary commit; trailing commits join the last."""
        result: list[Boundary] = []
        pending: list[str] = []
        for sha, when, subject in rows:
            pending.append(subject)
            if is_boundary(sha, subject):
                result.append(Boundary(sha[:8], when, pending))
                pending = []
        if pending and result:
            result[-1].subjects.extend(pending)
        return result

    merges = {sha[:8] for sha in git(repo, "rev-list", "--merges", "HEAD").split()}
    signals = (
        ("PR merge references", lambda sha, s: bool(PR_REF.search(s))),
        ("merge commits", lambda sha, s: sha[:8] in merges),
        ("feat: commits", lambda sha, s: bool(FEAT.match(s))),
    )
    for name, is_boundary in signals:
        bounds = collect(is_boundary)
        if len(bounds) > 1:
            return name, bounds

    last_sha, last_when, _ = rows[-1]
    return ("single release at head",
            [Boundary(last_sha[:8], last_when, [s for _, _, s in rows])])


def group_by_month(bounds: list[Boundary]) -> list[Boundary]:
    """Collapse boundaries to one per calendar month (guard for busy repos)."""
    buckets: dict[str, Boundary] = {}
    for b in bounds:
        key = b.date[:7]
        if key in buckets:
            buckets[key].subjects.extend(b.subjects)
            buckets[key].commit = b.commit
            buckets[key].date = b.date
        else:
            buckets[key] = Boundary(b.commit, b.date, list(b.subjects))
    return [buckets[k] for k in sorted(buckets)]


def level_for(subjects: list[str]) -> str:
    blob = "\n".join(subjects)
    if BREAKING.search(blob):
        return "major"
    if any(FEAT.match(s) for s in subjects):
        return "minor"
    return "patch"


def synthesize(repo: Path, floor: tuple[int, int, int] = (0, 0, 0),
               ) -> tuple[list[Entry], str]:
    """Build a version series for a repo whose version was never bumped.

    `floor` is the highest version already known from any source, so a
    synthesized series can never regress below something already shipped.
    """
    signal, bounds = boundary_signal(repo)
    note = f"{signal}: {len(bounds)} boundaries"
    if len(bounds) > BOUNDARY_GUARD:
        bounds = group_by_month(bounds)
        note += f" -> grouped by month into {len(bounds)}"

    entries: list[Entry] = []
    current = floor
    for b in bounds:
        current = bump(current, level_for(b.subjects))
        entries.append(Entry(fmt_version(current), b.commit, b.date, {"git"}))
    return entries, note


def is_placeholder(git_entries: list[Entry], changelog_count: int = 0) -> bool:
    """A version set once and never moved is a default, not a record (§5.1).

    A changelog declaring several versions IS a record even when the version
    file never moved — a small service shipped 0.1.0 and 0.2.0 while app/__init__.py
    sat at 0.1.0. Treating that as a placeholder would synthesize a series
    below what already shipped.
    """
    return len(git_entries) <= 1 and changelog_count <= 1


def known_floor(canonical: Location | None, entries: dict[str, Entry]
                ) -> tuple[int, int, int]:
    """Highest version known from any source, so nothing ever regresses."""
    candidates = [parse_version(v) for v in entries]
    if canonical and canonical.value:
        candidates.append(parse_version(canonical.value))
    real = [c for c in candidates if c is not None]
    return max(real) if real else (0, 0, 0)


# --------------------------------------------------------------------------
# changelog writing
# --------------------------------------------------------------------------

KAC_HEADER = """# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
"""

TYPE_SECTIONS = [
    ("Added", re.compile(r"^feat(\(|!|:)")),
    ("Fixed", re.compile(r"^fix(\(|!|:)")),
    ("Changed", re.compile(r"^(refactor|perf|docs|chore|build|ci|style|test)(\(|!|:)")),
]


def draft_entries(subjects: list[str]) -> str:
    """Group commit subjects into Keep a Changelog sections."""
    buckets: dict[str, list[str]] = {name: [] for name, _ in TYPE_SECTIONS}
    other: list[str] = []
    for s in subjects:
        for name, rx in TYPE_SECTIONS:
            if rx.match(s):
                buckets[name].append(s)
                break
        else:
            other.append(s)
    if other:
        buckets["Changed"].extend(other)

    parts: list[str] = []
    for name, _ in TYPE_SECTIONS:
        items = buckets[name]
        if not items:
            continue
        parts.append(f"### {name}")
        parts.extend(f"- {s}" for s in items)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n" if parts else "_No recorded changes._\n"


def insert_section(repo: Path, version: str, when: str, body: str) -> None:
    rel = changelog_path(repo)
    text = _read(repo, rel)
    if text is None:
        text = KAC_HEADER
    section = f"\n## [{version}] - {when}\n\n{body.rstrip()}\n"

    if "## [Unreleased]" in text:
        head, _, tail = text.partition("## [Unreleased]")
        # keep the Unreleased marker, insert immediately beneath it
        rest = tail.split("\n", 1)[1] if "\n" in tail else ""
        updated = f"{head}## [Unreleased]\n{section}{rest}"
    else:
        m = CHANGELOG_HEADING.search(text)
        if m:
            updated = text[:m.start()] + section.lstrip("\n") + "\n" + text[m.start():]
        else:
            updated = text.rstrip() + "\n" + section
    _write(repo / rel, updated)


def fix_changelog_date(repo: Path, version: str, when: str) -> bool:
    rel = changelog_path(repo)
    text = _read(repo, rel)
    if text is None:
        return False
    pattern = re.compile(rf"^(##\s*\[{re.escape(version)}\])\s*-\s*\d{{4}}-\d{{2}}-\d{{2}}",
                         re.M)
    if not pattern.search(text):
        return False
    _write(repo / rel, pattern.sub(rf"\1 - {when}", text))
    return True


# --------------------------------------------------------------------------
# verbs
# --------------------------------------------------------------------------

def _header(repo: Path) -> None:
    print(f"repo: {repo}")


def cmd_check(repo: Path, **_: object) -> int:
    _header(repo)
    canonical, mirrors, notes = detect(repo)
    for n in notes:
        print(f"  note: {n}")

    if canonical is None:
        print("  version location: NONE FOUND — backfill would create one")
    else:
        print(f"  canonical: {canonical.label} = {canonical.value}")
    for m in mirrors:
        flag = "" if m.value == (canonical.value if canonical else None) else "  <-- DISAGREES"
        kind = "display" if m.mirror_only else "mirror"
        print(f"  {kind}: {m.label} = {m.value}{flag}")

    rec = reconcile(repo, canonical)
    git_entries = [e for e in rec.entries.values() if "git" in e.sources]
    cl = changelog_ledger(repo)
    print(f"\n  ledger: {len(rec.entries)} versions "
          f"({len(git_entries)} from git, {len(cl)} from changelog)")

    if is_placeholder(git_entries, len(cl)):
        entries, note = synthesize(repo, known_floor(canonical, rec.entries))
        print("  classification: PLACEHOLDER — version never moved in history")
        print(f"    synthesized series: {len(entries)} versions via {note}")
        if entries:
            print(f"    would run {entries[0].version} .. {entries[-1].version}")
    else:
        print(f"  classification: real record — {len(git_entries)} bumps in history")

    # A shipped changelog ahead of the code is a small service's exact failure.
    if canonical and canonical.value and cl:
        highest = max(cl, key=version_key)
        if version_key(highest) > version_key(canonical.value):
            print(f"\n  VERSION BEHIND CHANGELOG: {canonical.label} = "
                  f"{canonical.value}, but changelog shipped {highest}")

    if rec.git_only:
        print(f"\n  MISSING FROM CHANGELOG ({len(rec.git_only)}): "
              + ", ".join(f"{v} ({rec.entries[v].date})" for v in rec.git_only))
    if rec.date_mismatch:
        print(f"  DATE MISMATCH ({len(rec.date_mismatch)}):")
        for v in rec.date_mismatch:
            e = rec.entries[v]
            print(f"    {v}: changelog {e.changelog_date} | git {e.date}")
    if rec.changelog_only:
        print(f"  NO LOCATABLE BUMP COMMIT ({len(rec.changelog_only)}): "
              + ", ".join(rec.changelog_only) + "  [reported, never tagged]")

    tags = existing_tags(repo)
    taggable = [v for v, e in rec.entries.items() if e.commit and f"v{v}" not in tags]
    print(f"\n  tags: {len(tags)} present, {len(taggable)} reconstructable")

    if tags:
        last = sorted((t for t in tags if parse_version(t.lstrip("v"))),
                      key=lambda t: version_key(t.lstrip("v")))
        if last:
            since = git(repo, "rev-list", "--count", f"{last[-1]}..HEAD",
                        check=False).strip()
            print(f"  commits since {last[-1]}: {since or '0'}")
    else:
        print("  commits since last release: unknown (no tags — run backfill)")
    return 0


def cmd_backfill(repo: Path, apply: bool = False, fix_dates: bool = False,
                 **_: object) -> int:
    _header(repo)
    canonical, mirrors, notes = detect(repo)
    for n in notes:
        print(f"  note: {n}")
    if apply and any(n.startswith(BLOCKING) for n in notes):
        # Otherwise a skipped manifest reads as "no version location" and
        # backfill would create a second home for the version beside it.
        print("  REFUSED: a version file cannot be written safely; fix the "
              "BLOCKING note above, then re-run.")
        return 1

    rec = reconcile(repo, canonical)
    git_entries =[e for e in rec.entries.values() if "git" in e.sources]
    plan: list[str] = []

    # Step 0 — placeholder repos get a synthesized ledger (§6)
    if is_placeholder(git_entries, len(changelog_ledger(repo))):
        entries, note = synthesize(repo, known_floor(canonical, rec.entries))
        old = canonical.value if canonical else "(none)"
        head = entries[-1].version if entries else "0.1.0"
        plan.append(f"classify PLACEHOLDER; synthesize {len(entries)} versions via {note}")
        plan.append(f"set version {old} -> {head}"
                    + ("" if canonical else " (creating a location)"))
        for e in entries:
            rec.entries.setdefault(e.version, e)
            if "changelog" not in rec.entries[e.version].sources:
                if e.version not in rec.git_only:
                    rec.git_only.append(e.version)
        rec.git_only.sort(key=version_key)
        if canonical is None:
            canonical = Location(Path("VERSION"), "version_file", None)
            if not (repo / "VERSION").exists() and apply:
                _write(repo / "VERSION", head + "\n")
        elif apply:
            write_version(repo, canonical, head)
            for m in mirrors:
                write_version(repo, m, head)

    tags = existing_tags(repo)
    to_tag = [(v, e) for v, e in sorted(rec.entries.items(), key=lambda kv: version_key(kv[0]))
              if e.commit and f"v{v}" not in tags]
    plan.append(f"create {len(to_tag)} annotated tags")
    for v in rec.git_only:
        plan.append(f"insert changelog section [{v}] - {rec.entries[v].date}")
    if fix_dates:
        for v in rec.date_mismatch:
            e = rec.entries[v]
            plan.append(f"correct changelog date [{v}] {e.changelog_date} -> {e.date}")
    if rec.changelog_only:
        plan.append(f"report {len(rec.changelog_only)} versions with no bump commit "
                    "(left untagged, never guessed)")

    print("\nPLAN" + ("" if apply else " (dry run — pass --apply to write)"))
    for step in plan:
        print(f"  - {step}")

    if not apply:
        return 0

    # 1. tags first, so a failure mid-run leaves a re-runnable state
    for v, e in to_tag:
        assert e.commit is not None  # to_tag filters on e.commit
        git(repo, "tag", "-a", f"v{v}", e.commit, "-m", f"Version {v}")
    # 2. changelog gaps
    for v in rec.git_only:
        e = rec.entries[v]
        subjects = _subjects_for(repo, rec, v)
        insert_section(repo, v, e.date or str(date.today()), draft_entries(subjects))
    # 3. dates, only on explicit request
    if fix_dates:
        for v in rec.date_mismatch:
            fix_changelog_date(repo, v, rec.entries[v].date or "")
    print(f"\napplied: {len(to_tag)} tags, {len(rec.git_only)} changelog sections")
    return 0


def _subjects_for(repo: Path, rec: Reconciliation, version: str) -> list[str]:
    """Commit subjects in the range ending at `version`'s bump commit."""
    ordered = sorted((v for v, e in rec.entries.items() if e.commit), key=version_key)
    try:
        idx = ordered.index(version)
    except ValueError:
        return []
    head = rec.entries[version].commit
    if head is None:
        return []
    if idx == 0:
        rng = head
    else:
        prev = rec.entries[ordered[idx - 1]].commit
        rng = f"{prev}..{head}" if prev else head
    out = git(repo, "log", "--format=%s", rng, check=False)
    return [s for s in out.splitlines() if s.strip()]


def cmd_release(repo: Path, level: str, apply: bool = False,
                notes: str | None = None, no_tag: bool = False,
                **_: object) -> int:
    _header(repo)
    if is_dirty(repo):
        print("  REFUSED: working tree is dirty — commit or stash first")
        return 1

    canonical, mirrors, det_notes = detect(repo)
    for n in det_notes:
        print(f"  note: {n}")
    if any(n.startswith(BLOCKING) for n in det_notes):
        print("  REFUSED: a version file cannot be written safely; fix the "
              "BLOCKING note above, then re-run.")
        return 1
    if canonical is None:
        print("  REFUSED: no version location — run backfill first")
        return 1

    disagree = [m for m in mirrors if m.value != canonical.value]
    if disagree:
        print(f"  REFUSED: version locations disagree — canonical "
              f"{canonical.label} = {canonical.value}, but:")
        for m in disagree:
            print(f"    {m.label} = {m.value}")
        print("  Resolve by hand, then re-run.")
        return 1

    current = parse_version(canonical.value or "")
    if current is None:
        print(f"  REFUSED: unparseable version {canonical.value!r}")
        return 1
    new = fmt_version(bump(current, level))
    tag = f"v{new}"
    if tag in existing_tags(repo):
        print(f"  REFUSED: tag {tag} already exists")
        return 1

    tags = existing_tags(repo)
    versioned = sorted((t for t in tags if parse_version(t.lstrip("v"))),
                       key=lambda t: version_key(t.lstrip("v")))
    rng = f"{versioned[-1]}..HEAD" if versioned else "HEAD"
    subjects = [s for s in git(repo, "log", "--format=%s", rng, check=False).splitlines()
                if s.strip()]

    suggested = level_for(subjects)
    print(f"  {canonical.value} -> {new}  ({level}"
          + (f"; commits suggest {suggested}" if suggested != level else "") + ")")
    print(f"  {len(subjects)} commits in {rng}")

    body = Path(notes).read_text(encoding="utf-8") if notes else draft_entries(subjects)
    print("\nCHANGELOG DRAFT" + ("" if notes else " (curate with --notes FILE)"))
    print("\n".join("  " + ln for ln in body.rstrip().splitlines()))

    targets = [canonical] + mirrors
    print("\nPLAN" + ("" if apply else " (dry run — pass --apply to write)"))
    for t in targets:
        print(f"  - set {t.label} = {new}")
    print(f"  - insert changelog [{new}] - {date.today()}")
    print("  - commit" + (" (tag deferred: the lander tags the merge commit)"
                          if no_tag else f" and tag {tag}"))

    if not apply:
        return 0

    for t in targets:
        write_version(repo, t, new)
    insert_section(repo, new, str(date.today()), body)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", f"chore(release): {tag}")
    if not no_tag:
        git(repo, "tag", "-a", tag, "-m", f"Version {new}")
    print(f"\nreleased {tag}" + (" (untagged)" if no_tag else ""))
    return 0


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="version_tool.py", description=__doc__)
    ap.add_argument("--repo", default=".", help="repository path (default: cwd)")
    sub = ap.add_subparsers(dest="verb", required=True)

    sub.add_parser("check", help="report drift; never writes")

    b = sub.add_parser("backfill", help="one-time history repair")
    b.add_argument("--apply", action="store_true")
    b.add_argument("--fix-dates", action="store_true",
                   help="also correct changelog dates that disagree with git")

    r = sub.add_parser("release", help="bump, changelog, tag, commit")
    r.add_argument("level", choices=["major", "minor", "patch"])
    r.add_argument("--apply", action="store_true")
    r.add_argument("--notes", help="file holding the curated changelog body")
    r.add_argument("--no-tag", action="store_true",
                   help="commit the bump but leave tagging to the lander, "
                        "which tags the merge commit once the PR has merged")

    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()
    if not is_repo(repo):
        print(f"not a git repository: {repo}", file=sys.stderr)
        return 2

    verbs = {"check": cmd_check, "backfill": cmd_backfill, "release": cmd_release}
    kwargs = {k: v for k, v in vars(args).items()
              if k not in {"verb", "repo", "fix_dates"}}
    if args.verb == "backfill":
        kwargs["fix_dates"] = args.fix_dates
    try:
        return verbs[args.verb](repo, **kwargs)
    except GitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
