"""Exercise the actual inner Codex command sandbox without credentials or a model call."""

import json
import socket
import subprocess
from threading import Thread

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
        "import socket; "
        f"s=socket.create_connection(('127.0.0.1',{port}),timeout=3); "
        "assert s.recv(100)==b'pocket-local-service'; s.close()"
    )
    result = subprocess.run(
        [
            "codex",
            "sandbox",
            "-c",
            'sandbox_mode="workspace-write"',
            "-c",
            "sandbox_workspace_write.network_access=true",
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
print(json.dumps({"codex_inner_sandbox_local_service_access": True}))
