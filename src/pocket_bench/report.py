"""Normalize Harbor artifacts without dropping failed or interrupted trials."""

import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

from pocket_bench.metrics import cohort, comparisons, efficiency, uncertainty


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def duration(timing):
    try:
        return max(
            0,
            (
                datetime.fromisoformat(timing["finished_at"])
                - datetime.fromisoformat(timing["started_at"])
            ).total_seconds(),
        )
    except (KeyError, TypeError, ValueError):
        return None


def normalize(job_path):
    job_path = Path(job_path)
    rows = []
    plan = read(job_path / "pocket-plan.json", {})
    specs = {s["id"]: s for s in plan.get("tasks", [])}
    for trial in sorted(job_path.iterdir()):
        if not trial.is_dir() or not (trial / "lock.json").exists():
            continue
        r = read(trial / "result.json", {})
        config = r.get("config") or read(trial / "config.json", {})
        task_name = r.get("task_name", trial.name.split("__")[0]).removeprefix("pocket/")
        task_path = Path(config.get("task", {}).get("path", "/nonexistent"))
        spec = specs.get(task_name) or read(task_path / "tests/spec.json", {})
        checks = read(trial / "verifier/checks.json", {})
        rewards = (r.get("verifier_result") or {}).get("rewards")
        exc = r.get("exception_info")
        agent = r.get("agent_result") or {}
        metadata = agent.get("metadata") or {}
        kwargs = config.get("agent", {}).get("kwargs", {})
        ac = config.get("agent", {})
        import_path = ac.get("import_path") or ""
        fallback = (
            "my-ai-employee"
            if "FleetAgent" in import_path
            else ("pocket-codex" if "CodexAgent" in import_path else ac.get("name", "unknown"))
        )
        agent_name = r.get("agent_info", {}).get("name", fallback)
        mode = metadata.get("mode", kwargs.get("mode", "single"))
        profile_name = kwargs.get("profile_name")
        identity = plan.get("profile_metadata", {}).get(profile_name, {})
        if profile_name:
            agent_name = identity.get("agent", metadata.get("agent", profile_name))
            mode = identity.get("mode", metadata.get("mode", "single"))
        status = "unscorable"
        if isinstance(rewards, dict) and "reward" in rewards:
            status = "success" if rewards["reward"] == 1 else "failure"
        # Diagnostic files alone cannot establish a grade: the agent can create logs.
        if (
            rewards is not None
            and checks.get("status") in ("success", "failure")
            and checks["status"] != status
        ):
            status = "unscorable"
        error_type = (exc or {}).get("exception_type", "")
        stage = (
            "verifier"
            if any(s in error_type.lower() for s in ("verifier", "reward"))
            else "unknown"
        )
        if "AgentSetup" in error_type:
            stage = "agent_setup"
        elif "AgentTimeout" in error_type:
            stage = "agent_timeout"
        elif "Environment" in error_type:
            stage = "environment"
        if not r:
            exc = {
                "exception_type": "MissingTrialResult",
                "exception_message": "Trial did not produce a result; see job log.",
            }
        if stage == "agent_timeout" and status == "unscorable":
            status = "failure"
        outputs = {}
        for p in sorted((trial / "agent").glob("*")) if (trial / "agent").exists() else []:
            if p.is_file() and p.suffix in (
                ".txt",
                ".json",
                ".stdout",
                ".stderr",
                ".patch",
                ".jsonl",
            ):
                outputs[p.name] = p.read_text(errors="replace")[:100_000]
        artifacts = {}
        for p in sorted((trial / "artifacts/app").rglob("*")):
            if p.is_file() and not p.is_symlink() and p.stat().st_size <= 100_000:
                artifacts[str(p.relative_to(trial / "artifacts/app"))] = p.read_text(
                    errors="replace"
                )
        rows.append(
            {
                "id": trial.name,
                "job": job_path.name,
                "task": task_name,
                "category": spec.get("category", "unknown"),
                "tags": spec.get("tags", []),
                "status": status,
                "agent": agent_name,
                "mode": mode,
                "model": (r.get("agent_info", {}).get("model_info") or {}).get("name"),
                "condition": profile_name or agent_name + "/" + mode,
                "profile_name": profile_name,
                "task_checksum": r.get("task_checksum"),
                "evaluation_kind": "regrade"
                if r.get("source_trial", {}).get("action") == "regrade"
                else "run",
                "regrade_verifier_sha256": r.get("regrade_verifier_sha256"),
                "seconds": duration(r.get("agent_execution") or {}),
                "total_seconds": duration(r),
                "tokens_in": agent.get("n_input_tokens"),
                "tokens_out": agent.get("n_output_tokens"),
                "tokens_cached": agent.get("n_cache_tokens"),
                "cost_usd": agent.get("cost_usd"),
                "metadata": metadata,
                "checks": checks.get("checks", []),
                "exception": exc,
                "failure_stage": stage if exc else None,
                "instruction": spec.get("instruction", ""),
                "artifacts": artifacts,
                "service_evidence": read(trial / "artifacts/var/lib/pocket/state.json"),
                "environment_evidence": read(trial / "artifacts/var/lib/pocket/environment.json"),
                "logs": outputs,
                "agent_config": config.get("agent", {}),
                "human_reviewed": False,
            }
        )
    for profile in plan.get("profiles", []):
        agent_name = (
            "my-ai-employee"
            if profile.startswith("fleet")
            else ("pocket-codex" if profile.startswith("codex") else profile)
        )
        mode = "team" if profile.endswith("team") else "single"
        identity = plan.get("profile_metadata", {}).get(profile)
        if identity:
            agent_name, mode = identity["agent"], identity["mode"]
        for spec in plan.get("tasks", []):
            present = sum(
                r["task"] == spec["id"]
                and (
                    r.get("profile_name") == profile
                    if identity
                    else r["agent"] == agent_name and r["mode"] == mode
                )
                for r in rows
            )
            for i in range(present, plan["attempts"]):
                rows.append(
                    {
                        "id": f"missing-{profile}-{spec['id']}-{i}",
                        "job": job_path.name,
                        "task": spec["id"],
                        "category": spec["category"],
                        "tags": spec["tags"],
                        "status": "unscorable",
                        "agent": agent_name,
                        "mode": mode,
                        "condition": profile if identity else agent_name + "/" + mode,
                        "profile_name": profile if identity else None,
                        "model": None,
                        "task_checksum": None,
                        "seconds": None,
                        "total_seconds": None,
                        "tokens_in": None,
                        "tokens_out": None,
                        "cost_usd": None,
                        "metadata": {},
                        "checks": [],
                        "exception": read(
                            job_path / "pocket-error.json",
                            {"message": "Scheduled trial has no recorded result"},
                        ),
                        "failure_stage": "setup_or_interrupted",
                        "instruction": spec["instruction"],
                        "artifacts": {},
                        "logs": {},
                        "agent_config": {},
                        "human_reviewed": False,
                    }
                )
    invalid = read(job_path / "pocket-invalidation.json")
    for r in rows:
        spec = specs.get(r["task"], {})
        selection = plan.get("suite") or {}
        r["suite_name"] = selection.get("name", "legacy")
        r["suite_version"] = selection.get("version")
        r["suite_partial"] = selection.get("partial")
        r["directional_only"] = selection.get("directional_only", False)
        r["difficulty"] = spec.get(
            "difficulty", "short" if r["suite_name"] == "regression" else "unknown"
        )
        r["decomposition"] = spec.get("decomposition", "unspecified")
        r["browser_required"] = bool(spec.get("browser"))
        r["task_fingerprint"] = selection.get("task_fingerprints", {}).get(r["task"])
        r["protocol"] = plan.get("evaluation_protocol", {})
        r["agent_seconds"] = r.get("metadata", {}).get("agent_seconds_used")
        evidence = r.get("service_evidence") or {}
        r["source_snapshot_sha256"] = (evidence.get("live_snapshot") or {}).get("sha256")
        if "attempts" in evidence:
            r["recovery_attempts"] = sum(
                max(0, count - 1) for count in evidence["attempts"].values()
            )
        elif "value_attempts" in evidence and spec.get("api") == "retry":
            r["recovery_attempts"] = max(0, evidence["value_attempts"] - 1)
        else:
            r["recovery_attempts"] = None
        stage = r.get("failure_stage")
        r["failure_category"] = (
            "none"
            if r["status"] == "success"
            else "infrastructure-or-grader"
            if r["status"] == "unscorable"
            else "budget-exhausted"
            if stage == "agent_timeout"
            else "correctness-or-delivery"
        )
        r["instruction"] = plan.get("public_instructions", {}).get(r["task"], r["instruction"])
        r["provenance"] = {
            k: plan.get(k) for k in ("version", "adapter_sha256", "runtime", "suite")
        }
        r["cohort"] = cohort(r)
    if invalid:
        for r in rows:
            if invalid.get("conditions") and r["condition"] not in invalid["conditions"]:
                continue
            if invalid.get("tasks") and r["task"] not in invalid["tasks"]:
                continue
            r["original_status"] = r["status"]
            r["status"] = "unscorable"
            r["invalidation"] = invalid
            r["failure_category"] = "invalidated"
            r["exception"] = {"type": "InvalidatedEvaluation", "message": invalid["reason"]}
    return rows


