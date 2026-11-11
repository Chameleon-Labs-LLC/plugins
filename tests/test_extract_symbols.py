"""extract_symbols.excluded() must prune nested directories with either separator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "docs-toolkit/skills/update-code-map/references"))
import extract_symbols as es  # noqa: E402


def test_excluded_splits_on_backslash_and_slash():
    pats = es.DEFAULT_EXCLUDES
    assert es.excluded(r"packages\foo\node_modules", pats)   # os.walk on Windows
    assert es.excluded("packages/foo/node_modules", pats)    # --only-changed input
    assert es.excluded(r"svc\.venv_linux\lib", pats)
    assert not es.excluded(r"src\app\main.py", pats)
