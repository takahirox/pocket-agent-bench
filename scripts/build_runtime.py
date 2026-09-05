"""Build a versioned runtime from an explicit Fleet snapshot without copying secrets."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fleet", type=Path, help="Optional My AI Employee source snapshot")
    p.add_argument("--tag", default="pocket-agent-bench-runtime:0.1")
    p.add_argument(
        "--manifest", type=Path, help="Optional manifest destination for an alternate build"
    )
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    fleet = args.fleet.resolve() if args.fleet else None
    with tempfile.TemporaryDirectory(prefix="pocket-build-") as d:
        context = Path(d)
        shutil.copy(root / "docker/Dockerfile", context / "Dockerfile")
        (context / "fleet").mkdir()
        if fleet:
            for name in ("pyproject.toml", "README.md", "LICENSE"):
                if (fleet / name).is_file():
                    shutil.copy(fleet / name, context / "fleet" / name)
            shutil.copytree(
                fleet / "src",
                context / "fleet/src",
                ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
            )
        digest = hashlib.sha256()
        for file in sorted((context / "fleet").rglob("*")):
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
                    "fleet_snapshot_sha256": digest.hexdigest() if fleet else None,
                    "fleet_head": subprocess.check_output(
                        ["git", "-C", str(fleet), "rev-parse", "HEAD"], text=True
                    ).strip()
                    if fleet
                    else None,
                },
                indent=2,
            )
            + "\n"
        )
        print(out.read_text())


if __name__ == "__main__":
    main()
