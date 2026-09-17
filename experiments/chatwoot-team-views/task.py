#!/usr/bin/env python3
"""Prepare and grade the versioned experimental Chatwoot engineering task."""

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import time
from pathlib import Path

import isolated
from artifact import collect, read_artifact, volume_tar
from execution_guard import run_bounded

HERE = Path(__file__).resolve().parent
CHECKS = json.loads((HERE / "checks.json").read_text())
REQUIRED_STAGES = {
    "submission",
    "services",
    "baseline-schema",
    "fixture",
    "migration",
    "legacy-data",
    "fresh-install",
    "test-schema",
    "ruby-regression",
    "frontend-regression",
    "ruby-lint",
    "frontend-lint",
    "production-build",
    "application",
    "container-boundary",
    "api",
    "behavior",
    "restart",
    "browser",
    "worker",
    "lifecycle",
    "cleanup",
}


class RequirementFailed(Exception):
    """Stop dependent work after a confirmed product failure, preserving its verdict."""


def verify_dependency_image(image, candidate):
    """Inspect locked manifests without starting image-provided code."""
    container = subprocess.check_output(
        ["docker", "create", "--entrypoint", "/bin/true", image], text=True
    ).strip()
    try:
        for name in ("Gemfile", "Gemfile.lock", "package.json", "pnpm-lock.yaml"):
            raw = subprocess.check_output(["docker", "cp", f"{container}:/app/{name}", "-"])
            with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
                members = archive.getmembers()
                if (
                    len(members) != 1
                    or not members[0].isfile()
                    or members[0].size > 4 * 1024 * 1024
                ):
                    raise ValueError("Dependency image has an invalid lockfile")
                content = archive.extractfile(members[0]).read()
            if candidate.get(name, (0, None))[1] != content:
                raise ValueError(
                    "Prepare a dependency image from the submitted locked manifests using the supplied Dockerfile; this is not a correctness failure"
                )
    finally:
        subprocess.run(["docker", "rm", "-v", container], check=True, stdout=subprocess.DEVNULL)


def decision(stages):
    statuses = [row["status"] for row in stages if row.get("required", True)]
    if any(s in {"error", "timeout", "protocol_error"} for s in statuses):
        return "inconclusive", None
    if "fail" in statuses:
        return "fail", 0
    if REQUIRED_STAGES <= {row["name"] for row in stages} and all(s == "pass" for s in statuses):
        return "pass", 1
    return "inconclusive", None


def json_objects(text):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        if isinstance(value, dict):
            yield value


