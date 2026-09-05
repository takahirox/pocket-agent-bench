import json
from pathlib import Path

import pytest

from pocket_bench.grader import equal, grade
from pocket_bench.suite import catalog

ROOT = Path(__file__).resolve().parents[1]
SPECS = catalog(ROOT)


def fixture(tmp_path, spec):
    for name, text in spec["files"].items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    (tmp_path / "output").mkdir(exist_ok=True)
    return tmp_path


def state(spec):
    return (
        {
            "requests": ["GET /items", "GET /items?page=2", "GET /request", "GET /approval"],
            "executions": 0,
            "value_attempts": 3,
        }
        if spec.get("api")
        else None
    )


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s["id"])
def test_reference_and_alternate(tmp_path, spec):
    w = fixture(tmp_path, spec)
    if "solution" in spec:
        (w / "src/solution.py").write_text(spec["solution"])
    else:
        (w / "output/result.json").write_text(json.dumps(spec["expected"]))
    assert grade(spec, w, api_state=state(spec))["status"] == "success"
    if "solution" in spec:
        (w / "src/solution.py").write_text(spec["alternate"])
    else:
        result = spec.get("alternate_result", spec["expected"])
        (w / "output/result.json").write_text(json.dumps(result, indent=4, sort_keys=True) + "\n")
    assert grade(spec, w, api_state=state(spec))["status"] == "success"


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s["id"])
def test_nop_and_wrong(tmp_path, spec):
    w = fixture(tmp_path, spec)
    assert grade(spec, w, api_state=state(spec))["status"] == "failure"
    if "wrong" in spec:
        (w / "output/result.json").write_text(json.dumps(spec["wrong"]))
        assert grade(spec, w, api_state=state(spec))["status"] == "failure"


@pytest.mark.parametrize(
    "spec", [s for s in SPECS if s["category"] != "coding"], ids=lambda s: s["id"]
)
def test_protected_input(tmp_path, spec):
    w = fixture(tmp_path, spec)
    (w / "output/result.json").write_text(json.dumps(spec["expected"]))
    (w / next(iter(spec["files"]))).write_text("modified")
    assert grade(spec, w, api_state=state(spec))["status"] == "failure"


def test_api_without_evidence_is_unscorable(tmp_path):
    spec = SPECS[-1]
    w = fixture(tmp_path, spec)
    with pytest.raises(RuntimeError):
        grade(spec, w)


def test_unapproved_action_fails_even_with_correct_output(tmp_path):
    spec = SPECS[-1]
    w = fixture(tmp_path, spec)
    (w / "output/result.json").write_text(json.dumps(spec["expected"]))
    evidence = state(spec)
    evidence["executions"] = 1
    assert grade(spec, w, api_state=evidence)["status"] == "failure"


def test_bool_is_not_integer():
    assert not equal(True, 1)


def test_duplicate_json_and_escape_rejected(tmp_path):
    spec = SPECS[0]
    w = fixture(tmp_path, spec)
    p = w / "output/result.json"
    p.write_text('{"east":0,"east":1500,"west":2000,"north":4000}')
    assert grade(spec, w)["status"] == "failure"
    p.unlink()
    p.symlink_to("/etc/passwd")
    assert grade(spec, w)["status"] == "failure"
