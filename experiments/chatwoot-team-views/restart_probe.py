#!/usr/bin/env python3
"""Check shared-view persistence across an application restart, without resetting DB."""

import argparse
import json
import subprocess
import time
import urllib.error
from pathlib import Path

from probe import API, Mismatch, require


def wait_ready(api):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            status, _ = api.request("health", "/app/login")
            if status == 200:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError("Readiness failed")


def check(root):
    root = root.resolve()
    fixture = json.loads((root / "fixture.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    api = API(f"http://localhost:{manifest['port']}")
    compose = ["docker", "compose", "-f", str(root / "compose.yaml")]
    subprocess.run([*compose, "up", "-d", "app", "proxy"], check=True)
    wait_ready(api)
    api.login("alice", fixture["users"]["alice"]["email"])
    path = f"/api/v1/accounts/{fixture['accounts']['A']}/custom_filters"
    data = {
        "name": "Restart qualification",
        "query": fixture["personal"]["alice"]["query"],
        "team_id": fixture["teams"]["support"],
        "filter_type": "conversation",
    }
    status, created = api.request("alice", path, "POST", {"custom_filter": data})
    require(status in {200, 201}, "Could not create restart fixture")
    try:
        subprocess.run([*compose, "restart", "app"], check=True)
        wait_ready(api)
        status, body = api.request("alice", f"{path}/{created['id']}")
        require(status == 200, "Saved view unavailable after restart")
        require(all(body[key] == value for key, value in data.items()), "Persisted view changed")
        report = {"kind": "application-restart-persistence", "status": "pass"}
        (root / "restart-check.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
    finally:
        api.request("alice", f"{path}/{created['id']}", "DELETE")


def run(root):
    try:
        check(root)
        return 0
    except Mismatch as error:
        report = {"kind": "application-restart-persistence", "status": "fail", "detail": str(error)}
        code = 1
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        report = {
            "kind": "application-restart-persistence",
            "status": "error",
            "detail": type(error).__name__,
        }
        code = 2
    (root / "restart-check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    raise SystemExit(run(parser.parse_args().workspace))
