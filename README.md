# Pocket Agent Bench

A small, local benchmark for **complete agent systems**: single agents, teams, and
different agent implementations. Harbor runs the containers and trials; Pocket supplies
reviewable tasks, adapters and a self-contained comparison report.

This is an initial regression/diagnostic suite, **not a general intelligence leaderboard**.
Twelve intentionally small original tasks cover data processing, coding, local-document
research and mock API workflows. Tasks and graders are automatically tested, not
human-certified. See [the goal](docs/GOAL.md) and [evaluation design](docs/DESIGN.md).

The [initial real comparison](docs/VALIDATION.md) ran 72 trials: Codex single 24/24,
Codex team 23/24, and the optional My AI Employee configuration 17/24. These are
small-suite observations, not general product rankings. A [shareable measured JSON
summary](examples/baseline-v2.json) is included; complete traces remain local.

## Quick start

Requirements: Python 3.12+, `uv`, Docker with Compose, and a Codex login (`codex login`).
The current real adapters use subscription-authenticated Codex. The benchmark core and
task format do not require a particular agent or model provider.

```sh
git clone git@github.com:takahirox/pocket-agent-bench.git
cd pocket-agent-bench
uv sync --frozen --extra dev
uv run python scripts/build_runtime.py
uv run pocket-bench build
uv run pocket-bench doctor
```

To also evaluate My AI Employee, build with the optional `--fleet ../my-ai-employee`
argument. My AI Employee is not required for Codex-only runs or the core suite.
The optional image build snapshots only My AI Employee's source/package files. It does not copy
its databases, credentials, worktrees or other project files. The snapshot digest, Git
HEAD and built image ID are recorded in `local/runtime.json`; existing local source
changes are preserved and included in the evaluated snapshot.

Run the automated verifier tests and reference/no-op controls without any model calls:

```sh
uv run pytest
uv run pocket-bench run --name controls --profiles oracle,nop --attempts 1
```

Run one small real-agent comparison (uses the logged-in account's model allowance):

```sh
uv run pocket-bench run --name smoke --tasks sales-dedup \
  --profiles codex-single,codex-team --attempts 1 --agent-seconds 180
```

Run the full repeated comparison:

```sh
uv run pocket-bench run --name baseline --attempts 2 --concurrency 1 --agent-seconds 180
```

After building the optional Fleet image, include it explicitly:

```sh
uv run python scripts/build_runtime.py --fleet ../my-ai-employee
uv run pocket-bench run --name baseline-with-fleet \
  --profiles codex-single,codex-team,fleet-single --attempts 2 --agent-seconds 180
```

Default model: `gpt-5.6-luna`, effort `low`; override with `--model` and `--effort`.
The default profiles are Codex single/team; Fleet is an explicit optional integration.
Keep these equal when comparing orchestration. `--agent-seconds` is an aggregate
upper bound on agent invocation time, **not a token or dollar cap**. The single agent
receives the whole allocation; each of two concurrent analysts receives 1/6, and the
coordinator receives 2/3. Concurrency between trials can add resource contention;
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
- `fleet-single`: actual `fleet work` fixed-routing runtime with its native Codex
  worker and mediation. It returns a candidate patch; the adapter materializes that
  patch only in the disposable task repository for independent grading. It never
  promotes into a real user repository. A public structural smoke check supplies
  Fleet's required internal evidence; it contains no hidden expected answers.
- `oracle`, `nop`: sanity controls only; never counted as real agent comparisons.

The Fleet adapter transparently preserves native worker stdout while recording JSONL
usage. It sets the internal model proxy environment, disables implicit native subagent
spawning/web search, and enables local service access inside the worker's workspace
sandbox. The outer Docker network still blocks non-model internet destinations.
Team analysts cannot call APIs; only the coordinator operates services, avoiding
duplicate side effects from analysis sessions.

For another agent, implement Harbor's `BaseAgent` interface and run the same tasks:

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