def prepare(args):
    candidate = read_artifact(args.artifact)
    baseline = collect(args.source, base=True)
    verify_dependency_image(args.image, candidate)
    verify_dependency_image(args.baseline_image, baseline)
    args.dependency_image_verified = True
    protected = CHECKS["ruby_regression"] + CHECKS["frontend_regression"]
    protected += [
        name for name in baseline if name.startswith(("spec/support/", "spec/factories/"))
    ]
    protected += [
        "spec/rails_helper.rb",
        "spec/spec_helper.rb",
        ".rubocop.yml",
        ".eslintrc.js",
        "vitest.config.ts",
        "vitest.setup.js",
        "vitest.i18n.js",
        ".rspec",
    ]
    violations = [name for name in protected if candidate.get(name) != baseline.get(name)]
    changed = [name for name in candidate if candidate[name] != baseline.get(name)]
    new_ruby_tests = [
        name
        for name in changed
        if name.startswith("spec/") and name.endswith("_spec.rb") and name not in baseline
    ]
    new_js_tests = [
        name
        for name in changed
        if name.startswith("app/javascript/")
        and name.endswith((".spec.js", ".test.js"))
        and name not in baseline
    ]
    notes = candidate.get("BENCHMARK_NOTES.md", (0, b""))[1]
    ui_bytes = args.ui_map.read_bytes()
    if len(ui_bytes) > 16384:
        raise ValueError("UI map exceeds 16 KiB")
    json.loads(ui_bytes)
    browser_id = subprocess.check_output(
        ["docker", "image", "inspect", args.browser_image, "--format", "{{.Id}}"], text=True
    ).strip()
    isolated.prepare(args)
    root = args.destination.resolve()
    config = json.loads((root / "compose.yaml").read_text())
    app = config["services"]["app"]
    app["environment"].update(
        RAILS_ENV="production",
        NODE_ENV="production",
        RAILS_SERVE_STATIC_FILES="true",
        ENABLE_RACK_ATTACK="false",
    )
    app["command"] = ["bundle", "exec", "rails", "server", "-b", "0.0.0.0", "-p", "3000"]
    config["services"]["build"] = {
        **app,
        "mem_limit": "5g",
        "cpus": 3,
        "environment": {
            **app["environment"],
            "NODE_OPTIONS": "--max-old-space-size=4096",
            "VITE_RUBY_SKIP_ASSETS_PRECOMPILE_INSTALL": "true",
            "SECRET_KEY_BASE_DUMMY": "1",
        },
    }
    config["services"]["worker"] = {
        **app,
        "mem_limit": "1g",
        "cpus": 1,
        "command": ["bundle", "exec", "sidekiq", "-c", "1"],
    }
    config["services"]["seed"]["environment"] = {
        **config["services"]["seed"]["environment"],
        "POCKET_COMPLETE_FIXTURE": "1",
    }
    config["services"]["seed"]["volumes"].append("verify:/verify-input")
    config["services"]["browser"] = {
        "image": browser_id,
        "user": "1000:1000",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "read_only": True,
        "tmpfs": ["/tmp:rw,nosuid,size=536870912,mode=1777"],
        "shm_size": "512m",
        "pids_limit": 512,
        "mem_limit": "2g",
        "cpus": 2,
        "volumes": ["verify:/verify-input:ro"],
        "environment": {"BROWSER_BASE_URL": "http://proxy:3000"},
    }
    config["volumes"]["verify"] = {}
    (root / "compose.yaml").write_text(json.dumps(config, indent=2) + "\n")
    (root / "ui-map.json").write_bytes(ui_bytes)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest.pop("correctness", None)
    manifest.pop("qualified_for_agent_comparison", None)
    manifest.update(
        kind="engineering-task-submission",
        task_id="chatwoot-team-views",
        task_version="0.2",
        fixture_version=2,
        ui_map_sha256=hashlib.sha256(ui_bytes).hexdigest(),
        browser_image=browser_id,
        protected_file_changes=violations,
        changed_files=changed,
        new_ruby_tests=new_ruby_tests,
        new_js_tests=new_js_tests,
        has_submission_notes=bool(notes.strip()),
        evaluator_fingerprints={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in HERE.iterdir()
            if p.suffix in {".py", ".cjs", ".json", ".rb"} and "evidence" not in p.name
        },
    )
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Prepared experimental task 0.2; candidate and verifier use separate volumes")


