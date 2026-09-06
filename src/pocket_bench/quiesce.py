"""Trusted post-attempt barrier: stop all task-user processes before transport/grading."""

import os
import signal
import time
from pathlib import Path


def quiesce():
    if os.getuid() != 0:
        raise PermissionError("quiescence requires the trusted container controller")
    deadline = time.monotonic() + 3
    while True:
        active = []
        for path in Path("/proc").glob("[0-9]*/status"):
            try:
                fields = dict(line.split(":", 1) for line in path.read_text().splitlines())
                if fields.get("Uid", "").split()[0] == "1000" and "Z" not in fields.get(
                    "State", ""
                ):
                    active.append(int(path.parent.name))
            except (FileNotFoundError, ProcessLookupError, IndexError):
                continue
        if not active:
            return
        for pid in active:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if time.monotonic() >= deadline:
            raise RuntimeError("task-user process cleanup not confirmed")
        time.sleep(0.02)


if __name__ == "__main__":
    quiesce()
