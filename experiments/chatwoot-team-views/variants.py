#!/usr/bin/env python3
"""Create reviewable source-level controls; run them through the ordinary grader."""

import argparse
import json
from pathlib import Path

from artifact import read_artifact, write_artifact


def replace(entries, path, before, after):
    mode, data = entries[path]
    text = data.decode()
    if text.count(before) != 1:
        raise ValueError(f"Control anchor not unique in {path}; reference changed")
    entries[path] = (mode, text.replace(before, after).encode())


def variant(entries, kind):
    entries = dict(entries)
    model = "app/models/custom_filter.rb"
    if kind == "reader_can_manage":
        replace(
            entries,
            model,
            """  def manageable_by?(viewer)
    return user_id == viewer.id unless shared?

    account.account_users.exists?(user_id: viewer.id, role: :administrator) ||
      (user_id == viewer.id && team&.team_members&.exists?(user_id: viewer.id))
  end""",
            "  def manageable_by?(_viewer) = true",
        )
    elif kind == "creator_deletes_shared":
        replace(
            entries,
            "app/models/user.rb",
            """  def retain_team_views
    # Shared views belong to the team even after their creator is deleted.
    custom_filters.where.not(team_id: nil).update_all(user_id: nil) # rubocop:disable Rails/SkipsModelValidations
    association(:custom_filters).reset
  end""",
            "  def retain_team_views; end",
        )
    elif kind == "creator_unread_counts":
        replace(
            entries,
            "app/services/conversations/unread_counts/shared_folder_counter.rb",
            "user: @user, query: filter.query",
            "user: filter.user || @user, query: filter.query",
        )
    elif kind == "stale_membership":
        replace(
            entries,
            model,
            "      teams = teams.where(id: viewer.team_members.select(:team_id)) unless membership.administrator?",
            """      cached = Rails.cache.fetch(['view-member-teams', current_account.id, viewer.id]) { viewer.team_members.pluck(:team_id) }
      teams = teams.where(id: cached) unless membership.administrator?""",
        )
    elif kind == "valid_join_and_wording":
        replace(
            entries,
            model,
            "      teams = teams.where(id: viewer.team_members.select(:team_id)) unless membership.administrator?",
            "      teams = teams.joins(:team_members).where(team_members: { user_id: viewer.id }) unless membership.administrator?",
        )
        replace(
            entries,
            "app/javascript/dashboard/i18n/locale/en/advancedFilters.json",
            '"AUDIENCE": "View audience"',
            '"AUDIENCE": "Who can use this view?"',
        )
    else:
        raise ValueError("Unknown control")
    return entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "kind",
        choices=[
            "reader_can_manage",
            "creator_deletes_shared",
            "creator_unread_counts",
            "stale_membership",
            "valid_join_and_wording",
        ],
    )
    parser.add_argument("--ui-map", type=Path, required=True)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=False)
    digest = write_artifact(
        variant(read_artifact(args.artifact), args.kind), args.destination / "candidate.zip"
    )
    ui = json.loads(args.ui_map.read_text())
    if args.kind == "valid_join_and_wording":
        ui["locators"]["audience"]["value"] = "Who can use this view?"
    (args.destination / "ui-map.json").write_text(json.dumps(ui, indent=2) + "\n")
    (args.destination / "control.json").write_text(
        json.dumps({"kind": args.kind, "artifact_sha256": digest}, indent=2) + "\n"
    )
    print(digest)
