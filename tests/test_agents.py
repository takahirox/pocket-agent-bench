import asyncio
import json
from types import SimpleNamespace

import pytest

from pocket_bench.agents import CodexAgent


class Environment:
    def __init__(self):
        self.commands = []

    async def exec(self, **kwargs):
        self.commands.append(kwargs)
        return SimpleNamespace(return_code=0, stdout="analyst report")

    async def download_dir(self, *args):
        pass


def test_native_network_and_single_session_configuration(tmp_path):
    agent = CodexAgent(logs_dir=tmp_path, model_name="test-model")
    env = Environment()
    asyncio.run(agent.invoke(env, "task", "single", 90))
    cmd = env.commands[0]
    assert "sandbox_workspace_write.network_access=true" in cmd["command"]
    assert "features.multi_agent=false" in cmd["command"]
    assert 'sandbox_mode="workspace-write"' in cmd["command"]
    assert cmd["user"] == "agent" and cmd["timeout_sec"] == 90


def test_team_budget_and_handoff(tmp_path):
    agent = CodexAgent(logs_dir=tmp_path, mode="team", agent_seconds=180)
    env, context = Environment(), SimpleNamespace()
    asyncio.run(agent.run("task", env, context))
    invocations = [c for c in env.commands if c["command"].startswith("codex exec")]
    assert sorted(c["timeout_sec"] for c in invocations) == [30, 30, 120]
    assert sum('sandbox_mode="read-only"' in c["command"] for c in invocations) == 2
    assert "Analyst 1: analyst report" in invocations[-1]["command"]
    assert context.metadata["usage_complete"] is False


def test_native_usage_not_agent_self_report(tmp_path):
    agent = CodexAgent(logs_dir=tmp_path)
    (tmp_path / "role.jsonl").write_text(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 123, "cached_input_tokens": 20, "output_tokens": 10},
            }
        )
        + "\n"
    )
    context = SimpleNamespace()
    asyncio.run(agent.collect(Environment(), context))
    assert (context.n_input_tokens, context.n_output_tokens, context.n_cache_tokens) == (
        123,
        10,
        20,
    )
    assert context.cost_usd is None


@pytest.mark.parametrize("seconds", [0, -1])
def test_invalid_budget(tmp_path, seconds):
    with pytest.raises(ValueError):
        CodexAgent(logs_dir=tmp_path, agent_seconds=seconds)
