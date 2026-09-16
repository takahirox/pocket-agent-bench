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
