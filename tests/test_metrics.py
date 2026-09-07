from copy import deepcopy

from pocket_bench.metrics import comparisons, uncertainty
from pocket_bench.report import summarize


def row(task="x", status="success", job="a", selection="one"):
    return {
        "task": task,
        "status": status,
        "job": job,
        "condition": "system",
        "seconds": 10,
        "agent_seconds": 15,
        "cost_usd": 2,
        "tokens_in": 10,
        "tokens_out": 5,
        "metadata": {"usage_complete": True},
        "model": "fixture",
        "agent_config": {"kwargs": {"effort": "low", "agent_seconds": 180}},
        "protocol": {"budget_basis": "aggregate-agent-seconds", "trial_concurrency": 1},
        "task_fingerprint": task + "-definition",
        "provenance": {
            "runtime": {"image_id": "sha-image"},
            "suite": {"name": "regression", "version": "1", "selection_sha256": selection},
        },
    }


def test_mixed_selections_have_counts_but_no_combined_score():
    result = summarize([row(), row(status="failure", selection="two")])
    assert result["total"] == 2 and result["success"] == 1
    assert result["success_rate_all"] is None and result["median_seconds"] is None
    assert result["mixed_suites_or_selections"]


def test_efficiency_includes_failures_and_handles_no_success():
    result = summarize([row(), row(status="failure")])
    assert result["cost_usd_per_success"] == 4
    assert result["seconds_per_success"] == 20
    assert result["agent_seconds_per_success"] == 30
    assert summarize([row(status="failure")])["cost_usd_per_success"] is None


def test_partial_usage_and_missing_cost_never_become_zero():
    sample = row()
    sample["metadata"]["usage_complete"] = False
    result = summarize([sample])
    assert result["total_tokens_in"] is None
    assert result["cost_usd_per_success"] is None
    sample["metadata"]["usage_complete"] = True
    sample["cost_usd"] = None
    assert summarize([sample])["cost_usd_per_success"] is None


def test_uncertainty_requires_diversity_and_repetition_and_is_repeatable():
    assert uncertainty([row()] * 100)["success_rate_ci95"] is None
    samples = [
        row(str(task), "success" if attempt % 2 else "failure")
        for task in range(5)
        for attempt in range(10)
    ]
    a = uncertainty(samples)
    assert a == uncertainty(samples)
    assert a["task_balanced_success_rate"] == 0.5
    assert a["success_rate_ci95"][0] < 0.5 < a["success_rate_ci95"][1]
    samples[0]["status"] = "unscorable"
    assert uncertainty(samples)["success_rate_ci95"] is None


def test_cross_suite_common_task_is_comparable_without_pooling_suites():
    a, b = row(), row(job="b", status="failure", selection="different")
    b["provenance"]["suite"]["name"] = "capability"
    result = comparisons([a, b])[0]
    assert result["blocked_reasons"] == []
    assert result["success_rate_difference"] == -1
    assert result["scope"] == "matched-task-only"


def test_changed_conditions_and_regrades_block_differences():
    a = row()
    variants = [row(job="b") for _ in range(5)]
    variants[0]["model"] = "other"
    variants[1]["agent_config"]["kwargs"]["agent_seconds"] = 300
    variants[2]["provenance"]["runtime"]["image_id"] = None
    variants[3]["evaluation_kind"] = "regrade"
    variants[4]["task_fingerprint"] = "modified-task"
    for b in variants:
        result = comparisons([a, b])[0]
        assert result["blocked_reasons"] and result["success_rate_difference"] is None


def test_live_snapshot_changes_block_comparison():
    a, b = row(), row(job="b")
    a["source_snapshot_sha256"] = "old"
    b["source_snapshot_sha256"] = "new"
    assert "live-source-changed" in comparisons([a, b])[0]["blocked_reasons"]


def test_unequal_repetitions_are_task_balanced():
    samples = [row("a")] * 10 + [row("b", status="failure")]
    assert uncertainty(samples)["task_balanced_success_rate"] == 0.5
    changed = deepcopy(samples)
    changed[0]["evaluation_kind"] = "regrade"
    assert uncertainty(changed)["success_rate_ci95"] is None


def test_intervals_do_not_pool_different_systems():
    samples = [
        row(str(task), job=job) for job in ("a", "b") for task in range(5) for attempt in range(10)
    ]
    assert uncertainty(samples)["interval_reason"] == "mixed-experiment-conditions"


def test_uniform_outcomes_do_not_claim_zero_uncertainty():
    samples = [row(str(task)) for task in range(5) for attempt in range(10)]
    result = uncertainty(samples)
    assert result["success_rate_ci95"] is None
    assert result["interval_reason"] == "no-observed-outcome-variation"


def test_regrades_do_not_pool_with_original_runs():
    a, b = row(), row(job="regraded")
    b["evaluation_kind"] = "regrade"
    b["regrade_verifier_sha256"] = "revised-grader"
    assert summarize([a, b])["mixed_suites_or_selections"]


def test_browser_version_must_be_known_and_equal():
    a, b = row(), row(job="b")
    a["browser_required"] = b["browser_required"] = True
    assert comparisons([a, b])[0]["blocked_reasons"]
    a["environment_evidence"] = b["environment_evidence"] = {"browser_version": "Chromium fixture"}
    assert comparisons([a, b])[0]["blocked_reasons"] == []
    b["environment_evidence"] = {"browser_version": "Chromium changed"}
    assert comparisons([a, b])[0]["blocked_reasons"]
