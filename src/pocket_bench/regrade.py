"""Regrade saved artifacts in a new offline container without rerunning an agent."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from pocket_bench.report import generate, read


def regrade(source, destination, suite_root):
    source, destination, suite_root = (Path(p).resolve() for p in (source, destination, suite_root))
    if destination.exists():
        raise ValueError("Destination exists; original results must not be overwritten")
    if destination.is_relative_to(source):
        raise ValueError("Regrade destination must not be nested in the source")
    destination.mkdir(parents=True)
    plan = read(source / "pocket-plan.json", {})
    (destination / "pocket-plan.json").write_text(json.dumps(plan, indent=2))
    for trial in sorted(source.iterdir()):
        original = read(trial / "result.json") if trial.is_dir() else None
        if original is None:
            continue
        name = original["task_name"].removeprefix("pocket/")
        tests = suite_root / "tasks" / name / "tests"
        target = destination / trial.name
        target.mkdir()
        for filename in ("lock.json", "config.json"):
            if (trial / filename).exists():
                shutil.copy(trial / filename, target / filename)
        for dirname in ("agent", "artifacts"):
            if (trial / dirname).is_dir():
                shutil.copytree(trial / dirname, target / dirname, symlinks=True)
        logs = target / "verifier"
        logs.mkdir()
        original["source_trial"] = {"path": str(trial), "action": "regrade"}
        original["verifier_result"] = None
        original["exception_info"] = None
        candidate = trial / "artifacts/app"
        if not candidate.is_dir() or not (tests / "spec.json").is_file():
            original["exception_info"] = {
                "exception_type": "RegradeInputsMissing",
                "exception_message": "Saved candidate or grader unavailable",
            }
        else:
            fingerprint = hashlib.sha256(
                (tests / "grader.py").read_bytes() + (tests / "spec.json").read_bytes()
            ).hexdigest()
            image = "pocket-regrade:" + fingerprint[:16]
            subprocess.run(
                ["docker", "build", "-q", "-t", image, str(tests)], check=True, capture_output=True
            )
            # Docker's read-only mount and no network prevent candidate code touching the host.
            # Hidden verifier is root-only; each candidate function executes as uid 1000.
            args = [
                "docker",
                "create",
                "--network",
                "none",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=32m",
                "--cpus",
                "2",
                "--memory",
                "1g",
                "--mount",
                f"type=bind,src={candidate},dst=/app,readonly",
            ]
            state = trial / "artifacts/var/lib/pocket/state.json"
            if state.is_file():
                args += [
                    "--mount",
                    f"type=bind,src={state},dst=/var/lib/pocket/state.json,readonly",
                ]
            args += [
                image,
                "sh",
                "-c",
                "chmod 700 /logs/verifier && python -I /tests/grader.py /tests/spec.json /app",
            ]
            cid = None
            try:
                cid = subprocess.check_output(args, text=True, timeout=30).strip()
                if len(cid) != 64 or any(c not in "0123456789abcdef" for c in cid):
                    raise RuntimeError("Invalid container ID")
                p = subprocess.run(
                    ["docker", "start", "-a", cid],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                (logs / "regrade-stderr.txt").write_text(p.stderr)
                subprocess.run(
                    ["docker", "cp", cid + ":/logs/verifier/.", str(logs)],
                    check=True,
                    capture_output=True,
                )
                grade = read(logs / "checks.json")
                if p.returncode or grade is None:
                    raise RuntimeError("Offline verifier failed; see regrade-stderr.txt")
                original["verifier_result"] = {
                    "rewards": {"reward": int(grade["status"] == "success")}
                }
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, RuntimeError) as e:
                original["exception_info"] = {
                    "exception_type": type(e).__name__,
                    "exception_message": str(e),
                }
            finally:
                if cid and len(cid) == 64 and all(c in "0123456789abcdef" for c in cid):
                    subprocess.run(["docker", "rm", "-f", cid], check=False, capture_output=True)
            original["regrade_verifier_sha256"] = hashlib.sha256(
                (tests / "grader.py").read_bytes() + (tests / "spec.json").read_bytes()
            ).hexdigest()
        (target / "result.json").write_text(json.dumps(original, indent=2))
    return generate([destination], destination / "report")
