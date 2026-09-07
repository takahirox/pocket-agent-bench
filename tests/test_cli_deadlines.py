import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_interface import Environment, configuration

import pocket_bench.connected_agent as connected


def test_request_allowance_excludes_setup_and_return_reserve(tmp_path, monkeypatch):
    clock = [10.0]
    requests = []

    class DelayedEnvironment(Environment):
        async def upload_file(self, source, destination):
            if destination.endswith("request.json"):
                requests.append(json.loads(Path(source).read_text()))
            clock[0] += 3.0

    monkeypatch.setattr(connected.time, "monotonic", lambda: clock[0])
    profile = configuration(tmp_path, input="request", argv=["fixture", "{request}"])
    agent = connected.ConnectedAgent(
        logs_dir=tmp_path / "logs", profile_file=profile, profile_name="example", agent_seconds=180
    )
    agent.logs_dir.mkdir()
    environment = DelayedEnvironment()
    asyncio.run(agent.cli("fixture", environment, 190.0))
    assert requests[0]["seconds"] == 172.0
    assert environment.commands[0]["command"].startswith("timeout --kill-after=2 174.0 ")


def test_expired_setup_never_starts_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(connected.time, "monotonic", lambda: 100.0)
    agent = connected.ConnectedAgent(
        logs_dir=tmp_path, profile_file=configuration(tmp_path), profile_name="example"
    )
    env = Environment()
    response = asyncio.run(agent.cli("fixture", env, 99.0))
    assert response["details"]["termination"] == "deadline_before_invocation"
    assert not env.commands


def test_container_launcher_clamps_stale_request_after_upload(tmp_path):
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"seconds": 172.0, "instruction": "literal $(never)"}))
    request.chmod(0o444)
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            connected._REQUEST_LAUNCHER,
            str(request),
            "150",
            sys.executable,
            "-I",
            "-c",
            "import sys; print('controller started')",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert process.stdout.strip() == "controller started"
    assert json.loads(request.read_text()) == {"seconds": 150.0, "instruction": "literal $(never)"}
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            connected._REQUEST_LAUNCHER,
            str(request),
            "0",
            "nonexistent-controller",
        ],
        capture_output=True,
        check=False,
    )
    assert process.returncode == 124


def test_timeout_retains_reason_and_marks_observed_usage_partial(tmp_path):
    class TimedOut(Environment):
        async def exec(self, **kwargs):
            self.commands.append(kwargs)
            return SimpleNamespace(
                return_code=124 if kwargs["command"].startswith("timeout") else 0
            )

    agent = connected.ConnectedAgent(
        logs_dir=tmp_path, profile_file=configuration(tmp_path), profile_name="example"
    )
    context = SimpleNamespace()
    with pytest.raises(RuntimeError, match="Agent connection"):
        asyncio.run(agent.run("fixture", TimedOut(), context))
    assert context.metadata["details"]["termination"] == "deadline"
    assert context.metadata["details"]["cli_exit_code"] == 124
    assert context.metadata["usage_complete"] is False


@pytest.mark.parametrize("partial", [False, True])
def test_normally_returned_controller_preserves_partial_usage(tmp_path, partial):
    class UsageEnvironment(Environment):
        async def download_dir(self, source, destination):
            events = [{"type": "fixture.usage", "usage": {"input_tokens": 7}}]
            if partial:
                events.append({"type": "fixture.usage", "complete": False, "usage": {}})
            events.append({"type": "fixture.usage", "complete": True, "usage": {"input_tokens": 3}})
            (destination / "native.jsonl").write_text(
                "\n".join(json.dumps(event) for event in events)
            )

    agent = connected.ConnectedAgent(
        logs_dir=tmp_path,
        profile_file=configuration(
            tmp_path,
            usage_jsonl={
                "event_key": "type",
                "event_value": "fixture.usage",
                "fields": {"input_tokens": "usage.input_tokens"},
            },
        ),
        profile_name="example",
    )
    response = asyncio.run(
        agent.cli("fixture", UsageEnvironment(), connected.time.monotonic() + 180)
    )
    assert response["outcome"] == "completed"
    assert response["usage"] == {"input_tokens": 10}
    assert response["usage_complete"] is (not partial)