def grade(root):
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("task_version") != "0.2":
        raise ValueError("Not a version 0.2 task environment")
    with (root / ".grading-started").open("x"):
        pass
    compose = ["docker", "compose", "-f", str(root / "compose.yaml")]
    started = time.monotonic()
    report = {
        "task_id": "chatwoot-team-views",
        "task_version": "0.2",
        "artifact_sha256": manifest["artifact_sha256"],
        "stages": [],
        "human_review": {"status": "not_performed", "rubric": "REVIEW.md"},
        "agent_difficulty": "unmeasured",
    }

    def add(name, status, requirement, **details):
        row = dict(name=name, status=status, requirement=requirement, **details)
        report["stages"].append(row)
        print(f"{name}: {status}", flush=True)
        return status == "pass"

    def command(name, args, requirement, *, timeout=300, parser=None, failure="error"):
        begin = time.monotonic()
        print(name + ": running", flush=True)
        code, interrupted = run_bounded(args, root / f"{name}.log", timeout)
        if interrupted:
            status, details = (
                "timeout" if interrupted == "timeout" else "error",
                {"reason": interrupted},
            )
        else:
            status, details = ("pass" if code == 0 else failure), {}
            log_text = (root / f"{name}.log").read_text(errors="replace")
            if code in {-9, 137, 143} or "heap out of memory" in log_text:
                status, details = (
                    "error",
                    {"reason": "Execution resources exhausted; no correctness penalty"},
                )
            if parser and "reason" not in details:
                status, details = parser(code, log_text)
        okay = add(name, status, requirement, seconds=round(time.monotonic() - begin, 2), **details)
        if interrupted and name != "cleanup":
            raise RuntimeError(f"{name}: {interrupted}; stop attempt and preserve evidence")
        return okay

    def run_service(name, service, argv, requirement, **kwargs):
        return command(name, [*compose, "run", "--rm", service, *argv], requirement, **kwargs)

    def report_parser(filename):
        def parse(code, _text):
            file = root / filename
            if not file.exists():
                return "error", {"reason": "Checker did not produce its structured report"}
            value = json.loads(file.read_text())
            if "summary" in value:
                counts = value["summary"]
                status = (
                    "error"
                    if counts.get("error")
                    else "fail"
                    if counts.get("fail")
                    else "error"
                    if counts.get("blocked")
                    else "pass"
                )
                if code not in (0, 1, 2) or (status == "pass" and code != 0):
                    status = "error"
                return status, {"checks": counts}
            return value.get("status", "error"), {}

        return parse

    def rspec_parser(minimum):
        def parse(code, text):
            matches = [v for v in json_objects(text) if "summary" in v and "examples" in v]
            if not matches:
                return "error", {"reason": "Missing RSpec structured result"}
            summary = matches[-1]["summary"]
            if summary["example_count"] < minimum or summary["pending_count"]:
                return "fail", {"summary": summary}
            return ("pass" if code == 0 and summary["failure_count"] == 0 else "fail"), {
                "summary": summary
            }

        return parse

    def vitest_parser(code, text):
        matches = [v for v in json_objects(text) if "numTotalTests" in v]
        if not matches:
            return "error", {"reason": "Missing Vitest structured result"}
        value = matches[-1]
        okay = (
            code == 0
            and value.get("success")
            and value["numPassedTests"] >= 184
            and not value["numPendingTests"]
        )
        return "pass" if okay else "fail", {
            "tests": value["numTotalTests"],
            "passed": value["numPassedTests"],
        }

    def browser_parser(code, text):
        lines = [
            line.removeprefix("POCKET_BROWSER=")
            for line in text.splitlines()
            if line.startswith("POCKET_BROWSER=")
        ]
        if len(lines) != 1:
            return "error", {"reason": "Missing browser report"}
        value = json.loads(lines[0])
        (root / "browser.json").write_text(json.dumps(value, indent=2) + "\n")
        states = [r["status"] for r in value["checks"]]
        if "error" in states:
            return "protocol_error", {
                "reason": "UI protocol or browser failure; inspect browser.json"
            }
        if "fail" in states:
            return "fail", {}
        return (
            "pass" if code == 0 and len(states) == 11 and not value["runtime_errors"] else "fail"
        ), {"checks": len(states), "browser": value["browser"]}

    try:
        add(
            "submission",
            "pass"
            if manifest["has_submission_notes"]
            and (manifest["new_ruby_tests"] or manifest["new_js_tests"])
            and not manifest["protected_file_changes"]
            else "fail",
            "R8",
            protected_file_changes=manifest["protected_file_changes"],
            added_tests=len(manifest["new_ruby_tests"]) + len(manifest["new_js_tests"]),
        )
        if not command("services", [*compose, "up", "-d", "--wait", "postgres", "redis"], "setup"):
            raise RuntimeError("Dependency services unavailable")
        if not run_service(
            "baseline-schema",
            "seed",
            ["bundle", "exec", "rails", "db:create", "db:schema:load"],
            "setup",
        ):
            raise RuntimeError("Baseline schema setup failed")
        if not run_service(
            "fixture",
            "seed",
            ["bundle", "exec", "rails", "runner", "/app/benchmark_fixture.rb"],
            "setup",
        ):
            raise RuntimeError("Baseline fixture failed")
        rows = [
            json.loads(line.removeprefix("POCKET_FIXTURE="))
            for line in (root / "fixture.log").read_text().splitlines()
            if line.startswith("POCKET_FIXTURE=")
        ]
        if len(rows) != 1 or rows[0]["fixture_version"] != 2:
            raise RuntimeError("Missing version 2 fixture")
        (root / "fixture.json").write_text(json.dumps(rows[0], indent=2) + "\n")
        if not run_service(
            "migration", "app", ["bundle", "exec", "rails", "db:migrate"], "R1", failure="fail"
        ):
            raise RequirementFailed("Candidate migration did not pass")
        command(
            "legacy-data",
            ["python3", str(HERE / "migration_probe.py"), str(root)],
            "R1",
            parser=report_parser("migration-check.json"),
        )
        command(
            "fresh-install",
            [
                *compose,
                "run",
                "--rm",
                "-e",
                "POSTGRES_DATABASE=pocket_team_views_fresh",
                "-e",
                "REDIS_URL=redis://redis:6379/2",
                "app",
                "bundle",
                "exec",
                "rails",
                "db:prepare",
            ],
            "R1",
            failure="fail",
        )
        test_env = [
            *compose,
            "run",
            "--rm",
            "-e",
            "RAILS_ENV=test",
            "-e",
            "POSTGRES_DATABASE=pocket_team_views_test",
            "-e",
            "REDIS_URL=redis://redis:6379/1",
            "app",
        ]
        if command(
            "test-schema",
            [*test_env, "bundle", "exec", "rails", "db:create", "db:schema:load"],
            "R8",
            failure="fail",
        ):
            command(
                "ruby-regression",
                [
                    *test_env,
                    "bundle",
                    "exec",
                    "rspec",
                    *CHECKS["ruby_regression"],
                    "--format",
                    "json",
                ],
                "R8",
                parser=rspec_parser(148),
            )
            if manifest["new_ruby_tests"]:
                command(
                    "added-ruby-tests",
                    [
                        *test_env,
                        "bundle",
                        "exec",
                        "rspec",
                        *manifest["new_ruby_tests"],
                        "--format",
                        "json",
                    ],
                    "R8",
                    parser=rspec_parser(1),
                )
        run_service(
            "frontend-regression",
            "app",
            [
                "env",
                "NODE_ENV=test",
                "/bin/sh",
                "-c",
                '"$@"; task_test_exit_code=$?; /bin/cat /tmp/frontend-results.json; exit "$task_test_exit_code"',
                "vitest-report",
                "pnpm",
                "test",
                *CHECKS["frontend_regression"],
                *manifest["new_js_tests"],
                "--minWorkers=1",
                "--maxWorkers=2",
                "--reporter=json",
                "--outputFile=/tmp/frontend-results.json",
            ],
            "R8",
            parser=vitest_parser,
        )
        ruby_files = [
            p for p in manifest["changed_files"] if p.endswith(".rb") and p != "db/schema.rb"
        ]
        js_files = [
            p
            for p in manifest["changed_files"]
            if p.startswith("app/") and p.endswith((".js", ".vue"))
        ]
        for language, files in (("ruby", ruby_files), ("frontend", js_files)):
            if files:
                run_service(
                    language + "-lint",
                    "app",
                    [*CHECKS[language + "_lint"], *files],
                    "R8",
                    failure="fail",
                )
            else:
                add(language + "-lint", "pass", "R8", applicable_files=0)
        built = run_service(
            "production-build",
            "build",
            CHECKS["production_build"],
            "R8",
            timeout=600,
            failure="fail",
        )
        if not built:
            raise RequirementFailed("Production build did not pass")
        command("application", [*compose, "up", "-d", "app", "proxy"], "R8")
        isolated.audit(compose, root)
        add("container-boundary", "pass", "setup")
        from probe import API
        from restart_probe import wait_ready

        wait_ready(API(f"http://localhost:{manifest['port']}"))
        basic = command(
            "api",
            ["python3", str(HERE / "probe.py"), str(root), "--output", str(root / "probe.json")],
            "R1-R6",
            parser=report_parser("probe.json"),
        )
        if basic:
            command(
                "behavior",
                ["python3", str(HERE / "behavior.py"), str(root)],
                "R1-R6",
                parser=report_parser("behavior.json"),
            )
            command(
                "restart",
                ["python3", str(HERE / "restart_probe.py"), str(root)],
                "R1",
                parser=report_parser("restart-check.json"),
            )
            # Verifier input is copied through the trusted, stopped baseline service.
            command("verifier-input-container", [*compose, "create", "seed"], "setup")
            seed = subprocess.check_output([*compose, "ps", "-aq", "seed"], text=True).strip()
            payload = {
                name: (0o100644, (root / name).read_bytes())
                for name in ("fixture.json", "ui-map.json")
            }
            subprocess.run(
                ["docker", "cp", "-a", "-", f"{seed}:/verify-input"],
                input=volume_tar(payload),
                check=True,
                stdout=subprocess.DEVNULL,
            )
            command(
                "browser",
                [*compose, "run", "--rm", "browser"],
                "R5/R7",
                timeout=600,
                parser=browser_parser,
            )
            command("worker", [*compose, "up", "-d", "worker"], "setup")
            command(
                "lifecycle",
                ["python3", str(HERE / "behavior.py"), str(root), "--lifecycle"],
                "R5",
                timeout=240,
                parser=report_parser("lifecycle.json"),
            )
        else:
            for name in ("behavior", "restart", "browser", "lifecycle"):
                add(name, "blocked", "R1-R7", reason="Basic shared-view API did not pass")
    except RequirementFailed as error:
        completed = {row["name"] for row in report["stages"]}
        for name in sorted(REQUIRED_STAGES - completed - {"cleanup"}):
            add(name, "blocked", "dependent", reason=str(error))
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        add("execution-stop", "error", "setup", detail=str(error)[:200])
    finally:
        try:
            ids = subprocess.check_output(
                [
                    "docker",
                    "container",
                    "ls",
                    "-q",
                    "--filter",
                    f"label=com.docker.compose.project={manifest['project']}",
                ],
                text=True,
                timeout=10,
            ).split()
            if ids:
                command(
                    "cleanup", ["docker", "stop", "--time", "10", *ids], "maintenance", timeout=45
                )
        except (subprocess.SubprocessError, OSError):
            add("cleanup", "error", "maintenance")
        report["automated_correctness"], report["reward"] = decision(report["stages"])
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        (root / "grade.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {key: report[key] for key in ("automated_correctness", "reward", "elapsed_seconds")}
        )
    )
    return {"pass": 0, "fail": 1, "inconclusive": 2}[report["automated_correctness"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare")
    setup.add_argument("--source", type=Path, required=True)
    setup.add_argument("--artifact", type=Path, required=True)
    setup.add_argument("--ui-map", type=Path, required=True)
    setup.add_argument("--destination", type=Path, required=True)
    setup.add_argument("--project", required=True)
    setup.add_argument("--port", type=int, default=33085)
    setup.add_argument("--vite-port", type=int, default=33341)
    setup.add_argument("--image", default="pocket-chatwoot-feasibility:5b7038b")
    setup.add_argument("--baseline-image", default="pocket-chatwoot-feasibility:5b7038b")
    setup.add_argument("--browser-image", default="pocket-team-views-browser:0.2")
    execute = commands.add_parser("grade")
    execute.add_argument("workspace", type=Path)
    args = parser.parse_args()
    return prepare(args) if args.command == "prepare" else grade(args.workspace)


if __name__ == "__main__":
    raise SystemExit(main())
