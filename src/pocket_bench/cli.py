import argparse
import asyncio
import hashlib
import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pocket_bench import __version__
from pocket_bench.report import generate
from pocket_bench.suite import build
from pocket_bench.suites import SUITES, select


async def run_job(args):
    from harbor.job import Job
    from harbor.models.job.config import JobConfig

    root = Path(args.root).resolve()
    suite_name = getattr(args, "suite", "regression")
    specs, selection = select(root, suite_name, args.tasks)
    args.attempts = args.attempts if args.attempts is not None else SUITES[suite_name]["attempts"]
    args.agent_seconds = (
        args.agent_seconds if args.agent_seconds is not None else SUITES[suite_name]["seconds"]
    )
    if (
        args.attempts < 1
        or args.concurrency < 1
        or not math.isfinite(args.agent_seconds)
        or args.agent_seconds <= 0
    ):
        raise ValueError("Attempts, concurrency and finite agent-seconds must be positive")
    if any(s.get("live_web") for s in specs) and not getattr(args, "allow_live_web", False):
        raise ValueError("Live-web tasks require --allow-live-web; or select browser-release only")
    build(root)
    profiles = args.profiles.split(",")
    from pocket_bench.interface import load_profiles, public_profile

    connections = (
        load_profiles(args.profile_file, args.allow_host_controller)
        if getattr(args, "profile_file", None)
        else {}
    )
    profile_metadata = {
        name: public_profile({"agent": name, **value})
        for name, value in connections.items()
        if name in profiles
    }
    if connections and args.concurrency != 1:
        raise ValueError(
            "Connected profiles currently require concurrency=1 for quota-stop ordering"
        )
    agents = []
    for name in profiles:
        if name in ("oracle", "nop"):
            agents.append({"name": name})
        elif name in connections:
            agents.append(
                {
                    "import_path": "pocket_bench.connected_agent:ConnectedAgent",
                    "model_name": connections[name].get("model", args.model),
                    "kwargs": {
                        "profile_file": str(Path(args.profile_file).resolve()),
                        "profile_name": name,
                        "allow_host_controller": args.allow_host_controller,
                        "agent_seconds": args.agent_seconds,
                        "effort": connections[name].get("effort", args.effort),
                        "profile_sha256": profile_metadata[name]["sha256"],
                    },
                    "override_timeout_sec": args.agent_seconds + 90,
                }
            )
        elif name in ("codex-single", "codex-team"):
            agents.append(
                {
                    "import_path": "pocket_bench.agents:" + "CodexAgent",
                    "model_name": args.model,
                    "kwargs": {
                        "mode": "team" if name.endswith("team") else "single",
                        "effort": args.effort,
                        "agent_seconds": args.agent_seconds,
                    },
                    "override_timeout_sec": args.agent_seconds + 30,
                }
            )
        else:
            raise ValueError(
                f"Unknown profile {name}; load operator connections with --profile-file. "
                "Legacy fleet-single has moved to the product repository."
            )
    jobs = root / "results/jobs"
    name = args.name or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("Job name must be a single directory name")
    if (jobs / name).exists():
        raise ValueError("Job already exists; use a new name to preserve evidence")
    for agent in agents:
        if agent.get("import_path") == "pocket_bench.connected_agent:ConnectedAgent":
            agent["kwargs"]["stop_file"] = str(jobs / name / "pocket-usage-stop")
    config = JobConfig.model_validate(
        {
            "job_name": name,
            "jobs_dir": str(jobs),
            "n_attempts": args.attempts,
            "n_concurrent_trials": args.concurrency,
            "retry": {"max_retries": 0},
            "environment": {"force_build": True},
            "agents": agents,
            "tasks": [{"path": str(root / "tasks" / s["id"])} for s in specs],
            "artifacts": [
                "/app/output",
                "/app/src",
                "/app/input",
                "/var/lib/pocket/state.json",
                "/var/lib/pocket/environment.json",
            ],
        }
    )
    # Record the intended matrix before preflight so setup failures cannot disappear.
    metadata = root / "results/plans" / f"{name}.json"
    if metadata.exists():
        raise ValueError("Plan already exists; use a new name to preserve evidence")
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(
        json.dumps(
            {
                "version": __version__,
                "adapter_sha256": hashlib.sha256(
                    b"".join(
                        Path(__file__).with_name(n).read_bytes()
                        for n in (
                            "agents.py",
                            "boundary_probe.py",
                            "sandbox_probe.py",
                            "codex_policy.py",
                            "execution.py",
                            "smoke.py",
                            "interface.py",
                            "connected_agent.py",
                            "workspace_transport.py",
                            "quiesce.py",
                        )
                    )
                ).hexdigest(),
                "profiles": profiles,
                "profile_metadata": profile_metadata,
                "attempts": args.attempts,
                "tasks": specs,
                "public_instructions": {
                    s["id"]: (root / "tasks" / s["id"] / "instruction.md").read_text()
                    for s in specs
                },
                "configuration": config.model_dump(mode="json"),
                "suite": selection,
                "evaluation_protocol": {
                    "version": "1.0",
                    "budget_basis": "aggregate-agent-seconds",
                    "agent_seconds": args.agent_seconds,
                    "attempts": args.attempts,
                    "trial_concurrency": args.concurrency,
                    "token_cap": None,
                    "dollar_cap": None,
                    "live_web": any(s.get("live_web") for s in specs),
                    "network_hosts": sorted({h for s in specs for h in s.get("network_hosts", [])}),
                    "sampling": "public-fixed-original-tasks",
                    "calibration": "structural-not-empirical",
                    "recommended_attempts": selection["recommended_attempts"],
                    "below_recommended_attempts": args.attempts < selection["recommended_attempts"],
                },
                "runtime": json.loads((root / "local/runtime.json").read_text())
                if (root / "local/runtime.json").exists()
                else None,
            },
            indent=2,
        )
        + "\n"
    )
    if getattr(args, "plan_only", False):
        print(f"Plan: {metadata}")
        print(
            json.dumps(
                {
                    "suite": selection,
                    "trials": len(specs) * len(profiles) * args.attempts,
                    "maximum_agent_seconds": len(specs)
                    * len(profiles)
                    * args.attempts
                    * args.agent_seconds,
                }
            )
        )
        return
    error = None
    try:
        manifest = json.loads(metadata.read_text())["runtime"]
        if manifest:
            inspected = await asyncio.to_thread(
                subprocess.run,
                ["docker", "image", "inspect", "--format", "{{.Id}}", manifest["image"]],
                capture_output=True,
                text=True,
                check=True,
            )
            actual = inspected.stdout.strip()
            if actual != manifest["image_id"]:
                raise RuntimeError(
                    "Runtime tag changed since its manifest; rebuild and record it before running"
                )
        job = await Job.create(config)
        await job.run()
    except Exception as e:  # noqa: BLE001 -- preserve a report even when a backend fails
        error = e
    finally:
        (jobs / name).mkdir(parents=True, exist_ok=True)
        (jobs / name / "pocket-plan.json").write_text(metadata.read_text())
        if error:
            (jobs / name / "pocket-error.json").write_text(
                json.dumps({"type": type(error).__name__, "message": str(error)})
            )
        report = generate([jobs / name], root / "results/reports" / name)
        print(f"Report: {report}")
        summary = json.loads(report.with_name("results.json").read_text())["summary"]
        print(json.dumps(summary, ensure_ascii=False))
    if error:
        raise error


