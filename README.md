# Pocket Agent Bench

A small, local benchmark for **complete agent systems**: single agents, teams, and
different agent implementations. Harbor runs the containers and trials; Pocket supplies
reviewable tasks, adapters and a self-contained comparison report.

This is an initial regression/diagnostic suite, **not a general intelligence leaderboard**.
Twelve intentionally small original tasks cover data processing, coding, local-document
research and mock API workflows. Tasks and graders are automatically tested, not
human-certified. See [the goal](docs/GOAL.md) and [evaluation design](docs/DESIGN.md).

The [initial real comparison](docs/VALIDATION.md) ran 72 trials, but a later audit
found benchmark-adapter defects affecting all six My AI Employee API trials. Those
six are invalidated for comparison; **the original 17/24 is not a fair product score**.
Original evidence is retained. A [shareable measured JSON summary](examples/baseline-v2.json)
is included; complete traces remain local. This small suite is not a product ranking.

The corrected API-only comparison ran 18 fresh trials: Codex single **5/6**, Codex
team **6/6**, and My AI Employee + corrected adapter **3/6**. Fleet's remaining
three failures are malformed patch proposals with no native repair turn, not the
old networking defect. See [results and root causes](docs/VALIDATION.md#corrected-api-comparison)
and [shareable JSON](examples/api-corrected-v1.json). That historical experiment did
not change My AI Employee itself.

The new generic host interface has also completed all 12 tasks using a product-owned
native controller: 4 successes, 8 failures. A post-run controller defect was reproduced
and fixed; this is an integration diagnostic, **not a fair product score**. See
[the complete validation](docs/VALIDATION.md#native-generic-interface-diagnostic-2026-09-06).

## Quick start

Requirements: Python 3.12+, `uv`, and Docker with Compose. The bundled Codex profiles
also need a Codex login (`codex login`); configured agent connections use their own
explicitly supplied authentication. The core and task format are provider-independent.

```sh
git clone git@github.com:takahirox/pocket-agent-bench.git
cd pocket-agent-bench
uv sync --frozen --extra dev
uv run python scripts/build_runtime.py
uv run pocket-bench build
uv run pocket-bench doctor
```

For other CLIs, see [the common agent interface](docs/AGENT-INTERFACE.md).
The optional `--install-project PATH` build argument includes an explicitly selected
Python agent project's metadata and source, not its databases or credentials.
External orchestrators use product-owned host controllers. For My AI Employee's
new isolated workflow, use its `fleet-bench` controller; do not embed a Docker socket
or use the old `fleet-single` proposal-mode adapter.

Run the automated verifier tests and reference/no-op controls without any model calls:

```sh
uv run pytest
uv run pocket-bench run --name controls --profiles oracle,nop --attempts 1
```

Run one small real-agent comparison (uses the logged-in account's model allowance):

```sh
uv run pocket-bench run --name smoke --tasks sales-dedup \
  --profiles codex-single,codex-team --attempts 1 --hard-timeout-seconds 3600
```

Run the full repeated comparison:

```sh
uv run pocket-bench run --name baseline --attempts 2 --concurrency 1 --hard-timeout-seconds 3600
```

To run an explicitly trusted external controller, create its ignored local profile
following [the interface contract](docs/AGENT-INTERFACE.md), then run:

```sh
uv run pocket-bench run --name connected-agent \
  --profile-file local/connections.json --allow-host-controller \
  --profiles my-agent-single --attempts 1 --concurrency 1 --hard-timeout-seconds 3600
```

Default model: `gpt-5.6-luna`, effort `low`; override with `--model` and `--effort`.
The default profiles are Codex single/team; other systems are explicit connections.
Keep these equal when comparing orchestration. `--hard-timeout-seconds` defaults to
3600 seconds and is an emergency wall-clock limit for active trial work, including
agent tools and optional declared execution. It is **not a grading deadline, token
cap, or dollar cap**. There are no short per-role allocations: concurrent analysts
and the coordinator share the remaining wall-clock allowance. Setup, verification,
and bounded cleanup retain separate infrastructure limits. Adjust the safety limit
for the workload and host; 3600 seconds is a configurable starting point, not a
claim that every normal task finishes within an hour.

Elapsed time is measured, not compared with a short pass/fail target. The independent
grader determines correctness. A timeout without a grade is `timed_out`; a grade
that is available is preserved, with the termination reason recorded separately.
Reports include all trials in the overall success and timeout rates, and retain
observed time and partial/unknown token usage. Aggregate agent invocation time
excludes declared execution and is the sum of worker durations, not parallel wall
time. Connected systems without worker timing evidence report it as unknown.
Harness retries remain disabled; inner retry/recovery evidence stays in agent logs.
Tasks that require a real deadline must state and grade it explicitly; the safety
limit does not add such a requirement to ordinary tasks.

`--agent-seconds` is a deprecated alias for the safety limit, with a warning; its
old aggregate-budget semantics and role fractions no longer apply. Old experiment
configurations remain recorded in their plans. Compare runs with matching timing
policies and safety limits; historical commands in `docs/VALIDATION.md` describe
the old implementation.

Concurrency between trials can add resource contention;
use `--concurrency 1` for careful latency comparisons. A two-attempt result is only
an initial observation, not a statistically reliable ranking.

## Results

Each run creates:

```text
results/plans/<name>.json        # intended matrix, versions, initial task definitions
results/jobs/<name>/            # Harbor raw evidence, artifacts and per-trial results
results/reports/<name>/
  index.html                   # open directly in a browser; no CDN or server required
  results.json                 # portable normalized results
```

```sh
open results/reports/baseline/index.html
uv run pocket-bench report results/jobs/baseline results/jobs/after-change \
  --output results/comparison
```

Filter by run, primary task category, overlapping capability tags, configuration or
task name. Open a trial for the instruction, exact checks, delivered files, agent logs,
role timings and budget information. Select a baseline run for matched comparisons.
Success, failure and unscorable counts include the entire intended trial matrix,
including tasks that never started. Both all-trial and scorable-trial rates are in JSON.

Unknown usage/cost is **not zero**. Token counts come from native CLI events, not a
model's self-report. Subscription tokens do not imply a known USD bill; cost is null.
Incomplete usage is flagged in metadata. Raw artifacts stay local by default and
are gitignored; review/redact before sharing.

## Agent configurations

- `codex-single`: one native Codex CLI session.
- `codex-team`: two independent read-only analytical sessions, with their final
  messages passed to an integrating native Codex session. This is one specific team
  design, not a claim about all multi-agent systems.
- Configured profiles: an ordinary CLI or a product-owned host controller, labeled
  `single` or `team`. The label describes the system; it does not create a team.
- `oracle`, `nop`: sanity controls only; never counted as real agent comparisons.

The old built-in `fleet-single` proposal adapter is no longer active; historical
results retain that name. Its integration source belongs to the product repository.
For bundled Codex profiles, the outer Docker network blocks non-model internet
destinations. Team analysts cannot call APIs; only the coordinator operates services,
avoiding duplicate side effects from analysis sessions. Host controllers must isolate
their own model tools and are explicitly trusted host code, not a sandboxed plugin.

API tasks expose the same optional `pocket-python-v1` execution transport to all
configurations: the agent explicitly authors `output/execute.json` with
`{"script":"src/any_name.py"}`. After its final response, the adapter runs that
program once as the task's unprivileged user, within the remaining wall-clock safety allowance.
No source filename is guessed, no answer is supplied, and internal structural
checks never execute API operations. Alternatively, an agent can call the service
directly and omit the manifest. The final private grader and trusted service audit
remain the authority for success. This evaluates **agent + adapter**, not the
standalone product's ability to execute arbitrary process proposals.

For another CLI, use a configuration-only connection. An unusual external orchestrator
can implement the [common file protocol](docs/AGENT-INTERFACE.md) in its own repository.
Alternatively, use Harbor's `BaseAgent` interface directly with the same tasks:

```sh
uv run harbor run -p tasks/sales-dedup --agent your_package.adapter:YourAgent \
  --model your-model --jobs-dir results/external
uv run pocket-bench report results/external/<job> --output results/external-report
```

An adapter must keep the model's actions inside the task container, honor timeouts,
record aggregate usage (or null), and never read `tests/` or `solution/` from the host.
For another provider, explicitly extend the fixed gateway allowlist and record the
change. Original tasks can also be run with Harbor's other adapters if their runtime
dependencies and network access are configured. Those adapters are not automatically
compatible with this prebuilt subscription runtime.

## Task and grader development

Edit `suite/catalog.json`, then run `uv run pocket-bench build`. The generated `tasks/`
directories are native Harbor tasks and are committed for direct use and inspection.
Do not edit generated files directly. Each task has one primary category and multiple
capability tags. The catalog stores instructions, fixed inputs, independent expected
results or behavioral test cases, reference solutions, alternate answers and wrong answers.

Run `uv run pytest` and reference/no-op Docker controls after a semantic grader change.
For coding tasks, the verifier launches the candidate in an unprivileged subprocess
with case inputs; expected answers stay in the trusted verifier process. Candidate
code is not imported into the host application. Public smoke checks are structural;
private graders evaluate the actual requirements.

See [DESIGN.md](docs/DESIGN.md) for limitations and [VALIDATION.md](docs/VALIDATION.md)
for actual measurements and the acceptance audit.

GitHub Actions runs unit checks on pushes/PRs. The manually triggered **Docker verifier
controls** workflow also builds the generic runtime and checks all 24 oracle/no-op
trials without model credentials. Real-agent runs stay local by default; no subscription
credential is uploaded to CI.

## Regrade or invalidate

```sh
# Uses saved artifacts in offline Docker containers; no model calls, no overwrite.
uv run pocket-bench regrade results/jobs/baseline results/jobs/baseline-regraded
# Preserve raw evidence while marking a run invalid for comparison.
uv run pocket-bench invalidate results/jobs/baseline --reason "Describe the discovered grading defect"
uv run pocket-bench report results/jobs/baseline --output results/invalidated-report
```

Regrading cannot recover a missing artifact, an API action that was never recorded, or
an interrupted task. Those trials remain unscorable. New task instructions require a
new agent run, not merely regrading old outputs.
# Agent connections

See [the common agent interface](docs/AGENT-INTERFACE.md) for configuration-only CLI
connections and explicitly trusted, product-owned external controllers. Tasks and
graders remain independent of the system being evaluated. Legacy `fleet-single`
commands below describe historical runs; use the product-owned controller for the
new isolated workflow. The runtime builder's old `--fleet` option is now the generic
`--install-project` option.
