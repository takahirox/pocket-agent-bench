#!/usr/bin/env python3
"""Qualify the complete runner using clean positive, negative and alternative artifacts."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from artifact import read_artifact, write_artifact
from variants import variant

HERE = Path(__file__).resolve().parent
EXPECTED = {
    "reference": ("pass", None, None),
    "baseline": ("fail", "probe.json", "shared.create"),
    "reader_can_manage": ("fail", "probe.json", "shared.denied_update.bob"),
    "creator_deletes_shared": ("fail", "lifecycle.json", "shared.creator_deleted"),
    "creator_unread_counts": ("fail", "behavior.json", "shared.viewer_counts_and_inbox_changes"),
    "stale_membership": ("fail", "behavior.json", "shared.membership_changes"),
    "valid_join_and_wording": ("pass", None, None),
}


def qualifies(kind, grade, checks):
    expected, _, case = EXPECTED[kind]
    if grade.get("automated_correctness") != expected:
        return False
    if case is None:
        return True
    return any(row.get("name") == case and row.get("status") == "fail" for row in checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--ui-map", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--project-prefix", required=True)
    parser.add_argument("--port", type=int, default=33085)
    parser.add_argument("--vite-port", type=int, default=33341)
    args = parser.parse_args()
    root = args.destination.resolve()
    root.mkdir(parents=True, exist_ok=False)
    reference = read_artifact(args.reference)
    baseline = read_artifact(args.baseline)
    base_map = json.loads(args.ui_map.read_text())
    records = []
    for index, kind in enumerate(EXPECTED):
        print(f"QUALIFY {kind}", flush=True)
        case = root / kind
        case.mkdir()
        artifact = case / "candidate.zip"
        entries = (
            baseline
            if kind == "baseline"
            else reference
            if kind == "reference"
            else variant(reference, kind)
        )
        digest = write_artifact(entries, artifact)
        ui = json.loads(json.dumps(base_map))
        if kind == "valid_join_and_wording":
            ui["locators"]["audience"]["value"] = "Who can use this view?"
        (case / "ui-map.json").write_text(json.dumps(ui, indent=2) + "\n")
        workspace = case / "runtime"
        command = [
            sys.executable,
            str(HERE / "task.py"),
            "prepare",
            "--source",
            str(args.source.resolve()),
            "--artifact",
            str(artifact),
            "--ui-map",
            str(case / "ui-map.json"),
            "--destination",
            str(workspace),
            "--project",
            f"{args.project_prefix}-{index}",
            "--port",
            str(args.port),
            "--vite-port",
            str(args.vite_port),
        ]
        prepared = subprocess.run(command, check=False)
        if prepared.returncode:
            records.append({"kind": kind, "qualified": False, "reason": "preparation failed"})
        else:
            subprocess.run(
                [sys.executable, str(HERE / "task.py"), "grade", str(workspace)], check=False
            )
            grade = json.loads((workspace / "grade.json").read_text())
            _, filename, expected_check = EXPECTED[kind]
            checks = (
                json.loads((workspace / filename).read_text())["checks"]
                if filename and (workspace / filename).exists()
                else []
            )
            records.append(
                {
                    "kind": kind,
                    "artifact_sha256": digest,
                    "qualified": qualifies(kind, grade, checks),
                    "automated_correctness": grade["automated_correctness"],
                    "expected_check": expected_check,
                    "observed_failure": [r for r in checks if r["name"] == expected_check],
                    "elapsed_seconds": grade["elapsed_seconds"],
                }
            )
        # Preserve source/DB volumes and all reports; free this attempt's network pool.
        if (workspace / "compose.yaml").exists():
            with (case / "release.log").open("w") as log:
                subprocess.run(
                    ["docker", "compose", "-f", str(workspace / "compose.yaml"), "down"],
                    check=True,
                    stdout=log,
                    stderr=log,
                )
        (root / "qualification.json").write_text(
            json.dumps({"version": "0.2", "cases": records}, indent=2) + "\n"
        )
        if not records[-1]["qualified"]:
            print(f"STOP: {kind} did not meet the control's expected result", flush=True)
            return 1
    print("All seven complete-runner controls qualified", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
