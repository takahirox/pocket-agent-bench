# Team-shared conversation views

Experimental engineering task v0.2. The runnable entry point is `pocket-engineering`.
Every numbered requirement below is public to the agent; private evaluation may
vary fixtures, but must not introduce additional requirements.

## Product brief

Support teams repeatedly use the same conversation filters. Chatwoot currently
lets each user save personal conversation folders. Add team-shared conversation
views so teammates can return to a common filter without recreating it, while
retaining existing personal folders and conversation access restrictions.

Work in Chatwoot Community at commit
`5b7038b950b763e230df2d544df9b87b8752fef3`.
You receive the full source, installed dependencies, a running disposable
PostgreSQL/Redis environment, browser access and synthetic accounts. No external
business service credentials or enterprise subscription are required.

Choose your own implementation structure, schema, UI layout, decomposition and
workflow. Deliver working product behavior, a migration from the supplied base,
relevant tests and concise verification notes. Completion is evaluated separately
from elapsed time, token usage and cost.

## Required behavior

### R1 — Preserve personal folders and existing data

Existing saved filters remain personal after migration. Preserve their IDs,
owners, accounts, names, filter types and query values. Their existing links and
create/list/read/update/delete behavior must keep working. Existing contact and
report filters remain personal and otherwise unchanged.

A normal schema migration must upgrade a populated base database; resetting or
re-seeding it is not an upgrade. New views and edits persist across application
restarts. Support both a fresh installation and the populated upgrade path.

### R2 — Create a view for one team

A conversation view is either personal or shared with exactly one team in the
same account. An ordinary agent may create a shared view only for a team they
currently belong to. An account administrator may create one for any team in
that account. The authenticated creator is recorded server-side.

Require a nonblank name and a query accepted by the existing conversation filter
system. Preserve the existing query semantics, including combinations of
conditions and any current-user-relative values: evaluate these for the person
using the view, not its creator. A shared view does not automatically add a
conversation-team condition. Its team defines its audience, not its query.

Two views may have the same display name; identity and authorization must not
rely on the name. Reject invalid, missing or cross-account team references without
creating or changing a view. Do not introduce sharing for contact/report filters.

### R3 — Enforce this permission model

| Actor in the view's account | Create for this team | List/read/use shared view | Edit name/query or delete |
| --- | --- | --- | --- |
| Administrator, including a nonmember | Yes | Yes | Yes |
| Creator who is still a member | Yes | Yes | Yes |
| Other current team member | Yes | Yes | No |
| Ordinary agent outside the team, including a former creator-member | No | No | No |
| User outside this account or unauthenticated user | No | No | No |

Administrator privileges here apply only to shared views. They do not make
another user's personal folders visible. Permissions must be enforced by the
server for individual IDs, collections and mutations, including forged requests.
Denied writes must leave data unchanged. Do not expose an inaccessible view's
name, query or results in error bodies or other listing/count endpoints.

### R4 — Keep conversation access independent

Being able to use a shared view grants no new access to conversations, messages,
contacts or inboxes. Apply the saved query within the user's existing authorized
conversation set. Two members using the same shared view can correctly see
different results. Respect account isolation and existing administrator access.

Lists, pagination totals and displayed unread/count badges must not reveal
inaccessible conversations. Where the existing UI offers a badge for a personal
folder, retain equivalent behavior for shared views with user-specific values.
A permitted view with no visible matches must open as an ordinary empty result,
not an authorization error. Direct conversation links retain existing checks.

### R5 — Handle changes to teams and creators

After a committed team-member addition/removal, the next API request must use the
new membership, even within an existing login session or after warming a cache.
A browser reload must reflect the change. Losing inbox access likewise removes
those conversations and their counts on the next request. Instant push updates
or erasing information already downloaded by a browser are not required.

If the creator leaves the team, leaves the account, or is deleted, shared views
remain available to eligible members and administrators. A former creator has
no special access; an administrator can still maintain those views. A deleted
creator must not break rendering or leave views unusable. Restoring an existing
creator's team membership restores the creator-member permissions in R3.

When a team is deleted, its shared views must no longer be accessible or appear
in lists. They must never become public or personal implicitly. Unrelated teams'
views and all surviving users' personal folders remain intact. Physical cleanup
may follow existing asynchronous deletion conventions; authorization must not
wait for a background cleanup job.

### R6 — Integrate API behavior compatibly

Use the existing account-scoped `custom_filters` collection/item API. For
conversation filters, expose an additive `team_id` field: null for personal,
an integer for shared. A create request omitting `team_id` (or setting it to null)
creates a personal filter; omitting it during an update preserves the audience.
Existing payload fields and filter-type query parameters keep their meanings.
Responses include `team_id`; old clients may ignore it.

