"""The engineering grader must never convert missing/error checks to a pass."""

import importlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest


@pytest.fixture
def grader(monkeypatch):
    path = Path(__file__).parents[1] / "experiments/chatwoot-team-views"
    monkeypatch.syspath_prepend(str(path))
    # Other qualification tests load these files under private module names.
    module = importlib.import_module("task")
    yield module
    sys.modules.pop("task", None)


def complete(grader):
    return [{"name": name, "status": "pass"} for name in grader.REQUIRED_STAGES]


def test_only_complete_successful_checks_award_a_pass(grader):
    assert grader.decision(complete(grader)) == ("pass", 1)
    assert grader.decision([]) == ("inconclusive", None)
    assert grader.decision(complete(grader)[1:]) == ("inconclusive", None)


@pytest.mark.parametrize("status", ["error", "timeout", "protocol_error"])
def test_infrastructure_or_incomplete_ui_does_not_become_incorrect(grader, status):
    stages = complete(grader)
    stages[0]["status"] = status
    stages[1]["status"] = "fail"
    assert grader.decision(stages) == ("inconclusive", None)


def test_observed_failure_can_block_dependent_checks_without_losing_evidence(grader):
    stages = complete(grader)
    stages[0]["status"] = "fail"
    stages[1]["status"] = "blocked"
    assert grader.decision(stages) == ("fail", 0)


def test_blocked_check_alone_does_not_award_completion(grader):
    stages = complete(grader)
    stages[0]["status"] = "blocked"
    assert grader.decision(stages) == ("inconclusive", None)


def test_json_result_parser_handles_tool_noise_and_never_evaluates_it(grader):
    assert list(grader.json_objects('Warning: {not json}\n{"summary": {"failure_count": 0}}')) == [
        {"summary": {"failure_count": 0}},
        {"failure_count": 0},
    ]
    assert list(grader.json_objects("__import__('os').system('bad')")) == []


def test_execution_guard_bounds_output_and_preserves_the_prefix(grader, tmp_path):
    log = tmp_path / "flood.log"
    _, reason = grader.run_bounded(
        [sys.executable, "-c", "print('x'*10000)"], log, 5, max_bytes=1024
    )
    assert reason == "output_limit"
    assert log.stat().st_size == 1024


