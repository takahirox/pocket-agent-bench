"""Explicit efficiency and task-balanced uncertainty, with conservative missing data."""

import random
import statistics
from collections import Counter, defaultdict


def cohort(row):
    suite = row.get("provenance", {}).get("suite") or {}
    # Legacy fingerprints identify a catalog, not necessarily the selected subset.
    if not suite.get("selection_sha256"):
        return "legacy:" + row.get("job", "unknown")
    identity = ":".join([suite["name"], suite["version"], suite["selection_sha256"]])
    if row.get("evaluation_kind") == "regrade":
        identity += ":regrade:" + (row.get("regrade_verifier_sha256") or row.get("job", "unknown"))
    return identity


def uncertainty(rows, *, draws=1000):
    tasks = defaultdict(list)
    for row in rows:
        tasks[row.get("task", "unknown")].append(int(row["status"] == "success"))
    means = [statistics.mean(values) for values in tasks.values()]
    result = {
        "task_count": len(tasks),
        "minimum_attempts": min(map(len, tasks.values()), default=0),
        "task_balanced_success_rate": statistics.mean(means) if means else None,
        "task_success_rate_stddev": statistics.stdev(means) if len(means) > 1 else None,
        "success_rate_ci95": None,
        "interval_method": "hierarchical-bootstrap-tasks-and-attempts-v1",
        "interval_draws": draws,
        "interval_reason": None,
    }
    if len({(r.get("job"), r.get("condition")) for r in rows}) > 1:
        result["interval_reason"] = "mixed-experiment-conditions"
    elif any(
        r["status"] in ("unscorable", "timed_out") or r.get("evaluation_kind") == "regrade"
        for r in rows
    ):
        result["interval_reason"] = "unscorable-or-regraded-evidence"
    elif len(tasks) < 5 or result["minimum_attempts"] < 5:
        result["interval_reason"] = "requires-at-least-5-tasks-and-5-attempts-per-task"
    elif len({v for values in tasks.values() for v in values}) < 2:
        result["interval_reason"] = "no-observed-outcome-variation"
    else:
        values = [tasks[k] for k in sorted(tasks)]
        rng = random.Random(0)
        samples = []
        for _ in range(draws):
            selected = rng.choices(values, k=len(values))
            samples.append(
                statistics.mean(statistics.mean(rng.choices(v, k=len(v))) for v in selected)
            )
        samples.sort()
        result["success_rate_ci95"] = [samples[int(0.025 * draws)], samples[int(0.975 * draws) - 1]]
    return result


def efficiency(rows):
    success = sum(r["status"] == "success" for r in rows)
    output = {}
    for field in (
        "seconds",
        "total_seconds",
        "agent_seconds",
        "cost_usd",
        "tokens_in",
        "tokens_out",
    ):
        known = [r[field] for r in rows if r.get(field) is not None]
        complete = len(known) == len(rows) and bool(rows)
        if field.startswith("tokens") or field == "cost_usd":
            complete &= all(r.get("metadata", {}).get("usage_complete") is not False for r in rows)
        total = sum(known) if complete else None
        output[f"total_{field}"] = total
        output[f"{field}_per_success"] = total / success if total is not None and success else None
        output[f"known_{field}_trials"] = len(known)
    total = output["total_seconds"]
    output["successes_per_wall_hour"] = success * 3600 / total if total else None
    output["efficiency_basis"] = (
        "all-trial-consumption-including-failures; seconds=sum-of-trial-wall-times"
    )
    output["failure_categories"] = dict(
        Counter(r.get("failure_category", "unknown") for r in rows if r["status"] != "success")
    )
    recovery = [r["recovery_attempts"] for r in rows if r.get("recovery_attempts") is not None]
    output["observed_recovery_attempts"] = sum(recovery) if recovery else None
    output["known_recovery_trials"] = len(recovery)
    return output


def condition_identity(row, *, include_safety_limit=False):
    config = row.get("agent_config", {})
    kwargs = config.get("kwargs", {})
    protocol = row.get("protocol", {})
    identity = {
        "model": row.get("model") or config.get("model_name"),
        "effort": kwargs.get("effort", row.get("metadata", {}).get("effort")),
        # Older plans used budget_basis for both aggregate budgets and safety guards.
        "timing_policy": protocol.get("timing_policy", protocol.get("budget_basis")),
        "concurrency": row.get("protocol", {}).get("trial_concurrency"),
        "runtime": (row.get("provenance", {}).get("runtime") or {}).get("image_id"),
        "browser": (row.get("environment_evidence") or {}).get("browser_version")
        if row.get("browser_required")
        else "not-required",
    }
    if identity["timing_policy"] == "wall-clock-safety-v1":
        # A guard that never fired is provenance, not an equal-compute condition.
        if include_safety_limit:
            identity["time_limit_seconds"] = kwargs.get(
                "hard_timeout_seconds", row.get("protocol", {}).get("hard_timeout_seconds")
            )
    else:
        identity["time_limit_seconds"] = kwargs.get(
            "agent_seconds", row.get("protocol", {}).get("agent_seconds")
        )
    return identity


def comparisons(rows):
    """Compare per-task evidence across systems or runs; never imply suite equivalence."""
    groups = defaultdict(list)
    for row in rows:
        groups[(row["job"], row["condition"])].append(row)
    result = []
    keys = sorted(groups)
    for i, left in enumerate(keys):
        for right in keys[i + 1 :]:
            a, b = groups[left], groups[right]
            common = sorted({r["task"] for r in a} & {r["task"] for r in b})
            for task in common:
                aa, bb = [r for r in a if r["task"] == task], [r for r in b if r["task"] == task]
                evidence = aa + bb
                interrupted = any(
                    r["status"] == "timed_out"
                    or r.get("termination_reason") in ("hard_timeout", "legacy_timeout")
                    or r.get("failure_stage") == "agent_timeout"
                    for r in evidence
                )
                identities = [
                    condition_identity(r, include_safety_limit=interrupted) for r in evidence
                ]
                hashes = {r.get("task_fingerprint") or r.get("task_checksum") for r in evidence}
                reasons = []
                if len(hashes) != 1 or None in hashes:
                    reasons.append("task-definition-different-or-unknown")
                if any(
                    r["status"] in ("unscorable", "timed_out") or r.get("invalidation")
                    for r in evidence
                ):
                    reasons.append("unscorable-or-invalidated")
                if any(r.get("evaluation_kind") == "regrade" for r in evidence):
                    reasons.append("regrade-is-not-an-independent-run")
                if any(v is None for identity in identities for v in identity.values()):
                    reasons.append("comparison-conditions-incomplete")
                if any(identity != identities[0] for identity in identities[1:]):
                    reasons.append("model-effort-budget-concurrency-or-runtime-different")
                snapshots = {r.get("source_snapshot_sha256") for r in evidence}
                known_snapshots = snapshots - {None}
                if len(known_snapshots) > 1:
                    reasons.append("live-source-changed")
                if known_snapshots and None in snapshots:
                    reasons.append("live-source-evidence-missing")
                result.append(
                    {
                        "left": list(left),
                        "right": list(right),
                        "task": task,
                        "left_attempts": len(aa),
                        "right_attempts": len(bb),
                        "scope": "matched-task-only",
                        "blocked_reasons": reasons,
                        "success_rate_difference": None
                        if reasons
                        else statistics.mean(r["status"] == "success" for r in bb)
                        - statistics.mean(r["status"] == "success" for r in aa),
                    }
                )
    return result