For v0, a view's audience is fixed at creation. Reject attempts to change it
(including shared-to-personal and moving teams); supplying the same audience is
allowed. Do not require conversion, copying or ownership-transfer workflows.

Collection responses include the actor's personal views and the shared views
they may read, without duplicates for an administrator who is also a member.
IDs, owners and accounts must not be forgeable through create/update payloads.
Use the application's existing JSON/error conventions: invalid input is 422;
unauthenticated requests are 401; authenticated authorization failures are 403
or 404, except existing cross-account access checks may use 401. No rejected
operation may succeed silently or return 500.

### R7 — Provide complete UI workflows

An eligible user can create a personal or team-shared conversation view from the
conversation filtering UI, select an eligible team, find saved views, see which
team owns a shared view, open it, and revisit it after reload/login. An eligible
creator or administrator can edit its name/query and delete it with confirmation.
Members who cannot manage a view can still open it, with no enabled edit/delete
controls. Existing personal-folder workflows remain available.

Expose success, validation, failed-save and empty-result states; do not claim a
save succeeded when the server rejected it. Preserve entered name/query after a
failed save so the user can correct or retry it. Follow existing localization and
component conventions. New controls need accessible names and keyboard operation.

Functional browser checks use a desktop viewport of 1440 x 1000. Exact wording,
pixel layout, component choices and whether views appear in a separate section
are design decisions. Visual integration/polish is reviewed separately by humans.

The [public UI evaluation protocol](ui-evaluation.md) specifies the submitted JSON
map that identifies controls without prescribing their wording or location.
Use protocol version 2; submit the map alongside the source artifact.

### R8 — Deliver and verify an integrated change

Preserve the supplied regression tests. Add relevant tests covering your feature,
including authorization, membership changes and populated-database migration.
The application must boot, the existing production frontend build command must
succeed, and the specified relevant upstream regression suites must pass. Run the
existing lint tools on changed supported source files; do not broadly reformat or
change unrelated code. Document what you tested and any unresolved limitations.

`CHECKS.json` supplies the exact upstream regression paths, build/lint commands
and baseline exceptions. Preserve those tests and their existing helpers and
factories, `.rspec`, `.rubocop.yml`, `.eslintrc.js`, `vitest.config.ts`,
`vitest.setup.js` and `vitest.i18n.js`.
New tests may use new support files. Write `BENCHMARK_NOTES.md` describing your
change, tests and limitations. The automated gate checks that notes and new tests
are present and runs them; a separate review assesses their relevance and quality.

Run Node tests with `NODE_ENV=test`. Build production assets with
`RAILS_ENV=production NODE_ENV=production NODE_OPTIONS=--max-old-space-size=4096
VITE_RUBY_SKIP_ASSETS_PRECOMPILE_INSTALL=true SECRET_KEY_BASE_DUMMY=1
sh -c 'pnpm run build:sdk && bundle exec rails vite:build_all'`.
This builds the existing SDK and Vite production entrypoints directly because
upstream `assets:precompile` unconditionally runs interactive `pnpm install`.
Dependencies are prepared and their locked manifests verified before grading.
The verifier provides a 5 GiB build container;
setup/build resources are not an agent efficiency score. Lint uses the existing
RuboCop and ESLint tools on changed supported files; existing warnings are not errors.

Stage new source files in Git (`git add -N path` is enough) before packaging;
untracked files are not collected. A commit is unnecessary. Do not submit Git
metadata, runtime files or secrets. Dependencies may change, but a corresponding
dependency image built from the submitted locked manifests must be prepared with
the supplied Dockerfile before grading. Missing/mismatched dependency preparation
is reported separately, never silently scored as incorrect behavior.

## Scope

No public links, cross-account sharing, multi-team sharing, real-time collaborative
editing, bulk sharing, new conversation filter operators, new user roles or
enterprise features are required. Production deployment, external integrations
and a rewrite of existing personal filters are outside this task.

Evaluation will check the requirements above through API behavior, a populated
upgrade, browser workflows and regression checks. Internal filenames, database
column choices (apart from the public API contract), number of agents, commits,
and the order of implementation are not grading criteria. Required automated
checks must all pass; a missing check cannot award a pass. Environment/protocol
errors or verification timeouts produce an inconclusive result. The operational
agent stop guard is four hours; elapsed time and stop reason are recorded
separately and do not themselves make a correct final artifact incorrect.
Human UX, accessibility, test-quality and scope review are reported separately
using the published rubric, without a required LLM judge.