def main():
    p = argparse.ArgumentParser(
        description="Pocket Agent Bench — real agent evaluation with Harbor"
    )
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="Compile native Harbor tasks")
    sub.add_parser("doctor", help="Check local requirements without reading secrets")
    re = sub.add_parser("regrade", help="Regrade saved artifacts offline; never rerun the model")
    re.add_argument("source", type=Path)
    re.add_argument("destination", type=Path)
    inv = sub.add_parser("invalidate", help="Attach a reason; preserve the original trial evidence")
    inv.add_argument("job", type=Path)
    inv.add_argument("--reason", required=True)
    inv.add_argument("--conditions", help="Limit to comma-separated exact condition names")
    inv.add_argument("--tasks", help="Limit to comma-separated task IDs (AND with conditions)")
    r = sub.add_parser("run", help="Run a versioned experiment; consumes configured model access")
    r.add_argument("--name")
    r.add_argument("--suite", choices=tuple(SUITES), default="regression")
    r.add_argument(
        "--plan-only",
        action="store_true",
        help="Write the experiment plan; no model or Docker execution",
    )
    r.add_argument(
        "--allow-live-web",
        action="store_true",
        help="Allow the explicitly selected live-web workload",
    )
    r.add_argument("--tasks", help="Comma-separated task IDs within --suite; default all members")
    r.add_argument("--profiles", default="codex-single,codex-team")
    r.add_argument("--profile-file", type=Path, help="Operator-owned pocket-agent-v1 JSON profiles")
    r.add_argument(
        "--allow-host-controller",
        action="store_true",
        help="Trust explicitly configured host orchestration code (never model code)",
    )
    r.add_argument("--model", default="gpt-5.6-luna")
    r.add_argument("--effort", default="low")
    r.add_argument(
        "--attempts", type=int, default=None, help="Default: regression 2, other suites 10"
    )
    r.add_argument("--concurrency", type=int, default=1)
    r.add_argument(
        "--agent-seconds",
        type=float,
        default=None,
        help="Aggregate time budget; suite default if omitted",
    )
    report = sub.add_parser("report")
    report.add_argument("jobs", nargs="+", type=Path)
    report.add_argument("--output", type=Path, default=Path("results/report"))
    a = p.parse_args()
    if a.command == "build":
        print(build(a.root))
    elif a.command == "doctor":
        import shutil

        checks = {x: shutil.which(x) is not None for x in ("docker", "uv")}
        checks["codex_auth_file"] = (Path.home() / ".codex/auth.json").is_file()
        checks["docker_running"] = (
            subprocess.run(
                ["docker", "info", "--format", "{{.OSType}}"], capture_output=True, check=False
            ).returncode
            == 0
            if checks["docker"]
            else False
        )
        checks["runtime_manifest"] = (Path(a.root) / "local/runtime.json").is_file()
        print(json.dumps(checks, indent=2))
        return 0 if all(checks.values()) else 1
    elif a.command == "regrade":
        from pocket_bench.regrade import regrade

        print(regrade(a.source, a.destination, a.root))
    elif a.command == "invalidate":
        if not a.job.is_dir():
            p.error("Job directory does not exist")
        with (a.job / "pocket-invalidation.json").open("x") as f:
            json.dump(
                {
                    "reason": a.reason,
                    "created_at": datetime.now(UTC).isoformat(),
                    "conditions": a.conditions.split(",") if a.conditions else None,
                    "tasks": a.tasks.split(",") if a.tasks else None,
                },
                f,
                indent=2,
            )
        print("Invalidation recorded; regenerate the report to display it.")
    elif a.command == "report":
        print(generate(a.jobs, a.output))
    else:
        if (
            (a.attempts is not None and a.attempts < 1)
            or a.concurrency < 1
            or (
                a.agent_seconds is not None
                and (not math.isfinite(a.agent_seconds) or a.agent_seconds <= 0)
            )
        ):
            p.error("attempts, concurrency and agent-seconds must be positive")
        asyncio.run(run_job(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