def summarize(rows):
    counts = Counter(r["status"] for r in rows)
    times = [r["seconds"] for r in rows if r.get("seconds") is not None]
    costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    n = len(rows)
    scored = counts["success"] + counts["failure"]
    usage = {}
    for key in ("tokens_in", "tokens_out", "tokens_cached"):
        known = [r[key] for r in rows if r.get(key) is not None]
        complete = all(r.get("metadata", {}).get("usage_complete") is not False for r in rows)
        usage[f"total_{key}"] = sum(known) if len(known) == n and n and complete else None
        usage[f"observed_{key}"] = sum(known) if known else None
        usage[f"known_{key}_trials"] = len(known)
    result = {
        "total": n,
        **{k: counts[k] for k in ("success", "failure", "unscorable")},
        "success_rate_all": counts["success"] / n if n else None,
        "success_rate_scored": counts["success"] / scored if scored else None,
        "median_seconds": statistics.median(times) if times else None,
        "total_cost_usd": sum(costs)
        if len(costs) == n
        and n
        and all(r.get("metadata", {}).get("usage_complete") is not False for r in rows)
        else None,
        "known_cost_trials": len(costs),
        **usage,
    }
    mixed = len({cohort(r) for r in rows}) > 1
    result["mixed_suites_or_selections"] = mixed
    if mixed:
        for key in ("success_rate_all", "success_rate_scored", "median_seconds"):
            result[key] = None
        result["aggregation_note"] = "Counts only; compare each suite/version/selection separately"
    else:
        result.update(efficiency(rows))
        result.update(uncertainty(rows))
    return result


