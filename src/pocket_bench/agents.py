"""Harbor adapters for real Codex CLI and My AI Employee systems.

The team uses two independent read-only analysts followed by one integrating agent.
Only the coordinator writes; it receives both analysts' messages. No benchmark solution
or private verifier is supplied to any real agent.
"""

import asyncio
import json
import os
import shlex
import tempfile
import time
from pathlib import Path

from harbor.agents.base import BaseAgent

from pocket_bench.codex_policy import permission_args


class CodexAgent(BaseAgent):
    command_policy = "workspace-write"

    def __init__(self, *args, mode="single", effort="low", agent_seconds=180, **kwargs):
        super().__init__(*args, **kwargs)
        if mode not in ("single", "team"):
            raise ValueError("mode must be single or team")
        self.mode, self.effort, self.agent_seconds = mode, effort, float(agent_seconds)
        if self.agent_seconds <= 0:
            raise ValueError("agent_seconds must be positive")
        self.events = []

    @staticmethod
    def name():
        return "pocket-codex"

    def version(self):
        return "0.1.0/codex-0.144.4"

    async def setup(self, environment):
        auth = Path(os.environ.get("POCKET_CODEX_AUTH", str(Path.home() / ".codex/auth.json")))
        if not auth.is_file():
            raise RuntimeError("Codex authentication unavailable; run codex login on the host")
        result = await environment.exec(
            command="mkdir -p /home/agent/.codex /logs/agent /app/output; chown -R agent:agent /home/agent /logs/agent /app; chmod 700 /logs/verifier",
            user="root",
        )
        if result.return_code:
            raise RuntimeError("Agent directory setup failed")
        await environment.upload_file(
            Path(__file__).with_name("boundary_probe.py"), "/opt/pocket/boundary_probe.py"
        )
        probe = await environment.exec(
            command="python -I /opt/pocket/boundary_probe.py", user="agent", timeout_sec=12
        )
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "boundary.json").write_text(probe.stdout or "{}")
        if probe.return_code:
            raise RuntimeError(
                "Isolation preflight failed: " + (probe.stderr or probe.stdout or "unknown")
            )
        for name in ("sandbox_probe.py", "codex_policy.py", "execution.py"):
            await environment.upload_file(Path(__file__).with_name(name), f"/opt/pocket/{name}")
        probe = await environment.exec(
            command=f"python -I /opt/pocket/sandbox_probe.py {self.command_policy}",
            user="agent",
            timeout_sec=15,
        )
        (self.logs_dir / "sandbox.json").write_text(probe.stdout or "{}")
        if probe.return_code:
            raise RuntimeError("Inner command sandbox preflight failed: " + (probe.stderr or ""))
        await environment.upload_file(auth, "/home/agent/.codex/auth.json")
        await environment.exec(
            command="chown agent:agent /home/agent/.codex/auth.json; chmod 600 /home/agent/.codex/auth.json",
            user="root",
        )
        await environment.exec(
            command="git init -q && git config user.email bench@example.invalid && git config user.name Benchmark && git add . && git commit -qm fixture",
            cwd="/app",
            user="agent",
        )

    async def invoke(self, environment, prompt, role, seconds, readonly=False):
        # Codex controls are scoped to an unprivileged user in a disposable container.
        # Agent runs have no host mount and cannot modify root-owned verifier/service state.
        argv = [
            "codex",
            "exec",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--ephemeral",
            "--json",
            "--model",
            self.model_name or "gpt-5.6-luna",
            "-c",
            f'model_reasoning_effort="{self.effort}"',
            "-c",
            "features.multi_agent=false",
            "-c",
            'web_search="disabled"',
            *permission_args("read-only" if readonly else self.command_policy),
            "-o",
            f"/logs/agent/{role}.txt",
            "--",
            prompt,
        ]
        started = time.time()
        command = shlex.join(argv) + f" > /logs/agent/{role}.jsonl 2> /logs/agent/{role}.stderr"
        try:
            r = await environment.exec(
                command=command, cwd="/app", user="agent", timeout_sec=seconds
            )
            code = r.return_code
        except Exception as e:
            code = None
            self.events.append(
                {
                    "role": role,
                    "error": type(e).__name__,
                    "started_at": started,
                    "duration_seconds": time.time() - started,
                }
            )
            raise
        self.events.append(
            {
                "role": role,
                "exit_code": code,
                "started_at": started,
                "duration_seconds": time.time() - started,
            }
        )
        r = await environment.exec(command=f"cat /logs/agent/{role}.txt", user="agent")
        return r.stdout or "No final message produced."

    async def run(self, instruction, environment, context):
        try:
            if self.mode == "team":
                analyst_limit = self.agent_seconds / 6
                reports = await asyncio.gather(
                    *[
                        self.invoke(
                            environment,
                            instruction
                            + "\nYou are a read-only analyst. Inspect inputs and propose a concrete solution. Do not edit files or call APIs; only the coordinator operates services. "
                            + focus,
                            role,
                            analyst_limit,
                            True,
                        )
                        for role, focus in (
                            ("analyst-data", "Focus on data and implementation."),
                            ("analyst-check", "Focus on constraints, edge cases and verification."),
                        )
                    ],
                    return_exceptions=True,
                )
                handoff = "\n\n".join(f"Analyst {i + 1}: {r}" for i, r in enumerate(reports))
                await self.invoke(
                    environment,
                    instruction
                    + "\n\nRead-only analyst reports (verify them yourself):\n"
                    + handoff,
                    "coordinator",
                    self.agent_seconds * 2 / 3,
                )
            else:
                await self.invoke(environment, instruction, "single", self.agent_seconds)
            await self.execute_declared(environment)
        finally:
            await self.collect(environment, context)

    async def execute_declared(self, environment):
        remaining = max(0, self.agent_seconds - sum(e["duration_seconds"] for e in self.events))
        started = time.time()
        r = await environment.exec(
            command=f"python -I /opt/pocket/execution.py {remaining}",
            cwd="/app",
            user="agent",
            timeout_sec=max(1, remaining) + 1,
        )
        self.events.append(
            {
                "role": "declared-execution",
                "kind": "transport",
                "exit_code": r.return_code,
                "started_at": started,
                "duration_seconds": time.time() - started,
                "remaining_seconds": remaining,
            }
        )

    async def collect(self, environment, context):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        await environment.download_dir("/logs/agent", self.logs_dir)
        usage = []
        for file in self.logs_dir.rglob("*.jsonl"):
            for line in file.read_text(errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
                    usage.append(event["usage"])
        if usage:
            context.n_input_tokens = sum(u.get("input_tokens", 0) for u in usage)
            context.n_cache_tokens = sum(u.get("cached_input_tokens", 0) for u in usage)
            context.n_output_tokens = sum(u.get("output_tokens", 0) for u in usage)
        context.cost_usd = None  # subscription tokens are not an invoice
        context.metadata = {
            "mode": self.mode,
            "events": self.events,
            "agent_seconds_limit": self.agent_seconds,
            "agent_seconds_used": sum(e["duration_seconds"] for e in self.events),
            "usage_complete": bool(usage)
            and len(usage) >= sum(e.get("kind") != "transport" for e in self.events)
            and not any(e.get("error") for e in self.events),
            "cost_basis": "unknown-subscription",
            "budget_enforcement": "per-role timeout; aggregate agent-seconds upper bound",
            "effort": self.effort,
        }
        (self.logs_dir / "events.json").write_text(json.dumps(context.metadata, indent=2))


class FleetAgent(CodexAgent):
    command_policy = "readonly-network"

    @staticmethod
    def name():
        return "my-ai-employee"

    def version(self):
        return "0.2.1/snapshot-recorded-in-runtime-manifest"

    async def setup(self, environment):
        installed = await environment.exec(
            command="python -c \"import importlib.util; assert importlib.util.find_spec('ai_employee') is not None\"",
            user="agent",
        )
        if installed.return_code:
            raise RuntimeError(
                "Fleet is unavailable in this image; build_runtime.py --fleet is required"
            )
        await super().setup(environment)
        await environment.exec(
            command="mkdir -p /.fleet-app; chown agent:agent /.fleet-app", user="root"
        )
        if self.mode != "single":
            raise ValueError(
                "Fleet adapter currently exposes fixed single-node mode; team comparison uses CodexAgent"
            )
        project = {
            "schema_version": 2,
            "commands": {"smoke": {"argv": ["python", "/opt/pocket/smoke.py"], "cwd": "."}},
            "paths": {
                "writable": ["output/**", "src/**"],
                "protected": ["input/**", ".git/**", ".fleet/**"],
            },
            "verification": {"required": ["smoke"], "review": {"required": False}},
            "worker": {
                "allowed": ["codex_cli"],
                "allowed_strategy_ids": ["bench"],
                "adaptive_routing": False,
            },
            "budgets": {"wall_seconds": self.agent_seconds, "worker_turns": 3, "processes": 12},
        }
        operator = {
            "schema_version": 1,
            "workers": {
                "codex_cli": {
                    "executable": "/usr/local/bin/pocket-codex",
                    "path_entries": ["/usr/local/bin", "/usr/bin", "/bin"],
                }
            },
            "routing": {
                "strategies": [
                    {
                        "id": "bench",
                        "backend": "codex_cli",
                        "model": self.model_name or "gpt-5.6-luna",
                        "effort": self.effort,
                        "capabilities": ["edit_intent", "process"],
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory(prefix="pocket-config-") as d:
            await environment.upload_file(
                Path(__file__).with_name("fleet_wrapper.py"), "/usr/local/bin/pocket-codex"
            )
            await environment.exec(command="chmod 755 /usr/local/bin/pocket-codex", user="root")
            for name, value, target in (
                ("project.json", project, "/app/.fleet/project.yaml"),
                ("operator.json", operator, "/home/agent/operator.yaml"),
            ):
                p = Path(d) / name
                p.write_text(json.dumps(value))
                await environment.exec(command="mkdir -p /app/.fleet", user="agent")
                await environment.upload_file(p, target)
        await environment.exec(
            command="chown -R agent:agent /app/.fleet /home/agent/operator.yaml", user="root"
        )
        await environment.exec(
            command="git add .fleet && git commit -qm harness", cwd="/app", user="agent"
        )

    async def run(self, instruction, environment, context):
        started = time.time()
        try:
            cmd = shlex.join(
                [
                    "fleet",
                    "work",
                    instruction,
                    "--repo",
                    "/app",
                    "--routing-mode",
                    "fixed",
                    "--strategy",
                    "bench",
                    "--operator-config",
                    "/home/agent/operator.yaml",
                    "--non-interactive",
                    "--json",
                    "--db",
                    "/home/agent/run/state.db",
                ]
            )
            r = await environment.exec(
                command=cmd + " > /logs/agent/fleet.json 2> /logs/agent/fleet.stderr",
                user="agent",
                timeout_sec=self.agent_seconds,
            )
            self.events.append(
                {
                    "role": "fleet",
                    "exit_code": r.return_code,
                    "started_at": started,
                    "duration_seconds": time.time() - started,
                }
            )
            r = await environment.exec(command="cat /logs/agent/fleet.json", user="agent")
            try:
                result = json.loads(r.stdout or "{}")
            except ValueError:
                result = {}
            if result.get("run_id"):
                inspect = shlex.join(
                    ["fleet", "inspect", result["run_id"], "--db", "/home/agent/run/state.db"]
                )
                await environment.exec(
                    command=inspect
                    + " > /logs/agent/fleet-inspect.json 2> /logs/agent/inspect.stderr",
                    user="agent",
                )
                # Materialize the agent's candidate for grading, not a promotion to a user repository.
                cmd = shlex.join(
                    ["fleet", "diff", result["run_id"], "--db", "/home/agent/run/state.db"]
                )
                r = await environment.exec(
                    command=cmd + " > /logs/agent/candidate.patch", user="agent"
                )
                if r.return_code == 0:
                    applied = await environment.exec(
                        command="git apply /logs/agent/candidate.patch", cwd="/app", user="agent"
                    )
                    if applied.return_code:
                        raise RuntimeError(
                            "Fleet candidate materialization failed: " + (applied.stderr or "")
                        )
            await self.execute_declared(environment)
        except Exception as e:
            if not self.events:
                self.events.append(
                    {
                        "role": "fleet",
                        "error": type(e).__name__,
                        "started_at": started,
                        "duration_seconds": time.time() - started,
                    }
                )
            raise
        finally:
            await self.collect(environment, context)
            context.metadata["fleet_usage_note"] = (
                "Native worker JSONL events are collected by a transparent executable wrapper."
            )
