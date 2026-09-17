# Chatwoot team views — experimental engineering task 0.2

The task adds team-shared saved conversation views to a fixed Chatwoot Community
checkout. The complete runner prepares source artifacts, performs a populated
upgrade, runs API/browser/lifecycle checks, regressions, lint and a production build.

Start with the [execution guide](../../docs/ENGINEERING.md),
[public requirements](../../docs/task-proposals/chatwoot-team-views/instruction.md),
[UI protocol](../../docs/task-proposals/chatwoot-team-views/ui-evaluation.md) and
[human review rubric](REVIEW.md). The [coverage matrix](COVERAGE.md) maps R1–R8
to automated checks and separate review items. The task catalog is `task.json`.

## Entry points

- `agent_workspace.py`: clean public source and disposable development environment.
- `artifact.py`: collect staged/tracked source, validate paths/modes/hashes.
- `task.py prepare` / `task.py grade`: isolated complete grading pipeline.
- `qualify.py`: seven clean full-runner controls, stopping on unexpected results.
- `variants.py`: source-level deliberate defects and a valid JOIN/wording variant.
- `checks.json`: public regressions, build and lint commands with baseline exceptions.

Use `pocket-engineering list|prepare-agent|package|prepare|grade` from the repository
installation, or `python -m pocket_bench.engineering`. These commands do not launch
agents or use model allowance. This separate multi-service runner is not a Harbor
short-task profile.

## Maintainer controls

The [reference patch](reference.patch) is applied to upstream commit
`5b7038b950b763e230df2d544df9b87b8752fef3`. It includes feature implementation,
13 regression/migration examples and verification notes. It is **not agent input**.
`prepare-agent` copies only the unchanged upstream and public documents/fixture.

Prepare the images as described in the execution guide, apply the patch in a
separate baseline checkout, stage new files, then package reference and baseline:

```sh
python3 experiments/chatwoot-team-views/artifact.py /path/to/reference local/reference.zip
python3 experiments/chatwoot-team-views/artifact.py /path/to/upstream local/base.zip --base
python3 experiments/chatwoot-team-views/qualify.py \
  --source /path/to/upstream --reference local/reference.zip --baseline local/base.zip \
  --ui-map experiments/chatwoot-team-views/task-ui-map.json \
  --destination local/team-views-qualification --project-prefix pocket-tv-qualification
```

Controls: reference and the valid variant must pass; baseline, unauthorized
editing, creator-deletion loss, creator-based unread counts and stale membership
must fail their named behavioral assertions. Each case uses a fresh database and
source volume. Logs/volumes remain after its containers/network are removed.
All seven controls produced their intended outcomes in clean complete runs on
2026-09-17. The task is registered as `qualified-experimental`; see
[complete-evidence.json](complete-evidence.json) for source, image and evaluator
identities, stage results and the public-workspace smoke.

| Submitted source | Automated result | Qualification |
| --- | --- | --- |
| Reference | Pass | Accepted |
| Unmodified baseline | Fail: sharing missing | Intended defect detected |
| Readers can edit | Fail: forbidden update accepted | Intended defect detected |
| Creator deletion removes shared views | Fail: view disappears after worker cleanup | Intended defect detected |
| Creator's unread counts reused | Fail: Bob gets 5 instead of 3 | Intended defect detected |
| Stale membership cache | Fail: removed member still has access | Intended defect detected |
| Valid JOIN query and different audience wording | Pass | Accepted |

Both positive controls passed all 24 executed stages: 148 existing Ruby examples,
13 added examples, 184 frontend tests, migration/fresh installation, API/behavior,
restart, 11 browser workflows, asynchronous lifecycle, lint and production build.
Tooling validation: **310 pytest tests**, **6 UI-protocol Node tests**, and Ruff
passed. The clean public workspace retained the fixed baseline and passed its
11 baseline API checks plus Ruby/frontend development-command smoke tests.

An earlier attempt stopped at upstream's interactive dependency-install prompt
and remains **inconclusive**. The build command was corrected before these seven
runs; that incomplete attempt was not relabeled as a pass.

A valid variant demonstrates acceptance of a different membership query and UI
wording. It is not an independently authored second implementation. Difficulty,
single/multi-agent comparisons and human UI approval are not implied by these
controls.

## Earlier evidence

These documents preserve earlier **partial, unscored** experiments:

- [Baseline harness](BASELINE.md) and `qualification-evidence.json`.
- [Reference qualification](REFERENCE.md) and `reference-evidence.json`.
- [Artifact-transfer qualification](ISOLATED.md) and `isolated-evidence.json`.

The original reference patch is archived as `reference-v01.patch`; its hash is the
one recorded in the earlier evidence. The current patch additionally contains a
populated-upgrade regression and `BENCHMARK_NOTES.md`. Do not reinterpret an old
partial result as a complete task pass.
