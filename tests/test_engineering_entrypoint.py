"""The engineering entry point must preserve caller arguments and grade failures."""

import json
import subprocess
from pathlib import Path

import pytest

from pocket_bench import engineering


def test_catalog_points_to_real_public_contract_and_unmeasured_task(capsys):
    assert engineering.main(["list"]) == 0
    task = json.loads(capsys.readouterr().out)[0]
    folder = Path(__file__).parents[1] / "experiments/chatwoot-team-views"
    assert (folder / task["instruction"]).is_file()
    assert (folder / task["entrypoint"]).is_file()
    assert task["reference_is_agent_input"] is False
    assert task["elapsed_time_is_correctness"] is False
    assert task["agent_difficulty"] == "unmeasured"


@pytest.mark.parametrize(
    ("command", "script", "forwarded"),
    [
        ("grade", "task.py", ["grade", "a workspace"]),
        ("prepare", "task.py", ["prepare", "--source", "a source"]),
        ("prepare", "task.py", ["prepare", "--help"]),
        ("package", "artifact.py", ["a source", "a target"]),
        ("prepare-agent", "agent_workspace.py", ["--source", "a source"]),
    ],
)
def test_forwarding_uses_argv_and_preserves_failure(monkeypatch, command, script, forwarded):
    seen = []

    def run(argv, *, check):
        seen.append(argv)
        assert check is False
        return subprocess.CompletedProcess(argv, 2)

    monkeypatch.setattr(engineering.subprocess, "run", run)
    rest = forwarded[1:] if command in {"prepare", "grade"} else forwarded
    assert engineering.main([command, *rest]) == 2
    assert Path(seen[0][1]).name == script
    assert seen[0][2:] == forwarded
