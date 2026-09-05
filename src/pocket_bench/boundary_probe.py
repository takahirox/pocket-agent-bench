"""Read-only preflight, executed before credentials are injected into the container."""

import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

assert os.getuid() == 1000, "Agent must be unprivileged"
assert not Path("/tests/spec.json").exists(), "Private verifier leaked before agent execution"
assert not os.access("/var/lib/pocket", os.R_OK), "Agent can read trusted API evidence"
try:
    with socket.create_connection(("1.1.1.1", 443), timeout=2):
        raise AssertionError("Direct internet egress was possible")
except (TimeoutError, OSError):
    pass
try:
    urllib.request.urlopen("https://example.com", timeout=5)
except urllib.error.URLError as e:
    assert "403" in str(e), f"Expected explicit proxy denial, observed {e}"
else:
    raise AssertionError("Proxy allowed a non-model domain")
print(
    json.dumps(
        {
            "uid": 1000,
            "private_verifier_hidden": True,
            "trusted_state_protected": True,
            "direct_egress_blocked": True,
            "non_model_proxy_denied": True,
        }
    )
)
