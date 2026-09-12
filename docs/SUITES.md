# Workloads and evaluation protocol

Pocket supports fast regression checks and broader complete-agent experiments as
separate named suites. A suite selects tasks; `--profiles` still selects agent systems.
The default command preserves the original twelve regression tasks and two attempts.
All suites use main's independent wall-clock safety timeout (3600 seconds by default);
no expanded suite is silently added to the default run.

| Suite | Tasks | Structural demand | Default attempts/task/profile | Default safety timeout seconds/trial |
| --- | ---: | --- | ---: | ---: |
| regression | 12 | Short diagnostic tasks | 2 | 3600 |
| capability-smoke | 3 | Ledger recovery, dependency planning, multi-file repair; directional only | 1 | 3600 |
| capability | 5 | Multi-file repair, evidence synthesis, ledger recovery, dependency planning, stateful API recovery | 10 | 3600 |
| long-horizon | 5 | Larger versions: 5,000 ledger events with revisions, 420 policy/noise documents, 120 dependency nodes, 120 auxiliary source modules, 48 ordered service jobs | 10 | 3600 |
| web | 2 | JavaScript rendering and live source retrieval with trusted snapshots | 10 | 3600 |

These are original public workloads, with independent deterministic grading, not
human-certified or empirically calibrated capability rankings. Five tasks in the
capability suite establish workload coverage, not broad statistical representativeness.
Long-horizon denotes extended workload demands; an efficient solver may finish quickly.
The browser task requires Chromium (installed only in that task image), while the
live task is explicitly a retrieval/evidence task, not a browser navigation claim.

## Run and inspect an experiment

```sh
# Record exact task definitions, selected members and the full intended trial matrix.
# No Docker job or model invocation occurs. Output includes the sum of active-trial safety allowances (not worker time or a runtime estimate).
pocket-bench run --suite capability --name capability-plan --plan-only

pocket-bench run --suite regression --name regression-check --attempts 1
pocket-bench run --suite capability --name capability-comparison
pocket-bench run --suite long-horizon --name extended-comparison

# Partial suite: --tasks intersects the named suite, never silently adds other tasks.
pocket-bench run --suite capability --tasks repository-repair --name repair-check
pocket-bench run --suite web --tasks browser-release --name browser-check

# Explicitly permits the live task's docs.python.org:443 destination.
pocket-bench run --suite web --allow-live-web --name web-comparison
```

Unknown suites, empty selections, duplicate task IDs, tasks outside the selected
suite, and nonpositive/nonfinite budgets are errors before build or execution.
`--attempts` overrides suite repetition defaults; `--hard-timeout-seconds` overrides
the independent safety limit. The deprecated `--agent-seconds` alias has the same
wall-clock safety semantics and emits a warning. Short smoke experiments
remain possible; plans record when attempts are below the recommendation. The dry
plan is a new named artifact; executing later should use a different run name.
Model/provider/token prices are not inferred from names or subscription usage.

The web gateway's extra destination is fixed in the live task's generated Compose
configuration. Regression, capability, long-horizon and the browser fixture retain
model-only external egress. The live service records the actual HTML, title, URL and
SHA-256 in root-owned service state before grading. Fetch failures are unscorable;
there is no fallback to memorized facts or a cached gold answer. Live snapshots are
part of comparison evidence; different observed sources block matched score deltas.

## Lightweight development loop

Use `capability-smoke` after a regression check to get an inexpensive directional
signal from three fixed capability tasks: `ledger-recovery` (parallel),
`dependency-schedule` (sequential), and `repository-repair` (mixed). They retain
exactly the full capability task inputs, instructions, graders and independent safety limit.
This subset does not cover research, workflow recovery, browser or live retrieval;
run those suites/tasks explicitly when relevant. No full-suite coverage is removed.

```sh
pocket-bench run --suite capability-smoke --name dev-plan --plan-only
pocket-bench run --suite capability-smoke --name dev-1
# If the signal is ambiguous or promising, run three attempts per task.
pocket-bench run --suite capability-smoke --name dev-3 --attempts 3
# Broader confirmation uses all five capability tasks, ten attempts by default.
pocket-bench run --suite capability --name confirmation
```

Counts are per profile: the smoke default schedules three trials per profile,
versus fifty for capability. Inspect `--plan-only` before execution to see the
selected profiles and the sum of active-trial wall-clock safety allowances; this mode does not impose a token cap.
Attempts are totals for each new run, not incremental top-ups. Preserve every run,
including failures, and record that escalation was chosen after seeing preliminary
results. Run long-horizon/web when relevant or before formal evaluation.

Smoke results are **directional only**, unsuitable for leaderboards or general
capability claims, even if `--attempts` is increased. Plans and normalized JSON
retain this designation and HTML labels the smoke cohort accordingly. More repeats
cannot compensate for the limited task coverage. Full evaluation still requires the
recorded comparison conditions and statistical caveats below.

