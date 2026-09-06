"""Bounded regular-file exchange; usable unchanged inside the task container."""

import base64
import json
import os
import stat
import sys
from pathlib import Path, PurePosixPath

LIMIT = 16 * 1024 * 1024
MAX_FILES = 4096
PUBLIC_ROOTS = ("input", "src", "output")
WRITABLE_ROOTS = ("src", "output")


def validate(bundle, roots=PUBLIC_ROOTS):
    if not isinstance(bundle, dict) or len(bundle) > MAX_FILES:
        raise ValueError("invalid workspace file count")
    total = 0
    decoded = {}
    for name, value in bundle.items():
        path = PurePosixPath(name)
        if (
            not isinstance(value, str)
            or path.is_absolute()
            or len(path.parts) < 2
            or path.parts[0] not in roots
            or any(p in ("", ".", "..", ".git") for p in name.split("/"))
            or "\\" in name
            or "\x00" in name
        ):
            raise ValueError("unsafe workspace path")
        if len(value) > LIMIT * 2:
            raise ValueError("workspace exceeds byte limit")
        data = base64.b64decode(value, validate=True)
        total += len(data)
        if total > LIMIT:
            raise ValueError("workspace exceeds byte limit")
        decoded[name] = data
    for name in decoded:
        if any(str(p) in decoded for p in PurePosixPath(name).parents):
            raise ValueError("file/directory collision")
    return decoded


def snapshot(root, roots=PUBLIC_ROOTS):
    root = Path(root)
    result = {}
    total = 0
    for name in roots:
        top = root / name
        if top.is_symlink() or (top.exists() and not top.is_dir()):
            raise ValueError("workspace roots must be regular directories")
        for parent, dirs, files in os.walk(top, followlinks=False):
            for child in dirs + files:
                path = Path(parent) / child
                info = path.lstat()
                if stat.S_ISDIR(info.st_mode):
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError("workspace links/devices are forbidden")
                total += info.st_size
                if total > LIMIT or len(result) >= MAX_FILES:
                    raise ValueError("workspace exceeds transport budget")
                with path.open("rb") as stream:
                    data = stream.read(LIMIT + 1)
                if len(data) != info.st_size:
                    raise ValueError("workspace changed during capture")
                result[path.relative_to(root).as_posix()] = base64.b64encode(data).decode()
    validate(result, roots)
    return result


def materialize(root, bundle, roots=PUBLIC_ROOTS, replace=False):
    import shutil

    root = Path(root)
    decoded = validate(bundle, roots)
    # Reject links in the destination before writing or removing anything.
    snapshot(root, roots)
    for name in roots:
        target = root / name
        if replace and target.exists():
            shutil.rmtree(target)  # exact validated disposable task subdirectory
        target.mkdir(parents=True, exist_ok=True)
    for name, data in decoded.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


if __name__ == "__main__":
    if sys.argv[1] == "export":
        print(json.dumps(snapshot(Path("/app"))))
    elif sys.argv[1] == "import":
        source = Path(sys.argv[2])
        if source.stat().st_size > LIMIT * 2:
            raise ValueError("oversized workspace manifest")
        materialize(Path("/app"), json.loads(source.read_text()), WRITABLE_ROOTS, replace=True)
    else:
        raise ValueError("unknown transport operation")
