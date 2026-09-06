import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pocket_bench import connected_agent
from pocket_bench.connected_agent import ConnectedAgent
from pocket_bench.interface import PROTOCOL
from pocket_bench.workspace_transport import snapshot


class PublicEnvironment:
    def __init__(self, fixture):
        self.commands = []
        self.bundle = snapshot(fixture)
        self.returned = None

    async def exec(self, **kwargs):
        self.commands.append(kwargs)
        if kwargs["command"].endswith(" export"):
            return SimpleNamespace(return_code=0, stdout=json.dumps(self.bundle))
        return SimpleNamespace(return_code=0, stdout="")

    async def download_file(self, source, target):
        target.write_bytes(Path(connected_agent.__file__).with_name(Path(source).name).read_bytes())

    async def upload_file(self, source, target):
        if target.endswith("outputs.json"):
            self.returned = json.loads(source.read_text())


def controller_fixture(tmp_path, behavior="completed"):
    source = tmp_path / "fixture_controller.py"
    source.write_text(
        "import json,sys,time\nfrom pathlib import Path\n"
        "r=json.load(open(sys.argv[1])); marker=Path(r['settings']['resource'])\n"
        "if r['operation']=='cleanup':\n"
        " marker.unlink(missing_ok=True); outcome='cleaned'\n"
        "else:\n"
        " marker.write_text('owned resource'); w=Path(r['workspace'])\n"
        " assert not (w/'tests').exists() and not (w/'solution').exists()\n"
        " assert set(p.name for p in w.iterdir()) <= {'input','src','output'}\n"
        " if r['settings']['behavior']=='timeout': time.sleep(60)\n"
        " (w/'output/result.json').write_text('{}'); outcome=r['settings']['behavior']\n"
        "json.dump({'protocol':'pocket-agent-v1','outcome':outcome},open(sys.argv[2],'w'))\n"
    )
    path = tmp_path / "connections.json"
    path.write_text(
        json.dumps(
            {
                "protocol": PROTOCOL,
                "profiles": {
                    "example": {
                        "execution": "host-controller",
                        "argv": [sys.executable, str(source), "{request}", "{response}"],
                        "settings": {"resource": str(tmp_path / "resource"), "behavior": behavior},
                    }
                },
            }
        )
    )
    return path


TASKS = sorted(path for path in (Path(__file__).parents[1] / "tasks").iterdir() if path.is_dir())


@pytest.mark.parametrize("task", TASKS, ids=lambda path: path.name)
def test_all_twelve_public_task_fixtures_cross_common_controller_protocol(tmp_path, task):
    profile = controller_fixture(tmp_path)
    environment = PublicEnvironment(task / "environment")
    agent = ConnectedAgent(
        logs_dir=tmp_path / "logs",
        profile_file=profile,
        profile_name="example",
        allow_host_controller=True,
    )
    agent.logs_dir.mkdir()
    context = SimpleNamespace()
    asyncio.run(agent.run((task / "instruction.md").read_text(), environment, context))
    assert "output/result.json" in environment.returned
    assert all(name.split("/")[0] in ("src", "output") for name in environment.returned)
    assert not (tmp_path / "resource").exists()
    assert context.metadata["connection_outcome"] == "completed"


@pytest.mark.parametrize("behavior", ["timeout", "bad-outcome"])
def test_host_cleanup_even_after_timeout_or_protocol_error(tmp_path, behavior):
    profile = controller_fixture(tmp_path, behavior)
    agent = ConnectedAgent(
        logs_dir=tmp_path / "logs",
        profile_file=profile,
        profile_name="example",
        allow_host_controller=True,
        agent_seconds=0.2 if behavior == "timeout" else 3,
    )
    agent.logs_dir.mkdir()
    with pytest.raises((TimeoutError, ValueError)):
        asyncio.run(agent.run("task", PublicEnvironment(tmp_path / "empty"), SimpleNamespace()))
    assert not (tmp_path / "resource").exists()
