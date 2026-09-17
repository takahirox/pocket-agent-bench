# Chatwoot team views: maintainer qualification harness

**Historical partial harness.** The current complete task entry point and status
are in [README.md](README.md) and the [execution guide](../../docs/ENGINEERING.md).
The limitations and unscored results below describe this earlier experiment.

Experimental tooling for the [v0.1 proposal](../../docs/task-proposals/chatwoot-team-views/README.md).
This is **not a registered task or a final grading environment**. It currently
establishes that the fixture works on the upstream baseline and detects missing
team-sharing behavior. It must not be used to rank agents.

## Implemented

- Fresh checkout of upstream commit `5b7038b950b763e230df2d544df9b87b8752fef3`.
- Dependency image recipe; isolated app/PostgreSQL/Redis, local-only proxy ports.
- Seven synthetic users, two accounts, three teams, three inboxes, nine
  conversations and four legacy saved filters. Ordinary team members have
  different inbox access. No production data or credentials are used.
- HTTP checks of baseline visibility and personal privacy, shared creation,
  permission-specific read/list/update, visible conversation sets/counts,
  invalid inputs and fixed audiences. Temporary probe filters are cleaned up.
- Browser smoke for the existing personal-folder path: Alice sees five matching
  conversations, Bob sees three and cannot see Restricted inbox content.
- Report separation between assertion failure, transport/checker error and
  blocked checks. The report always says `correctness: unscored` while required
  final evaluation coverage is missing.

## Reproduce

Prerequisites: Docker Compose, Python 3, Git and an upstream Chatwoot clone
containing the fixed commit. Run from the PocketAgentBench repository root.
Use a **new directory, new project name and unused ports** per initialized trial.

```sh
python3 experiments/chatwoot-team-views/prepare.py \
  --source /path/to/chatwoot \
  --destination local/team-views-example \
  --project pocket-tv-example --port 33081 --vite-port 33337

docker compose -f local/team-views-example/compose.yaml build app
python3 experiments/chatwoot-team-views/initialize.py local/team-views-example
python3 experiments/chatwoot-team-views/probe.py local/team-views-example \
  --output local/team-views-example/probe.json
```

`prepare.py --image IMAGE` can reuse a previously built dependency image with the
same fixed Gemfile/package lockfiles. Initialization records the actual image IDs,
not just mutable tags. The Dockerfile retains the original lockfiles; native gRPC
build parallelism is capped at two. The first dependency build can take ten
minutes or longer. Build time is environment preparation, not agent task time.

Initialization refuses an existing attempt marker or an existing Compose project
(container, volume or network). It does not reset a populated DB implicitly. An
interrupted initialization requires investigation or a genuinely fresh project.
Do not remove the marker just to retry. No worker runs during qualification;
asynchronous lifecycle checks still need a controlled job-draining mechanism.

A successful tool exit does not imply task success. Probe exit codes:

- `0`: all implemented probes passed; **still not a final task pass**.
- `1`: one or more implemented assertions failed.
- `2`: an environment or checker error prevented evaluation.

On unmodified upstream, exit `1` is expected because shared views do not exist.
The eleven baseline checks must nevertheless pass. Raw report totals include
cleanup operations; do not interpret them as a feature score.

For optional browser smoke, install the pinned Playwright client outside tracked
source and provide a Chromium executable. The browser version is recorded.
A future packaged task must pin the browser too; this local smoke is not that package.

```sh
npm install --prefix local/team-views-browser-tools --ignore-scripts \
  --no-audit --no-fund playwright@1.56.1
NODE_PATH="$PWD/local/team-views-browser-tools/node_modules" \
  node experiments/chatwoot-team-views/browser-baseline.cjs \
  local/team-views-example /path/to/chromium
```

All fixture logins use `PocketBench123!`, for example `alice@example.test` and
`bob@example.test`. Generated `.env` contains a separate random application secret
with mode 0600. Do not commit runtime directories or `.env` files. Reports do not
contain login tokens. The HTTP probe disables redirects and ambient HTTP proxies.

Stop only this trial with:

```sh
docker compose -f local/team-views-example/compose.yaml down
```

This preserves its named volumes. A subsequent fresh initialization must use a
new project name. The prior feasibility preview is a separate Compose project.

## Qualification evidence (2026-09-17)

A fresh `pocket-tv-v03` environment using the fixed, unmodified upstream produced:

- Baseline HTTP checks: **11 passed**.
- Shared-feature HTTP checks: **13 passed, 20 failed**. Failures include missing
  `team_id`, members/admin unable to read the creator's shared view, and invalid
  shared inputs being accepted as personal filters. These are expected missing-feature failures.
- Cleanup: **7 passed**; these are maintenance checks, not feature credits.
- Browser smoke: Alice **5** visible Open conversations; Bob **3**; both passed
  without browser runtime errors. Chromium reported `152.0.7977.83`.
- Probe/safety unit tests: **12 passed**.

`qualification-evidence.json` records sanitized summaries, image identifiers and
source fingerprints. Full local logs are under `local/chatwoot-team-views-v03/`.
The app source is unchanged; only ignored local process configuration is added.

Fixture validation uncovered two setup problems, both fixed before accepting the
baseline: `display_id` must be reloaded after its database trigger, and incoming
message after-commit hooks reopen resolved conversations. Final fixture statuses
are now applied after the outer transaction commits. Earlier results under
`v01`/`v02` are not accepted task evidence and are retained locally for diagnosis.

## Reference qualification added

A [reference implementation and expanded qualification](REFERENCE.md) are now available,
including populated migration, restart, lifecycle/permission/count checks, shared UI
workflows, production build, four incorrect controls and a valid visibility variant.
See `reference-evidence.json` for the later results. The baseline results above remain
a historical record of the unmodified source.

## Remaining gates before agent evaluation

The [isolated submission path](ISOLATED.md) now implements immutable source
transfer into named Docker volumes and a combined populated-upgrade/API/restart
runner, with optional declarative UI checks. This replaces host source mounts for
that qualification path; it does not yet combine all required checks into a final
grader. The original maintainer harness below retains its original limitations.

The HTTP probe alone still does not claim complete R1–R8 verification. Separate
reference checks now cover many of those scenarios. The clean candidate-transfer
runner, isolated final verifier and a layout-independent public UI evaluation
contract remain to be completed before registration.

The reference and controls are qualification evidence, not a complete grader. A baseline failing
these checks proves only that the checks notice a missing feature; it does not
prove they accept all valid implementations or catch all invalid ones. Do not
register this as a scored suite task until those gates are covered.

This maintainer Compose setup bind-mounts its own checkout and fixture. It is not
the sandbox or hidden-verifier boundary for untrusted candidate execution. A real
run must collect the candidate into a clean verifier, with no agent credentials
or host mounts available to it, as described in the proposal.
