"""The experimental probe must not award a task pass or hide oracle failures."""

import importlib.util
import urllib.error
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "experiments/chatwoot-team-views/probe.py"
spec = importlib.util.spec_from_file_location("team_views_probe", MODULE_PATH)
probe_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe_module)


@pytest.mark.parametrize(
    "rows,count", [([1, 2], 2), ([1, 3], 2), ([1, 2, 3], 3), ([1, 1, 2], 3), ([1, 2], 3)]
)
def test_oracle_rejects_missing_extra_duplicate_or_miscounted_results(rows, count):
    body = {"payload": [{"id": item} for item in rows], "meta": {"all_count": count}}
    if rows == [1, 2] and count == 2:
        probe_module.verify_conversations(body, {1, 2})
    else:
        with pytest.raises(probe_module.Mismatch):
            probe_module.verify_conversations(body, {1, 2})


@pytest.mark.parametrize("base", ["https://localhost", "http://example.com", "file:///etc/passwd"])
def test_probe_rejects_nonlocal_or_non_http_endpoint(base):
    with pytest.raises(ValueError):
        probe_module.API(base)


def test_partial_probe_never_awards_task_pass():
    probe = probe_module.Probe(None, {"accounts": {"A": 1}, "personal": {"alice": {"query": {}}}})
    probe.check("passing sample", "R2", lambda: None)
    report = probe.report()
    assert report["summary"] == {"pass": 1}
    assert report["correctness"] == "unscored"
    assert report["qualified_for_agent_comparison"] is False
    assert report["missing_coverage"]


def test_transport_and_checker_faults_are_distinct_from_candidate_mismatch():
    probe = probe_module.Probe(None, {"accounts": {"A": 1}, "personal": {"alice": {"query": {}}}})
    for error in (
        probe_module.Mismatch("wrong result"),
        urllib.error.URLError("down"),
        KeyError("broken checker"),
    ):

        def fail(error=error):
            raise error

        probe.check(type(error).__name__, "test", fail)
    assert [result["status"] for result in probe.results] == ["fail", "error", "error"]


def test_http_redirect_does_not_forward_fixture_credentials():
    handler = probe_module.NoRedirect()
    assert handler.redirect_request(None, None, 302, "redirect", {}, "http://example.com") is None


def test_existing_compose_project_is_not_initialized(tmp_path, monkeypatch):
    import json

    path = MODULE_PATH.with_name("initialize.py")
    init_spec = importlib.util.spec_from_file_location("team_views_initialize", path)
    module = importlib.util.module_from_spec(init_spec)
    init_spec.loader.exec_module(module)
    (tmp_path / "manifest.json").write_text(json.dumps({"project": "pocket-tv-existing"}))
    commands = []

    def output(command, **kwargs):
        commands.append(command)
        return "existing-volume\n" if command[1] == "volume" else ""

    monkeypatch.setattr(module.subprocess, "check_output", output)
    with pytest.raises(RuntimeError, match="already has resources"):
        module.initialize(tmp_path)
    assert not (tmp_path / ".initialization-started").exists()
    assert any(command[1] == "volume" for command in commands)


def test_negative_control_requires_the_intended_assertion_failure():
    control_spec = importlib.util.spec_from_file_location(
        "team_views_controls", MODULE_PATH.with_name("check_controls.py")
    )
    controls = importlib.util.module_from_spec(control_spec)
    control_spec.loader.exec_module(controls)
    intended = "expected: 1\n got: 2\n1 example, 1 failure\n"
    assert controls.detected("creator_unread_counts", 1, intended)
    assert not controls.detected("creator_unread_counts", 0, intended)
    assert not controls.detected("creator_unread_counts", 1, "NameError\n1 example, 1 failure\n")
    assert not controls.detected("creator_unread_counts", 1, "expected: 1\n got: 2\n0 examples\n")
