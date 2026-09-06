import asyncio
import base64
import json
import os
import sys
from types import SimpleNamespace

import pytest

from pocket_bench.connected_agent import ConnectedAgent
from pocket_bench.interface import (
    PROTOCOL,
    controller_call,
    load_profiles,
    read_response,
    render_argv,
)
from pocket_bench.workspace_transport import materialize, snapshot, validate


def configuration(tmp_path, **profile):
    path = tmp_path / "connections.json"
    path.write_text(
        json.dumps(
            {
                "protocol": PROTOCOL,
                "profiles": {
                    "example": {
                        "execution": "cli",
                        "argv": ["agent", "{instruction}"],
                        **profile,
                    }
                },
            }
        )
    )
    return path


def test_host_controller_requires_explicit_trust(tmp_path):
    path = configuration(tmp_path, execution="host-controller")
    with pytest.raises(ValueError, match="allow-host-controller"):
        load_profiles(path)
    assert load_profiles(path, True)["example"]["execution"] == "host-controller"


def test_instruction_is_data_not_shell_or_format_string():
    prompt = "$(touch /tmp/never); {model} `whoami`"
    assert render_argv(
        ["agent", "{instruction}", "{model}"], {"instruction": prompt, "model": "fixed"}
    ) == ["agent", prompt, "fixed"]


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/src/a",
        "tests/spec.json",
        "src/../input/a",
        "src/a/../../outside",
        "src//a",
        "src/.git/a",
        "src\\x/a",
    ],
)
def test_transport_rejects_escape(path):
    with pytest.raises(ValueError):
        validate({path: "eA=="})


def test_transport_rejects_symlink_and_hardlink(tmp_path):
    (tmp_path / "src").mkdir()
    file = tmp_path / "src/a"
    file.write_text("public")
    (tmp_path / "src/link").symlink_to(file)
    with pytest.raises(ValueError, match="links"):
        snapshot(tmp_path)
    (tmp_path / "src/link").unlink()
    os.link(file, tmp_path / "src/link")
    with pytest.raises(ValueError, match="links"):
        snapshot(tmp_path)


def test_transport_never_exports_grader(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/spec.json").write_text("hidden")
    bundle = {"input/a": base64.b64encode(b"public").decode()}
    materialize(tmp_path, bundle)
    assert snapshot(tmp_path) == bundle
    with pytest.raises(ValueError):
        materialize(tmp_path, {"input/a": "eA=="}, roots=("src", "output"), replace=True)
    assert (tmp_path / "input/a").read_text() == "public"


@pytest.mark.parametrize("usage", [{"input_tokens": True}, {"output_tokens": -1}, []])
def test_response_rejects_invalid_usage(tmp_path, usage):
    path = tmp_path / "response.json"
    path.write_text(json.dumps({"protocol": PROTOCOL, "outcome": "completed", "usage": usage}))
    with pytest.raises((ValueError, TypeError)):
        read_response(path)


def test_controller_file_protocol_and_timeout(tmp_path):
    source = tmp_path / "controller.py"
    source.write_text(
        "import json,sys,time\n"
        "r=json.load(open(sys.argv[1]))\n"
        "if r.get('sleep'): time.sleep(60)\n"
        "json.dump({'protocol':'pocket-agent-v1','outcome':'completed'},open(sys.argv[2],'w'))\n"
    )
    request, response = tmp_path / "request.json", tmp_path / "response.json"
    request.write_text("{}")
    argv = [sys.executable, str(source), "{request}", "{response}"]
    assert asyncio.run(controller_call(argv, request, response, 3))["outcome"] == "completed"
    request.write_text('{"sleep":true}')
    with pytest.raises(TimeoutError):
        asyncio.run(controller_call(argv, request, tmp_path / "timeout.json", 0.1))


class Environment:
    def __init__(self):
        self.commands = []

    async def exec(self, **kwargs):
        self.commands.append(kwargs)
        return SimpleNamespace(return_code=0, stdout="")

    async def upload_file(self, *args):
        pass

    async def download_dir(self, *args):
        pass


@pytest.mark.parametrize(
    "argv,mode",
    [
        (["first-agent", "{instruction}"], "argument"),
        (["another-agent", "--stdin"], "stdin"),
        (["third-agent", "{request}"], "request"),
    ],
)
def test_unrelated_clis_need_configuration_only(tmp_path, argv, mode):
    path = configuration(tmp_path, argv=argv, input=mode)
    agent = ConnectedAgent(logs_dir=tmp_path / "logs", profile_file=path, profile_name="example")
    agent.logs_dir.mkdir()
    environment, context = Environment(), SimpleNamespace()
    asyncio.run(agent.run("public task", environment, context))
    command = environment.commands[0]
    assert command["user"] == "agent" and command["cwd"] == "/app"
    assert command["command"].startswith("timeout --kill-after=2 ")
    assert argv[0] in command["command"]
    assert (" < " in command["command"]) == (mode == "stdin")
    assert context.n_input_tokens is None and context.cost_usd is None


def test_quota_gate_prevents_later_model_call(tmp_path):
    path = configuration(tmp_path)
    stop = tmp_path / "stop"
    agent = ConnectedAgent(
        logs_dir=tmp_path / "logs", profile_file=path, profile_name="example", stop_file=stop
    )
    agent.logs_dir.mkdir()

    async def quota(*args):
        return {"outcome": "usage_limit"}

    agent.cli = quota
    with pytest.raises(RuntimeError, match="Usage limit reached"):
        asyncio.run(agent.run("task", Environment(), SimpleNamespace()))
    assert stop.exists()
    environment = Environment()
    with pytest.raises(RuntimeError, match="previously stopped"):
        asyncio.run(agent.run("next task", environment, SimpleNamespace()))
    assert environment.commands == []


def test_profile_mutation_invalidates_plan(tmp_path):
    path = configuration(tmp_path)
    with pytest.raises(ValueError, match="changed"):
        ConnectedAgent(
            logs_dir=tmp_path, profile_file=path, profile_name="example", profile_sha256="old"
        )
