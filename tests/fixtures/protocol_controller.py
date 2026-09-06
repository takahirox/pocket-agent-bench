"""Model-free connection probe, deliberately NOT a task solver or an oracle."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    assert request["protocol"] == "pocket-agent-v1"
    if request["operation"] == "cleanup":
        outcome = "cleaned"  # This probe creates no external resources.
    else:
        assert request["operation"] == "run"
        workspace = Path(request["workspace"])
        assert {p.name for p in workspace.iterdir()} <= {"input", "src", "output"}
        assert {p.name for p in Path(request["public_checks"]).iterdir()} == {
            "smoke.py",
            "execution.py",
        }
        (workspace / "output/result.json").write_text("{}")
        outcome = "completed"
    args.response.write_text(json.dumps({"protocol": "pocket-agent-v1", "outcome": outcome}))


if __name__ == "__main__":
    main()
