"""Fail if any reference/no-op control has the wrong grade or missing evidence."""

import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
rows = report["trials"]
assert rows, "No control trials"
counts = {"oracle": 0, "nop": 0}
for row in rows:
    agent = row["agent_config"].get("name") or row["agent"]
    assert agent in counts, f"Unexpected control agent: {agent}"
    expected = "success" if agent == "oracle" else "failure"
    assert row["status"] == expected, (row["task"], agent, row["status"], row.get("exception"))
    counts[agent] += 1
assert counts["oracle"] == counts["nop"] > 0, counts
print(json.dumps(counts))
