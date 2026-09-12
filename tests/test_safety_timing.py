import asyncio
import json
import sys
import time
from types import SimpleNamespace

import pytest
from test_agents import Environment
from test_interface import configuration
from test_reports import job

from pocket_bench import agents, cli
from pocket_bench.agents import CodexAgent
from pocket_bench.connected_agent import ConnectedAgent
from pocket_bench.interface import PROTOCOL, read_response
from pocket_bench.report import generate, normalize, summarize
from pocket_bench.timing import hard_timeout_seconds


def test_slow_parallel_workers_finish_without_old_role_cutoffs(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(agents, "time", SimpleNamespace(time=time.time, monotonic=lambda: clock[0]))

    class Slow(Environment):
        async def exec(self, **kwargs):
            command = kwargs["command"]
            if command.startswith("codex exec"):
                if "/analyst-data.txt" in command:
                    await asyncio.sleep(0)  # Both analysts start before time advances.
                else:
                    clock[0] += 240
            return await super().exec(**kwargs)

    agent = CodexAgent(logs_dir=tmp_path, mode="team")
    environment, context = Slow(), SimpleNamespace()
    asyncio.run(agent.run("task", environment, context))
    invocations = [c for c in environment.commands if c["command"].startswith("codex exec")]
    assert [c["timeout_sec"] for c in invocations] == [3600, 3600, 3360]
    assert context.metadata["wall_seconds"] == 480
    assert context.metadata["aggregate_agent_seconds"] == 720
    assert context.metadata["termination_reason"] is None
    execution = next(c for c in environment.commands if "/execution.py" in c["command"])
    assert execution["command"].endswith("3120.0")


@pytest.mark.parametrize("mode", ["single", "team"])
def test_hung_workers_are_cancelled_cleaned_and_measured(tmp_path, mode):
    stopped = []

    class Hung(Environment):
        async def exec(self, **kwargs):
            if kwargs["command"].startswith("codex exec"):
                try:
                    await asyncio.sleep(60)
                finally:
                    stopped.append(True)
            return await super().exec(**kwargs)

    agent = CodexAgent(logs_dir=tmp_path, mode=mode, hard_timeout_seconds=0.02)
    environment, context = Hung(), SimpleNamespace()
    with pytest.raises(TimeoutError):
        asyncio.run(agent.run("task", environment, context))
    assert len(stopped) == (2 if mode == "team" else 1)
    assert context.metadata["termination_reason"] == "hard_timeout"
    assert context.metadata["aggregate_agent_seconds"] > 0
    assert context.metadata["usage_complete"] is False
    assert any("quiesce.py" in c["command"] for c in environment.commands)
    assert not any("execution.py" in c["command"] for c in environment.commands)


@pytest.mark.parametrize("reward", [None, 0, 1])
@pytest.mark.parametrize("legacy", [False, True])
def test_timeout_and_independent_grade_are_separate(tmp_path, reward, legacy):
    root = job(tmp_path)
    path = root / "x__one/result.json"
    result = json.loads(path.read_text())
    result["verifier_result"] = None if reward is None else {"rewards": {"reward": reward}}
    result["exception_info"] = {"exception_type": "AgentTimeoutError"}
    if not legacy:
        result["agent_result"]["metadata"] = {
            "timing_policy": "wall-clock-safety-v1",
            "termination_reason": "hard_timeout",
            "usage_complete": False,
        }
    path.write_text(json.dumps(result))
    rows = normalize(root)
    expected = "timed_out" if reward is None else "success" if reward == 1 else "failure"
    assert rows[0]["status"] == expected
    assert rows[0]["grade_status"] == ("unscorable" if reward is None else expected)
    summary = summarize(rows)
    assert summary["total"] == 2
    assert summary["timeout_trials"] == 1
    assert summary["timeout_rate_all"] == 0.5
    assert summary["success_rate_all"] == (0.5 if reward == 1 else 0)
    html = generate([root], tmp_path / "report").read_text()
    assert "時間切れ" in html


def test_slow_success_is_not_regraded_by_elapsed_time(tmp_path):
    root = job(tmp_path)
    path = root / "x__one/result.json"
    result = json.loads(path.read_text())
    result["verifier_result"]["rewards"]["reward"] = 1
    result["agent_execution"] = {
        "started_at": "2026-09-13T00:00:00",
        "finished_at": "2026-09-13T00:10:00",
    }
    path.write_text(json.dumps(result))
    row = normalize(root)[0]
    assert row["status"] == "success" and row["seconds"] == 600


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_safety_limit_validation(tmp_path, seconds):
    with pytest.raises(ValueError):
        CodexAgent(logs_dir=tmp_path, hard_timeout_seconds=seconds)
    with pytest.raises(ValueError):
        ConnectedAgent(
            logs_dir=tmp_path,
            profile_file=configuration(tmp_path),
            profile_name="example",
            hard_timeout_seconds=seconds,
        )


def test_legacy_alias_is_explicit_about_changed_semantics():
    with pytest.warns(FutureWarning, match="wall-clock safety"):
        assert hard_timeout_seconds(legacy=600) == 600
    with pytest.raises(ValueError):
        hard_timeout_seconds(3600, 180)


@pytest.mark.parametrize(
    "options,expected", [([], 3600), (["--hard-timeout-seconds", "7200"], 7200)]
)
def test_cli_passes_independent_safety_limit(monkeypatch, options, expected):
    observed = []

    async def run(args):
        observed.append(args.hard_timeout_seconds)

    monkeypatch.setattr(cli, "run_job", run)
    monkeypatch.setattr(sys, "argv", ["pocket-bench", "run", *options])
    assert cli.main() == 0
    assert observed == [expected]


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_cli_rejects_invalid_limits(monkeypatch, value):
    monkeypatch.setattr(sys, "argv", ["pocket-bench", "run", "--hard-timeout-seconds", value])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_controller_measured_aggregate_is_optional(tmp_path):
    agent = ConnectedAgent(
        logs_dir=tmp_path, profile_file=configuration(tmp_path), profile_name="example"
    )
    context = SimpleNamespace()
    agent.record(context, {"outcome": "completed"}, time.monotonic())
    assert context.metadata["aggregate_agent_seconds"] is None
    response = {
        "protocol": PROTOCOL,
        "outcome": "completed",
        "timings": {
            "aggregate_agent_seconds": 800,
            "events": [{"role": "worker", "started_at": 100, "duration_seconds": 800}],
        },
    }
    path = tmp_path / "response.json"
    path.write_text(json.dumps(response))
    agent.record(context, read_response(path), time.monotonic())
    assert context.metadata["aggregate_agent_seconds"] == 800
    assert len(context.metadata["events"]) == 1
    response["timings"]["aggregate_agent_seconds"] = float("nan")
    path.write_text(json.dumps(response))
    with pytest.raises(ValueError):
        read_response(path)


def test_plans_record_safety_policy_and_cleanup_reserve(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path

    from harbor.job import Job

    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "suite", tmp_path / "suite")
    configs = []

    async def create(config):
        configs.append(config)
        raise RuntimeError("fixture backend stops before any model invocation")

    monkeypatch.setattr(Job, "create", create)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pocket-bench",
            "--root",
            str(tmp_path),
            "run",
            "--name",
            "timing-plan",
            "--hard-timeout-seconds",
            "7200",
        ],
    )
    with pytest.raises(RuntimeError, match="fixture backend"):
        cli.main()
    plan = json.loads((tmp_path / "results/plans/timing-plan.json").read_text())
    assert plan["timing_policy"] == {
        "kind": "wall-clock-safety-v1",
        "hard_timeout_seconds": 7200,
        "max_retries": 0,
    }
    assert all(a.kwargs["hard_timeout_seconds"] == 7200 for a in configs[0].agents)
    assert all(a.override_timeout_sec == 7230 for a in configs[0].agents)
    assert configs[0].retry.max_retries == 0


