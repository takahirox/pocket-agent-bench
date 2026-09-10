"""Named workloads and immutable selection identities, separate from agent profiles."""

import hashlib
import json
from pathlib import Path

SUITES = {
    "regression": {"version": "1.1", "attempts": 2, "seconds": 180},
    "capability-smoke": {"version": "1.0", "attempts": 1, "seconds": 600},
    "capability": {"version": "1.1", "attempts": 10, "seconds": 600},
    "long-horizon": {"version": "1.1", "attempts": 10, "seconds": 1800},
    "web": {"version": "1.0", "attempts": 10, "seconds": 600},
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def select(root, name="regression", tasks=None):
    from pocket_bench.suite import catalog

    if name not in SUITES:
        raise ValueError(f"Unknown suite {name!r}; choose from {', '.join(SUITES)}")
    members = catalog(root, name)
    selected = members
    if tasks is not None:
        names = tasks.split(",")
        if not all(names) or len(names) != len(set(names)):
            raise ValueError("Task selection must contain nonempty, unique task IDs")
        missing = set(names) - {s["id"] for s in members}
        if missing:
            raise ValueError(f"Tasks outside suite {name}: {sorted(missing)}")
        selected = [s for s in members if s["id"] in names]
    if not selected:
        raise ValueError("Suite selection is empty")
    sources = {
        n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
        for n in (
            "suite.py",
            "grader.py",
            "execution.py",
            "mock_api.py",
            "bootstrap.py",
            "model_proxy.py",
        )
    }
    fingerprints = {s["id"]: digest({"task": s, "sources": sources}) for s in members}
    return selected, {
        "name": name,
        "version": SUITES[name]["version"],
        "sha256": digest(fingerprints),
        "selection_sha256": digest({s["id"]: fingerprints[s["id"]] for s in selected}),
        "task_fingerprints": {s["id"]: fingerprints[s["id"]] for s in selected},
        "task_ids": [s["id"] for s in selected],
        "tasks": len(selected),
        "available_tasks": len(members),
        "partial": len(selected) != len(members),
        "human_reviewed": False,
        "directional_only": name == "capability-smoke",
        "recommended_attempts": SUITES[name]["attempts"],
    }
