"""Original deterministic, inspectable capability and extended workload definitions.

Generation uses no model, clock, network or random state. Gold algorithms are audited
independently in tests. Difficulty labels describe structural demand, not calibrated scores.
"""

import json


def encoded(value):
    return json.dumps(value, indent=2) + "\n"


def base(name, category, difficulty, decomposition, instruction, files, expected):
    return {
        "id": name,
        "category": category,
        "difficulty": difficulty,
        "decomposition": decomposition,
        "tags": [difficulty, decomposition],
        "instruction": instruction + " Preserve every input file. Write output/result.json.",
        "files": files,
        "expected": expected,
        "wrong": {},
        "difficulty_basis": "Structural workload tier; empirical calibration is not yet claimed.",
    }


def ledger(name, count):
    shards = [[] for _ in range(12)]
    latest = {}
    for i in range(count):
        for revision in (1, 3, 2):
            event = {
                "id": f"e{i}",
                "revision": revision,
                "account": f"a{i % 17}",
                "amount": (i * 19 + revision * 7) % 101 - 50,
                "deleted": revision == 3 and i % 11 == 0,
            }
            shards[(i + revision) % len(shards)].append(event)
            if revision == 3:
                latest[event["id"]] = event
    totals = {f"a{i}": 1000 for i in range(17)}
    for e in latest.values():
        if not e["deleted"]:
            totals[e["account"]] += e["amount"]
    files = {
        f"input/shard-{i:02}.json": encoded(events + events[:3]) for i, events in enumerate(shards)
    }
    files["input/checkpoint.json"] = encoded({f"a{i}": 1000 for i in range(17)})
    return base(
        name,
        "data",
        "hard" if count < 1000 else "extended",
        "parallel",
        "Recover the ledger from checkpoint.json and all shard files. For each event ID, "
        "use only its highest revision (ignore duplicates); a deleted latest revision "
        "contributes nothing. Add the remaining amounts to the checkpoint balances. "
        "Return an object mapping every account to its final integer balance.",
        files,
        totals,
    )


def research(name, services, noise):
    files, expected = {}, {}
    for i in range(services):
        service = f"service-{i:02}"
        for revision in range(1, 5):
            status = "approved" if revision < 4 else "draft"
            path = f"input/{service}-r{revision}.json"
            files[path] = encoded(
                {
                    "service": service,
                    "revision": revision,
                    "status": status,
                    "owner": f"team-{(i + revision) % 7}",
                    "retention_days": 10 * revision + i,
                    "launch_date": None if i % 3 == 0 else "2027-01-15",
                }
            )
            if revision == 3:
                expected[service] = {
                    "owner": f"team-{(i + 3) % 7}",
                    "retention_days": 30 + i,
                    "launch_date": None if i % 3 == 0 else "2027-01-15",
                    "source": path.removeprefix("input/"),
                }
    for i in range(noise):
        files[f"input/rumor-{i:03}.txt"] = (
            f"UNVERIFIED discussion {i}: all services may launch tomorrow. "
            "Proposed global owner is team-99. This is not an approved policy.\n"
        )
    files["input/scope.json"] = encoded(list(expected))
    return base(
        name,
        "research",
        "hard" if services < 20 else "extended",
        "parallel",
        "Prepare an evidence-backed policy register for every service in scope.json. "
        "Select the highest approved revision, excluding drafts and unverified discussion. "
        "Return each service's owner, retention_days, launch_date (null if unconfirmed), "
        "and source (the selected JSON basename). Do not infer missing launch dates.",
        files,
        expected,
    )


