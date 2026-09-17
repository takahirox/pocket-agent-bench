# Requirement coverage and review boundaries — 0.2

The [public task](../../docs/task-proposals/chatwoot-team-views/instruction.md)
defines behavior. The grader combines these checks; none alone awards a task pass.

| Requirement | Automated evidence | Separate review |
| --- | --- | --- |
| R1: personal data and migration | Seed the fixed upstream schema, migrate the populated DB, compare four original personal rows and their IDs/owners/accounts/names/types/queries; personal CRUD for conversation/contact/report; fresh DB preparation; shared persistence after restart; UI edit/reload. | Migration safety beyond the finite fixture; unnecessary rewrites of personal storage. |
| R2: team views and queries | Member/admin creation, invalid/foreign team IDs and input types, blank names and invalid queries, two same-name views in different teams, literal assignee IDs, compound AND/OR and pagination. | Appropriate design and supported-query test coverage. |
| R3: authorization | Read/list/update permission matrix across creator, other member, outsider, administrator and foreign account; member/admin creation and unauthorized creation; creator/admin deletion plus rejected member/anonymous deletion; forged owner/account/ID; denied writes leave data unchanged; personal privacy. | No hardcoding, alternate-endpoint leaks or misleading UI-map selectors. |
| R4: conversation access | Expected result IDs independently computed from fixture access; total counts and pagination across 26/27 visible rows; shared unread values 5/3/0 for different viewers; empty results; direct restricted-conversation denial; browser excludes restricted contacts. | Broader privacy/security review beyond those requests. |
| R5: lifecycle | Membership removal/rejoin in the same API/browser login, warmed unread/inbox access changes, team deletion with unrelated records retained, creator account removal and deletion before/after Sidekiq completion, subsequent administrator maintenance. | Races/concurrency and lifecycle paths outside the fixture. |
| R6: compatibility | Existing `custom_filters` endpoint and old omitted/null audience payloads, immutable audience and same-audience no-op, filter-type lists, duplicate avoidance, status codes, identity preservation and ownership forgery. | API evolution and scope consistency. |
| R7: UI | Eleven fixed workflows: create/validation/422 recovery, reload/login, query/name edit and recovery, member read-only, empty view, membership reload, outsider nondiscovery, admin edit, delete cancel/failure/retry, personal CRUD/privacy. New-control names/focus and keyboard activation are checked. | Complete keyboard/focus path, appearance, localization, discoverability and whether selectors identify real controls. |
| R8: engineering | 148 existing Ruby and 184 frontend regression examples, added tests, notes present, protected test/helper/config integrity, changed Ruby/JS/Vue lint, SDK and Vite production builds, application startup and actual container-boundary audit. | Added-test relevance, notes accuracy and unrelated changes. This is not the entire upstream test suite. |

`probe.py` contributes API assertions but keeps its historical standalone
`unscored` output. Only `task.py` combines the required stages into a final
automated verdict. Maintenance cleanup counts are included in raw probe totals;
they are not independent feature credits or a proportional completion score.

The baseline has no symbolic current-user assignee operator. Literal assignee IDs
retain their existing meaning; implementing a new “me” operator is not required.
Shared-table design is not inspected. The populated migration check reads the
original personal storage fields, whose preservation is part of R1; a rewrite of
existing personal filters is outside scope.

Timeouts, output/resource limits and UI-protocol/infrastructure errors are
inconclusive, with observed assertions retained. Confirmed build/migration or
behavioral failures remain failures when later dependent stages are blocked.
Missing stages cannot produce a pass. Agent elapsed time and stop reason are
separate from artifact correctness.

The qualification controls test known positives and known defects. A passing
finite fixture cannot prove exhaustive correctness or absence of hardcoding.
Human review remains `not_performed` until separately recorded with observations;
the automatic report never awards it implicitly.
