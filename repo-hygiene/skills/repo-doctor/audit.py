#!/usr/bin/env python3
"""Deterministic health checks for a repo's agent-facing documentation layer.

Measures what can be measured — file topology, always-loaded token cost, CodeMap
age and line-number accuracy, pointer integrity, changelog currency — and emits
findings with a recommended remediation order. Never edits anything.

    python3 audit.py --repo /path/to/repo [--json] [--sample N]

Exit code 0 = no findings, 1 = findings present, 2 = bad usage.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime, timezone

CODE_EXT = ('py|ts|tsx|js|jsx|mjs|cjs|cs|go|rs|rb|java|kt|swift|php|scala|sh|vue|svelte')
PATHBLOCK_RE = re.compile(rf'\*\*Path\*\*:\s*`([^`]+\.(?:{CODE_EXT}))`')
TS_RE = re.compile(r'\**Last Updated:?\**\s*:?\s*(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}(?::\d{2})?))?')

# Instruction files that get loaded into an agent's context every session.
INSTRUCTION_FILES = [
    'AGENTS.md', 'CLAUDE.md', 'GEMINI.md',
    '.github/copilot-instructions.md', 'AGENT.md', '.cursorrules',
]
CODEMAP_CANDIDATES = ['Docs/CodeMap.md', 'docs/CodeMap.md', 'Docs/codemap.md',
                      'docs/codemap.md', 'CodeMap.md']
CHANGELOG_CANDIDATES = ['CHANGELOG.md', 'Changelog.md', 'docs/CHANGELOG.md',
                        'Docs/CHANGELOG.md', 'CHANGES.md']

# Always-loaded budget, in estimated tokens (bytes/4). Past the soft cap the
# file is paying rent on every single request in the repo.
SOFT_CAP = 2500
HARD_CAP = 5000


def rel(root, *parts):
    return os.path.join(root, *parts)


def read(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return None


def est_tokens(nbytes):
    return round(nbytes / 4)


def find_first(root, candidates):
    for c in candidates:
        p = rel(root, c)
        if os.path.isfile(p):
            return c, p
    return None, None


class Audit:
    def __init__(self, root, sample=40, seed=None):
        self.root = os.path.abspath(root)
        self.sample = sample
        self.rng = random.Random(seed)
        self.findings = []
        self.facts = {}

    def add(self, fid, severity, title, detail, remedy=None):
        self.findings.append({
            'id': fid, 'severity': severity, 'title': title,
            'detail': detail, 'remedy': remedy,
        })

    # ---------------- 1. instruction-file topology ----------------
    def check_topology(self):
        present = {}
        for name in INSTRUCTION_FILES:
            p = rel(self.root, name)
            if os.path.isfile(p):
                body = read(p) or ''
                present[name] = {
                    'bytes': len(body.encode('utf-8')),
                    'tokens': est_tokens(len(body.encode('utf-8'))),
                    'first_line': (body.split('\n', 1)[0].strip() if body else ''),
                }
        self.facts['instruction_files'] = present

        if not present:
            self.add('topology.none', 'high',
                     'No agent instruction file at all',
                     'None of AGENTS.md / CLAUDE.md / GEMINI.md exists, so every '
                     'agent starts with zero repo context.',
                     'unify-agents-md')
            return

        has_agents = 'AGENTS.md' in present
        importers = {}
        for name in ('CLAUDE.md', 'GEMINI.md'):
            if name in present:
                fl = present[name]['first_line']
                importers[name] = bool(re.match(r'^@AGENTS\.md\s*$', fl))

        if not has_agents:
            others = ', '.join(sorted(present))
            self.add('topology.no-agents-md', 'high',
                     'AGENTS.md missing — non-Claude CLIs read nothing',
                     f'Repo carries {others} but no AGENTS.md. Codex, Copilot, '
                     'agy and Pi look for AGENTS.md, so they run without any of '
                     'these rules. Run unify-agents-md FIRST: rightsizing a '
                     'CLAUDE.md that is about to become an @import pointer is '
                     'wasted work.',
                     'unify-agents-md')
        else:
            for name, ok in importers.items():
                if not ok:
                    self.add(f'topology.{name.lower()}-not-pointer', 'medium',
                             f'{name} does not @import AGENTS.md on line 1',
                             f'AGENTS.md exists, but {name} starts with '
                             f'{present[name]["first_line"]!r}. Content is likely '
                             'duplicated across both, which drifts.',
                             'unify-agents-md')

    # ---------------- 2. always-loaded token cost ----------------
    def check_size(self):
        files = self.facts.get('instruction_files', {})
        # Cost of one turn = AGENTS.md + whichever tool file @imports it.
        loaded = {n: d for n, d in files.items()
                  if n in ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md')}
        total = sum(d['tokens'] for d in loaded.values())
        self.facts['always_loaded_tokens'] = total
        if not loaded:
            return
        biggest = max(loaded.items(), key=lambda kv: kv[1]['tokens'])
        if total > HARD_CAP:
            self.add('size.hard', 'high',
                     f'Always-loaded instructions ≈{total} tokens (cap {HARD_CAP})',
                     f'Largest is {biggest[0]} at ≈{biggest[1]["tokens"]} tokens. '
                     'This is paid on every request in the repo; over a long '
                     'session that is hundreds of thousands of tokens.',
                     'claude-md-optimizer')
        elif total > SOFT_CAP:
            self.add('size.soft', 'medium',
                     f'Always-loaded instructions ≈{total} tokens (target ≤{SOFT_CAP})',
                     f'Largest is {biggest[0]} at ≈{biggest[1]["tokens"]} tokens. '
                     'Likely carrying folder trees, tech-stack prose, or '
                     'playbooks the model can infer or load on demand.',
                     'claude-md-optimizer')

    # ---------------- 3. pointer integrity ----------------
    # Filename templates ("Review_YYYYMMDD.md", "<name>.md", "{slug}.md") name a
    # convention, not a file — resolving them is meaningless.
    PLACEHOLDER = re.compile(r'YYYY|MM-?DD|<[^>]+>|\{[^}]+\}|\*|N\.N\.N')

    def check_pointers(self):
        broken = []
        pat = re.compile(r'`([~./][\w./-]*\.(?:md|py|json|toml|ini|ya?ml))`')
        for name in self.facts.get('instruction_files', {}):
            body = read(rel(self.root, name)) or ''
            for m in pat.finditer(body):
                raw = m.group(1)
                if self.PLACEHOLDER.search(raw):
                    continue
                if raw.startswith('~'):
                    target = os.path.expanduser(raw)
                else:
                    target = os.path.normpath(rel(self.root, raw))
                if not os.path.exists(target):
                    broken.append({'file': name, 'pointer': raw})
        # also bare-word pointers like `Docs/CodeMap.md`
        bare = re.compile(r'`([A-Z][\w-]*(?:/[\w.-]+)+\.md)`')
        for name in self.facts.get('instruction_files', {}):
            body = read(rel(self.root, name)) or ''
            for m in bare.finditer(body):
                raw = m.group(1)
                if self.PLACEHOLDER.search(raw):
                    continue
                if not os.path.exists(rel(self.root, raw)):
                    broken.append({'file': name, 'pointer': raw})
        # de-dup
        seen, uniq = set(), []
        for b in broken:
            k = (b['file'], b['pointer'])
            if k not in seen:
                seen.add(k)
                uniq.append(b)
        self.facts['broken_pointers'] = uniq
        if uniq:
            listing = '; '.join(f'{b["file"]} → {b["pointer"]}' for b in uniq[:8])
            self.add('pointers.broken', 'medium',
                     f'{len(uniq)} instruction pointer(s) target missing files',
                     f'A pointer that does not resolve is a dead end the agent '
                     f'will follow anyway: {listing}',
                     None)

    # ---------------- 4. CodeMap freshness + accuracy ----------------
    def check_codemap(self):
        name, path = find_first(self.root, CODEMAP_CANDIDATES)
        self.facts['codemap'] = dict(path=name)
        if not path:
            # Only worth flagging if the repo actually has meaningful source.
            n = self._source_file_count()
            self.facts['source_files'] = n
            if n >= 25:
                self.add('codemap.missing', 'medium',
                         f'No CodeMap, but repo has ~{n} source files',
                         'Agents have no line-accurate navigation aid and will '
                         'grep from scratch every session.',
                         'update-code-map')
            return

        body = read(path) or ''
        m = TS_RE.search(body)
        age_days = None
        if m:
            stamp = m.group(1) + (' ' + m.group(2) if m.group(2) else '')
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(stamp, fmt)
                    age_days = (datetime.now() - dt).days
                    break
                except ValueError:
                    continue
        self.facts['codemap']['age_days'] = age_days
        if age_days is None:
            self.add('codemap.no-timestamp', 'low',
                     f'{name} has no parseable "Last Updated" line',
                     'Without a timestamp nobody can tell whether the line '
                     'numbers can be trusted.',
                     'update-code-map')
        elif age_days > 7:
            sev = 'high' if age_days > 60 else 'medium'
            self.add('codemap.stale', sev,
                     f'{name} is {age_days} days old',
                     'Line numbers drift fast; a map this old sends agents to '
                     'the wrong line, which is worse than no map.',
                     'update-code-map')

        acc = self._codemap_accuracy(body)
        self.facts['codemap'].update(acc)
        if acc['checked'] >= 8:
            pct = 100.0 * acc['ok'] / acc['checked']
            if pct < 90:
                sev = 'high' if pct < 70 else 'medium'
                self.add('codemap.inaccurate', sev,
                         f'{name} line numbers {pct:.0f}% accurate '
                         f'({acc["ok"]}/{acc["checked"]} sampled)',
                         'Sampled file:line claims do not resolve to the named '
                         'symbol in the source. Examples: '
                         + '; '.join(acc['examples'][:3]),
                         'update-code-map')

    def _codemap_accuracy(self, body):
        """Sample (file, symbol, line) claims and check them against source."""
        lines = body.split('\n')
        owner, cur = [], None
        for l in lines:
            mm = PATHBLOCK_RE.search(l)
            if mm:
                cur = mm.group(1)
            owner.append(cur)

        row = re.compile(r'^\|\s*`?([A-Za-z_][\w.]*)`?(?:\([^)]*\))?\s*\|\s*(\d{1,6})\s*\|')
        cands = []
        for i, l in enumerate(lines):
            f = owner[i]
            if f and '|' in l:
                mm = row.match(l)
                if mm:
                    cands.append((f, mm.group(1), int(mm.group(2))))
        inline = re.compile(rf'`([\w./-]+\.(?:{CODE_EXT})):(\d+)`\s*(?:—|-)\s*`([A-Za-z_][\w.]*)`')
        for mm in inline.finditer(body):
            cands.append((mm.group(1), mm.group(3), int(mm.group(2))))

        if not cands:
            return {'checked': 0, 'ok': 0, 'examples': []}
        pick = self.rng.sample(cands, min(self.sample, len(cands)))
        ok, examples = 0, []
        for f, symbol, ln in pick:
            p = rel(self.root, f)
            if not os.path.isfile(p):
                examples.append(f'{f} (no such file)')
                continue
            try:
                with open(p, encoding='utf-8', errors='replace') as fh:
                    src = fh.readlines()
            except OSError:
                continue
            lo, hi = max(0, ln - 3), min(len(src), ln + 2)
            window = ''.join(src[lo:hi])
            leaf = symbol.rsplit('.', 1)[-1]
            if re.search(rf'\b{re.escape(leaf)}\b', window):
                ok += 1
            else:
                examples.append(f'{f}:{ln} expected {leaf!r}')
        return {'checked': len(pick), 'ok': ok, 'examples': examples}

    def _source_file_count(self):
        exts = tuple('.' + e for e in CODE_EXT.split('|'))
        skip = {'.git', 'node_modules', '.venv', '.venv_linux', 'venv',
                '__pycache__', 'dist', 'build', 'vendor', '.next', 'target'}
        n = 0
        for _dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith('.')]
            n += sum(1 for f in filenames if f.endswith(exts))
            if n > 5000:
                break
        return n

    # ---------------- 5. changelog currency ----------------
    def check_changelog(self):
        name, path = find_first(self.root, CHANGELOG_CANDIDATES)
        self.facts['changelog'] = {'path': name}
        if not path:
            self.add('changelog.missing', 'low',
                     'No CHANGELOG found',
                     'Release history is only recoverable from git log.',
                     'version-manager')
            return
        body = read(path) or ''
        vers = re.findall(r'^#{1,3}\s*\[?v?(\d+\.\d+\.\d+)', body, re.M)
        newest = vers[0] if vers else None
        self.facts['changelog']['newest'] = newest

        code_ver, code_loc = self._code_version()
        self.facts['code_version'] = {'version': code_ver, 'location': code_loc}
        if code_ver and newest and code_ver != newest:
            self.add('changelog.drift', 'medium',
                     f'Code version {code_ver} but changelog newest is {newest}',
                     f'{code_loc} and {name} disagree — one of them was updated '
                     'by hand.',
                     'version-manager')

    def _code_version(self):
        probes = [
            ('core/constants.py', r'^VERSION\s*=\s*["\']([^"\']+)["\']'),
            ('pyproject.toml', r'^version\s*=\s*["\']([^"\']+)["\']'),
            ('package.json', r'"version"\s*:\s*"([^"]+)"'),
            ('VERSION', r'^(\d+\.\d+\.\d+)'),
        ]
        for fname, pat in probes:
            p = rel(self.root, fname)
            if os.path.isfile(p):
                body = read(p) or ''
                m = re.search(pat, body, re.M)
                if m:
                    return m.group(1), fname
        # any *.py defining VERSION = "x.y.z"
        try:
            out = subprocess.run(
                ['git', '-C', self.root, 'grep', '-lE',
                 r'^(VERSION|__version__)\s*=', '--', '*.py'],
                capture_output=True, text=True, timeout=15).stdout.split()
            for f in out[:5]:
                body = read(rel(self.root, f)) or ''
                m = re.search(r'^(?:VERSION|__version__)\s*=\s*["\']([^"\']+)["\']',
                              body, re.M)
                if m:
                    return m.group(1), f
        except (OSError, subprocess.SubprocessError):
            pass
        return None, None

    # ---------------- run ----------------
    def run(self):
        self.check_topology()
        self.check_size()
        self.check_pointers()
        self.check_codemap()
        self.check_changelog()
        order, seen = [], set()
        for want in ('unify-agents-md', 'claude-md-optimizer',
                     'update-code-map', 'version-manager'):
            for f in self.findings:
                if f['remedy'] == want and want not in seen:
                    seen.add(want)
                    order.append(want)
        return {
            'root': self.root,
            'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'facts': self.facts,
            'findings': self.findings,
            'recommended_order': order,
        }


SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2}
SEV_MARK = {'high': '[HIGH]', 'medium': '[MED ]', 'low': '[LOW ]'}


def report(res):
    out = [f'repo-doctor — {res["root"]}', '']
    f = res['facts']
    files = f.get('instruction_files', {})
    if files:
        out.append('Instruction files:')
        for n, d in sorted(files.items(), key=lambda kv: -kv[1]['tokens']):
            ptr = ''
            if n in ('CLAUDE.md', 'GEMINI.md'):
                ptr = ' (@imports AGENTS.md)' if d['first_line'] == '@AGENTS.md' else ' (standalone)'
            out.append(f'  {n:38} ≈{d["tokens"]:5} tok{ptr}')
        out.append(f'  {"always loaded per request":38} ≈{f.get("always_loaded_tokens", 0):5} tok')
    cm = f.get('codemap', {})
    if cm.get('path'):
        age = cm.get('age_days')
        # Under 8 parsed claims the percentage is noise — usually means the map
        # is not in the update-code-map format, so claims could not be extracted.
        if cm.get('checked', 0) >= 8:
            acc = f'{100.0 * cm["ok"] / cm["checked"]:.0f}% of {cm["checked"]} sampled'
        elif cm.get('checked'):
            acc = f'unmeasurable (only {cm["checked"]} claims parsed)'
        else:
            acc = 'unmeasurable (no parseable file:line claims)'
        out.append('')
        out.append(f'CodeMap: {cm["path"]}  '
                   f'age={"unknown" if age is None else str(age) + "d"}  accuracy={acc}')
    cl = f.get('changelog', {})
    if cl.get('path'):
        cv = f.get('code_version', {}).get('version')
        out.append(f'Changelog: {cl["path"]}  newest={cl.get("newest")}  code={cv}')

    out.append('')
    if not res['findings']:
        out.append('No findings — agent docs layer is healthy.')
        return '\n'.join(out)

    out.append(f'{len(res["findings"])} finding(s):')
    for fi in sorted(res['findings'], key=lambda x: SEV_ORDER[x['severity']]):
        out.append(f'  {SEV_MARK[fi["severity"]]} {fi["title"]}')
        for line in _wrap(fi['detail'], 72):
            out.append(f'          {line}')
        if fi['remedy']:
            out.append(f'          → /{fi["remedy"]}')
        out.append('')
    if res['recommended_order']:
        out.append('Recommended order (topology → content → accuracy):')
        for i, r in enumerate(res['recommended_order'], 1):
            out.append(f'  {i}. /{r}')
    return '\n'.join(out)


def _wrap(text, width):
    words, line, out = text.split(), '', []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f'{line} {w}'.strip()
    if line:
        out.append(line)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', default='.', help='repository root (default: cwd)')
    ap.add_argument('--json', action='store_true', help='emit JSON instead of a report')
    ap.add_argument('--sample', type=int, default=40,
                    help='CodeMap claims to spot-check (default 40)')
    ap.add_argument('--seed', type=int, default=None, help='sampling seed')
    a = ap.parse_args()
    if not os.path.isdir(a.repo):
        print(f'not a directory: {a.repo}', file=sys.stderr)
        return 2
    res = Audit(a.repo, sample=a.sample, seed=a.seed).run()
    print(json.dumps(res, indent=2) if a.json else report(res))
    return 1 if res['findings'] else 0


if __name__ == '__main__':
    sys.exit(main())
