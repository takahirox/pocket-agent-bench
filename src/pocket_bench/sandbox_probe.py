"""Exercise the actual inner Codex command sandbox without credentials or a model call."""

import json
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).parent))
from codex_policy import permission_args

policy = sys.argv[1]
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(10)
    port = listener.getsockname()[1]

    def serve():
        connection, _ = listener.accept()
        with connection:
            connection.sendall(b"pocket-local-service")

    thread = Thread(target=serve, daemon=True)
    thread.start()
    command = (
        "import socket,pathlib,errno; "
        f"s=socket.create_connection(('127.0.0.1',{port}),timeout=3); "
        "assert s.recv(100)==b'pocket-local-service'; s.close()"
    )
    path = "/app/output/probe-" + uuid.uuid4().hex
    command += f"\np=pathlib.Path({path!r})\n"
    if policy == "readonly-network":
        command += (
            "try: p.write_text('must-deny')\n"
            "except OSError as e: assert e.errno in (errno.EACCES,errno.EPERM,errno.EROFS)\n"
            "else: raise AssertionError('read-only worker can write')\n"
        )
    else:
        command += "p.write_text('allowed'); p.unlink()\n"
    result = subprocess.run(
        [
            "codex",
            "sandbox",
            *permission_args(policy),
            "--",
            "python",
            "-I",
            "-c",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    thread.join(timeout=1)
print(
    json.dumps({"policy": policy, "local_service_access": True, "filesystem_policy_checked": True})
)
