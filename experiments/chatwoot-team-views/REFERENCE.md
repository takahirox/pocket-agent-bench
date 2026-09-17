# Reference implementation and qualification

**Historical scenario qualification.** The current complete task and its status
are described in [README.md](README.md). The results below used the archived
`reference-v01.patch`; the current `reference.patch` adds a migration regression
and submission notes. Old scenario totals are not a complete task grade.

The [reference patch](reference.patch) adds team-shared conversation views to
Chatwoot Community commit `5b7038b950b763e230df2d544df9b87b8752fef3`.
It is a maintainer validation artifact, **not part of the starting task supplied
to an agent**. Keep it and these validation resources out of evaluated workspaces.

## What the reference does

- Keeps existing personal filters and their IDs/query values during migration.
- Adds one immutable team audience to a conversation view, scoped to its account.
- Restricts shared creation to members/admins, reading to current members/admins,
  and editing/deletion to the eligible creator/admins.
- Retains shared views after creator removal/deletion, and removes them with a team.
- Uses existing conversation permission filtering; computes shared unread badges
  for the requesting user on each request. The original personal-view cache is
  retained. This deliberately favors simple correctness over a new shared-cache design.
- Adds audience selection and team identification to the existing folder UI;
  hides management controls from readers and preserves input after save failures.
- Includes public request regression tests and English localization for new strings.

The reference does not establish that this is the only good implementation, or
that a single agent cannot solve the task.

## Reproduce the populated upgrade

From the PocketAgentBench root, first follow `BASELINE.md` to prepare and initialize
a fresh baseline project. Do not replace this with seeding an already modified
schema: the initialized personal records are the migration input.

```sh
# Substitute your prepared runtime directory throughout.
git -C local/team-views-reference/source apply "$PWD/experiments/chatwoot-team-views/reference.patch"
docker compose -f local/team-views-reference/compose.yaml run --rm app \
  bundle exec rails db:migrate
python3 experiments/chatwoot-team-views/migration_probe.py local/team-views-reference
python3 experiments/chatwoot-team-views/probe.py local/team-views-reference \
  --output local/team-views-reference/reference-probe.json
python3 experiments/chatwoot-team-views/restart_probe.py local/team-views-reference
```

`migration_probe.py` compares the four baseline rows directly in PostgreSQL,
including owner/account IDs, filter types and query values. The reference patch
also applies cleanly to the untouched qualification checkout (`git apply --check`).

## Regression and lifecycle checks

Create a separate test DB, then run the maintainer-owned request suite and the
specified upstream tests. The qualification fixture is not reset by these tests.

```sh
docker compose -f local/team-views-reference/compose.yaml run --rm \
  -e RAILS_ENV=test -e POSTGRES_DATABASE=pocket_team_views_test \
  -e REDIS_URL=redis://redis:6379/1 app bundle exec rails db:create db:schema:load

docker compose -f local/team-views-reference/compose.yaml run --rm \
  -v "$PWD/experiments/chatwoot-team-views/acceptance_spec.rb:/bench/acceptance_spec.rb:ro" \
  -e RAILS_ENV=test -e POSTGRES_DATABASE=pocket_team_views_test \
  -e REDIS_URL=redis://redis:6379/1 app bundle exec rspec \
  /bench/acceptance_spec.rb \
  spec/models/custom_filter_spec.rb \
  spec/controllers/api/v1/accounts/custom_filters_controller_spec.rb \
  spec/models/team_spec.rb spec/models/team_member_spec.rb \
  spec/controllers/api/v1/accounts/teams_controller_spec.rb \
  spec/controllers/api/v1/accounts/team_members_controller_spec.rb \
  spec/services/conversations/filter_service_spec.rb \
  spec/services/conversations/permission_filter_service_spec.rb \
  spec/services/conversations/unread_counts/filtered_counter_spec.rb \
  spec/services/conversations/unread_counts/filtered_count_invalidator_spec.rb

python3 experiments/chatwoot-team-views/check_controls.py local/team-views-reference
```

The request checks cover member addition/removal, creator leaving/rejoining,
creator account removal, creator deletion including asynchronous association
cleanup, team deletion, management restrictions, forged ownership, invalid queries,
unread counts before/after visibility changes, empty results and AND/OR pagination.
Expected counts and identifiers come from fixtures, not from another candidate API.

