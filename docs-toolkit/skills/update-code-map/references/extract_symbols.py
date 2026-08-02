#!/usr/bin/env python3
"""Deterministic symbol inventory for CodeMap generation.

Emits JSON: {file: {"lines": N, "symbols": [{"kind", "name", "line",
"end_line", "parent", "signature"}]}}. Line numbers come from the AST
(Python) or regex scanning (JS/TS/C#/XAML) — never from an LLM.

Usage:
    python3 extract_symbols.py --root . --out inventory.json \
        [--exclude PAT ...] [--only-changed file1 file2 ...]
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import sys

DEFAULT_EXCLUDES = [
    ".git", ".venv*", "venv", "node_modules", "__pycache__", ".repo_cache",
    "bin", "obj", "dist", "build", ".next", ".idea", ".pytest_cache",
    ".mypy_cache", "coverage", "*.egg-info", ".claude", ".remember",
]

SOURCE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".cs", ".xaml"}


def sig_from_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        args = node.args
        parts = [a.arg for a in args.posonlyargs + args.args]
        if args.vararg:
            parts.append("*" + args.vararg.arg)
        parts += [a.arg for a in args.kwonlyargs]
        if args.kwarg:
            parts.append("**" + args.kwarg.arg)
        return "(" + ", ".join(parts) + ")"
    except Exception:
        return "(...)"


def extract_python(source: str) -> list[dict]:
    symbols: list[dict] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [{"kind": "error", "name": f"SyntaxError: {exc}", "line": exc.lineno or 0}]

    def visit(node: ast.AST, parent: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                symbols.append({
                    "kind": "class", "name": child.name, "line": child.lineno,
                    "end_line": getattr(child, "end_lineno", child.lineno),
                    "parent": parent, "signature": "",
                })
                visit(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                deco = {getattr(d, "id", getattr(getattr(d, "func", None), "id", None) or getattr(d, "attr", None))
                        for d in child.decorator_list}
                kind = "async def" if isinstance(child, ast.AsyncFunctionDef) else "def"
                if "property" in deco:
                    kind = "property"
                elif "staticmethod" in deco:
                    kind = "staticmethod"
                elif "classmethod" in deco:
                    kind = "classmethod"
                symbols.append({
                    "kind": kind if parent else f"{kind} (module)", "name": child.name,
                    "line": child.lineno,
                    "end_line": getattr(child, "end_lineno", child.lineno),
                    "parent": parent, "signature": sig_from_args(child),
                })
                visit(child, parent)  # nested defs keep outer parent context
            elif isinstance(child, (ast.Assign, ast.AnnAssign)) and parent is None:
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        symbols.append({
                            "kind": "constant", "name": target.id, "line": child.lineno,
                            "end_line": getattr(child, "end_lineno", child.lineno),
                            "parent": None, "signature": "",
                        })
            else:
                visit(child, parent)

    visit(tree, None)
    return symbols


REGEX_PATTERNS = {
    # ext -> [(kind, compiled regex with 'name' group)]
    ".js": [
        ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+(?P<name>\w+)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(?P<name>\w+)")),
        ("const fn", re.compile(r"^\s*(?:export\s+)?const\s+(?P<name>\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>")),
    ],
    ".ts": None,  # filled below (same as .js plus interface/type/enum)
    ".cs": [
        ("namespace", re.compile(r"^\s*namespace\s+(?P<name>[\w.]+)")),
        ("class", re.compile(r"^\s*(?:public|internal|private|protected|sealed|static|abstract|partial|\s)*\bclass\s+(?P<name>\w+)")),
        ("interface", re.compile(r"^\s*(?:public|internal|\s)*\binterface\s+(?P<name>\w+)")),
        ("enum", re.compile(r"^\s*(?:public|internal|\s)*\benum\s+(?P<name>\w+)")),
        ("record", re.compile(r"^\s*(?:public|internal|\s)*\brecord\s+(?P<name>\w+)")),
        ("method", re.compile(r"^\s{4,}(?:public|internal|private|protected)[\w<>,\s\[\]?]*\s(?P<name>\w+)\s*\([^;]*$")),
    ],
    ".xaml": [
        ("element", re.compile(r"x:Name=\"(?P<name>\w+)\"")),
        ("resource", re.compile(r"x:Key=\"(?P<name>\w+)\"")),
    ],
}
_ts_extra = [
    ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+(?P<name>\w+)")),
    ("type", re.compile(r"^\s*(?:export\s+)?type\s+(?P<name>\w+)\s*=")),
    ("enum", re.compile(r"^\s*(?:export\s+)?(?:const\s+)?enum\s+(?P<name>\w+)")),
]
REGEX_PATTERNS[".ts"] = REGEX_PATTERNS[".js"] + _ts_extra
REGEX_PATTERNS[".tsx"] = REGEX_PATTERNS[".ts"]
REGEX_PATTERNS[".jsx"] = REGEX_PATTERNS[".js"]


def extract_regex(ext: str, source: str) -> list[dict]:
    patterns = REGEX_PATTERNS.get(ext) or []
    symbols = []
    for lineno, line in enumerate(source.splitlines(), 1):
        for kind, rx in patterns:
            m = rx.search(line)
            if m:
                symbols.append({
                    "kind": kind, "name": m.group("name"), "line": lineno,
                    "end_line": lineno, "parent": None, "signature": "",
                })
                break
    return symbols


def excluded(rel: str, patterns: list[str]) -> bool:
    parts = rel.split(os.sep)
    return any(fnmatch.fnmatch(part, pat) for part in parts for pat in patterns)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="inventory.json")
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--only-changed", nargs="*", default=None,
                    help="Limit to these paths (relative to root)")
    args = ap.parse_args()

    patterns = DEFAULT_EXCLUDES + args.exclude
    inventory: dict[str, dict] = {}
    root = os.path.abspath(args.root)

    if args.only_changed is not None:
        candidates = [p for p in args.only_changed
                      if os.path.splitext(p)[1] in SOURCE_EXTS]
    else:
        candidates = []
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root)
            dirnames[:] = [d for d in dirnames
                           if not excluded(os.path.join(rel_dir, d) if rel_dir != "." else d, patterns)]
            for fn in filenames:
                if os.path.splitext(fn)[1] in SOURCE_EXTS:
                    rel = os.path.normpath(os.path.join(rel_dir, fn)) if rel_dir != "." else fn
                    if not excluded(rel, patterns):
                        candidates.append(rel)

    for rel in sorted(candidates):
        full = os.path.join(root, rel)
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except OSError as exc:
            print(f"skip {rel}: {exc}", file=sys.stderr)
            continue
        ext = os.path.splitext(rel)[1]
        symbols = extract_python(source) if ext == ".py" else extract_regex(ext, source)
        inventory[rel.replace(os.sep, "/")] = {
            "lines": len(source.splitlines()),  # matches wc -l for newline-terminated files
            "symbols": symbols,
        }

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(inventory, fh, indent=1)

    n_sym = sum(len(v["symbols"]) for v in inventory.values())
    print(f"{len(inventory)} files, {n_sym} symbols -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