def test_declared_execution_timeout_keeps_completed_agent_usage(tmp_path):
    class TransportTimeout(Environment):
        async def exec(self, **kwargs):
            result = await super().exec(**kwargs)
            if "execution.py" in kwargs["command"]:
                result.return_code = 124
            return result

    (tmp_path / "single.jsonl").write_text(
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}})
    )
    context = SimpleNamespace()
    asyncio.run(CodexAgent(logs_dir=tmp_path).run("task", TransportTimeout(), context))
    assert context.metadata["termination_reason"] == "hard_timeout"
    assert context.metadata["usage_complete"] is True
    assert context.n_input_tokens == 3


def test_control_profiles_honor_configured_safety_limit(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path

    from harbor.job import Job

    shutil.copytree(Path(__file__).resolve().parents[1] / "suite", tmp_path / "suite")
    configs = []

    async def create(config):
        configs.append(config)
        raise RuntimeError("fixture backend")

    monkeypatch.setattr(Job, "create", create)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pocket-bench",
            "--root",
            str(tmp_path),
            "run",
            "--name",
            "controls",
            "--profiles",
            "oracle,nop",
            "--hard-timeout-seconds",
            "600",
        ],
    )
    with pytest.raises(RuntimeError, match="fixture backend"):
        cli.main()
    assert all(a.override_timeout_sec == 600 for a in configs[0].agents)
