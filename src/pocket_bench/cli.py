import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pocket_bench import __version__
from pocket_bench.report import generate
from pocket_bench.suite import build, catalog


async def run_job(args):
    from harbor.job import Job
    from harbor.models.job.config import JobConfig

    root = Path(args.root).resolve()
    build(root)
    specs = catalog(root)
    if args.tasks:
        names = set(args.tasks.split(","))
        missing = names - {s["id"] for s in specs}
        if missing:
            raise ValueError(f"Unknown tasks: {sorted(missing)}")
        specs = [s for s in specs if s["id"] in names]
    profiles = args.profiles.split(",")
    agents = []
    for name in profiles:
        if name in ("oracle", "nop"):
            agents.append({"name": name})
        elif name in ("codex-single", "codex-team", "fleet-single"):
            agents.append(
                {
                    "import_path": "pocket_bench.agents:"
                    + ("FleetAgent" if name.startswith("fleet") else "CodexAgent"),
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
            raise ValueError(f"Unknown profile {name}")
    jobs = root / "results/jobs"
    name = args.name or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("Job name must be a single directory name")
    if (jobs / name).exists():
        raise ValueError("Job already exists; use a new name to preserve evidence")
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
            "artifacts": ["/app/output", "/app/src", "/app/input", "/var/lib/pocket/state.json"],
        }
    )
    # Record the intended matrix before preflight so setup failures cannot disappear.
    metadata = root / "results/plans" / f"{name}.json"
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
                            "fleet_wrapper.py",
                            "execution.py",
                            "smoke.py",
                        )
                    )
                ).hexdigest(),
                "profiles": profiles,
                "attempts": args.attempts,
                "tasks": specs,
                "public_instructions": {
                    s["id"]: (root / "tasks" / s["id"] / "instruction.md").read_text()
                    for s in specs
                },
                "configuration": config.model_dump(mode="json"),
                "suite": json.loads((root / "suite/manifest.json").read_text()),
                "runtime": json.loads((root / "local/runtime.json").read_text())
                if (root / "local/runtime.json").exists()
                else None,
            },
            indent=2,
        )
        + "\n"
    )
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
    r.add_argument("--tasks", help="Comma-separated task IDs; default all")
    r.add_argument("--profiles", default="codex-single,codex-team")
    r.add_argument("--model", default="gpt-5.6-luna")
    r.add_argument("--effort", default="low")
    r.add_argument("--attempts", type=int, default=2)
    r.add_argument("--concurrency", type=int, default=1)
    r.add_argument("--agent-seconds", type=float, default=180)
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
        if a.attempts < 1 or a.concurrency < 1 or a.agent_seconds <= 0:
            p.error("attempts, concurrency and agent-seconds must be positive")
        asyncio.run(run_job(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
