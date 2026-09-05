"""Recompute small gold answers from public inputs, independently of shipped solutions."""

import csv
import io
import itertools
import json
import re
from collections import defaultdict
from pathlib import Path

from pocket_bench.grader import grade
from pocket_bench.suite import catalog

SPECS = {s["id"]: s for s in catalog(Path(__file__).resolve().parents[1])}


def test_sales_gold_from_unique_completed_records():
    spec, orders = SPECS["sales-dedup"], {}
    for text in spec["files"].values():
        for row in csv.DictReader(io.StringIO(text)):
            assert row["order_id"] not in orders or orders[row["order_id"]] == row
            orders[row["order_id"]] = row
    amounts = defaultdict(int)
    for row in orders.values():
        if row["status"] == "completed":
            amounts[row["region"]] += int(row["amount"])
    assert dict(amounts) == spec["expected"]


def test_inventory_gold_from_join():
    spec = SPECS["inventory-join"]
    products = json.loads(spec["files"]["input/products.json"])
    stocks = json.loads(spec["files"]["input/stock.json"])
    assert spec["expected"] == {
        p["sku"]: sum(s["qty"] for s in stocks if s["sku"] == p["sku"]) for p in products
    }


def test_event_gold_from_highest_versions():
    spec = SPECS["event-reconciliation"]
    events = list(itertools.chain.from_iterable(json.loads(s) for s in spec["files"].values()))
    result = {}
    for key in {e["id"] for e in events}:
        last = max((e for e in events if e["id"] == key), key=lambda e: e["version"])
        if not last["deleted"]:
            result[key] = last["value"]
    assert result == spec["expected"]


def test_policy_gold_from_effective_revision():
    spec = SPECS["research-policy"]
    name, doc = max(
        ((n, d) for n, d in spec["files"].items() if "DRAFT" not in d),
        key=lambda item: int(re.search(r"Revision (\d+)", item[1]).group(1)),
    )
    result = {
        service: {"days": int(days), "source": Path(name).name}
        for service, days in re.findall(r"(\w+): (\d+) days", doc)
    }
    assert result == spec["expected"]


def test_confirmed_evidence_gold():
    spec = SPECS["research-evidence"]
    doc = spec["files"]["input/report.txt"]
    result = {
        "owner": re.search(r"Confirmed owner: ([^.]+)", doc).group(1),
        "launch_date": re.search(r"Confirmed launch date: ([^.]+)", doc).group(1),
        "budget": None,
    }
    assert "There is no confirmed budget." in doc
    assert result == spec["expected"]


def test_all_dependency_orderings(tmp_path):
    spec = SPECS["research-dependencies"]
    (tmp_path / "input").mkdir()
    (tmp_path / "output").mkdir()
    for name, content in spec["files"].items():
        (tmp_path / name).write_text(content)
    edges = re.findall(r"(\w) must finish before (\w)", " ".join(spec["files"].values()))
    successes = 0
    for order in itertools.permutations("ABCD"):
        (tmp_path / "output/result.json").write_text(json.dumps(order))
        valid = all(order.index(a) < order.index(b) for a, b in edges)
        assert (grade(spec, tmp_path)["status"] == "success") == valid
        successes += valid
    assert successes == 2


def test_slug_cases_with_character_scanner():
    spec = SPECS["code-slug"]
    for source, expected in spec["cases"]:
        words, word = [], ""
        for char in source.lower():
            if char in "abcdefghijklmnopqrstuvwxyz0123456789":
                word += char
            elif word:
                words.append(word)
                word = ""
        if word:
            words.append(word)
        assert "-".join(words) == expected


def test_chunk_case_properties():
    for (items, size), expected in SPECS["code-chunks"]["cases"]:
        if size <= 0:
            assert expected == {"raises": "ValueError"}
        else:
            assert list(itertools.chain.from_iterable(expected)) == items
            assert all(len(c) == size for c in expected[:-1])
            assert not expected or 0 < len(expected[-1]) <= size


def test_interval_case_coverage_and_separation():
    # These fixtures use integer endpoints. Half-unit coverage catches gaps at touching endpoints.
    for source, expected in SPECS["code-intervals"]["cases"]:

        def coverage(intervals):
            return {n for a, b in intervals for n in range(2 * a, 2 * b + 1)}

        assert coverage(source) == coverage(expected)
        assert all(a[1] < b[0] for a, b in itertools.pairwise(expected))
