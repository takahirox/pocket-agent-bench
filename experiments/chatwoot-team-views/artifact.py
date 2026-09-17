#!/usr/bin/env python3
"""Freeze tracked candidate source; never transfer Git state or runtime files."""

import argparse
import hashlib
import io
import json
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

COMMIT = "5b7038b950b763e230df2d544df9b87b8752fef3"
MAX_FILES = 30000
MAX_FILE = 96 * 1024 * 1024  # Upstream includes a 69 MB model fixture.
MAX_TOTAL = 384 * 1024 * 1024
EXCLUDED = {".git", ".env", "node_modules", "log", "tmp", "coverage", ".bundle"}


def safe_path(name):
    path = PurePosixPath(name)
    if (
        not name
        or name == "."
        or path.is_absolute()
        or str(path) != name
        or any(p in {".", ".."} for p in path.parts)
        or "\\" in name
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("Unsafe artifact path")
    if name in {"log/.keep", "tmp/.keep"}:
        return path
    if any(p in EXCLUDED for p in path.parts) or any(
        p.startswith(".env.") and p != ".env.example" for p in path.parts
    ):
        raise ValueError("Runtime or Git file is not a source artifact")
    return path


def validate(entries):
    if not entries or len(entries) > MAX_FILES:
        raise ValueError("Invalid artifact file count")
    total = 0
    for name, (mode, data) in entries.items():
        path = safe_path(name)
        if mode not in {0o100644, 0o100755, 0o120000} or len(data) > MAX_FILE:
            raise ValueError("Unsupported mode or oversized file")
        if any(str(parent) in entries for parent in path.parents if str(parent) != "."):
            raise ValueError("File or symlink used as a directory")
        total += len(data)
        if mode == 0o120000:
            # Links may only target another regular file inside this snapshot.
            target = data.decode("utf-8")
            if PurePosixPath(target).is_absolute() or "\\" in target:
                raise ValueError("External symlink")
            parts = list(path.parent.parts)
            for part in PurePosixPath(target).parts:
                if part == "..":
                    if not parts:
                        raise ValueError("Escaping symlink")
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            linked = entries.get("/".join(parts))
            if linked is None or linked[0] == 0o120000:
                raise ValueError("Symlink target must be an included regular file")
    if total > MAX_TOTAL:
        raise ValueError("Oversized artifact")


def collect(source, base=False):
    source = source.resolve()
    entries = {}
    if base:
        raw = subprocess.check_output(["git", "-C", str(source), "archive", COMMIT])
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            for member in archive:
                if member.isdir():
                    continue
                if member.issym():
                    entries[member.name] = (0o120000, member.linkname.encode())
                elif member.isfile():
                    mode = 0o100755 if member.mode & 0o111 else 0o100644
                    entries[member.name] = (mode, archive.extractfile(member).read())
                else:
                    raise ValueError("Unsupported upstream archive entry")
    else:
        names = (
            subprocess.check_output(["git", "-C", str(source), "ls-files", "-z", "--cached"])
            .decode()
            .split("\0")
        )
        for name in sorted(set(names) - {""}):
            safe_path(name)
            file = source / name
            # Never follow a substituted directory symlink while collecting.
            if any(parent.is_symlink() for parent in file.parents if parent != source):
                raise ValueError("Symlink in source path")
            if not file.exists() and not file.is_symlink():
                continue  # Working-tree deletion is part of the submission.
            mode = file.lstat().st_mode
            if stat.S_ISLNK(mode):
                entries[name] = (0o120000, str(file.readlink()).encode())
            elif stat.S_ISREG(mode):
                if file.stat().st_size > MAX_FILE:
                    raise ValueError("Oversized source file")
                entries[name] = (0o100755 if mode & 0o111 else 0o100644, file.read_bytes())
            else:
                raise ValueError("Only regular files and internal symlinks are supported")
    validate(entries)
    return entries


def write_artifact(entries, destination):
    validate(entries)
    manifest = {"format": 1, "base_commit": COMMIT, "files": []}
    # Exclusive creation: never silently replace a previously submitted artifact.
    with destination.open("xb") as output, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for name, (mode, data) in sorted(entries.items()):
            manifest["files"].append(
                {
                    "path": name,
                    "mode": mode,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            z.writestr("source/" + name, data)
        z.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def read_artifact(artifact):
    if artifact.stat().st_size > MAX_TOTAL:
        raise ValueError("Oversized archive")
    with zipfile.ZipFile(artifact) as z:
        infos = z.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or len(names) > MAX_FILES + 1:
            raise ValueError("Duplicate entries or excessive file count")
        if (
            any(i.file_size > MAX_FILE for i in infos)
            or sum(i.file_size for i in infos) > MAX_TOTAL
        ):
            raise ValueError("Oversized uncompressed archive")
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("format") != 1 or manifest.get("base_commit") != COMMIT:
            raise ValueError("Unsupported artifact format/base")
        entries = {}
        for record in manifest["files"]:
            name = record["path"]
            safe_path(name)
            if name in entries:
                raise ValueError("Duplicate manifest path")
            data = z.read("source/" + name)
            if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("Artifact content does not match manifest")
            entries[name] = (record["mode"], data)
        if set(names) != {"manifest.json", *("source/" + name for name in entries)}:
            raise ValueError("Unexpected artifact contents")
    validate(entries)
    return entries


def volume_tar(entries):
    """Docker-copy stream only; no archive paths are extracted on the host."""
    validate(entries)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        directories = {"."}
        for name in entries:
            directories.update(str(p) for p in PurePosixPath(name).parents)
        for name in sorted(directories, key=lambda p: (p.count("/"), p)):
            info = tarfile.TarInfo(name)
            info.type, info.mode, info.uid, info.gid = tarfile.DIRTYPE, 0o755, 1000, 1000
            archive.addfile(info)
        for name, (mode, data) in sorted(entries.items()):
            info = tarfile.TarInfo(name)
            info.uid = info.gid = 1000
            info.mode = mode & 0o777
            if mode == 0o120000:
                info.type, info.linkname = tarfile.SYMTYPE, data.decode()
                archive.addfile(info)
            else:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--base", action="store_true", help="Export the pinned upstream commit")
    args = parser.parse_args()
    print(write_artifact(collect(args.source, args.base), args.destination))
