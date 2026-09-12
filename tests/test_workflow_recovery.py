"""Exercise the real fixture handlers and grade their persisted recovery evidence."""

import io
import json
from types import SimpleNamespace

import pytest
from test_workloads import SPECS, workspace

from pocket_bench import mock_api
from pocket_bench.grader import grade
from pocket_bench.suites import SUITES

WORKFLOWS = [s for s in SPECS if s.get("api") == "workflow"]


def service(tmp_path, monkeypatch, count):
    handlers = []

    def server(address, handler):
        handlers.append(handler)
        return SimpleNamespace(serve_forever=lambda: None)

    monkeypatch.setattr(mock_api, "HTTPServer", server)
    state_path = tmp_path / "trusted-state.json"
    mock_api.serve(f"workflow-{count}", state_path)

    def request(method, path, payload=None):
        handler = object.__new__(handlers[0])
        body = json.dumps(payload).encode() if payload is not None else b""
        handler.path = path
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile, handler.wfile = io.BytesIO(body), io.BytesIO()
        codes = []
        handler.send_response = codes.append
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        getattr(handler, "do_" + method)()
        return codes[0], json.loads(handler.wfile.getvalue())

    return request, lambda: json.loads(state_path.read_text())


@pytest.mark.parametrize("spec", WORKFLOWS, ids=lambda s: s["id"])
@pytest.mark.parametrize("recovery", ["retry", "get", "mixed"])
def test_both_recovery_methods_have_trusted_evidence_and_pass(
    tmp_path, monkeypatch, spec, recovery
):
    root = workspace(tmp_path, spec)
    request, state = service(tmp_path, monkeypatch, spec["workflow_count"])
    code, initial = request("GET", "/workflow")
    assert code == 200
    for i, job in enumerate(j for j in initial["jobs"] if j["approved"]):
        payload = {"id": job["id"], "amount": job["amount"], "key": job["id"]}
        assert request("POST", "/commit", payload)[0] == 503
        use_get = recovery == "get" or (recovery == "mixed" and i % 2 == 0)
        if use_get:
            code, confirmed = request("GET", "/workflow")
            assert code == 200 and job["id"] in confirmed["committed"]
            assert job["id"] in state()["confirmed_via_get"]
            assert state()["attempts"][job["id"]] == 1
        else:
            assert request("POST", "/commit", payload)[0] == 200
            assert job["id"] not in state()["confirmed_via_get"]
            assert job["id"] in state()["confirmed_via_retry"]
    (root / "output/result.json").write_text(json.dumps(spec["expected"]))
    assert grade(spec, root, api_state=state())["status"] == "success"
    assert state()["committed"] == spec["expected"]["committed"]
    assert state()["violations"] == 0


@pytest.mark.parametrize("spec", WORKFLOWS, ids=lambda s: s["id"])
@pytest.mark.parametrize(
    "recovery", ["none", "final-get", "late-retry", "excess-retries", "wrong-key", "denied"]
)
def test_invalid_recovery_still_fails(tmp_path, monkeypatch, spec, recovery):
    root = workspace(tmp_path, spec)
    request, state = service(tmp_path, monkeypatch, spec["workflow_count"])
    _, initial = request("GET", "/workflow")
    assert state()["confirmed_via_get"] == []
    for job in (j for j in initial["jobs"] if j["approved"]):
        payload = {"id": job["id"], "amount": job["amount"], "key": job["id"]}
        assert request("POST", "/commit", payload)[0] == 503
        if recovery == "excess-retries":
            for _ in range(3):
                request("POST", "/commit", payload)
            request("GET", "/workflow")
        elif recovery == "wrong-key":
            assert request("POST", "/commit", {**payload, "key": "different"})[0] == 400
            request("GET", "/workflow")
        elif recovery == "denied":
            request("GET", "/workflow")
    if recovery == "final-get":
        request("GET", "/workflow")
        assert state()["confirmed_via_get"] == spec["expected"]["committed"][-1:]
    if recovery == "late-retry":
        for job in (j for j in initial["jobs"] if j["approved"]):
            request("POST", "/commit", {**job, "key": job["id"]})
    if recovery == "denied":
        job = next(j for j in initial["jobs"] if not j["approved"])
        assert request("POST", "/commit", {**job, "key": job["id"]})[0] == 400
    (root / "output/result.json").write_text(json.dumps(spec["expected"]))
    result = grade(spec, root, api_state=state())
    assert result["status"] == "failure"
    if recovery in ("none", "final-get", "late-retry", "excess-retries"):
        assert any(
            c["name"] == "recovered-ambiguous-commits" and not c["passed"] for c in result["checks"]
        )


def test_workflow_grading_revision_is_versioned():
    assert SUITES["capability"]["version"] == "1.2"
    assert SUITES["long-horizon"]["version"] == "1.2"
