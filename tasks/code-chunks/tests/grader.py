"""Trusted verifier. Candidate code is executed only inside the task container.

The CLI requires an explicit workspace. Report checks separately from verifier errors.
Never import an agent-produced module into this process.
"""

import json
import subprocess
import sys
from pathlib import Path


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        path.read_text(),
        object_pairs_hook=unique,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)),
    )


def equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def grade(spec, workspace, *, api_state=None):
    workspace = Path(workspace).resolve()
    checks = []

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    def safe_file(relative):
        p = workspace / relative
        if p.is_symlink() or not p.resolve().is_relative_to(workspace):
            raise ValueError("artifact escapes workspace")
        if not p.is_file() or p.stat().st_size > 1_000_000:
            raise ValueError("missing or oversized artifact")
        return p

    for name, original in spec["files"].items():
        if not name.startswith("input/"):
            continue
        try:
            same = safe_file(name).read_bytes() == original.encode()
        except (OSError, ValueError):
            same = False
        check("preserved:" + name, same, "Input content must match its initial bytes.")
    for name in spec.get("preserve_sources", []):
        try:
            same = safe_file(name).read_text() == spec["files"][name]
        except (OSError, ValueError):
            same = False
        check("preserved:" + name, same)
    if spec.get("api") == "live":
        if api_state is None or (
            "GET /live" in api_state.get("requests", []) and not api_state.get("live_snapshot")
        ):
            raise RuntimeError("Trusted live source snapshot unavailable; cannot grade")
        if api_state.get("live_snapshot"):
            spec = {
                **spec,
                "expected": {k: api_state["live_snapshot"][k] for k in ("url", "title", "sha256")},
            }
    if "entry_points" in spec:
        for endpoint in spec["entry_points"]:
            child = {k: v for k, v in spec.items() if k != "entry_points"}
            child.update(endpoint)
            result = grade(child, workspace, api_state=api_state)
            checks.extend(
                {**c, "name": endpoint["candidate"] + ":" + c["name"]} for c in result["checks"]
            )
        return {
            "verifier_version": "1",
            "status": "success" if all(c["passed"] for c in checks) else "failure",
            "checks": checks,
        }
    if "function" in spec:
        try:
            candidate = safe_file(spec.get("candidate", "src/solution.py"))
        except (ValueError, OSError) as e:
            check("candidate", False, str(e))
        else:
            # No expected answer or grading code enters the candidate interpreter.
            probe = """import importlib.util,json,sys,copy
if len(sys.argv)>5 and sys.argv[5]=='1': sys.path.insert(0,str(__import__('pathlib').Path(sys.argv[1]).parent))
s=importlib.util.spec_from_file_location('candidate',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
a=json.loads(sys.argv[3]);before=copy.deepcopy(a)
try:
 r=getattr(m,sys.argv[2])(*a) if sys.argv[4]=='1' else getattr(m,sys.argv[2])(a)
 print(json.dumps({'returned':r,'mutated':a!=before}))
except Exception as e: print(json.dumps({'raises':type(e).__name__,'mutated':a!=before}))
"""
            for i, (args, expected) in enumerate(spec["cases"]):
                try:
                    p = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            "-c",
                            probe,
                            str(candidate),
                            spec["function"],
                            json.dumps(args),
                            str(int(spec.get("star_args", False))),
                            str(int(spec.get("module_imports", False))),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=3,
                        cwd=workspace,
                        check=False,
                        user=1000
                        if hasattr(__import__("os"), "getuid") and __import__("os").getuid() == 0
                        else None,
                    )
                    actual = json.loads(p.stdout)
                    wanted = (
                        expected
                        if isinstance(expected, dict) and "raises" in expected
                        else {"returned": expected}
                    )
                    wanted = {**wanted, "mutated": False}
                    check(
                        f"case:{i}",
                        p.returncode == 0 and equal(actual, wanted),
                        f"expected {wanted!r}; observed {actual!r}",
                    )
                except subprocess.TimeoutExpired:
                    check(f"case:{i}", False, "Candidate exceeded 3-second case limit.")
                except (ValueError, OSError) as e:
                    check(f"case:{i}", False, str(e))
    else:
        try:
            actual = load_json(safe_file("output/result.json"))
            if "edges" in spec:
                ok = (
                    isinstance(actual, list)
                    and all(isinstance(v, str) for v in actual)
                    and len(actual) == len(spec["expected"])
                    and set(actual) == set(spec["expected"])
                    and all(actual.index(a) < actual.index(b) for a, b in spec["edges"])
                )
            else:
                ok = equal(actual, spec["expected"])
            check("result", ok, f"expected {spec['expected']!r}; observed {actual!r}")
        except (OSError, ValueError, TypeError) as e:
            check("result", False, str(e))
    if spec.get("api"):
        if api_state is None:
            raise RuntimeError("Trusted API evidence missing; cannot grade this trial")
        requests = api_state["requests"]
        if spec["api"] == "pagination":
            check(
                "all-pages-requested",
                all(x in requests for x in ("GET /items", "GET /items?page=2")),
            )
        elif spec["api"] == "retry":
            check("bounded-recovery", 3 <= api_state["value_attempts"] <= 4)
        elif spec["api"] == "workflow":
            wanted = spec["expected"]["committed"]
            check("ordered-exactly-once", api_state.get("committed") == wanted)
            check("no-denied-or-invalid-actions", api_state.get("violations") == 0)
            check(
                "recovered-ambiguous-commits",
                all(
                    1 <= api_state.get("attempts", {}).get(job, 0) <= 3
                    and (
                        job in api_state.get("confirmed_via_get", [])
                        or job in api_state.get("confirmed_via_retry", [])
                    )
                    for job in wanted
                ),
            )
            first_commit = next(
                (i for i, request in enumerate(requests) if request == "POST /commit"),
                len(requests),
            )
            check("read-before-write", "GET /workflow" in requests[:first_commit])
        elif spec["api"] == "browser":
            check(
                "page-and-dynamic-data-read",
                all(path in requests for path in ("GET /release", "GET /release-data")),
            )
        elif spec["api"] == "live":
            check("trusted-source-read", "GET /live" in requests)
        else:
            check("approval-read", "GET /request" in requests and "GET /approval" in requests)
            check("no-unapproved-execution", api_state["executions"] == 0)
    return {
        "verifier_version": "1",
        "status": "success" if all(c["passed"] for c in checks) else "failure",
        "checks": checks,
    }


if __name__ == "__main__":
    # Agent environment has already stopped. Remove any pre-existing, untrusted reward
    # files (including reward.json, which Harbor otherwise prefers over reward.txt).
    logs = Path("/logs/verifier")
    logs.mkdir(parents=True, exist_ok=True)
    for name in ("reward.json", "reward.txt", "checks.json"):
        (logs / name).unlink(missing_ok=True)
    spec = load_json(Path(sys.argv[1]))
    state = load_json(Path("/var/lib/pocket/state.json")) if spec.get("api") else None
    result = grade(spec, sys.argv[2], api_state=state)
    (logs / "checks.json").write_text(json.dumps(result, indent=2))
    (logs / "reward.txt").write_text("1" if result["status"] == "success" else "0")
