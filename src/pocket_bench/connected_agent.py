"""Harbor bridge. Tasks and verifiers do not know which agent is connected."""

import json
import os
import shlex
import tempfile
import time
from pathlib import Path

from harbor.agents.base import BaseAgent

from pocket_bench.interface import (
    PROTOCOL,
    controller_call,
    controller_directory,
    load_profiles,
    public_profile,
    render_argv,
)
from pocket_bench.workspace_transport import WRITABLE_ROOTS, materialize, snapshot


class ConnectedAgent(BaseAgent):
    def __init__(
        self,
        *args,
        profile_file,
        profile_name,
        allow_host_controller=False,
        agent_seconds=180,
        effort="low",
        stop_file=None,
        profile_sha256=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.profile = load_profiles(profile_file, allow_host_controller)[profile_name]
        self.profile = {"agent": profile_name, **self.profile}
        self.seconds, self.effort = float(agent_seconds), effort
        self.stop_file = Path(stop_file) if stop_file else None
        self.identity = public_profile(self.profile)
        self.identity["profile_name"] = profile_name
        if profile_sha256 and self.identity["sha256"] != profile_sha256:
            raise ValueError("Connection profile changed after experiment planning")

    @staticmethod
    def name():
        return "connected-agent"

    def version(self):
        return PROTOCOL

    def check_stop(self):
        if self.stop_file and self.stop_file.exists():
            reason = self.stop_file.read_text().strip()
            raise RuntimeError(
                f"Experiment previously stopped ({reason}); operator action required"
            )

    async def setup(self, environment):
        self.check_stop()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        result = await environment.exec(
            command="mkdir -p /logs/agent /app/src /app/output /home/agent/pocket; "
            "chown -R agent:agent /logs/agent /app /home/agent/pocket; chmod 700 /logs/verifier",
            user="root",
            timeout_sec=15,
        )
        if result.return_code:
            raise RuntimeError("Task workspace setup failed")
        for name in ("boundary_probe.py", "execution.py", "workspace_transport.py", "quiesce.py"):
            await environment.upload_file(Path(__file__).with_name(name), f"/opt/pocket/{name}")
        probe = await environment.exec(
            command="python -I /opt/pocket/boundary_probe.py", user="agent", timeout_sec=12
        )
        (self.logs_dir / "boundary.json").write_text(probe.stdout or "{}")
        if probe.return_code:
            raise RuntimeError("Task isolation preflight failed")
        if self.profile["execution"] == "cli":
            for binding in self.profile.get("credentials", []):
                target = binding["target"]
                path = Path(target)
                if not path.is_relative_to("/home/agent") or ".." in path.parts:
                    raise ValueError("credential target must be under /home/agent")
                source = Path(os.environ[binding["source_env"]])
                if source.is_symlink() or not source.is_file() or source.stat().st_size > 65536:
                    raise ValueError("explicit credential file missing or invalid")
                await environment.exec(
                    command="mkdir -p " + shlex.quote(str(path.parent)), user="root"
                )
                await environment.upload_file(source, target)
                await environment.exec(
                    command="chown -R agent:agent "
                    + shlex.quote(str(path.parent))
                    + " && chmod 600 "
                    + shlex.quote(target),
                    user="root",
                )
            for argv in self.profile.get("setup_argv", []):
                result = await environment.exec(
                    command=shlex.join(argv), cwd="/app", user="agent", timeout_sec=15
                )
                if result.return_code:
                    raise RuntimeError("Configured CLI setup failed")

    async def host(self, instruction, environment, deadline):
        result = await environment.exec(
            command="python -I /opt/pocket/workspace_transport.py export",
            user="agent",
            timeout_sec=15,
        )
        if result.return_code:
            raise RuntimeError("Public workspace export failed")
        public = json.loads(result.stdout)
        with controller_directory(self.logs_dir) as control:
            workspace = control / "workspace"
            materialize(workspace, public)
            checks = control / "public-checks"
            checks.mkdir()
            for name in ("smoke.py", "execution.py"):
                await environment.download_file(f"/opt/pocket/{name}", checks / name)
            request = {
                "protocol": PROTOCOL,
                "operation": "run",
                "instruction": instruction,
                "workspace": str(workspace),
                "control_dir": str(control),
                "public_checks": str(checks),
                "writable_roots": list(WRITABLE_ROOTS),
                "seconds": max(0, deadline - time.monotonic()),
                "model": self.model_name,
                "effort": self.effort,
                "settings": self.profile.get("settings", {}),
            }
            request_file, response_file = control / "request.json", control / "response.json"
            request_file.write_text(json.dumps(request))
            try:
                response = await controller_call(
                    self.profile["argv"],
                    request_file,
                    response_file,
                    max(0, deadline - time.monotonic()),
                )
                if response["outcome"] == "usage_limit" and self.stop_file:
                    self.stop_file.parent.mkdir(parents=True, exist_ok=True)
                    self.stop_file.write_text("usage_limit\n")
            finally:
                request["operation"] = "cleanup"
                request_file.write_text(json.dumps(request))
                try:
                    cleaned = await controller_call(
                        self.profile["argv"], request_file, control / "cleanup.json", 60
                    )
                    if cleaned["outcome"] != "cleaned":
                        raise RuntimeError("Controller cleanup not confirmed")
                except BaseException:
                    if self.stop_file:
                        self.stop_file.parent.mkdir(parents=True, exist_ok=True)
                        self.stop_file.write_text("cleanup_unconfirmed\n")
                    raise
            after = snapshot(workspace)
            if {k: v for k, v in after.items() if k.startswith("input/")} != {
                k: v for k, v in public.items() if k.startswith("input/")
            }:
                raise ValueError("Controller changed protected public inputs")
            if response["outcome"] == "completed":
                outputs = {k: v for k, v in after.items() if k.split("/")[0] in WRITABLE_ROOTS}
                artifact = control / "outputs.json"
                artifact.write_text(json.dumps(outputs))
                await environment.upload_file(artifact, "/home/agent/pocket/outputs.json")
                result = await environment.exec(
                    command="python -I /opt/pocket/workspace_transport.py import /home/agent/pocket/outputs.json",
                    user="agent",
                    timeout_sec=15,
                )
                if result.return_code:
                    raise RuntimeError("Candidate materialization failed")
            return response

    async def cli(self, instruction, environment, deadline):
        with tempfile.TemporaryDirectory(prefix="pocket-input-") as temporary:
            source = Path(temporary) / "instruction.txt"
            source.write_text(instruction)
            await environment.upload_file(source, "/home/agent/pocket/instruction.txt")
            source.write_text(
                json.dumps(
                    {
                        "protocol": PROTOCOL,
                        "instruction": instruction,
                        "workspace": "/app",
                        "seconds": self.seconds,
                        "model": self.model_name,
                        "effort": self.effort,
                    }
                )
            )
            await environment.upload_file(source, "/home/agent/pocket/request.json")
        argv = render_argv(
            self.profile["argv"],
            {
                "instruction": instruction,
                "request": "/home/agent/pocket/request.json",
                "workspace": "/app",
                "model": self.model_name,
                "effort": self.effort,
            },
        )
        remaining = max(0.1, deadline - time.monotonic())
        command = shlex.join(["timeout", "--kill-after=2", str(remaining), *argv])
        if self.profile.get("input", "argument") == "stdin":
            command += " < /home/agent/pocket/instruction.txt"
        result = await environment.exec(
            command=command + " > /logs/agent/native.jsonl 2> /logs/agent/native.stderr",
            cwd="/app",
            user="agent",
            timeout_sec=remaining + 3,
        )
        await self.quiesce(environment)
        await environment.download_dir("/logs/agent", self.logs_dir)
        usage = {}
        outcome = "completed" if result.return_code == 0 else "failed"
        mapping = self.profile.get("usage_jsonl", {})
        logs = ""
        for path in self.logs_dir.rglob("native.*"):
            with path.open(errors="replace") as stream:
                logs += stream.read(1_000_000)
        for marker in self.profile.get("usage_limit_markers", []):
            if marker.lower() in logs.lower():
                outcome = "usage_limit"
        for line in logs.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict) or event.get(mapping.get("event_key")) != mapping.get(
                "event_value"
            ):
                continue
            for normalized, dotted in mapping.get("fields", {}).items():
                value = event
                for key in dotted.split("."):
                    value = value.get(key) if isinstance(value, dict) else None
                if type(value) is int and value >= 0:
                    usage[normalized] = usage.get(normalized, 0) + value
        return {"protocol": PROTOCOL, "outcome": outcome, "usage": usage}

    async def quiesce(self, environment):
        result = await environment.exec(
            command="python -I /opt/pocket/quiesce.py", user="root", timeout_sec=5
        )
        if result.return_code:
            raise RuntimeError("Task-user process cleanup not confirmed")

    async def run(self, instruction, environment, context):
        self.check_stop()
        started = time.monotonic()
        deadline = started + self.seconds
        response = {"outcome": "failed"}
        try:
            method = self.host if self.profile["execution"] == "host-controller" else self.cli
            response = await method(instruction, environment, deadline)
            if response["outcome"] == "usage_limit":
                if self.stop_file:
                    self.stop_file.parent.mkdir(parents=True, exist_ok=True)
                    self.stop_file.write_text("usage_limit\n")
                raise RuntimeError("Usage limit reached; no reset, retry or provider switch")
            if response["outcome"] != "completed":
                raise RuntimeError("Agent connection returned failure")
            remaining = max(0, deadline - time.monotonic())
            result = await environment.exec(
                command=f"python -I /opt/pocket/execution.py {remaining}",
                cwd="/app",
                user="agent",
                timeout_sec=max(1, remaining) + 1,
            )
            response["execution_exit_code"] = result.return_code
        finally:
            try:
                await self.quiesce(environment)
            except Exception:
                response["outcome"] = "failed"
                raise
            finally:
                self.record(context, response, started)

    def record(self, context, response, started):
        usage = response.get("usage") or {}
        context.n_input_tokens = usage.get("input_tokens")
        context.n_output_tokens = usage.get("output_tokens")
        context.n_cache_tokens = usage.get("cached_input_tokens")
        context.cost_usd = None
        context.metadata = {
            **self.identity,
            "connection_outcome": response["outcome"],
            "execution_exit_code": response.get("execution_exit_code"),
            "agent_seconds_limit": self.seconds,
            "agent_seconds_used": time.monotonic() - started,
            "usage_complete": all(k in usage for k in ("input_tokens", "output_tokens")),
            "details": response.get("details", {}),
            "effort": self.effort,
        }
        (self.logs_dir / "connection.json").write_text(json.dumps(context.metadata, indent=2))