`negative_control.rb` injects variants only inside a test process. Four wrong
variants must fail one specifically selected example for the expected reason:
reader management, creator-dependent deletion, creator-based unread counts and
stale membership. A process crash, missing selection or unrelated assertion is
not accepted as detection. Logs retain the actual failed assertion.

The same file provides `TEAM_VIEW_CONTROL=join_visibility`: a valid alternative
that uses JOIN-based visibility instead of the reference scope. Run the request
suite with `--require /bench/negative_control.rb` and that environment variable;
all twelve examples must pass. This is a localized valid variant, not a separately
authored second product implementation.

## Browser and production build

Use the Playwright installation and Chromium executable from `README.md`:

```sh
NODE_PATH="$PWD/local/team-views-browser-tools/node_modules" \
  node experiments/chatwoot-team-views/browser-shared.cjs \
  local/team-views-reference /path/to/chromium
```

The browser qualification exercises rejected-save recovery, successful shared
creation, reload, creator rename, read-only members, zero visible conversations,
and administrator deletion with confirmation. Its labels describe **this
reference UI**. They are not private required labels for alternative candidate UIs.

The historical production command was `bundle exec rails assets:precompile`, with
`RAILS_ENV=production`, `NODE_ENV=production`,
`VITE_RUBY_SKIP_ASSETS_PRECOMPILE_INSTALL=true`, `SECRET_KEY_BASE_DUMMY=1`, and
`NODE_OPTIONS=--max-old-space-size=4096`. The skip flag reuses the already-installed
locked dependencies in Vite's own hook. The later complete-runner audit found
that upstream's separate `before_assets_precompile` hook still invokes interactive
`pnpm install`. The current grader instead executes the SDK and Vite entrypoints
directly, as documented in `checks.json`; it does not rely on that reinstall failing.
Stop the reference development app while building and use a Compose override
setting `services.app.mem_limit: 5g`; restart the app afterward. A 2GB Node heap
ran out of memory in this experiment. Build resources are preparation/verification
conditions, not a correctness penalty for slower agents.

## Recorded results

The sanitized `reference-evidence.json` records versions, fingerprints and results.
Full logs are in `local/chatwoot-team-views-reference/` (not committed).

- Existing regression plus maintainer request checks: **160 examples, 0 failures**
  (148 existing + 12 added; this is not the full upstream suite).
- Reference's public request tests: **12 examples, 0 failures**, run separately.
  These overlap the maintainer scenarios and are not twelve additional independent cases.
- Frontend regression: **184 passed across 8 files**.
- HTTP probe: **45 passed**, including maintenance cleanup; this is not a score.
- Populated migration: **4 legacy records preserved**.
- Shared view survives application restart.
- Reference browser workflows: **5 passed**; the first includes failure recovery.
- Incorrect controls: **4/4 detected with the expected assertion**.
- Valid JOIN-based variant: **12 examples, 0 failures**.
- Production assets build passed with the resource settings above.
- Ruby changes and added public tests: lint passed. UI: no lint errors;
  three existing dynamic-translation-key warnings remain in the list/header.
- Qualification tooling unit tests: **13 passed**.

## Remaining work before scored agent runs

Subsequent work implements a [separate artifact-transfer runner](ISOLATED.md)
and a [public declarative UI protocol](../../docs/task-proposals/chatwoot-team-views/ui-evaluation.md).
These qualify populated migration/API/restart and five UI workflows in a fresh
candidate container without host source mounts. The list below remains the
overall registration checklist; it is not a claim that no transfer work exists.

This completes reference-based qualification of these scenarios, not the final
isolated grader or task registration. The remaining gates are:

1. Package a clean agent starting environment and a separate credential-free
   verifier, with no reference patch or trusted tests in the agent workspace.
2. Finalize and publish the minimal UI automation contract, or another consistent
   evaluation protocol that accepts alternate layouts/wording. Do not use this
   reference-specific Playwright script unchanged as a hidden universal grader.
3. Connect the checks into one runner with explicit setup/error/timeout outcomes,
   pinned browser/runtime resources and artifact collection. Test the complete
   transfer/migration lifecycle on clean candidate artifacts.
4. Run baseline, reference, valid variants and wrong controls through that full
   runner before adding an experimental suite entry or comparing agents.

The pinned base stores assignee filters as concrete IDs; no current-user sentinel
was found in the inspected filter path. Preserve supported upstream semantics;
do not add a new symbolic “me” operator as an undisclosed requirement. More varied
fixtures (same-name shared views, literal assignee conditions and invalid-ID/type
combinations) should be included when consolidating the final runner.
