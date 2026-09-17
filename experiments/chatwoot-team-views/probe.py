#!/usr/bin/env python3
"""Maintainer HTTP qualification probe. Deliberately NOT a final task grader."""

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

DENIED = {401, 403, 404}
PASSWORD = "PocketBench123!"


class Mismatch(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Mismatch(message)


def verify_conversations(body, expected_ids):
    require(isinstance(body, dict), "Expected JSON object")
    rows = body.get("payload")
    require(isinstance(rows, list), "Missing conversation payload")
    actual = [row.get("id") for row in rows]
    require(len(actual) == len(set(actual)), "Duplicate conversation IDs")
    require(
        set(actual) == set(expected_ids),
        f"Wrong visible conversations: expected {len(expected_ids)}, got {len(actual)}",
    )
    require(body.get("meta", {}).get("all_count") == len(expected_ids), "Incorrect all_count")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class API:
    def __init__(self, base):
        parsed = urllib.parse.urlparse(base)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Only a local synthetic fixture HTTP endpoint is accepted")
        self.base = base.rstrip("/")
        self.headers = {}
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, actor, path, method="GET", payload=None):
        headers = {"Content-Type": "application/json", **self.headers.get(actor, {})}
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            body = (
                json.loads(raw)
                if raw and "json" in response.headers.get("Content-Type", "")
                else None
            )
            # Token rotation is kept in memory and is never emitted in reports.
            tokens = {key: response.headers.get(key) for key in ("access-token", "client", "uid")}
            if all(tokens.values()):
                self.headers[actor] = tokens
            return response.status, body

    def login(self, actor, email):
        status, _ = self.request(
            actor, "/auth/sign_in", "POST", {"email": email, "password": PASSWORD}
        )
        require(
            status == 200 and actor in self.headers,
            f"Fixture login failed for {actor}: HTTP {status}",
        )


