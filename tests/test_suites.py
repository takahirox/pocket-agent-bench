import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from pocket_bench.cli import run_job
from pocket_bench.suite import catalog
from pocket_bench.suites import SUITES, select

ROOT = Path(__file__).resolve().parents[1]


def test_default_is_historical_twelve_tasks():
    specs, identity = select(ROOT)
    assert specs == catalog(ROOT)
    assert len(specs) == 12
    assert identity["name"] == "regression" and identity["partial"] is False


@pytest.mark.parametrize("name", SUITES)
def test_selection_identifies_exact_membership_and_is_stable(name):
    specs, full = select(ROOT, name)
    selected, partial = select(ROOT, name, specs[0]["id"])
    assert full == select(ROOT, name)[1]
    assert selected == specs[:1]
    assert partial["partial"] is True
    assert full["sha256"] == partial["sha256"]
    assert full["selection_sha256"] != partial["selection_sha256"]
    assert partial["task_fingerprints"][specs[0]["id"]] == full["task_fingerprints"][specs[0]["id"]]


@pytest.mark.parametrize(
    "name,tasks",
    [
        ("missing", None),
        ("regression", "workflow-recovery"),
        ("regression", ""),
        ("regression", "sales-dedup,sales-dedup"),
    ],
)
def test_invalid_selection_rejected(name, tasks):
    with pytest.raises(ValueError):
        select(ROOT, name, tasks)


def args(root, **kw):
    return SimpleNamespace(
        root=str(root),
        suite="capability",
        tasks=None,
        attempts=None,
        agent_seconds=None,
        profiles="oracle,nop",
        concurrency=1,
        model="fixture-model",
        effort="low",
        name="plan",
        profile_file=None,
        plan_only=True,
        allow_live_web=False,
        **kw,
    )


def test_plan_only_no_docker_or_model_and_suite_defaults(tmp_path, monkeypatch):
    (tmp_path / "suite").mkdir()
    shutil.copy(ROOT / "suite/catalog.json", tmp_path / "suite/catalog.json")
    import harbor.job

    async def forbidden(*args, **kwargs):
        pytest.fail("plan-only must not launch a job")

    monkeypatch.setattr(harbor.job.Job, "create", forbidden)
    asyncio.run(run_job(args(tmp_path)))
    plan = json.loads((tmp_path / "results/plans/plan.json").read_text())
    assert plan["attempts"] == 10
    assert plan["evaluation_protocol"]["agent_seconds"] == 600
    assert plan["suite"]["tasks"] == 5
    assert len(plan["configuration"]["tasks"]) == 5
    assert not (tmp_path / "results/jobs/plan").exists()


def test_live_gate_precedes_build(tmp_path):
    options = args(tmp_path)
    options.suite = "web"
    with pytest.raises(ValueError, match="allow-live-web"):
        asyncio.run(run_job(options))
    assert not (tmp_path / "tasks").exists()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1])
def test_invalid_budget_rejected_before_build(tmp_path, value):
    options = args(tmp_path)
    options.agent_seconds = value
    with pytest.raises(ValueError, match="positive"):
        asyncio.run(run_job(options))
    assert not (tmp_path / "tasks").exists()
