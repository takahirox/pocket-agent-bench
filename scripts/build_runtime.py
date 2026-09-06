"""Build a versioned runtime with an optional explicit agent project snapshot."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--install-project", type=Path, help="Optional agent Python project snapshot")
    p.add_argument("--tag", default="pocket-agent-bench-runtime:0.1")
    p.add_argument(
        "--manifest", type=Path, help="Optional manifest destination for an alternate build"
    )
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = args.install_project.resolve() if args.install_project else None
    with tempfile.TemporaryDirectory(prefix="pocket-build-") as d:
        context = Path(d)
        shutil.copy(root / "docker/Dockerfile", context / "Dockerfile")
        (context / "project").mkdir()
        if project:
            for name in ("pyproject.toml", "README.md", "LICENSE"):
                if (project / name).is_file():
                    shutil.copy(project / name, context / "project" / name)
            shutil.copytree(
                project / "src",
                context / "project/src",
                ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
            )
        digest = hashlib.sha256()
        for file in sorted((context / "project").rglob("*")):
            if file.is_file():
                digest.update(
                    file.relative_to(context).as_posix().encode() + b"\0" + file.read_bytes()
                )
        subprocess.run(["docker", "build", "-t", args.tag, str(context)], check=True)
        image = subprocess.check_output(
            ["docker", "image", "inspect", args.tag, "--format", "{{.Id}}"], text=True
        ).strip()
        out = args.manifest or root / "local/runtime.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "image": args.tag,
                    "image_id": image,
                    "project_snapshot_sha256": digest.hexdigest() if project else None,
                    "project_head": subprocess.check_output(
                        ["git", "-C", str(project), "rev-parse", "HEAD"], text=True
                    ).strip()
                    if project
                    else None,
                },
                indent=2,
            )
            + "\n"
        )
        print(out.read_text())


if __name__ == "__main__":
    main()
