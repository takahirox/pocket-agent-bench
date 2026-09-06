import json
import subprocess
import sys
from pathlib import Path

import pytest

from pocket_bench.codex_policy import fleet_exec_args, permission_args
from pocket_bench.execution import declared_script, execute


def workspace(tmp_path, program="print('explicit execution')", script="src/main.py"):
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    (tmp_path / "src/main.py").write_text(program)
    (tmp_path / "output/execute.json").write_text(json.dumps({"script": script}))
    return tmp_path


def test_explicit_program_runs_once_with_any_source_name(tmp_path):
    root = workspace(
        tmp_path,
        "from pathlib import Path\np=Path('output/calls'); p.write_text(p.read_text()+'x' if p.exists() else 'x')",
    )
    assert execute(root, 2, root / "logs") == 0
    assert (root / "output/calls").read_text() == "x"
    assert json.loads((root / "logs/execution.json").read_text())["executed"]


def test_no_inferred_script(tmp_path):
    workspace(tmp_path, "raise AssertionError('must not run')")
    (tmp_path / "output/execute.json").unlink()
    assert execute(tmp_path, 2, tmp_path / "logs") == 0
    assert not json.loads((tmp_path / "logs/execution.json").read_text())["executed"]


@pytest.mark.parametrize(
    "script", ["/etc/x.py", "src/../x.py", "input/x.py", "src/a.sh", "src/missing.py"]
)
def test_reject_invalid_script(tmp_path, script):
    workspace(tmp_path, script=script)
    with pytest.raises(ValueError):
        declared_script(tmp_path)


def test_reject_symlink(tmp_path):
    workspace(tmp_path)
    (tmp_path / "src/main.py").unlink()
    (tmp_path / "src/main.py").symlink_to(__file__)
    with pytest.raises(ValueError):
        declared_script(tmp_path)


@pytest.mark.parametrize("seconds", [0, 0.05])
def test_execution_budget(tmp_path, seconds):
    workspace(tmp_path, "import time; time.sleep(10)")
    assert execute(tmp_path, seconds, tmp_path / "logs") != 0


def test_smoke_parses_arbitrary_script_without_running_it(tmp_path):
    workspace(tmp_path, "raise AssertionError('must not run in smoke')")
    import pocket_bench.execution

    smoke = Path(pocket_bench.execution.__file__).with_name("smoke.py")
    p = subprocess.run(
        [sys.executable, "-I", str(smoke)], cwd=tmp_path, capture_output=True, check=False
    )
    assert p.returncode == 0, p.stderr


def test_worker_and_probe_share_readonly_network_flags():
    prompt = "Do not change --sandbox read-only text in the prompt"
    argv = fleet_exec_args(["exec", "--sandbox", "read-only", "--", prompt], "final.txt")
    expected = permission_args("readonly-network")
    start = argv.index('default_permissions="pocket-readonly"') - 1
    assert argv[start : start + len(expected)] == expected
    assert "--sandbox" not in argv and argv[-1] == prompt
    assert not any("sandbox_mode=" in a or "sandbox_workspace_write" in a for a in argv)


@pytest.mark.parametrize(
    "args",
    [
        ["exec"],
        ["exec", "--sandbox", "workspace-write"],
        ["exec", "--sandbox", "read-only", "-c", 'sandbox_mode="read-only"'],
    ],
)
def test_policy_drift_fails_closed(args):
    with pytest.raises(ValueError):
        fleet_exec_args(args, "final.txt")
