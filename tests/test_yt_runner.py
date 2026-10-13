"""Exercise the real Bash runner with controlled interpreter/platform probes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASH = (str(Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Git/bin/bash.exe") if os.name == "nt" else shutil.which("bash"))

PROBE = '''import json, os, pathlib, sys
minor = int(sys.argv[1])
args = sys.argv[2:]
with open(os.environ["EVENTS"], "a") as f:
    f.write(json.dumps([minor, args]) + "\\n")
if args[0] == "-c":
    if "version_info" in args[1]:
        sys.version_info = (3, minor, 0)
        exec(args[1])
    elif "youtube_transcript_api" in args[1]:
        pass
    else:
        sys.exit(1)
elif args[:2] == ["-m", "venv"]:
    settings = json.loads(pathlib.Path(os.environ["PROBE_CONFIG"]).read_text(encoding="utf-8"))
    target = pathlib.Path(args[2]) / settings["venv_py"]
    target.parent.mkdir(parents=True)
    # These are shell scripts even when the probe runs under native Windows.
    target.write_bytes(settings["shim"].encode("utf-8"))
    target.chmod(0o755)
elif args[0] == "yt_transcript.py":
    print("RUN", minor, json.dumps(args[1:]))
else:
    sys.exit("Unexpected pip/install invocation")
'''


@pytest.mark.parametrize("platform", ["Linux", "Darwin", "MINGW64_NT"])
@pytest.mark.parametrize("case", ["old_boot", "fallback_boot", "old_venv",
                                  "fallback_venv", "blocked_venvs", "broken_venv",
                                  "supported_venv"])
def test_runner_requires_supported_working_python(tmp_path, platform, case):
    project = tmp_path / "project with spaces"
    project.mkdir()
    bins = tmp_path / "bin"
    bins.mkdir()
    probe = tmp_path / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    events = tmp_path / "events.jsonl"
    windows = platform.startswith("MINGW")
    venv_py = "Scripts/python.exe" if windows else "bin/python"
    venvs = ([".venv", ".venv_windows"] if windows else
             [".venv", ".venv_linux"] if platform == "Darwin" else
             [".venv_linux", ".venv"])

    def shim(minor):
        return (f'#!/bin/bash\nexec "{Path(sys.executable).as_posix()}" '
                f'"{probe.as_posix()}" {minor} "$@"\n')

    def executable(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        path.chmod(0o755)

    executable(bins / "uname", f"#!/bin/bash\necho {platform}\n")
    for name in ("py", "python", "python3"):
        version = 9 if case == "old_boot" else 10
        if case == "fallback_boot" and name in ("py", "python3"):
            version = 8
        # Emulate the Windows py launcher's -3 selector.
        content = shim(version).replace("exec ", '[ "$1" != "-3" ] || shift\nexec ')
        executable(bins / name, content)
    if case in ("old_venv", "fallback_venv", "blocked_venvs", "broken_venv",
                "supported_venv"):
        executable(project / venvs[0] / venv_py,
                   "#!/bin/bash\nexit 126\n" if case == "broken_venv" else
                   shim(10 if case == "supported_venv" else 9))
    if case in ("fallback_venv", "blocked_venvs"):
        executable(project / venvs[1] / venv_py,
                   shim(8 if case == "blocked_venvs" else 10))
    originals = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    bin_path = bins.as_posix()
    if os.name == "nt":
        bin_path = "/" + bin_path[0].lower() + bin_path[2:]
    # MSYS can rewrite path-like environment values when calling native Python.
    # Keep relative paths and shell source in a file; only its real path crosses
    # the shell/native boundary.
    config = tmp_path / "probe-config.json"
    config.write_text(json.dumps({"venv_py": venv_py, "shim": shim(10)}), encoding="utf-8")
    env = dict(os.environ, PROBE_BIN=bin_path, YT_TRANSCRIPT_PROJECT=str(project),
               EVENTS=str(events), PROBE_CONFIG=str(config))
    result = subprocess.run([BASH, "-c", 'export PATH="$PROBE_BIN"; source "$@"', "test",
                             str(ROOT / "yt-transcript/skills/yt-transcript/scripts/run.sh"),
                             "dQw4w9WgXcQ", "-t"], env=env, capture_output=True, text=True)
    calls = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
    if any(args[:2] == ["-m", "venv"] for _, args in calls):
        created = next(args[2] for _, args in calls if args[:2] == ["-m", "venv"])
        generated = project / created / venv_py
        assert generated.is_file(), result.stdout + result.stderr
        assert generated.read_bytes() == shim(10).encode("utf-8")
    if case in ("old_boot", "blocked_venvs"):
        assert result.returncode == 1, result.stdout + result.stderr
        assert "Python 3.10+" in result.stderr
        assert not any(args[0] != "-c" for _, args in calls)
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'RUN 10 ["-r", "dQw4w9WgXcQ", "-t"]' in result.stdout
        if case in ("old_venv", "broken_venv"):
            assert (project / venvs[1] / venv_py).is_file()
        if case in ("supported_venv", "fallback_venv"):
            assert not any(args[:2] == ["-m", "venv"] for _, args in calls)
    for path in project.rglob("*"):
        if path.is_file():
            assert b"\r\n" not in path.read_bytes(), "shell fixtures must use LF on every platform"
    for path, content in originals.items():
        assert path.read_bytes() == content, "existing environments must be preserved"
