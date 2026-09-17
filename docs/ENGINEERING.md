# Engineering task: Chatwoot team views

`chatwoot-team-views` is an experimental engineering task: add team-shared saved
conversation views to a fixed Chatwoot Community checkout. It covers migration,
permissions, conversation filtering, caching, asynchronous deletion and the UI.
The [public requirements](task-proposals/chatwoot-team-views/instruction.md) are
the contract. Difficulty and the advantage of multiple agents are **unmeasured**.

This task has a separate Docker runner because it needs Rails, PostgreSQL, Redis,
a worker and a browser. It is available through `pocket-engineering`; it is not
part of the small Harbor suites or their model profiles. The runner prepares and
grades source; it does not start an agent or spend model allowance.

## Prepare dependencies once

Run commands from the PocketAgentBench root after installing this project.
`python -m pocket_bench.engineering` can replace `pocket-engineering` in all examples.
Use Python 3.12+, Git and Docker Compose. The tested Docker VM has 8 GiB RAM;
the production build alone has a 5 GiB container limit. Run attempts sequentially.

```sh
git clone https://github.com/chatwoot/chatwoot local/chatwoot-upstream
git -C local/chatwoot-upstream checkout 5b7038b950b763e230df2d544df9b87b8752fef3
docker build -f experiments/chatwoot-team-views/Dockerfile \
  -t pocket-chatwoot-feasibility:5b7038b local/chatwoot-upstream
docker build -f experiments/chatwoot-team-views/Browser.Dockerfile \
  -t pocket-team-views-browser:0.2 experiments/chatwoot-team-views
pocket-engineering list
```

The dependency image contains Ruby/Node dependencies, not a reference solution.
The browser base digest and Playwright version are pinned. Actual image IDs,
source hashes, evaluator hashes and resource settings are recorded per attempt.
First-time image downloads/builds are setup time, not agent working time.

## Give an agent a clean starting workspace

```sh
pocket-engineering prepare-agent \
  --source local/chatwoot-upstream \
  --destination local/team-views-agent-01 \
  --project pocket-tv-agent-01 --port 33087 --vite-port 33343
```

Give the agent `local/team-views-agent-01/source/`, its `TASK.md`, and the
disposable app URL `http://localhost:33087`. That checkout includes public
requirements, fixture data, regression paths, a review rubric and a UI-map example.
`DEVELOPMENT.md` explains migrations, isolated test databases and worker execution.
It does not contain the reference patch or private verifier. Do not give evaluated
agents access to the maintainer's PocketAgentBench checkout or other attempts.
The app has only synthetic users; their shared password is `PocketBench123!`.

The agent implements the feature, adds meaningful tests and writes
`BENCHMARK_NOTES.md`. It also supplies `UI-MAP.json` following the
[public UI protocol](task-proposals/chatwoot-team-views/ui-evaluation.md).
The map declares locators and simple click/select/fill steps; it cannot change
assertions or execute candidate JavaScript. Button wording and layout may vary.

The initial operational stop guard is four hours. Whoever starts the agent must
enforce that guard and record the stop reason, elapsed time and available cost/token
measurements separately. A usage-limit stop must not trigger purchases, allowance
resets or a switch to evade the limit. The grader can still assess recovered source.

## Freeze and grade a submission

Stop agent activity before collecting source. Stage new implementation/test files
and `BENCHMARK_NOTES.md` (`git add -N path` is sufficient); the packager excludes
untracked files and includes current edits and deletions of tracked files.
Never stage secrets. No commit is required.

```sh
pocket-engineering package local/team-views-agent-01/source local/team-views-01.zip
pocket-engineering prepare \
  --source local/chatwoot-upstream \
  --artifact local/team-views-01.zip \
  --ui-map local/team-views-agent-01/source/UI-MAP.json \
  --destination local/team-views-grade-01 \
  --project pocket-tv-grade-01 --port 33085 --vite-port 33341
pocket-engineering grade local/team-views-grade-01
```

Each initialization and grade requires a fresh directory/project. Existing
attempts are never reset implicitly. ZIP hashes and individual file hashes are
validated before source is copied into dedicated named volumes. Candidate
containers run as a non-root user with reduced privileges, an internal network,
no host directory/Docker socket mounts and no agent credentials. The trusted
browser and its inputs use separate volumes. Only a loopback proxy is exposed.

Dependency changes are allowed. Build a matching dependency image from the
candidate's locked manifests with the supplied Dockerfile and pass `--image TAG`
to `prepare`. Preparation checks all four manifests against the actual image
without running image-provided code. An image mismatch is a setup error, not a
feature failure. The baseline source supplied via `--source` must still contain
the fixed upstream commit.
The trusted seed uses `--baseline-image` (the unchanged dependency image by
default), so upgrading candidate dependencies does not change baseline initialization.

## Interpret the result

`grade.json` reports `automated_correctness` and an independent `human_review`:

| Automated result | Reward | Meaning |
| --- | --- | --- |
| `pass` | 1 | All required automated stages passed. |
| `fail` | 0 | A requirement violation was observed, without an unresolved execution error. |
| `inconclusive` | null | Infrastructure, protocol, timeout or incomplete execution prevents a verdict. |

Exit codes are respectively 0, 1 and 2. Runtime speed is not a correctness
threshold. Bounded commands prevent stuck verification and excessive output;
an interrupted check is reported as inconclusive. Logs retain observed failures
even when an independent execution error prevents a final verdict.

Checks cover a populated upgrade and fresh install, personal-view preservation,
shared API permissions, viewer-specific results/counts, compound queries and
pagination, membership/inbox changes, creator/team deletion, restart persistence,
11 browser scenarios, fixed Ruby/frontend regressions, added tests, lint and a
production build. [CHECKS.json](../experiments/chatwoot-team-views/checks.json)
lists the public regression commands and baseline exceptions.
The build runs the existing SDK and Vite entrypoints directly: the upstream
`assets:precompile` hook attempts an interactive dependency reinstall, whereas
grading uses dependencies prepared before isolation.

Human UX, accessibility, scope and test-quality review stays separate using
[REVIEW.md](../experiments/chatwoot-team-views/REVIEW.md). Automated success is
not a claim of exhaustive correctness or human approval. Hardcoded solutions
and misleading UI maps require source review. No LLM judge is required.

Grade stops its own containers and preserves logs/volumes. Release its network
without deleting evidence with:

```sh
docker compose -f local/team-views-grade-01/compose.yaml down
```

## Maintainer qualification

The maintainer-only [harness directory](../experiments/chatwoot-team-views/README.md)
contains the reference patch and controls. These are never copied by
`prepare-agent`. `qualify.py` runs each source artifact through a fresh complete
grader: reference, unmodified baseline, four deliberate defects and a valid
JOIN/wording variation. A negative control qualifies only if its intended
behavioral assertion fails; an unrelated lint error does not qualify it.

This validates known acceptance/rejection cases. It is not an independently
authored second solution, an agent trial or evidence that one agent cannot solve
the task.

The complete qualification has passed: both positive controls were accepted and
all five negative controls failed for their intended reasons. See the
[recorded results](../experiments/chatwoot-team-views/complete-evidence.json).
