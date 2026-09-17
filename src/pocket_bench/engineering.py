"""Entry point for substantial engineering tasks with a separate Docker verifier."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def catalog(root):
    path = Path(root) / "experiments/chatwoot-team-views/task.json"
    return [json.loads(path.read_text())]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("command", choices=["list", "package", "prepare-agent", "prepare", "grade"])
    parser.add_argument("task_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    rest = args.task_args
    folder = args.root.resolve() / "experiments/chatwoot-team-views"
    if args.command == "list":
        if rest:
            parser.error("list does not accept task arguments")
        print(json.dumps(catalog(args.root), indent=2))
        return 0
    script = (
        "artifact.py"
        if args.command == "package"
        else "agent_workspace.py"
        if args.command == "prepare-agent"
        else "task.py"
    )
    command = [sys.executable, str(folder / script)]
    if args.command in {"prepare", "grade"}:
        command.append(args.command)
    return subprocess.run([*command, *rest], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
