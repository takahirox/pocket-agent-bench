#!/usr/bin/env python3
"""Reject four known-bad reference variants without editing candidate files."""

import argparse
import json
import re
import subprocess
from pathlib import Path

CONTROLS = {
    "reader_can_manage": "does not let a reader delete",
    "creator_deletes_shared": "keeps shared views after creator deletion",
    "creator_unread_counts": "keeps unread badges viewer-specific",
    "stale_membership": "uses fresh membership within an existing login",
}
HERE = Path(__file__).resolve().parent

FAILURE_MARKERS = {
    "reader_can_manage": ("forbidden (403)", "no_content (204)"),
    "creator_deletes_shared": ("success status code (2xx)", "but it was 404"),
    "creator_unread_counts": ("expected: 1", "got: 2"),
    "stale_membership": ("not_found status code (404)", "but it was 200"),
}


def detected(control, returncode, output):
    return (
        returncode == 1
        and bool(re.search(r"1 example, 1 failure\b", output))
        and all(marker in output for marker in FAILURE_MARKERS[control])
    )


def main(root):
    results = []
    for control, example in CONTROLS.items():
        cmd = [
            "docker",
            "compose",
            "-f",
            str(root.resolve() / "compose.yaml"),
            "run",
            "--rm",
            "-v",
            f"{HERE}/acceptance_spec.rb:/bench/acceptance_spec.rb:ro",
            "-v",
            f"{HERE}/negative_control.rb:/bench/negative_control.rb:ro",
            "-e",
            "RAILS_ENV=test",
            "-e",
            "POSTGRES_DATABASE=pocket_team_views_test",
            "-e",
            "REDIS_URL=redis://redis:6379/1",
            "-e",
            f"TEAM_VIEW_CONTROL={control}",
            "app",
            "bundle",
            "exec",
            "rspec",
            "--require",
            "/bench/negative_control.rb",
            "/bench/acceptance_spec.rb",
            "--example",
            example,
        ]
        with (root / f"control-{control}.log").open("w") as log:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False)
        output = (root / f"control-{control}.log").read_text()
        # A boot error or empty selection is not evidence of catching the bug.
        rejected = detected(control, result.returncode, output)
        results.append({"control": control, "example": example, "detected": rejected})
        print(f"{control}: {'detected' if rejected else 'NOT qualified'}", flush=True)
    (root / "negative-controls.json").write_text(json.dumps(results, indent=2) + "\n")
    return all(row["detected"] for row in results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    raise SystemExit(0 if main(parser.parse_args().workspace) else 1)
