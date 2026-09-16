import copy
import inspect
import json
from pathlib import Path

import pytest

from pocket_bench.grader import grade
from pocket_bench.open_path import billing_gold, catalog, resolver_gold
from pocket_bench.suite import build

SPECS = catalog()


def workspace(tmp_path, spec):
    for name, text in spec["files"].items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s["id"])
def test_reference_alternative_noop_and_preservation(tmp_path, spec):
    w = workspace(tmp_path, spec)
    assert grade(spec, w)["status"] == "failure"
    (w / "src/solution.py").write_text(spec["solution"])
    assert grade(spec, w)["status"] == "success"
    # Structurally different implementations pass without repairing named internal modules.
    gold = resolver_gold if "resolver" in spec["id"] else billing_gold
    alternative = inspect.getsource(gold).replace("def " + gold.__name__ + "(", "def solve(", 1)
    (w / "src/solution.py").write_text(alternative)
    assert grade(spec, w)["status"] == "success"
    (w / "input/incident.md").write_text("changed")
    assert grade(spec, w)["status"] == "failure"


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s["id"])
def test_reference_agrees_with_independent_oracle_and_is_pure(spec):
    namespace = {}
    exec(spec["solution"], namespace)  # noqa: S102 — trusted checked-in reference only
    for request, expected in spec["cases"]:
        original = copy.deepcopy(request)
        assert namespace["solve"](request) == expected
        assert request == original


@pytest.mark.parametrize(
    "old,new",
    [
        ("key = (e['tenant'], e['id'])", "key = e['id']"),
        ("e['revision'] > seen[key]['revision']", "e['revision'] < seen[key]['revision']"),
        ("e.get('deleted', False)", "False"),
        ("e['at'] > request['as_of']", "False"),
        ("min(e.get('discount', 0), sum(floors))", "0"),
        ("tax = (net * line['tax_bps'] * 2 + 10000) // 20000", "tax = 0"),
        ("invoice['refunded'].add(line)", "pass"),
        ("e['at'], e['tenant'], e['id']", "e['at'], e['tenant']"),
        ("min(e.get('discount', 0), sum(floors))", "e.get('discount', 0)"),
    ],
)
def test_plausible_billing_partial_fixes_fail(tmp_path, old, new):
    spec = SPECS[1]
    w = workspace(tmp_path, spec)
    assert old in spec["solution"]
    (w / "src/solution.py").write_text(spec["solution"].replace(old, new))
    assert grade(spec, w)["status"] == "failure"


@pytest.mark.parametrize(
    "old,new",
    [
        ("r.get('yanked', False)", "False"),
        ("request.get('pins', {}).items()", "{}.items()"),
        ("r.get('conflicts', {}).items()", "{}.items()"),
        ("score = (changed, len(versions),", "score = (0, len(versions),"),
        ("tuple(-versions.get(n, 0)", "tuple(versions.get(n, 0)"),
    ],
)
def test_plausible_resolver_partial_fixes_fail(tmp_path, old, new):
    spec = SPECS[0]
    w = workspace(tmp_path, spec)
    assert old in spec["solution"]
    (w / "src/solution.py").write_text(spec["solution"].replace(old, new))
    assert grade(spec, w)["status"] == "failure"


def test_build_keeps_private_cases_and_oracles_out_of_agent_snapshot(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "suite").mkdir()
    (tmp_path / "suite/catalog.json").write_bytes((root / "suite/catalog.json").read_bytes())
    build(tmp_path)
    assert catalog() == SPECS
    for spec in SPECS:
        task = tmp_path / "tasks" / spec["id"]
        private = json.loads((task / "tests/spec.json").read_text())
        assert private["cases"] == spec["cases"]
        assert not (task / "environment/spec.json").exists()
        # Only declared public files enter input/src; the reference is solution-side only.
        for folder in ["input", "src"]:
            actual = {
                str(p.relative_to(task / "environment")): p.read_text()
                for p in (task / "environment" / folder).rglob("*")
                if p.is_file()
            }
            assert actual == {n: t for n, t in spec["files"].items() if n.startswith(folder + "/")}


def test_billing_allocation_uses_ids_not_original_order(tmp_path):
    spec = SPECS[1]
    w = workspace(tmp_path, spec)
    # Sorting the input first is optional if the actual allocation uses ID ties.
    alternative = spec["solution"].replace("key=lambda l: l['id']", "key=lambda l: ''")
    (w / "src/solution.py").write_text(alternative)
    assert grade(spec, w)["status"] == "success"
    (w / "src/solution.py").write_text(alternative.replace("lines[i]['id']", "i"))
    assert grade(spec, w)["status"] == "failure"


def test_candidate_cannot_damage_inputs_during_verification(tmp_path):
    spec = dict(SPECS[0], cases=SPECS[0]["cases"][:1])
    w = workspace(tmp_path, spec)
    malicious = (
        spec["solution"]
        + "\noriginal_solve = solve\ndef solve(request):\n    from pathlib import Path\n    Path('input/incident.md').write_text('damaged')\n    return original_solve(request)\n"
    )
    (w / "src/solution.py").write_text(malicious)
    result = grade(spec, w)
    assert result["status"] == "failure"
    assert any(c["name"] == "case:0" and c["passed"] for c in result["checks"])
    assert any(
        c["name"] == "preserved-final:input/incident.md" and not c["passed"]
        for c in result["checks"]
    )


def test_case_timeout_is_a_bounded_failure(tmp_path, monkeypatch):
    import subprocess

    import pocket_bench.grader as verifier

    spec = SPECS[1]
    w = workspace(tmp_path, spec)
    calls = []

    def timeout(*args, **kwargs):
        calls.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(verifier.subprocess, "run", timeout)
    result = grade(spec, w)
    assert result["status"] == "failure"
    assert calls == [3]
    assert any(c["name"] == "case:0" and not c["passed"] for c in result["checks"])


def test_verifier_allows_every_case_its_execution_guard(tmp_path):
    import tomllib

    root = Path(__file__).resolve().parents[1]
    (tmp_path / "suite").mkdir()
    (tmp_path / "suite/catalog.json").write_bytes((root / "suite/catalog.json").read_bytes())
    build(tmp_path)
    for spec in SPECS:
        config = tomllib.loads((tmp_path / "tasks" / spec["id"] / "task.toml").read_text())
        assert config["verifier"]["timeout_sec"] >= len(spec["cases"]) * 3 + 15
        assert config["agent"]["timeout_sec"] == 3690