class Probe:
    def __init__(self, api, fixture):
        self.api = api
        self.f = fixture
        self.results = []
        self.created = []
        self.path = f"/api/v1/accounts/{fixture['accounts']['A']}/custom_filters"
        self.query = fixture["personal"]["alice"]["query"]
        self.tag = f"Qualification {time.time_ns()}"

    def check(self, name, requirement, action):
        try:
            action()
        except Mismatch as error:
            result = {"status": "fail", "detail": str(error)}
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            result = {"status": "error", "detail": type(error).__name__ + ": endpoint unavailable"}
        except Exception as error:  # noqa: BLE001 - report evaluator faults as unscored
            # Evaluator bugs/unexpected schemas do not become a candidate failure.
            result = {
                "status": "error",
                "detail": type(error).__name__ + ": probe could not evaluate",
            }
        else:
            result = {"status": "pass"}
        self.results.append(dict(name=name, requirement=requirement, **result))

    def create(self, actor, team, name=None, extra=None):
        data = {"name": name or self.tag, "filter_type": "conversation", "query": self.query}
        if team is not ...:
            data["team_id"] = team
        data.update(extra or {})
        status, body = self.api.request(actor, self.path, "POST", {"custom_filter": data})
        if status in {200, 201} and isinstance(body, dict) and isinstance(body.get("id"), int):
            self.created.append((actor, body["id"]))
        return status, body

    def get(self, actor, view_id):
        return self.api.request(actor, f"{self.path}/{view_id}")

    def visible_ids(self, actor):
        inboxes = {
            "admin": {"general", "restricted"},
            "alice": {"general", "restricted"},
            "bob": {"general"},
            "carol": {"general"},
            "dana": set(),
            "erin": {"general"},
        }[actor]
        # Expected values come from the trusted fixture, not another candidate endpoint.
        # Chatwoot conversation JSON id is the account-scoped display_id.
        return {
            c["display_id"]
            for c in self.f["conversations"]
            if c["account"] == "A" and c["inbox"] in inboxes and c["status"] == "open"
        }

    def conversations(self, actor, query):
        status, body = self.api.request(
            actor, f"/api/v1/accounts/{self.f['accounts']['A']}/conversations/filter", "POST", query
        )
        require(status == 200, f"Conversation filter HTTP {status}")
        verify_conversations(body, self.visible_ids(actor))

    def baseline(self):
        for actor in ("admin", "alice", "bob", "carol", "dana", "erin"):
            self.check(
                f"baseline.conversations.{actor}",
                "baseline",
                lambda actor=actor: self.conversations(actor, self.query),
            )
        for actor in ("alice", "bob"):

            def own(actor=actor):
                status, body = self.get(actor, self.f["personal"][actor]["id"])
                require(status == 200, f"Personal read HTTP {status}")
                require(
                    body["query"] == self.query and body["name"] == "My open requests",
                    "Personal filter changed",
                )

            self.check(f"baseline.personal.{actor}", "baseline", own)
        for actor in ("admin", "bob", "foreign_admin"):

            def denied(actor=actor):
                status, body = self.get(actor, self.f["personal"]["alice"]["id"])
                require(status in DENIED, f"Personal isolation HTTP {status}")
                require("My open requests" not in json.dumps(body), "Personal name leaked")

            self.check(f"baseline.personal_isolation.{actor}", "baseline", denied)

    def shared(self):
        team = self.f["teams"]["support"]
        holder = {}

        def create():
            status, body = self.create("alice", team)
            require(status in {200, 201}, f"Create HTTP {status}")
            require(
                isinstance(body, dict) and isinstance(body.get("id"), int), "Missing created ID"
            )
            holder["id"] = body["id"]
            require(body.get("team_id") == team, "Shared team_id not persisted/exposed")

        self.check("shared.create", "R2/R6", create)
        if "id" not in holder:
            self.results.append(
                {
                    "name": "shared.dependent_checks",
                    "requirement": "R3-R6",
                    "status": "blocked",
                    "detail": "No created view ID",
                }
            )
            return
        view_id = holder["id"]
        for actor in ("admin", "alice", "bob", "carol", "dana", "erin", "foreign_admin"):
            allowed = actor in {"admin", "alice", "bob", "dana"}

            def read(actor=actor, allowed=allowed):
                status, body = self.get(actor, view_id)
                if allowed:
                    require(status == 200, f"Shared read HTTP {status}")
                    require(body.get("team_id") == team, "Missing/wrong team_id")
                    require(body.get("query") == self.query, "Shared query changed")
                else:
                    require(status in DENIED, f"Unauthorized read HTTP {status}")
                    require(self.tag not in json.dumps(body), "Shared name leaked")

            self.check(f"shared.read.{actor}", "R3/R6", read)

            def listing(actor=actor, allowed=allowed):
                status, body = self.api.request(actor, self.path)
                if actor == "foreign_admin":
                    require(status in DENIED, f"Cross-account list HTTP {status}")
                    return
                require(status == 200 and isinstance(body, list), f"List HTTP {status}")
                count = sum(row.get("id") == view_id for row in body)
                require(
                    count == int(allowed),
                    f"Expected shared view occurrences {int(allowed)}, got {count}",
                )

            self.check(f"shared.list.{actor}", "R3/R6", listing)
            if allowed:

                def filtered(actor=actor):
                    status, body = self.get(actor, view_id)
                    require(status == 200, f"Cannot obtain shared query: HTTP {status}")
                    self.conversations(actor, body["query"])

                self.check(f"shared.conversations.{actor}", "R4", filtered)

        for actor in ("bob", "carol", "dana", "erin", "foreign_admin"):

            def forbidden_write(actor=actor):
                before_status, before = self.get("alice", view_id)
                require(before_status == 200, "Owner cannot read before denied write")
                status, _ = self.api.request(
                    actor,
                    f"{self.path}/{view_id}",
                    "PATCH",
                    {"custom_filter": {"name": self.tag + " forbidden"}},
                )
                require(status in DENIED, f"Forbidden update HTTP {status}")
                after_status, after = self.get("alice", view_id)
                require(after_status == 200 and after == before, "Denied update changed data")

            self.check(f"shared.denied_update.{actor}", "R3", forbidden_write)

        for actor in ("alice", "admin"):

            def edit(actor=actor):
                name = self.tag + " " + actor
                status, _ = self.api.request(
                    actor, f"{self.path}/{view_id}", "PATCH", {"custom_filter": {"name": name}}
                )
                require(status == 200, f"Permitted update HTTP {status}")
                status, body = self.get("alice", view_id)
                require(status == 200 and body.get("name") == name, "Rename did not persist")
                require(body.get("team_id") == team, "Omitted audience changed sharing")

            self.check(f"shared.update.{actor}", "R3/R6", edit)

        def fixed_audience():
            status, _ = self.api.request(
                "alice", f"{self.path}/{view_id}", "PATCH", {"custom_filter": {"team_id": None}}
            )
            require(status == 422, f"Audience change HTTP {status}")
            status, body = self.get("alice", view_id)
            require(
                status == 200 and body.get("team_id") == team, "Rejected audience change persisted"
            )

        self.check("shared.fixed_audience", "R6", fixed_audience)

        for label, actor, target, extra, expected in (
            ("cross_account", "alice", self.f["teams"]["support_b"], {}, {422}),
            ("missing_team", "alice", max(self.f["teams"].values()) + 100000, {}, {422}),
            ("blank_name", "alice", team, {"name": "   "}, {422}),
            ("contact_type", "alice", team, {"filter_type": "contact"}, {422}),
            ("report_type", "alice", team, {"filter_type": "report"}, {422}),
            ("nonmember", "carol", team, {}, {403, 404}),
        ):

            def invalid(actor=actor, target=target, extra=extra, expected=expected):
                status, _ = self.create(actor, target, extra=extra)
                require(status in expected, f"Invalid/unauthorized create HTTP {status}")

            self.check(f"shared.invalid.{label}", "R2/R3/R6", invalid)

    def cleanup(self):
        for actor, view_id in reversed(self.created):

            def delete(actor=actor, view_id=view_id):
                status, _ = self.api.request(actor, f"{self.path}/{view_id}", "DELETE")
                require(status in {200, 204, 404}, f"Cleanup HTTP {status}")

            self.check(f"cleanup.{actor}.{view_id}", "maintenance", delete)

    def report(self):
        counts = dict(Counter(r["status"] for r in self.results))
        return {
            "schema_version": 1,
            "kind": "maintainer-qualification",
            "task_version": "0.1-draft",
            "correctness": "unscored",
            "qualified_for_agent_comparison": False,
            "missing_coverage": [
                "populated upgrade and restart",
                "membership/cache lifecycle",
                "creator/account/team deletion",
                "unread and pagination",
                "compound/current-user queries",
                "browser workflows",
                "build/lint and expanded regression",
                "reference and negative-control validation",
                "isolated final-verifier integration",
            ],
            "summary": counts,
            "checks": self.results,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.workspace / "manifest.json").read_text())
    fixture = json.loads((args.workspace / "fixture.json").read_text())
    probe = Probe(API(f"http://localhost:{manifest['port']}"), fixture)
    try:
        for actor, info in fixture["users"].items():
            probe.api.login(actor, info["email"])
        probe.baseline()
        probe.shared()
    except Exception as error:  # noqa: BLE001 - report evaluator faults as unscored
        probe.results.append(
            {
                "name": "environment",
                "requirement": "setup",
                "status": "error",
                "detail": type(error).__name__ + ": fixture or endpoint unavailable",
            }
        )
    finally:
        probe.cleanup()
    report = probe.report()
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("kind", "correctness", "summary")}, indent=2))
    raise SystemExit(
        2 if report["summary"].get("error") else 1 if report["summary"].get("fail") else 0
    )


if __name__ == "__main__":
    main()