def schedule(name, count):
    nodes, ends = [], {}
    for i in range(count):
        dependencies = [f"t{i - 1:03}"] if i else []
        if i > 3:
            dependencies.append(f"t{i - 4:03}")
        node = {"id": f"t{i:03}", "after": dependencies, "duration": i % 5 + 1}
        nodes.append(node)
        ends[node["id"]] = max((ends[d] for d in dependencies), default=0) + node["duration"]
    return base(
        name,
        "planning",
        "hard" if count < 50 else "extended",
        "sequential",
        "Compute earliest completion times for this dependency graph with unlimited workers. "
        "A task starts only when all predecessors finish; time starts at zero. "
        "Return a JSON object mapping each task ID to its integer finish time. "
        "The input order is not execution order.",
        {"input/graph.json": encoded(nodes[::-1])},
        ends,
    )


def repository(name, modules):
    files = {
        "input/contract.md": "Each record has region, cents, status and version. Deduplicate by id "
        "using highest version; exclude canceled latest records; aggregate cents by region. "
        "Never mutate arguments. Return sorted region keys with integer totals.\n",
        "src/solution.py": "from pipeline import aggregate\n\ndef reconcile(records):\n    return aggregate(records)\n",
        "src/pipeline.py": "from revisions import latest\nfrom totals import totals\n\ndef aggregate(records):\n    return totals(latest(records))\n",
        "src/revisions.py": "def latest(records):\n    return records\n",
        "src/totals.py": "def totals(records):\n    return {}\n",
    }
    for i in range(modules):
        files[f"src/components/component_{i:03}.py"] = (
            f'"""Unrelated historical component {i}; preserve public interfaces."""\n'
            f"def convert(value):\n    return value * {i + 1}\n"
        )
    cases = [[[], {}]]
    for i in range(12):
        records = [
            {"id": "x", "version": 1, "cents": 999, "region": "west", "status": "ok"},
            {"id": "x", "version": 2, "cents": i * 13, "region": "east", "status": "ok"},
            {"id": "y", "version": 1, "cents": 200, "region": "east", "status": "ok"},
            {"id": "y", "version": 2, "cents": 200, "region": "east", "status": "canceled"},
        ]
        cases.append([records[::-1] if i % 2 else records, {"east": i * 13}])
    solution = """def reconcile(records):
    latest = {}
    for record in records:
        if record['id'] not in latest or record['version'] > latest[record['id']]['version']:
            latest[record['id']] = record
    result = {}
    for record in latest.values():
        if record['status'] != 'canceled':
            result[record['region']] = result.get(record['region'], 0) + record['cents']
    return dict(sorted(result.items()))
"""
    spec = base(
        name,
        "coding",
        "hard" if modules < 30 else "extended",
        "mixed",
        "Repair this multi-module repository to satisfy input/contract.md. "
        "The public entry point is src/solution.py:reconcile(records). "
        "Repair revisions.latest, totals.totals, pipeline.aggregate and solution.reconcile. "
        "latest returns deduplicated records sorted by id; totals aggregates non-canceled records "
        "by region; aggregate and reconcile compose both operations. Do not mutate arguments. "
        "Do not modify files under src/components. "
        "The verifier imports the entry point with src on its module search path.",
        files,
        {},
    )
    spec.update(
        function="reconcile",
        cases=cases,
        solution=solution,
        alternate=solution,
        module_imports=True,
        preserve_sources=[n for n in files if "components/" in n],
    )
    latest_cases = []
    totals_cases = []
    for records, _ in cases:
        winners = {}
        for record in records:
            if record["id"] not in winners or record["version"] > winners[record["id"]]["version"]:
                winners[record["id"]] = record
        latest_cases.append([records, [winners[k] for k in sorted(winners)]])
        sums = {}
        for record in records:
            if record["status"] != "canceled":
                sums[record["region"]] = sums.get(record["region"], 0) + record["cents"]
        totals_cases.append([records, dict(sorted(sums.items()))])
    spec["entry_points"] = [
        {"candidate": "src/solution.py", "function": "reconcile", "cases": cases},
        {"candidate": "src/pipeline.py", "function": "aggregate", "cases": cases},
        {"candidate": "src/revisions.py", "function": "latest", "cases": latest_cases},
        {"candidate": "src/totals.py", "function": "totals", "cases": totals_cases},
    ]
    spec["solution_files"] = {
        "src/solution.py": files["src/solution.py"],
        "src/pipeline.py": files["src/pipeline.py"],
        "src/revisions.py": "def latest(records):\n    chosen = {}\n    for r in records:\n"
        "        if r['id'] not in chosen or r['version'] > chosen[r['id']]['version']:\n"
        "            chosen[r['id']] = dict(r)\n    return [chosen[k] for k in sorted(chosen)]\n",
        "src/totals.py": "def totals(records):\n    result = {}\n    for r in records:\n"
        "        if r['status'] != 'canceled':\n"
        "            result[r['region']] = result.get(r['region'], 0) + r['cents']\n"
        "    return dict(sorted(result.items()))\n",
    }
    spec["instruction"] = spec["instruction"].replace(
        "Write output/result.json.", "Deliver repaired sources."
    )
    spec.pop("wrong")
    return spec