def test_execution_guard_stops_a_stuck_command(grader, tmp_path):
    _, reason = grader.run_bounded(
        [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path / "timeout.log", 0.1
    )
    assert reason == "timeout"


def test_execution_guard_keeps_normal_exit_and_diagnostics(grader, tmp_path):
    log = tmp_path / "normal.log"
    code, reason = grader.run_bounded(
        [sys.executable, "-c", "print('diagnostic'); raise SystemExit(1)"], log, 5
    )
    assert (code, reason) == (1, None)
    assert log.read_text() == "diagnostic\n"


def test_negative_control_requires_its_intended_behavioral_failure(grader):
    qualify = importlib.import_module("qualify")
    grade = {"automated_correctness": "fail"}
    assert not qualify.qualifies("reader_can_manage", grade, [])
    assert not qualify.qualifies(
        "reader_can_manage", grade, [{"name": "unrelated", "status": "fail"}]
    )
    expected = [{"name": "shared.denied_update.bob", "status": "fail"}]
    assert qualify.qualifies("reader_can_manage", grade, expected)
    assert not qualify.qualifies(
        "reader_can_manage", {"automated_correctness": "inconclusive"}, expected
    )


def test_positive_controls_must_complete_successfully(grader):
    qualify = importlib.import_module("qualify")
    for kind in ("reference", "valid_join_and_wording"):
        assert qualify.qualifies(kind, {"automated_correctness": "pass"}, [])
        assert not qualify.qualifies(kind, {"automated_correctness": "inconclusive"}, [])
        assert not qualify.qualifies(kind, {"automated_correctness": "fail"}, [])


@pytest.mark.parametrize(
    ("stage", "code", "reason", "expected"),
    [
        ("production-build", 1, None, "fail"),
        ("migration", 1, None, "fail"),
        ("production-build", 137, None, "inconclusive"),
        ("production-build", -15, "timeout", "inconclusive"),
    ],
)
def test_stopping_after_build_or_migration_preserves_failure_kind(
    grader, monkeypatch, tmp_path, stage, code, reason, expected
):
    manifest = {
        "task_version": "0.2",
        "artifact_sha256": "fixture",
        "has_submission_notes": True,
        "new_ruby_tests": [],
        "new_js_tests": ["app/javascript/new.spec.js"],
        "protected_file_changes": [],
        "changed_files": [],
        "project": "test-only",
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "migration-check.json").write_text('{"status":"pass"}')

    def execute(args, log, timeout):
        contents = {
            "fixture": 'POCKET_FIXTURE={"fixture_version":2}\n',
            "ruby-regression": json.dumps(
                {
                    "examples": [],
                    "summary": {"example_count": 148, "pending_count": 0, "failure_count": 0},
                }
            ),
            "frontend-regression": json.dumps(
                {"numTotalTests": 185, "numPassedTests": 185, "numPendingTests": 0, "success": True}
            ),
        }
        log.write_text(contents.get(log.stem, "diagnostic\n"))
        return (code, reason) if log.stem == stage else (0, None)

    monkeypatch.setattr(grader, "run_bounded", execute)
    monkeypatch.setattr(grader.subprocess, "check_output", lambda *a, **kw: "")
    assert grader.grade(tmp_path) == (1 if expected == "fail" else 2)
    report = json.loads((tmp_path / "grade.json").read_text())
    assert report["automated_correctness"] == expected
    assert any(row["name"] == stage for row in report["stages"])


def test_restart_mismatch_is_a_failure_but_transport_error_is_inconclusive(
    grader, monkeypatch, tmp_path
):
    restart = importlib.import_module("restart_probe")
    for error, code, status in (
        (restart.Mismatch("Saved view unavailable after restart"), 1, "fail"),
        (ConnectionError("unavailable"), 2, "error"),
    ):

        def check(_root, error=error):
            raise error

        monkeypatch.setattr(restart, "check", check)
        assert restart.run(tmp_path) == code
        assert json.loads((tmp_path / "restart-check.json").read_text())["status"] == status


def test_upgraded_candidate_dependencies_cannot_replace_baseline_dependencies(grader):
    images = {
        "app": "candidate",
        "seed": "baseline",
        "postgres": "db",
        "redis": "cache",
        "proxy": "proxy",
    }
    config = grader.isolated.configuration("pocket-tv-test", 33085, 33341, images)
    assert config["services"]["app"]["image"] == "candidate"
    assert config["services"]["seed"]["image"] == "baseline"
    assert config["services"]["app"]["volumes"] != config["services"]["seed"]["volumes"]


@pytest.mark.parametrize("mismatch", [False, True])
def test_dependency_inspection_never_starts_image_and_always_removes_container(
    grader, monkeypatch, mismatch
):
    commands = []
    names = ("Gemfile", "Gemfile.lock", "package.json", "pnpm-lock.yaml")
    candidate = {name: (0o100644, b"locked content") for name in names}
    if mismatch:
        candidate["package.json"] = (0o100644, b"changed dependency")

    def output(command, **kwargs):
        commands.append(command)
        if command[1] == "create":
            return "inspection-container\n"
        assert command[1] == "cp"
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            info = tarfile.TarInfo(command[2].split("/")[-1])
            info.size = len(b"locked content")
            archive.addfile(info, io.BytesIO(b"locked content"))
        return buffer.getvalue()

    monkeypatch.setattr(grader.subprocess, "check_output", output)
    monkeypatch.setattr(
        grader.subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    if mismatch:
        with pytest.raises(ValueError, match="not a correctness failure"):
            grader.verify_dependency_image("prepared-image", candidate)
    else:
        grader.verify_dependency_image("prepared-image", candidate)
    assert commands[-1] == ["docker", "rm", "-v", "inspection-container"]
    assert {command[1] for command in commands} <= {"create", "cp", "rm"}
