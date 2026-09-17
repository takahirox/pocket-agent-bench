#!/usr/bin/env python3
"""Qualify an immutable candidate in fresh Docker volumes, without host mounts."""

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from artifact import COMMIT, collect, read_artifact, volume_tar

HERE = Path(__file__).resolve().parent


def audit(compose, root):
    container = subprocess.check_output([*compose, "ps", "-aq", "app"], text=True).strip()
    # Request relevant fields only; never copy container environment secrets to logs.
    template = '{"mounts":{{json .Mounts}},"user":{{json .Config.User}},"privileged":{{json .HostConfig.Privileged}},"cap_drop":{{json .HostConfig.CapDrop}},"security":{{json .HostConfig.SecurityOpt}},"networks":{{json .NetworkSettings.Networks}}}'
    actual = json.loads(
        subprocess.check_output(["docker", "inspect", "--format", template, container], text=True)
    )
    project = json.loads((root / "manifest.json").read_text())["project"]
    allowed = {f"{project}_candidate", f"{project}_dependencies"}
    if (
        actual["user"] != "1000:1000"
        or actual["privileged"]
        or "ALL" not in actual["cap_drop"]
        or "no-new-privileges:true" not in actual["security"]
        or set(actual["networks"]) != {f"{project}_default"}
        or any(m["Type"] != "volume" or m["Name"] not in allowed for m in actual["mounts"])
    ):
        raise RuntimeError("Candidate container boundary differs from required configuration")
    internal = subprocess.check_output(
        ["docker", "network", "inspect", f"{project}_default", "--format", "{{.Internal}}"],
        text=True,
    ).strip()
    if internal != "true":
        raise RuntimeError("Candidate network is not internal")
    report = {
        "status": "pass",
        "user": actual["user"],
        "host_mounts": 0,
        "volume_names": sorted(m["Name"] for m in actual["mounts"]),
        "internal_network": True,
        "privileged": False,
        "capabilities_dropped": ["ALL"],
    }
    (root / "boundary-check.json").write_text(json.dumps(report, indent=2) + "\n")


def configuration(project, port, vite_port, images):
    environment = {
        "RAILS_ENV": "development",
        "NODE_ENV": "development",
        "DISABLE_ENTERPRISE": "true",
        "POSTGRES_HOST": "postgres",
        "POSTGRES_USERNAME": "pocket",
        "POSTGRES_PASSWORD": "pocket-local-only",
        "POSTGRES_DATABASE": "pocket_team_views",
        "REDIS_URL": "redis://redis:6379",
        "FRONTEND_URL": f"http://localhost:{port}",
        "VITE_RUBY_HOST": "localhost",
        "VITE_RUBY_PORT": str(vite_port),
        "ACTIVE_STORAGE_SERVICE": "local",
        "DISABLE_SPRING": "1",
        "RAILS_LOG_TO_STDOUT": "true",
        "LOG_LEVEL": "warn",
        "ENABLE_ACCOUNT_SIGNUP": "false",
        "DISABLE_TELEMETRY": "true",
    }
    app = {
        "image": images["app"],
        "working_dir": "/app",
        "user": "1000:1000",
        "env_file": ".env",
        "environment": environment,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "pids_limit": 512,
        "mem_limit": "3g",
        "cpus": 2,
        "command": ["bundle", "exec", "foreman", "start", "-f", "/app/Procfile.benchmark"],
        "volumes": ["candidate:/app", "dependencies:/app/node_modules"],
    }
    seed = dict(
        app,
        image=images.get("seed", images["app"]),
        volumes=[
            "baseline:/app",
            "seed_dependencies:/app/node_modules",
            "proxy_config:/proxy-config",
        ],
    )
    return {
        "name": project,
        "services": {
            "app": app,
            "seed": seed,
            "postgres": {
                "image": images["postgres"],
                "mem_limit": "512m",
                "environment": {
                    "POSTGRES_USER": "pocket",
                    "POSTGRES_PASSWORD": "pocket-local-only",
                    "POSTGRES_DB": "pocket_team_views",
                },
                "volumes": ["postgres:/var/lib/postgresql/data"],
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U pocket -d pocket_team_views"],
                    "interval": "3s",
                    "retries": 20,
                },
            },
            "redis": {
                "image": images["redis"],
                "mem_limit": "128m",
                "command": ["redis-server", "--save", "", "--appendonly", "no"],
                "healthcheck": {
                    "test": ["CMD", "redis-cli", "ping"],
                    "interval": "3s",
                    "retries": 20,
                },
            },
            "proxy": {
                "image": images["proxy"],
                "mem_limit": "128m",
                "ports": [f"127.0.0.1:{port}:3000", f"127.0.0.1:{vite_port}:{vite_port}"],
                "volumes": ["proxy_config:/etc/nginx/conf.d:ro"],
                "networks": ["default", "ingress"],
            },
        },
        "volumes": {
            name: {}
            for name in (
                "candidate",
                "baseline",
                "dependencies",
                "seed_dependencies",
                "postgres",
                "proxy_config",
            )
        },
        "networks": {"default": {"internal": True}, "ingress": {}},
    }