## Identities and compatibility

A run plan and every normalized trial retain suite name/version, complete suite
fingerprint, selected task IDs, selection fingerprint, per-task definition fingerprints,
partial/full status, agent configuration, source/runtime provenance, and evaluation
protocol. The fingerprint includes task content and runtime/grader source dependencies.
A version names a release; the fingerprint detects changes even before a version bump.

Capability and long-horizon version 1.1 clarify that policy-register output is a JSON
object keyed by service ID. Version 1.0 omitted this container shape while its verifier
required it, so a semantically correct array could fail. Research results from the two
versions must not be pooled. Existing version 1.0 control records remain historical
evidence; that output-shape correction did not change task counts, workload data or
grading requirements. The later integration of Issue #10 replaces short aggregate
budgets with an independent wall-clock safety limit for all suites.

Capability and long-horizon version 1.2 accept either same-key POST retry or a
subsequent GET confirming the ambiguous job before another commit (or completion).
Both methods must confirm each job before moving on. The fixture records GET and
retry confirmations in trusted service state; merely writing the
expected answer or reading once at the beginning/end does not prove per-job recovery.
The previous retry-only grading could reject valid GET-based solutions. Do not pool
version 1.2 workflow results with version 1.1 results; old evidence without per-job GET
or retry confirmation order cannot establish the revised per-job recovery contract.
Existing archived controls retain
their original versions and fingerprints.

Results JSON schema 2 is generated from both new and historical job artifacts/plans
through the normalizer. Existing standalone HTML reports remain unchanged. Legacy runs retain their original provenance and have **unknown selection
identity**; they are not guessed to be complete regression runs. Counts are retained
across all requested jobs, but a mixed-suite/selection summary has no combined success
rate or time median. JSON and HTML groups separate suite/version/selection and system.
Difficulty and decomposition breakdowns use the same boundary. Partial selections are
clearly labeled rather than presented as a complete-suite score.

Matched task comparisons can cross suite boundaries when task definitions agree.
They require known and equal model, effort, timing policy, trial concurrency,
and immutable base-runtime ID (plus observed Chromium version for browser tasks), plus scorable evidence and unchanged live source snapshots.
The safety-limit value is retained as provenance, but differing values do not block
comparisons when neither side timed out. If any included trial timed out, known equal
safety limits are required; ungraded timeouts still block grade comparisons. Historical
aggregate-budget runs continue to require equal allocations and cannot be matched
against the new safety policy. Measured runtime is never an equality condition.
They never imply that the entire suites measure the same thing. Regraded and invalidated
trials are not independent runs and do not receive these deltas. Agent implementations,
prompts, tools and orchestration can differ because the subject is the complete system;
their configurations and adapter fingerprints remain attached for interpretation.

## Single-agent versus team protocol

The bundled team already has two concurrent read-only analysts followed by a writer.
The issue was insufficient workload coverage, not absence of parallel execution.

Every system receives the same task, inputs, available task services and private grader.
The task metadata identifies `parallel`, `sequential`, or `mixed` decomposition demand:
ledger/research workloads offer independent shards; dependency/workflow tasks constrain
ordering; repository repair requires integration. A single/team comparison must report
these strata separately, not select only favorable parallel tasks after seeing results.
Different worker/tool policies are part of the system under evaluation, not hidden
changes to the task or grader. Wider teams connect through the existing generic agent
interface, preserving native per-role events and complete aggregate usage when available.

The timing policy is **wall-clock-safety-v1**. Concurrent analysts and the coordinator
share the remaining trial safety allowance without fixed role fractions. Declared
execution uses the same remaining allowance; bounded cleanup is separate. Correctness
comes from the independent grader, with timeout termination recorded separately.
Observed aggregate agent time sums worker invocations and excludes harness transport;
unknown connected-worker timing stays unknown. Compare orchestration under the same
model/effort and safety policy, reporting observed wall time and all-worker usage
alongside success. This implementation does not claim token or dollar caps. Prefer
trial concurrency 1 for latency comparison; record higher concurrency and do not
compare it as equivalent to a sequential run. Historical aggregate-budget experiments
are not matched against the new timing policy.

Fixed worker-count scaling experiments use operator-defined profiles (for example
single, team-2, team-4) on the same suite and repeated task set. A team label does not
create workers. Record the native controller/profile digest, actual role events and
aggregate usage; missing worker usage stays unknown. No subscription reset, purchase,
provider switch or automatic allowance bypass is part of this protocol.

## Metrics and statistical interpretation

- **Success/all:** successful trials divided by the intended matrix, including missing
  trials in the denominator. **Success/scored:** excludes unscorable and ungraded timed-out trials, displayed
  together with unscorable and timeout counts, never as a replacement for all-trial results.
