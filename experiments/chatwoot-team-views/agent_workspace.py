#!/usr/bin/env python3
"""Prepare the clean public starting environment, without any reference solution."""

import argparse
import json
from pathlib import Path

import initialize
import prepare

HERE = Path(__file__).resolve().parent
DOCS = HERE.parents[1] / "docs/task-proposals/chatwoot-team-views"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--port", type=int, default=33087)
    parser.add_argument("--vite-port", type=int, default=33343)
    parser.add_argument("--image", default="pocket-chatwoot-feasibility:5b7038b")
    args = parser.parse_args()
    prepare.prepare(args)
    root = args.destination.resolve()
    initialize.initialize(root)
    source = root / "source"
    instruction = (
        (DOCS / "instruction.md").read_text().replace("(ui-evaluation.md)", "(UI-PROTOCOL.md)")
    )
    public = {
        "TASK.md": instruction,
        "UI-PROTOCOL.md": (DOCS / "ui-evaluation.md")
        .read_text()
        .replace(
            "../../../experiments/chatwoot-team-views/task-ui-map.json", "UI-MAP.example.json"
        ),
        "CHECKS.json": (HERE / "checks.json").read_text(),
        "DEVELOPMENT.md": (DOCS / "development.md").read_text(),
        "REVIEW.md": (HERE / "REVIEW.md").read_text(),
        "UI-MAP.example.json": (HERE / "task-ui-map.json").read_text(),
        "BENCHMARK_FIXTURE.json": (root / "fixture.json").read_text(),
    }
    for name, content in public.items():
        (source / name).write_text(content)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest.update(
        purpose="public agent development environment",
        task_version="0.2",
        public_files=list(public),
        reference_provided=False,
    )
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        "Ready. Give the agent source/TASK.md and source/, plus this disposable app's browser URL."
    )


if __name__ == "__main__":
    main()
