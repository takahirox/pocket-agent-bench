"""Legacy optional Codex CLI integration, retained for reproducible old experiments.

The team uses two independent read-only analysts followed by one integrating agent.
Only the coordinator writes; it receives both analysts' messages. No benchmark solution
or private verifier is supplied to any real agent.
"""

import asyncio
import json
import os
import shlex
import time
from pathlib import Path

from harbor.agents.base import BaseAgent

from pocket_bench.codex_policy import permission_args
from pocket_bench.timing import hard_timeout_seconds as resolve_timeout


class CodexAgent(BaseAgent):
    command_policy = "workspace-write"

    def __init__(
        self,
        *args,
        mode="single",
        effort="low",
        hard_timeout_seconds=None,
        agent_seconds=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if mode not in ("single", "team"):
            raise ValueError("mode must be single or team")
        self.mode, self.effort = mode, effort
        self.hard_timeout_seconds = resolve_timeout(hard_timeout_seconds, agent_seconds)
        self.events = []
        self.termination_reason = None

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
        for name in ("sandbox_probe.py", "codex_policy.py", "execution.py", "quiesce.py"):
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
        clock_started = time.monotonic()
        command = shlex.join(argv) + f" > /logs/agent/{role}.jsonl 2> /logs/agent/{role}.stderr"
        try:
            r = await environment.exec(
                command=command, cwd="/app", user="agent", timeout_sec=seconds
            )
            code = r.return_code
        except BaseException as e:
            code = None
            self.events.append(
                {
                    "role": role,
                    "error": type(e).__name__,
                    "started_at": started,
                    "duration_seconds": time.monotonic() - clock_started,
                }
            )
            raise
        self.events.append(
            {
                "role": role,
                "exit_code": code,
                "started_at": started,
                "duration_seconds": time.monotonic() - clock_started,
            }
        )
        if code == 124:
            self.termination_reason = "hard_timeout"
            raise TimeoutError("Agent invocation reached the hard safety timeout")
        r = await environment.exec(command=f"cat /logs/agent/{role}.txt", user="agent")
        return r.stdout or "No final message produced."

    async def run(self, instruction, environment, context):
        self.started = time.monotonic()
        self.deadline = self.started + self.hard_timeout_seconds
        try:
            async with asyncio.timeout(self.hard_timeout_seconds):
                await self.run_work(instruction, environment)
        except TimeoutError:
            self.termination_reason = "hard_timeout"
            raise
        finally:
            self.wall_seconds = time.monotonic() - self.started
            try:
                result = await environment.exec(
                    command="python -I /opt/pocket/quiesce.py", user="root", timeout_sec=5
                )
                if result.return_code:
                    raise RuntimeError("Task-user process cleanup not confirmed")
            finally:
                await self.collect(environment, context)

    def remaining(self):
        seconds = self.deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError("Hard safety timeout exhausted")
        return seconds

    async def run_work(self, instruction, environment):
        if self.mode == "team":
            analyst_limit = self.remaining()
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
                instruction + "\n\nRead-only analyst reports (verify them yourself):\n" + handoff,
                "coordinator",
                self.remaining(),
            )
        else:
            await self.invoke(environment, instruction, "single", self.remaining())
        await self.execute_declared(environment)

    async def execute_declared(self, environment):
        remaining = self.remaining()
        started = time.time()
        clock_started = time.monotonic()
        r = await environment.exec(
            command=f"python -I /opt/pocket/execution.py {remaining}",
            cwd="/app",
            user="agent",
            timeout_sec=max(1, remaining) + 1,
        )
        if r.return_code == 124:
            self.termination_reason = "hard_timeout"
        self.events.append(
            {
                "role": "declared-execution",
                "kind": "transport",
                "exit_code": r.return_code,
                "started_at": started,
                "duration_seconds": time.monotonic() - clock_started,
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
            "timing_policy": "wall-clock-safety-v1",
            "hard_timeout_seconds": self.hard_timeout_seconds,
            "termination_reason": self.termination_reason,
            "wall_seconds": getattr(self, "wall_seconds", None),
            "aggregate_agent_seconds": sum(
                e["duration_seconds"] for e in self.events if e.get("kind") != "transport"
            )
            if self.events
            else None,
            "usage_complete": bool(usage)
            and len(usage) >= sum(e.get("kind") != "transport" for e in self.events)
            and not any(
                e.get("error") or e.get("exit_code", 0) != 0
                for e in self.events
                if e.get("kind") != "transport"
            ),
            "cost_basis": "unknown-subscription",
            "budget_enforcement": "shared wall-clock safety timeout; no role allocation",
            "effort": self.effort,
        }
        (self.logs_dir / "events.json").write_text(json.dumps(context.metadata, indent=2))
