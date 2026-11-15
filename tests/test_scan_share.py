"""Share preparation must not ingest private scanner output, even indirectly."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "scan-source/skills/scan-source"
SCRIPT = SKILL / "scripts/prepare-share.py"


def test_share_draft_omits_all_private_inputs_and_preserves_local_evidence(tmp_path):
    markers = ["FAKE_SECRET_DO_NOT_USE_123", "def proprietary_algorithm():",
               "https://private.example.invalid/internal", "private_user_123",
               "/home/private_user_123/project", r"C:\Users\private_user_123\project"]
    private = "\n".join(markers)
    reports = tmp_path / ".scan-reports"
    reports.mkdir()
    for name in ("scan.log", "scan-report.md", "scan-fix.sh"):
        (reports / name).write_text(private, encoding="utf-8")
    share = reports / "share"
    share.mkdir()
    (share / "old-raw.log").write_text(private, encoding="utf-8")
    output = share / "new-scan"
    result = subprocess.run([sys.executable, str(SCRIPT), "--output-dir", str(output)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert [p.name for p in output.iterdir()] == ["report.md"]
    draft = (output / "report.md").read_text(encoding="utf-8")
    assert all(marker not in draft for marker in markers)
    assert "Reproduce this scan" in draft
    assert "explicit approval" in draft
    assert "DRAFT" in draft
    for name in ("scan.log", "scan-report.md", "scan-fix.sh"):
        assert (reports / name).read_text(encoding="utf-8") == private
    assert (share / "old-raw.log").read_text(encoding="utf-8") == private
    # Reruns may not silently reuse a directory with stale or edited content.
    (output / "report.md").write_text(private, encoding="utf-8")
    again = subprocess.run([sys.executable, str(SCRIPT), "--output-dir", str(output)],
                           capture_output=True, text=True)
    assert again.returncode != 0
    assert (output / "report.md").read_text(encoding="utf-8") == private


def test_skill_keeps_sharing_opt_in_and_forbids_raw_copies():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    step9 = text.split("### 9.")[1].split("### 10.")[0]
    assert "prepare-share.py" in step9
    assert "Do not copy" in step9
    assert "raw log" in step9
    assert "explicit approval" in step9
    assert "never file without asking" in text
    assert "private-disclosure process" in text
