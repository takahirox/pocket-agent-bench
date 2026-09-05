"""Check artifacts against actual auth values without printing those values."""

import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("directory", type=Path)
p.add_argument("--auth", type=Path, default=Path.home() / ".codex/auth.json")
args = p.parse_args()


def values(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from values(x)
    elif isinstance(v, list):
        for x in v:
            yield from values(x)
    elif isinstance(v, str) and len(v) > 40:
        yield v.encode()


secrets = list(values(json.loads(args.auth.read_text())))
if not secrets:
    raise SystemExit("No credential values found to compare; scan not performed")
leaks = []
scanned = 0
for file in args.directory.rglob("*"):
    if file.is_file() and not file.is_symlink():
        scanned += 1
        data = file.read_bytes()
        if any(secret in data for secret in secrets):
            leaks.append(str(file))
print(json.dumps({"files_scanned": scanned, "leaked_files": leaks}))
raise SystemExit(bool(leaks))
