"""Container entry point; starts root-owned mock service when required."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

browser = shutil.which("chromium")
browser_version = (
    subprocess.check_output([browser, "--version"], text=True).strip() if browser else None
)
Path("/var/lib/pocket/environment.json").write_text(
    json.dumps(
        {
            "python": sys.version,
            "browser_version": browser_version,
        }
    )
)
p = Path("/app/input/api.json")
Path("/var/lib/pocket/state.json").write_text("{}")
if p.exists():
    config = json.loads(p.read_text())
    subprocess.Popen(
        [sys.executable, "/opt/pocket/mock_api.py", config["mode"], "/var/lib/pocket/state.json"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
os.execvp(sys.argv[1], sys.argv[1:])
