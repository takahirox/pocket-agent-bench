#!/usr/bin/env python3
"""Initialize a fresh maintainer qualification environment exactly once."""

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def initialize(root):
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if (root / ".initialization-started").exists():
        raise RuntimeError("Initialization already attempted; no implicit reset")
    # A different directory must not reuse and reset an existing project's volumes.
    for command in (("container", "ls", "-a"), ("volume", "ls"), ("network", "ls")):
        existing = subprocess.check_output(
            [
                "docker",
                *command,
                "--filter",
                f"label=com.docker.compose.project={manifest['project']}",
                "--format",
                "{{.ID}}" if command[0] != "volume" else "{{.Name}}",
            ],
            text=True,
        ).strip()
        if existing:
            raise RuntimeError("Compose project already has resources; choose a fresh project name")
    # An interrupted init also needs explicit investigation, never implicit data deletion.
    with (root / ".initialization-started").open("x") as marker:
        marker.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    compose = ["docker", "compose", "-f", str(root / "compose.yaml")]

    def run(name, *args):
        with (root / (name + ".log")).open("w") as log:
            subprocess.run([*compose, *args], stdout=log, stderr=subprocess.STDOUT, check=True)
        print(name + ": completed", flush=True)

    run("services", "up", "-d", "postgres", "redis")
    run("schema", "run", "--rm", "app", "bundle", "exec", "rails", "db:create", "db:schema:load")
    run("fixture", "run", "--rm", "app", "bundle", "exec", "rails", "runner", "/bench/fixture.rb")
    lines = (root / "fixture.log").read_text().splitlines()
    records = [
        json.loads(line.removeprefix("POCKET_FIXTURE="))
        for line in lines
        if line.startswith("POCKET_FIXTURE=")
    ]
    if len(records) != 1:
        raise RuntimeError("Expected exactly one fixture manifest from Rails")
    (root / "fixture.json").write_text(json.dumps(records[0], indent=2) + "\n")
    run("application", "up", "-d", "app", "proxy")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{manifest['port']}/app/login", timeout=5
            ) as r:
                if r.status == 200:
                    break
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Application not ready within setup allowance")
    images = {}
    for name in (
        manifest["dependency_image"],
        "nginx:1.28-alpine",
        "pgvector/pgvector:pg16",
        "redis:7.4-alpine",
    ):
        images[name] = subprocess.check_output(
            ["docker", "image", "inspect", name, "--format", "{{.Id}}"], text=True
        ).strip()
    manifest["observed_image_ids"] = images
    manifest["initialized_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("ready; fixture.json contains synthetic identifiers only")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    initialize(parser.parse_args().workspace)