def prepare(args):
    root = args.destination.resolve()
    if root.exists():
        raise ValueError("Destination exists; choose a new directory and project")
    if not re.fullmatch(r"pocket-tv-[a-z0-9-]+", args.project):
        raise ValueError("Invalid project name")
    if args.port == args.vite_port or not all(
        1024 <= p <= 65535 for p in (args.port, args.vite_port)
    ):
        raise ValueError("Choose two distinct unprivileged ports")
    candidate = read_artifact(args.artifact)
    baseline = collect(args.source, base=True)
    for name in ("Gemfile", "Gemfile.lock", "package.json", "pnpm-lock.yaml"):
        if candidate.get(name) != baseline.get(name) and not getattr(
            args, "dependency_image_verified", False
        ):
            raise ValueError(
                "Changed dependencies need a separately prepared image; not graded as failure"
            )
    for kind in ("container", "volume", "network"):
        command = ["docker", kind, "ls"] + (["-a"] if kind == "container" else [])
        output = subprocess.check_output(
            [*command, "--filter", f"label=com.docker.compose.project={args.project}", "-q"],
            text=True,
        )
        if output.strip():
            raise ValueError("Project already has resources; refusing reuse")
    image_names = {
        "app": args.image,
        "seed": getattr(args, "baseline_image", args.image),
        "postgres": "pgvector/pgvector:pg16",
        "redis": "redis:7.4-alpine",
        "proxy": "nginx:1.28-alpine",
    }
    images = {
        role: subprocess.check_output(
            ["docker", "image", "inspect", name, "--format", "{{.Id}}"], text=True
        ).strip()
        for role, name in image_names.items()
    }
    root.mkdir(parents=True)
    secret = root / ".env"
    secret.touch(mode=0o600)
    secret.write_text("SECRET_KEY_BASE=" + secrets.token_hex(64) + "\n")
    config = configuration(args.project, args.port, args.vite_port, images)
    (root / "compose.yaml").write_text(json.dumps(config, indent=2) + "\n")
    manifest = {
        "source_commit": COMMIT,
        "project": args.project,
        "port": args.port,
        "vite_port": args.vite_port,
        "artifact_sha256": hashlib.sha256(args.artifact.read_bytes()).hexdigest(),
        "observed_image_ids": images,
        "kind": "isolated-candidate-qualification",
        "correctness": "unscored",
        "qualified_for_agent_comparison": False,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    compose = ["docker", "compose", "-f", str(root / "compose.yaml")]
    with (root / "transfer.log").open("w") as log:
        subprocess.run(
            [*compose, "create", "seed", "app", "proxy"], check=True, stdout=log, stderr=log
        )
        # The dependency image was built as root. Prepare its disposable cache
        # volume before any candidate files arrive, then execute the app as uid 1000.
        subprocess.run(
            [
                *compose,
                "run",
                "--rm",
                "--user",
                "0:0",
                "--cap-add",
                "CHOWN",
                "--entrypoint",
                "/bin/chown",
                "app",
                "-R",
                "1000:1000",
                "/app",
            ],
            check=True,
            stdout=log,
            stderr=log,
        )
        for service, entries in (("seed", baseline), ("app", candidate)):
            entries = dict(entries)
            entries["Procfile.benchmark"] = (
                0o100644,
                (
                    "backend: bundle exec rails server -b 0.0.0.0 -p 3000\n"
                    f"vite: VITE_RUBY_HOST=0.0.0.0 pnpm exec vite --port {args.vite_port}\n"
                ).encode(),
            )
            if service == "seed":
                entries["benchmark_fixture.rb"] = (0o100644, (HERE / "fixture.rb").read_bytes())
            container = subprocess.check_output([*compose, "ps", "-aq", service], text=True).strip()
            subprocess.run(
                ["docker", "cp", "-a", "-", f"{container}:/app"],
                input=volume_tar(entries),
                check=True,
                stdout=log,
                stderr=log,
            )
        seed = subprocess.check_output([*compose, "ps", "-aq", "seed"], text=True).strip()
        nginx = (HERE / "nginx.conf").read_text().replace("33336", str(args.vite_port)).encode()
        subprocess.run(
            ["docker", "cp", "-a", "-", f"{seed}:/proxy-config"],
            input=volume_tar({"default.conf": (0o100644, nginx)}),
            check=True,
            stdout=log,
            stderr=log,
        )
    (root / ".transferred").touch()
    print("Transferred source to named volumes; no host directories mounted", flush=True)


def run(root, ui_map=None, browser=None):
    root = root.resolve()
    if not (root / ".transferred").exists():
        raise ValueError("Transfer incomplete")
    with (root / ".run-started").open("x"):
        pass
    compose = ["docker", "compose", "-f", str(root / "compose.yaml")]
    report = {
        "correctness": "unscored",
        "qualified_for_agent_comparison": False,
        "stages": [],
        "remaining_gates": [
            "remaining R7 workflows and alternate-UI controls",
            "full regression/build integration",
            "full runner controls and task registration",
        ],
    }
    if ui_map is not None:
        # Copy before execution so the UI adapter cannot change during a run.
        content = ui_map.read_bytes()
        if len(content) > 16384 or browser is None:
            raise ValueError("UI map requires a browser executable and must be <= 16 KiB")
        (root / "ui-map.json").write_bytes(content)
        report["ui_map_sha256"] = hashlib.sha256(content).hexdigest()

    def stage(name, command, timeout=300, candidate=False):
        print(name + ": running", flush=True)
        started = time.monotonic()
        with (root / f"{name}.log").open("w") as log:
            try:
                completed = subprocess.run(
                    command, stdout=log, stderr=log, timeout=timeout, check=False
                )
                status = "pass" if completed.returncode == 0 else "error"
                # Only a structured oracle mismatch is evidence of incorrect behavior.
                # A migration/process crash may also be an infrastructure problem.
                if candidate and name == "http" and completed.returncode == 1:
                    status = "fail"
                if candidate and name == "legacy-data" and (root / "migration-check.json").exists():
                    status = json.loads((root / "migration-check.json").read_text())["status"]
            except subprocess.TimeoutExpired:
                status = "timeout"
        report["stages"].append(
            {"name": name, "status": status, "seconds": round(time.monotonic() - started, 2)}
        )
        if status != "pass":
            raise RuntimeError(f"{name}: {status}")

    try:
        stage("services", [*compose, "up", "-d", "--wait", "postgres", "redis"])
        stage(
            "baseline-schema",
            [
                *compose,
                "run",
                "--rm",
                "seed",
                "bundle",
                "exec",
                "rails",
                "db:create",
                "db:schema:load",
            ],
        )
        stage(
            "fixture",
            [
                *compose,
                "run",
                "--rm",
                "seed",
                "bundle",
                "exec",
                "rails",
                "runner",
                "/app/benchmark_fixture.rb",
            ],
        )
        rows = [
            json.loads(line.removeprefix("POCKET_FIXTURE="))
            for line in (root / "fixture.log").read_text().splitlines()
            if line.startswith("POCKET_FIXTURE=")
        ]
        if len(rows) != 1:
            raise RuntimeError("Expected exactly one trusted fixture manifest")
        (root / "fixture.json").write_text(json.dumps(rows[0], indent=2) + "\n")
        stage(
            "migration",
            [*compose, "run", "--rm", "app", "bundle", "exec", "rails", "db:migrate"],
            candidate=True,
        )
        stage(
            "legacy-data", ["python3", str(HERE / "migration_probe.py"), str(root)], candidate=True
        )
        stage("application", [*compose, "up", "-d", "app", "proxy"])
        audit(compose, root)
        report["stages"].append({"name": "container-boundary", "status": "pass"})
        manifest = json.loads((root / "manifest.json").read_text())
        deadline = time.monotonic() + 180
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            try:
                with opener.open(
                    f"http://localhost:{manifest['port']}/app/login", timeout=5
                ) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(1)
        else:
            report["stages"].append({"name": "readiness", "status": "timeout"})
            raise RuntimeError("Candidate readiness allowance exhausted")
        stage(
            "http",
            ["python3", str(HERE / "probe.py"), str(root), "--output", str(root / "probe.json")],
            candidate=True,
        )
        stage("restart", ["python3", str(HERE / "restart_probe.py"), str(root)], candidate=True)
        if ui_map is not None:
            stage(
                "browser",
                [
                    "node",
                    str(HERE / "browser-mapped.cjs"),
                    str(root),
                    str(browser.resolve()),
                    str(root / "ui-map.json"),
                ],
                timeout=600,
            )
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        report["stopped"] = str(error)[:200]
    finally:
        # Stop only this attempt. Keep volumes/logs for diagnosis; never reset the DB.
        try:
            project = json.loads((root / "manifest.json").read_text())["project"]
            containers = subprocess.check_output(
                [
                    "docker",
                    "container",
                    "ls",
                    "-q",
                    "--filter",
                    f"label=com.docker.compose.project={project}",
                ],
                text=True,
                timeout=10,
            ).split()
            # Includes one-off migration containers after a CLI timeout.
            with (root / "stop.log").open("w") as log:
                stopped = (
                    subprocess.run(
                        ["docker", "stop", "--time", "10", *containers],
                        stdout=log,
                        stderr=log,
                        timeout=45,
                        check=False,
                    )
                    if containers
                    else None
                )
            report["cleanup"] = "pass" if stopped is None or stopped.returncode == 0 else "error"
        except (subprocess.SubprocessError, OSError):
            report["cleanup"] = "error"
        (root / "isolated-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if "stopped" in report or report["cleanup"] != "pass" else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("prepare")
    setup.add_argument("--source", type=Path, required=True, help="Trusted upstream clone")
    setup.add_argument("--artifact", type=Path, required=True)
    setup.add_argument("--destination", type=Path, required=True)
    setup.add_argument("--project", required=True)
    setup.add_argument("--port", type=int, default=33085)
    setup.add_argument("--vite-port", type=int, default=33341)
    setup.add_argument("--image", default="pocket-chatwoot-feasibility:5b7038b")
    execute = sub.add_parser("run")
    execute.add_argument("workspace", type=Path)
    execute.add_argument("--ui-map", type=Path)
    execute.add_argument("--browser", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    else:
        raise SystemExit(run(args.workspace, args.ui_map, args.browser))