def generate(job_paths, output):
    rows = [row for job in job_paths for row in normalize(job)]
    groups = {}
    for dimension in ("condition", "category", "difficulty", "decomposition"):
        keys = sorted({(r["job"], r["condition"], r["cohort"], r[dimension]) for r in rows})
        groups[dimension] = [
            {
                "job": job,
                "condition": condition,
                "cohort": identity,
                dimension: value,
                **summarize(
                    [
                        r
                        for r in rows
                        if r["job"] == job
                        and r["condition"] == condition
                        and r["cohort"] == identity
                        and r[dimension] == value
                    ]
                ),
            }
            for job, condition, identity, value in keys
        ]
    data = {
        "schema_version": 2,
        "trials": rows,
        "summary": summarize(rows),
        "groups": groups,
        "comparisons": comparisons(rows),
        "notes": [
            "Public original workloads; structural difficulty tiers, not human-certified or empirically calibrated.",
            "Suite/version/selection groups are separate; legacy runs have unknown selection identity.",
            "Bootstrap intervals need >=5 tasks and >=5 attempts each; they do not establish population-wide ability.",
            "Efficiency includes failed trials; unknown or incomplete usage is not zero.",
            "Tag groups overlap.",
            "Unknown usage and unscorable trials are never treated as zero.",
            "Regrades reuse saved candidate evidence and original agent usage; they are not new independent agent runs.",
        ],
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    template = Path(__file__).with_name("report.html").read_text()
    payload = (
        json.dumps(data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    (output / "index.html").write_text(template.replace("__DATA__", payload))
    return output / "index.html"
