import json

import pytest

from pocket_bench.report import generate, normalize, summarize


def job(tmp_path):
    root = tmp_path / "job"
    root.mkdir()
    (root / "pocket-plan.json").write_text(
        json.dumps(
            {
                "profiles": ["codex-single"],
                "attempts": 2,
                "tasks": [
                    {
                        "id": "x",
                        "category": "data",
                        "tags": ["a"],
                        "instruction": "<script>alert(1)</script>",
                    }
                ],
            }
        )
    )
    t = root / "x__one"
    t.mkdir()
    (t / "lock.json").write_text("{}")
    (t / "result.json").write_text(
        json.dumps(
            {
                "task_name": "x",
                "config": {
                    "agent": {
                        "import_path": "pocket_bench.agents:CodexAgent",
                        "kwargs": {"mode": "single"},
                    }
                },
                "agent_info": {"name": "pocket-codex"},
                "verifier_result": {"rewards": {"reward": 0}},
                "agent_result": {"cost_usd": None},
            }
        )
    )
    return root


def test_every_scheduled_trial_counts(tmp_path):
    rows = normalize(job(tmp_path))
    s = summarize(rows)
    assert s["total"] == 2 and s["failure"] == 1 and s["unscorable"] == 1
    assert s["total_cost_usd"] is None and s["success_rate_all"] == 0


def test_custom_profiles_same_agent_and_mode_are_not_collapsed(tmp_path):
    root = job(tmp_path)
    plan = json.loads((root / "pocket-plan.json").read_text())
    plan["profiles"] = ["experimental-a", "experimental-b"]
    plan["attempts"] = 1
    plan["profile_metadata"] = {
        name: {"agent": "unrelated-system", "mode": "single"} for name in plan["profiles"]
    }
    (root / "pocket-plan.json").write_text(json.dumps(plan))
    path = root / "x__one/result.json"
    result = json.loads(path.read_text())
    result["config"]["agent"] = {
        "import_path": "pocket_bench.connected_agent:ConnectedAgent",
        "kwargs": {"profile_name": "experimental-a"},
    }
    result["agent_info"] = {"name": "connected-agent"}
    path.write_text(json.dumps(result))
    rows = normalize(root)
    assert len(rows) == 2
    assert {row["condition"] for row in rows} == {"experimental-a", "experimental-b"}
    assert {row["agent"] for row in rows} == {"unrelated-system"}
    assert [row["status"] for row in rows] == ["failure", "unscorable"]


def test_partial_result_not_duplicated(tmp_path):
    root = job(tmp_path)
    t = root / "x__one"
    (t / "config.json").write_text(
        json.dumps({"agent": {"import_path": "pocket_bench.agents:CodexAgent"}})
    )
    (t / "result.json").unlink()
    assert len(normalize(root)) == 2


def test_report_payload_cannot_inject_script(tmp_path):
    root = job(tmp_path)
    page = generate([root], tmp_path / "report").read_text()
    assert "<script>alert(1)</script>" not in page
    assert "\\u003cscript" in page


def test_invalidation_retains_original_grade(tmp_path):
    root = job(tmp_path)
    (root / "pocket-invalidation.json").write_text('{"reason":"broken environment"}')
    rows = normalize(root)
    assert all(r["status"] == "unscorable" for r in rows)
    assert rows[0]["original_status"] == "failure"


@pytest.mark.parametrize(
    "conditions,tasks,matched",
    [
        (["pocket-codex/single"], ["x"], True),
        (["my-ai-employee/single"], ["x"], False),
        (["pocket-codex/single"], ["other"], False),
    ],
)
def test_selective_invalidation_preserves_unaffected_trials(tmp_path, conditions, tasks, matched):
    root = job(tmp_path)
    (root / "pocket-invalidation.json").write_text(
        json.dumps(
            {
                "reason": "adapter defect",
                "conditions": conditions,
                "tasks": tasks,
            }
        )
    )
    rows = normalize(root)
    assert len(rows) == 2
    assert (rows[0]["status"] == "unscorable") == matched
    assert ("original_status" in rows[0]) == matched


def test_incomplete_usage_not_presented_as_full_total():
    rows = [{"status": "failure", "tokens_in": 10, "metadata": {"usage_complete": False}}]
    s = summarize(rows)
    assert s["total_tokens_in"] is None
    assert s["observed_tokens_in"] == 10


def test_report_exports_grouped_summaries_and_provenance(tmp_path):
    root = job(tmp_path)
    page = generate([root], tmp_path / "report")
    report = json.loads(page.with_name("results.json").read_text())
    assert report["groups"]["category"][0]["total"] == 2
    assert "provenance" in report["trials"][0]