- **Task-balanced success:** mean of per-task success fractions, so tasks with extra
  repetitions do not receive extra weight. Missing scheduled trials count as not
  successful here, and prevent an uncertainty interval.
- **Variance:** sample standard deviation across per-task success fractions. This is
  task variation, not a standard error or a claim about all possible agent tasks.
- **95% interval:** deterministic hierarchical bootstrap, resampling tasks and then
  attempts within sampled tasks, 1,000 draws, seed 0, percentile endpoints. It is
  suppressed below five tasks or five attempts per task, or with unscorable/ungraded-timeout/regraded
  evidence, mixed experiment conditions, or no observed outcome variation. A zero-width
  all-success bootstrap interval is not presented as certainty. Ten attempts is an operating recommendation, not a guarantee of precision.
  The interval describes uncertainty under this public task sampling design. It does
  not remove contamination, correlated provider conditions or dataset-selection bias.
- **Efficiency:** sum consumption over **all trials, including failures**, divided by
  successful trials. Wall seconds, aggregate agent seconds, tokens and USD are separate.
  Zero successes gives null cost/time per success. Unknown/incomplete usage gives null
  totals and per-success metrics, with observed values and known-trial counts retained.
- **Successes/wall-hour:** successes / sum of trial agent-execution wall seconds × 3,600.
  This is a sequential-equivalent efficiency measure, not total job throughput under
  concurrent execution. `total_seconds` on a trial includes its entire lifecycle.
- **Recovery:** extra attempts recorded by trusted retry/workflow services; unknown for
  workloads without such evidence. No retry count is guessed from a final answer.
- **Timeout incidence:** includes both graded and ungraded timeout trials; all scheduled
  trials remain in the denominator. An available independent grade is preserved.
- **Failure categories:** correctness/delivery, safety timeout, historical budget exhaustion, infrastructure/grader,
  or invalidation. More specific planning/reasoning diagnoses require retained trace
  evidence and remain analyst hypotheses; they cannot be established by a binary grade.

Choose the task set, attempts, resource allocation and comparison before looking at
results. Retain all runs, report category/difficulty/decomposition breakdowns and avoid
turning a smoke check into a leaderboard. For a broader claim, expand task diversity,
repeat under recorded conditions and collect human/reference baselines. References
here are oracle/no-op controls, not human performance estimates. No human baseline or
held-out validation is claimed by the shipped public corpus.

## Task quality, calibration and extensions

`src/pocket_bench/workloads.py` holds deterministic original fixture definitions for
expanded suites; `suite/catalog.json` remains the original regression catalog.
`pocket-bench build` compiles both into native Harbor tasks. Do not edit generated tasks.
A structural `hard` task requires multiple sources/modules or ordered stateful operations;
`extended` increases these demands; `short` names the original diagnostic workload.
Difficulty must be revised against measured success/time distributions before labeling
these tiers empirically calibrated. Keep calibration runs separate from final comparisons.

New task acceptance requires: explicit public contract, reproducible initial state,
reference pass, no-op failure, deliberately wrong output or invalid service-history
failure, input preservation checks, and an independent gold audit where possible.
Coding gold cases run in the isolated candidate subprocess; trusted service history,
not an agent-authored explanation, proves side effects and recovery. The browser oracle
runs actual Chromium, and its private grade checks both the rendered answer and access
to the page/data service. This checks observable behavior, not tool-use authenticity.

Browser/live-web, large repository, long research, recovery and wider team experiments
remain part of this design. Real third-party repositories/datasets may be run using
Harbor's native interface with an external adapter; retain upstream version, license,
attribution and scoring rules. This release adds original workloads without claiming
scores on SWE-bench, Terminal-Bench or another dataset. Held-out datasets require a
separate curator-controlled source and audit; committing gold fixtures to this public
repository cannot create a genuinely held-out benchmark.

## Review acceptance map (Issue #2)

| Review concern | Delivered behavior | Verification |
| --- | --- | --- |
| Mixed test scores | Suite/version/selection groups; no mixed overall rate; gated common-task deltas | metrics/report and browser checks |
| Unbounded implementation scope | Four full suites plus a fixed development subset with concrete tasks and this acceptance map | suite selection plus all-suite controls |
| Existing versus new features | Regression task/repetition defaults preserved; suites distinct from agent profiles; defined task intersection | CLI planning/selection tests |
| Fair single/team comparisons | Equal recorded timing-policy/model/effort/runtime conditions; safety limits gated only on timeout; parallel/sequential/mixed strata | comparison gating tests and task metadata |
| Undefined evaluation | Defined repetition policy, structural difficulty, bootstrap, failure/recovery and all-trial efficiency | metric edge-case tests and independent gold audits |

The complete implementation is one reviewable PR; no original workload dimension is
removed to make the issue smaller. Empirical agent rankings, human certification and
claims of held-out performance are intentionally not fabricated by implementation tests.
