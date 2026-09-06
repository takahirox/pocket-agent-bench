"""Public opt-in execution transport. Never infer a program or supply its solution."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

CONTRACT = """
Optional execution transport (pocket-python-v1), identical for every configuration:
You may perform the API workflow directly, OR author a Python program under src/
and output/execute.json containing exactly {"script":"src/your_program.py"}.
If declared, after your final response the harness runs that program ONCE in /app
as the unprivileged agent, using the remaining aggregate time budget. It must perform
the requested operations and write output/result.json itself. Python's standard
library is available. The harness does not infer a program or supply an answer.
Do not both perform state-changing API calls now and declare a program that repeats
them. Internal structural smoke checks do not run the program. This transport is
optional; a final response alone is not the required result artifact.
"""


def declared_script(root):
    root = Path(root).resolve()
    manifest = root / "output/execute.json"
    if not manifest.exists() and not manifest.is_symlink():
        return None
    if manifest.is_symlink() or manifest.parent.is_symlink() or manifest.stat().st_size > 4096:
        raise ValueError("Execution manifest must be a small regular workspace file")
    value = json.loads(manifest.read_text())
    if (
        not isinstance(value, dict)
        or set(value) != {"script"}
        or not isinstance(value["script"], str)
    ):
        raise ValueError('Expected exactly {"script":"src/program.py"}')
    path = Path(value["script"])
    if (
        path.is_absolute()
        or ".." in path.parts
        or len(path.parts) < 2
        or path.parts[0] != "src"
        or path.suffix != ".py"
    ):
        raise ValueError("Execution script must be a Python file below src/")
    target = root / path
    if any(p.is_symlink() for p in [target, *target.parents] if p != root and root in p.parents):
        raise ValueError("Execution script must not traverse symlinks")
    if not target.is_file() or not target.resolve().is_relative_to(root / "src"):
        raise ValueError("Declared script is missing or outside src/")
    return target


def execute(root, seconds, logs):
    logs = Path(logs)
    logs.mkdir(parents=True, exist_ok=True)
    event = {"protocol": "pocket-python-v1", "executed": False}
    code = 0
    try:
        script = declared_script(root)
        if script:
            if seconds <= 0:
                raise TimeoutError("No aggregate agent time remains for declared execution")
            event.update(script=str(script.relative_to(root)), executed=True)
            with (
                (logs / "execution.stdout").open("wb") as out,
                (logs / "execution.stderr").open("wb") as err,
            ):
                proc = subprocess.Popen(
                    [sys.executable, "-I", str(script)],
                    cwd=root,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
                try:
                    code = proc.wait(timeout=seconds)
                except subprocess.TimeoutExpired:
                    code = 124
                    event["error"] = "execution timeout"
                finally:
                    # No child process may continue mutating service state after this phase.
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
    except (ValueError, OSError, TimeoutError) as exc:
        code = 2
        event["error"] = str(exc)
    event["exit_code"] = code
    (logs / "execution.json").write_text(json.dumps(event, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(execute(Path("/app"), float(sys.argv[1]), Path("/logs/agent")))
