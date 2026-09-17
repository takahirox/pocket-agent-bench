#!/usr/bin/env python3
"""Black-box R1–R6 checks; expectations come from the pre-migration fixture."""

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

from probe import API, DENIED, Probe, require, verify_conversations


def condition(attribute, values, join=None):
    return {
        "attribute_key": attribute,
        "filter_operator": "equal_to",
        "values": values,
        "query_operator": join,
    }


class Behavior(Probe):
    def request(self, actor, path, method="GET", data=None, expected=(200,)):
        status, body = self.api.request(actor, path, method, data)
        require(status in expected, f"{method} returned HTTP {status}; expected {list(expected)}")
        return body

    def make(self, actor="alice", team=None, name=None, **extra):
        status, body = self.create(
            actor, self.f["teams"]["support"] if team is None else team, name=name, extra=extra
        )
        require(status in {200, 201} and isinstance(body, dict), f"Create returned HTTP {status}")
        return body["id"]

    def read(self, actor, view):
        return self.request(actor, f"{self.path}/{view}")

    def patch(self, actor, view, **data):
        return self.request(actor, f"{self.path}/{view}", "PATCH", {"custom_filter": data})

    def membership(self, actor, add):
        self.request(
            "admin",
            f"/api/v1/accounts/{self.f['accounts']['A']}/teams/{self.f['teams']['support']}/team_members",
            "POST" if add else "DELETE",
            {"user_ids": [self.f["users"][actor]["id"]]},
        )

    def unread(self, actor, view, count):
        body = self.request(
            actor, f"/api/v1/accounts/{self.f['accounts']['A']}/conversations/unread_counts"
        )
        folders = body["payload"]["folders"]
        require(
            folders.get(str(view), 0) == count,
            f"Wrong unread count for {actor}: expected {count}, got {folders.get(str(view), 0)}",
        )
        if count == 0:
            require(
                str(view) not in folders or folders[str(view)] == 0,
                "Inaccessible unread count leaked",
            )

    def personal(self):
        for filter_type in ("conversation", "contact", "report"):
            for audience in (..., None):
                status, body = self.create("alice", audience, extra={"filter_type": filter_type})
                require(status in {200, 201}, "Legacy create failed")
                view = body["id"]
                require(body.get("team_id") is None, "Legacy create became shared")
                self.patch("alice", view, name="Personal updated")
                require(
                    self.read("alice", view)["name"] == "Personal updated", "Personal update lost"
                )
                for actor in ("admin", "bob"):
                    self.request(actor, f"{self.path}/{view}", expected=DENIED)
                self.request("alice", f"{self.path}/{view}", "DELETE", expected=(200, 204))
                self.request("alice", f"{self.path}/{view}", expected=(404,))

    def identities(self):
        name = self.tag + " duplicate"
        first = self.make(name=name)
        second = self.make("admin", team=self.f["teams"]["billing"], name=name)
        require(first != second, "Same-name views collapsed")
        for actor, allowed in (("alice", first), ("carol", second)):
            listed = self.request(actor, self.path)
            require(
                [row["id"] for row in listed if row["name"] == name] == [allowed],
                "Same-name audience isolation failed",
            )
        # Same audience is a legal no-op; a different team and personal conversion are not.
        self.patch("alice", first, team_id=self.f["teams"]["support"])
        for team in (None, self.f["teams"]["billing"]):
            before = self.read("alice", first)
            self.request(
                "alice",
                f"{self.path}/{first}",
                "PATCH",
                {"custom_filter": {"team_id": team}},
                expected=(422,),
            )
            require(self.read("alice", first) == before, "Rejected audience mutation changed data")
        self.membership("admin", True)
        try:
            require(
                sum(r["id"] == first for r in self.request("admin", self.path)) == 1,
                "Administrator/member duplicate",
            )
        finally:
            self.membership("admin", False)

    def forged(self):
        view = self.make(
            user_id=self.f["users"]["bob"]["id"], account_id=self.f["accounts"]["B"], id=999999
        )
        require(view != 999999, "Caller chose primary key")
        self.patch(
            "alice",
            view,
            name="Creator still owns",
            user_id=self.f["users"]["bob"]["id"],
            account_id=self.f["accounts"]["B"],
        )
        for method, data in (("PATCH", {"custom_filter": {"name": "Stolen"}}), ("DELETE", None)):
            before = self.read("alice", view)
            self.request("bob", f"{self.path}/{view}", method, data, DENIED)
            require(self.read("alice", view) == before, "Forbidden mutation persisted")
        for method, data in (
            ("GET", None),
            ("PATCH", {"custom_filter": {"name": "Anonymous"}}),
            ("DELETE", None),
        ):
            self.request("anonymous", f"{self.path}/{view}", method, data, (401,))
        self.request("anonymous", self.path, expected=(401,))
        self.request(
            "anonymous",
            self.path,
            "POST",
            {"custom_filter": {"name": "anonymous", "query": self.query}},
            (401,),
        )

    def invalid(self):
        invalid = [
            {"query": None},
            {"query": {}},
            {"query": {"payload": []}},
            {"query": {"payload": [condition("nonexistent", ["x"])]}},
            {
                "query": {
                    "payload": [dict(condition("status", ["open"]), filter_operator="nonexistent")]
                }
            },
            *({"team_id": value} for value in ("wrong", True, 1.5, [], {})),
            *({"name": value} for value in (None, [], {})),
            {"filter_type": "unknown"},
        ]
        for extra in invalid:
            before = self.request("alice", self.path)
            status, _ = self.create("alice", self.f["teams"]["support"], extra=extra)
            require(status == 422, f"Invalid {next(iter(extra))} returned HTTP {status}")
            require(
                self.request("alice", self.path) == before, "Rejected create changed collection"
            )
        view = self.make()
        for extra in ({"name": " "}, {"query": {}}, {"team_id": -1}):
            before = self.read("alice", view)
            self.request("alice", f"{self.path}/{view}", "PATCH", {"custom_filter": extra}, (422,))
            require(self.read("alice", view) == before, "Rejected update changed data")

    def membership_changes(self):
        view = self.make()
        self.read("alice", view)
        self.membership("alice", False)
        try:
            self.request("alice", f"{self.path}/{view}", expected=DENIED)
            self.request(
                "alice",
                f"{self.path}/{view}",
                "PATCH",
                {"custom_filter": {"name": "Former creator"}},
                DENIED,
            )
            require(
                all(row["id"] != view for row in self.request("alice", self.path)),
                "Former creator still listed",
            )
            self.read("bob", view)
        finally:
            self.membership("alice", True)
        self.patch("alice", view, name="Rejoined creator")
        self.request("erin", f"{self.path}/{view}", expected=DENIED)
        self.membership("erin", True)
        try:
            self.read("erin", view)
        finally:
            self.membership("erin", False)
        self.request("erin", f"{self.path}/{view}", expected=DENIED)
        require(
            all(row["id"] != view for row in self.request("erin", self.path)),
            "Removed member still listed",
        )

    def counts_and_inbox(self):
        view = self.make()
        for actor, count in (
            ("alice", 5),
            ("bob", 3),
            ("alice", 5),
            ("bob", 3),
            ("dana", 0),
            ("erin", 0),
        ):
            self.unread(actor, view, count)
        self.membership("bob", False)
        try:
            self.unread("bob", view, 0)
        finally:
            self.membership("bob", True)
        path = f"/api/v1/accounts/{self.f['accounts']['A']}/inbox_members"
        self.request(
            "admin",
            path,
            "DELETE",
            {"inbox_id": self.f["inboxes"]["general"], "user_ids": [self.f["users"]["bob"]["id"]]},
        )
        try:
            self.read("bob", view)
            self.unread("bob", view, 0)
            body = self.request(
                "bob",
                f"/api/v1/accounts/{self.f['accounts']['A']}/conversations/filter",
                "POST",
                self.query,
            )
            verify_conversations(body, set())
        finally:
            self.request(
                "admin",
                "/api/v1/accounts/" + str(self.f["accounts"]["A"]) + "/inbox_members",
                "POST",
                {
                    "inbox_id": self.f["inboxes"]["general"],
                    "user_ids": [self.f["users"]["bob"]["id"]],
                },
            )
        hidden = next(r for r in self.f["conversations"] if r["inbox"] == "restricted")
        self.request(
            "bob",
            f"/api/v1/accounts/{self.f['accounts']['A']}/conversations/{hidden['display_id']}",
            expected=DENIED,
        )

    def literal_assignee(self):
        query = {
            "payload": [
                condition("status", ["open"], "AND"),
                condition("assignee_id", [self.f["users"]["alice"]["id"]]),
            ]
        }
        view = self.make(query=query)
        for actor, inboxes in (("alice", {"general", "restricted"}), ("bob", {"general"})):
            stored = self.read(actor, view)["query"]
            body = self.request(
                actor,
                f"/api/v1/accounts/{self.f['accounts']['A']}/conversations/filter",
                "POST",
                stored,
            )
            expected = {
                r["display_id"]
                for r in self.f["conversations"]
                if r["inbox"] in inboxes
                and r["status"] == "open"
                and r["assignee_id"] == self.f["users"]["alice"]["id"]
            }
            verify_conversations(body, expected)

    def pagination(self):
        account = self.f["accounts"]["C"]
        path = f"/api/v1/accounts/{account}/custom_filters"
        query = {
            "payload": [
                condition("status", ["open"], "AND"),
                condition("inbox_id", [self.f["inboxes"]["paging"]]),
            ]
        }
        view = self.request(
            "page_admin",
            path,
            "POST",
            {
                "custom_filter": {
                    "name": "Paged",
                    "team_id": self.f["teams"]["support_c"],
                    "filter_type": "conversation",
                    "query": query,
                }
            },
            (200, 201),
        )["id"]
        try:
            for statuses, current in (
                ({"open"}, query),
                (
                    {"open", "resolved"},
                    {
                        "payload": [
                            condition("status", ["open"], "OR"),
                            condition("status", ["resolved"]),
                        ]
                    },
                ),
            ):
                self.request(
                    "page_admin", f"{path}/{view}", "PATCH", {"custom_filter": {"query": current}}
                )
                stored = self.request("pager", f"{path}/{view}")["query"]
                expected = {
                    r["display_id"]
                    for r in self.f["conversations"]
                    if r["inbox"] == "paging" and r["status"] in statuses
                }
                found = []
                for page in range(1, 8):
                    body = self.request(
                        "pager",
                        f"/api/v1/accounts/{account}/conversations/filter",
                        "POST",
                        {**stored, "page": page},
                    )
                    require(
                        body["meta"]["all_count"] == len(expected),
                        "Pagination total includes hidden/missing conversations",
                    )
                    rows = body["payload"]
                    if not rows:
                        break
                    found.extend(r["id"] for r in rows)
                require(
                    len(found) == len(set(found)) and set(found) == expected,
                    "Paginated results missing, duplicated, or unauthorized",
                )
        finally:
            self.request("page_admin", f"{path}/{view}", "DELETE", expected=(200, 204))

    def team_deletion(self):
        teams = f"/api/v1/accounts/{self.f['accounts']['A']}/teams"
        team = self.request(
            "admin",
            teams,
            "POST",
            {"team": {"name": "disposable-team", "allow_auto_assign": False}},
            (200, 201),
        )["id"]
        view = self.make("admin", team=team)
        other = self.make()
        self.request("admin", f"{teams}/{team}", "DELETE", expected=(200, 204))
        self.request("admin", f"{self.path}/{view}", expected=(403, 404))
        require(
            all(r["id"] != view for r in self.request("admin", self.path)),
            "Deleted team still listed",
        )
        self.read("bob", other)
        self.read("bob", self.f["personal"]["bob"]["id"])

    def creator_deletion(self, root, actor):
        view = self.make(actor)
        self.created[-1] = ("admin", view)
        uid = self.f["users"][actor]["id"]
        self.request(
            "admin",
            f"/api/v1/accounts/{self.f['accounts']['A']}/agents/{uid}",
            "DELETE",
            expected=(200, 204),
        )
        self.request(actor, f"{self.path}/{view}", expected=DENIED)
        self.read("bob", view)
        # Observe completion in the unchanged upstream user/team-membership tables.
        # This does not prescribe the candidate's shared-view schema.
        sql = (
            f"SELECT count(*) FROM users WHERE id={uid}"
            if actor == "deleted"
            else f"SELECT count(*) FROM team_members WHERE user_id={uid} AND team_id={self.f['teams']['support']}"
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            raw = subprocess.check_output(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(root / "compose.yaml"),
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "pocket",
                    "-d",
                    "pocket_team_views",
                    "-At",
                    "-c",
                    sql,
                ],
                text=True,
            )
            if raw.strip() == "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Asynchronous creator cleanup did not complete")
        # Job enqueues dependent cleanup. Wait for all database destruction queues to settle.
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(root / "compose.yaml"),
                "exec",
                "-T",
                "worker",
                "bundle",
                "exec",
                "rails",
                "runner",
                "require 'sidekiq/api'; deadline=Process.clock_gettime(Process::CLOCK_MONOTONIC)+30; loop { busy=Sidekiq::Workers.new.size; size=Sidekiq::Queue.all.sum(&:size); break if busy.zero? && size.zero?; raise 'Jobs did not drain' if Process.clock_gettime(Process::CLOCK_MONOTONIC)>deadline; sleep 0.2 }",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
        )
        self.read("bob", view)
        self.patch("admin", view, name="Maintained after creator departure")

    def evaluate(self, root, lifecycle=False):
        cases = [
            ("personal.crud", "R1/R6", self.personal),
            ("shared.identity_and_audience", "R2/R3/R6", self.identities),
            ("shared.forged_and_anonymous", "R3/R6", self.forged),
            ("shared.invalid_inputs", "R2/R6", self.invalid),
            ("shared.membership_changes", "R3/R5", self.membership_changes),
            ("shared.viewer_counts_and_inbox_changes", "R4/R5", self.counts_and_inbox),
            ("shared.literal_assignee", "R2/R4", self.literal_assignee),
            ("shared.compound_pagination", "R2/R4", self.pagination),
            ("shared.team_deletion", "R5", self.team_deletion),
        ]
        if lifecycle:
            cases = [
                (
                    f"shared.creator_{actor}",
                    "R5",
                    lambda actor=actor: self.creator_deletion(root, actor),
                )
                for actor in ("removed", "deleted")
            ]
        for name, requirement, action in cases:
            self.check(name, requirement, action)
        self.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--lifecycle", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    fixture = json.loads((root / "fixture.json").read_text())
    probe = Behavior(API(f"http://localhost:{manifest['port']}"), fixture)
    for actor, info in fixture["users"].items():
        probe.api.login(actor, info["email"])
    probe.evaluate(root, args.lifecycle)
    report = {
        "schema_version": 1,
        "checks": probe.results,
        "summary": dict(Counter(r["status"] for r in probe.results)),
    }
    name = "lifecycle" if args.lifecycle else "behavior"
    (root / f"{name}.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"]))
    return 2 if report["summary"].get("error") else 1 if report["summary"].get("fail") else 0


if __name__ == "__main__":
    raise SystemExit(main())
