#!/usr/bin/env python3
"""Compare legacy saved-filter rows with the immutable pre-migration fixture."""

import argparse
import json
import subprocess
from pathlib import Path


def check(root):
    root = root.resolve()
    fixture = json.loads((root / "fixture.json").read_text())
    expected = sorted(fixture["personal"].values(), key=lambda row: row["id"])
    ids = [row["id"] for row in expected]
    if not all(type(value) is int for value in ids):
        raise ValueError("Fixture IDs must be integers")
    sql = f"""SELECT coalesce(json_agg(row_to_json(rows)), '[]'::json) FROM (
      SELECT id, account_id, user_id, name,
        CASE filter_type WHEN 0 THEN 'conversation' WHEN 1 THEN 'contact' WHEN 2 THEN 'report' END AS filter_type,
        query
      FROM custom_filters WHERE id IN ({",".join(map(str, ids))}) ORDER BY id
    ) rows"""
    raw = subprocess.check_output(
        [
            "docker",
            "compose",
            "-f",
            str(root / "compose.yaml"),
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "pocket",
            "-d",
            "pocket_team_views",
            "-At",
            "-c",
            sql,
        ],
        text=True,
    )
    actual = json.loads(raw)
    report = {
        "kind": "populated-upgrade-legacy-data",
        "rows_checked": len(expected),
        "status": "pass" if actual == expected else "fail",
    }
    (root / "migration-check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return actual == expected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    raise SystemExit(0 if check(parser.parse_args().workspace) else 1)