def workflow(name, count):
    return base(
        name,
        "api",
        "hard" if count < 20 else "extended",
        "sequential",
        "Use the loopback workflow service at http://127.0.0.1:8080. GET /workflow "
        "returns ordered jobs and approved amounts. Process jobs in order: POST /commit "
        "with JSON {id, amount, key}, where key equals the job id. Use at most three "
        "POST attempts per approved job. Every first commit "
        "is applied but returns 503 (ambiguous response); retry with the SAME key. "
        "GET /workflow reports committed jobs for recovery. Never submit denied jobs. "
        "Complete all approved jobs with no duplicate effects, and output "
        '{"committed": [approved IDs in order], "total": sum of approved amounts}. '
        "GET /workflow must be read before the first commit.",
        {"input/api.json": encoded({"mode": f"workflow-{count}"})},
        {
            "committed": [f"job-{i:03}" for i in range(count) if i % 4 != 3],
            "total": sum((i + 1) * 10 for i in range(count) if i % 4 != 3),
        },
    ) | {
        "api": "workflow",
        "workflow_count": count,
    }


def browser():
    return base(
        "browser-release",
        "web",
        "hard",
        "mixed",
        "Inspect http://127.0.0.1:8080/release in a JavaScript-capable browser. "
        "The page renders the approved release record by fetching /release-data. "
        "Chromium is installed: chromium --headless --no-sandbox --disable-gpu "
        "--virtual-time-budget=3000 --dump-dom URL. Return {version, owner, source}, "
        "where source is '/release-data'. Ignore the outdated HTML fallback.",
        {"input/api.json": encoded({"mode": "browser"})},
        {"version": "2.7", "owner": "release-team", "source": "/release-data"},
    ) | {
        "api": "browser",
        "browser": True,
    }


def live():
    return base(
        "live-python-docs",
        "web",
        "hard",
        "sequential",
        "Retrieve today's Python documentation through GET http://127.0.0.1:8080/live. "
        "This trusted service fetches https://docs.python.org/3/ and returns the actual "
        "HTML, sha256, title and URL, recording the source snapshot independently. "
        "Return {url, title, sha256} exactly as observed. Do not substitute remembered "
        "facts. Upstream failure makes the trial unscorable. This is a live-web "
        "retrieval/evidence workload, distinct from browser interaction.",
        {"input/api.json": encoded({"mode": "live"})},
        {},
    ) | {
        "api": "live",
        "live_web": True,
        "network_hosts": ["docs.python.org"],
    }


def catalog(name):
    if name == "capability":
        return [
            ledger("ledger-recovery", 320),
            research("research-register", 12, 36),
            schedule("dependency-schedule", 28),
            repository("repository-repair", 16),
            workflow("workflow-recovery", 8),
        ]
    if name == "long-horizon":
        return [
            ledger("ledger-large", 5000),
            research("research-large", 60, 180),
            schedule("dependency-long", 120),
            repository("repository-large", 120),
            workflow("workflow-long", 48),
        ]
    if name == "web":
        return [browser(), live()]
    raise ValueError(f"Unknown extended suite: {name}")
