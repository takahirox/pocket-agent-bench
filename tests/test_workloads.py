import json
from collections import defaultdict
from pathlib import Path

import pytest

from pocket_bench.grader import grade
from pocket_bench.suite import catalog

ROOT = Path(__file__).resolve().parents[1]
SPECS = [s for name in ("capability", "long-horizon", "web") for s in catalog(ROOT, name)]


def workspace(tmp_path, spec):
    for name, content in spec["files"].items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (tmp_path / "output").mkdir()
    return tmp_path


def evidence(spec):
    if spec.get("api") == "workflow":
        return {
            "requests": ["GET /workflow"],
            "committed": list(spec["expected"]["committed"]),
            "violations": 0,
            "attempts": {j: 2 for j in spec["expected"]["committed"]},
        }
    if spec.get("api") == "browser":
        return {"requests": ["GET /release", "GET /release-data"]}
    if spec.get("api") == "live":
        return {
            "requests": ["GET /live"],
            "live_snapshot": {
                "url": "https://docs.python.org/3/",
                "title": "Actual observed title",
                "sha256": "a" * 64,
            },
        }
    return None


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s["id"])
def test_positive_negative_and_protected_inputs(tmp_path, spec):
    w = workspace(tmp_path, spec)
    trusted = evidence(spec)
    assert grade(spec, w, api_state=trusted)["status"] == "failure"
    if "solution_files" in spec:
        for name, content in spec["solution_files"].items():
            (w / name).write_text(content)
    elif "solution" in spec:
        (w / "src/solution.py").write_text(spec["solution"])
    else:
        result = trusted["live_snapshot"] if spec.get("api") == "live" else spec["expected"]
        (w / "output/result.json").write_text(json.dumps(result))
    assert grade(spec, w, api_state=trusted)["status"] == "success"
    name = next(n for n in spec["files"] if n.startswith("input/"))
    (w / name).write_text("changed")
    assert grade(spec, w, api_state=trusted)["status"] == "failure"


@pytest.mark.parametrize(
    "spec", [s for s in SPECS if s["id"].startswith("ledger-")], ids=lambda s: s["id"]
)
def test_ledger_gold_independently_sorted_fold(spec):
    events = [r for n, text in spec["files"].items() if "shard-" in n for r in json.loads(text)]
    unique = {}
    for r in sorted(events, key=lambda r: r["revision"]):
        unique[r["id"]] = r
    totals = json.loads(spec["files"]["input/checkpoint.json"])
    for r in unique.values():
        totals[r["account"]] += 0 if r["deleted"] else r["amount"]
    assert totals == spec["expected"]


@pytest.mark.parametrize(
    "spec", [s for s in SPECS if s["category"] == "research"], ids=lambda s: s["id"]
)
def test_research_gold_uses_only_approved_evidence(spec):
    grouped = defaultdict(list)
    for name, content in spec["files"].items():
        if name.endswith(".json") and name != "input/scope.json":
            doc = json.loads(content)
            if doc["status"] == "approved":
                grouped[doc["service"]].append((doc["revision"], name, doc))
    observed = {}
    for service, documents in grouped.items():
        _, name, doc = max(documents)
        observed[service] = {k: doc[k] for k in ("owner", "retention_days", "launch_date")}
        observed[service]["source"] = Path(name).name
    assert observed == spec["expected"]


@pytest.mark.parametrize(
    "spec", [s for s in SPECS if s["category"] == "planning"], ids=lambda s: s["id"]
)
def test_schedule_gold_with_recursive_dependency_walk(spec):
    nodes = {n["id"]: n for n in json.loads(spec["files"]["input/graph.json"])}
    from functools import cache

    @cache
    def finish(name):
        node = nodes[name]
        return node["duration"] + max(map(finish, node["after"]), default=0)

    assert {n: finish(n) for n in nodes} == spec["expected"]


def test_workflow_rejects_answer_without_recovery_or_with_duplicate_effects(tmp_path):
    spec = next(s for s in SPECS if s["id"] == "workflow-recovery")
    w = workspace(tmp_path, spec)
    (w / "output/result.json").write_text(json.dumps(spec["expected"]))
    state = evidence(spec)
    state["committed"].append("job-000")
    assert grade(spec, w, api_state=state)["status"] == "failure"
    state = evidence(spec)
    state["attempts"] = {}
    assert grade(spec, w, api_state=state)["status"] == "failure"


def test_live_missing_snapshot_is_unscorable(tmp_path):
    spec = next(s for s in SPECS if s.get("live_web"))
    w = workspace(tmp_path, spec)
    with pytest.raises(RuntimeError, match="snapshot unavailable"):
        grade(spec, w, api_state={"requests": ["GET /live"], "live_error": "TimeoutError"})


def test_repository_entrypoint_only_patch_is_insufficient(tmp_path):
    spec = next(s for s in SPECS if s["id"] == "repository-repair")
    w = workspace(tmp_path, spec)
    (w / "src/solution.py").write_text(spec["solution"])
    result = grade(spec, w)
    assert result["status"] == "failure"
    assert any(
        not c["passed"] and c["name"].startswith("src/revisions.py:case") for c in result["checks"]
    )


def test_live_nop_fails_without_being_mistaken_for_upstream_failure(tmp_path):
    spec = next(s for s in SPECS if s.get("live_web"))
    w = workspace(tmp_path, spec)
    assert grade(spec, w, api_state={"requests": []})["status"] == "failure"
