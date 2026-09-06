"""Product-neutral, operator-selected agent connection profiles (pocket-agent-v1)."""

import asyncio
import hashlib
import json
import math
import os
import shutil
import signal
import tempfile
from contextlib import contextmanager
from pathlib import Path

PROTOCOL = "pocket-agent-v1"
MAX_RESPONSE = 1_000_000


@contextmanager
def controller_directory(logs_dir):
    """Keep private recovery evidence if cleanup cannot be confirmed."""
    directory = Path(tempfile.mkdtemp(prefix="pocket-controller-"))
    recovery = Path(logs_dir) / "controller-recovery.json"
    recovery.write_text(json.dumps({"directory": str(directory), "cleanup": "pending"}))
    try:
        yield directory
    finally:
        try:
            confirmed = read_response(directory / "cleanup.json")["outcome"] == "cleaned"
        except (OSError, ValueError, TypeError):
            confirmed = False
        if confirmed:
            shutil.rmtree(directory)  # exact controller-owned disposable directory
            recovery.write_text(json.dumps({"cleanup": "confirmed"}))
        else:
            recovery.write_text(json.dumps({"directory": str(directory), "cleanup": "unconfirmed"}))


def load_profiles(path, allow_host=False):
    document = json.loads(Path(path).read_text())
    if document.get("protocol") != PROTOCOL or not isinstance(document.get("profiles"), dict):
        raise ValueError("expected pocket-agent-v1 profiles document")
    profiles = document["profiles"]
    for name, profile in profiles.items():
        if not name or not isinstance(profile, dict):
            raise ValueError("invalid profile")
        if profile.get("execution") not in ("cli", "host-controller"):
            raise ValueError("execution must be cli or host-controller")
        argv = profile.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(x, str) or not x for x in argv)
        ):
            raise ValueError("argv must be a nonempty string array, not a shell command")
        if profile["execution"] == "host-controller" and not allow_host:
            raise ValueError("trusted host controllers require --allow-host-controller")
        if profile.get("input", "argument") not in ("argument", "stdin", "request"):
            raise ValueError("unsupported CLI input mode")
        if profile.get("mode", "single") not in ("single", "team"):
            raise ValueError("mode must describe single or team")
        if not isinstance(profile.get("agent", name), str):
            raise TypeError("agent must be a string")
    return profiles


def public_profile(profile):
    """Store identity/digest, never operator argv/settings/credential paths in reports."""
    return {
        "agent": profile["agent"],
        "mode": profile.get("mode", "single"),
        "execution": profile["execution"],
        "protocol": PROTOCOL,
        "sha256": hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest(),
    }


def render_argv(argv, values):
    # Only entire argv elements are substituted; instruction contents are never evaluated.
    return [
        str(values.get(item[1:-1], item)) if item.startswith("{") and item.endswith("}") else item
        for item in argv
    ]


def read_response(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RESPONSE:
        raise ValueError("missing or oversized controller response")
    result = json.loads(path.read_text())
    if not isinstance(result, dict) or result.get("protocol") != PROTOCOL:
        raise ValueError("controller protocol mismatch")
    if result.get("outcome") not in ("completed", "failed", "usage_limit", "cleaned"):
        raise ValueError("invalid controller outcome (not a benchmark grade)")
    usage = result.get("usage", {})
    if usage is None:
        usage = {}
    if not isinstance(usage, dict):
        raise TypeError("invalid usage")
    for name in ("input_tokens", "output_tokens", "cached_input_tokens"):
        value = usage.get(name)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("invalid usage count")
    return result


async def controller_call(argv, request, response, seconds):
    if not math.isfinite(seconds) or seconds <= 0:
        raise TimeoutError("controller deadline exhausted")
    command = render_argv(argv, {"request": request, "response": response})
    if "{request}" not in argv or "{response}" not in argv:
        raise ValueError("controller argv must explicitly include {request} and {response}")
    # Controller is explicitly trusted host software, not agent-generated code. No shell.
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(Path(request).parent),
        start_new_session=True,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(process.wait(), seconds)
    finally:
        # Include children even if the controller exited first. Its external resources
        # are separately handled by the mandatory cleanup operation.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
    result = read_response(response)
    if process.returncode != 0:
        raise RuntimeError("controller exited unsuccessfully")
    return result
