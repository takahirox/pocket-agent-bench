"""Bound verifier command time/output without treating either as product correctness."""

import os
import selectors
import signal
import subprocess
import time


def run_bounded(args, log_path, timeout, max_bytes=16 * 1024 * 1024):
    started = time.monotonic()
    reason = None
    count = 0
    with (
        log_path.open("wb") as log,
        subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True
        ) as process,
    ):
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                if time.monotonic() - started >= timeout:
                    reason = "timeout"
                    break
                for key, _ in selector.select(timeout=0.1):
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = max_bytes - count
                    log.write(data[:remaining])
                    log.flush()
                    count += len(data)
                    if count > max_bytes:
                        reason = "output_limit"
                        break
                if reason:
                    break
            if not reason:
                try:
                    process.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
                except subprocess.TimeoutExpired:
                    reason = "timeout"
        finally:
            selector.close()
            if process.poll() is None or reason:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
    return process.returncode, reason
