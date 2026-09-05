# Validation and initial measurements

Validation date: 2026-09-05. This is an automatically validated **initial diagnostic
suite**, not a human-certified benchmark or a statistically reliable leaderboard.

## Initial real comparison

Experiment: `baseline-v2`. Twelve tasks × three configurations × two repetitions.
Every trial starts with fresh synthetic inputs and services. The model is
`gpt-5.6-luna`, reasoning effort `low`, and the invocation-time allocation is 180
aggregate agent-seconds per system. Two analysts each receive 30 seconds and the
coordinator receives 120 seconds. Trials were run with concurrency 3; timing therefore
includes shared-machine contention. Timeout cleanup can add small timing overhead.

| Configuration | Success | Failure | Unscorable | Success rate | Agent time median |
| --- | ---: | ---: | ---: | ---: | ---: |
| Codex single | 24 | 0 | 0 | 100.0% | 25.7 s |
| Codex team | 23 | 1 | 0 | 95.8% | 47.5 s |
| My AI Employee single | 17 | 7 | 0 | 70.8% | 32.2 s |

All 72 scheduled trials completed: 64 successes, 8 failures, zero unscorable trials
and zero Harbor exceptions. The complete job took approximately 21 minutes.

| Task category | Codex single | Codex team | My AI Employee single |
| --- | ---: | ---: | ---: |
| Data | 6/6 | 6/6 | 6/6 |
| Coding | 6/6 | 6/6 | 5/6 |
| Local-document research | 6/6 | 5/6 | 6/6 |
| Mock API workflows | 6/6 | 6/6 | 0/6 |

Observed input/output usage was 4,497,705 / 76,480 tokens, including 3,637,504
cached input tokens. Some team analysts hit their sub-budgets without final usage
events; those aggregate observations are lower bounds, not complete totals. Monetary
cost is null because these were subscription-authenticated sessions.

Do not infer that a particular orchestration architecture is generally better from
two repetitions on twelve short tasks. The full system, including output transport,
internal verification, tool policies and orchestration, is what is evaluated.

Reproduce the requested conditions with:

```sh
uv sync --frozen --extra dev
uv run python scripts/build_runtime.py --fleet ../my-ai-employee
uv run pocket-bench run --name my-baseline \
  --profiles codex-single,codex-team,fleet-single \
  --attempts 2 --concurrency 3 --agent-seconds 180 \
  --model gpt-5.6-luna --effort low
```

The evaluated runtime image ID is
`sha256:2446176326e8dfdf83d730bd9bafc696799d75f13fa5b469ea8adea672d50010`.
The My AI Employee source snapshot digest is
`aae1101d4dc7d5b3b60bc767c487c1f67a0a41d5c0835b86ee6814ddb39ce245`,
based on Git HEAD `fd64ae4d856ecdbe637b11318e57d40aa6bc2b5f` plus existing local source
changes. Those changes were preserved; the benchmark did not modify My AI Employee.
Harbor is 0.22.0 and native Codex CLI is 0.144.4. Base tags and server-side model aliases
can change later: future rebuilding is not a promise of bit-identical behavior.

## What the failures tell us

Examples from the recorded final experiment:

- `api-pagination__PN6m3qj` / Fleet: produced a Python script but did not run the
  requested service workflow. Trusted service evidence contains no requests, and
  the required result file is absent. Internal `ready_to_promote` is not task success.
- `api-retry__XE5QHhV` / Fleet: similarly proposed a recovery script without
  performing the API calls or producing the required result artifact.
- `api-approval__3RbALRP` / Fleet: the required approval-reading check failed.
  Merely returning an expected status does not establish that the service was consulted.
- `code-intervals__n7PNnwz` / Fleet: `DIFF_HUNK_AMBIGUOUS` at the worker envelope
  boundary led to `NODE_EXECUTION_FAILED`; the delivered source remained the original
  incorrect implementation. The verifier's interval failures are downstream symptoms.
- `research-policy__uGqfc6s` / Codex team: the final message reports creating
  `/app/result.json`, while the task requires `/app/output/result.json`. The required
  artifact is absent even though the agent reports completion.

These are trace-backed observations about these trials, not claims that every failure
of the corresponding product has the same root cause. No failing system was modified
to improve its score during the final comparison.
In particular, the Fleet configuration is a fixed-node candidate-patch workflow with
only a structural smoke command declared in its project harness. It is not claimed
to be the best configuration for arbitrary execution-oriented workflows. The API
results expose that configuration's failure to perform the requested operations;
they are not a pure comparison of identical tool interfaces or product-wide capability.

## Acceptance evidence

| Requirement | Evidence |
| --- | --- |
| Generic task format and execution | Native Harbor tasks, optional Fleet adapter; base runtime independently built without `ai_employee` installed |
| Single and multi-agent execution | Native single session and two concurrent native analysts with an integrating coordinator; actual handoffs and role timing retained |
| Two real systems | Native Codex and actual My AI Employee fixed-routing runtime; neither replaced by reference scripts |
| Verifier correctness checks | 57 passing unit tests, including independent gold recomputation, alternate/wrong answers, input preservation and all 24 dependency permutations |
| Positive/negative Docker controls | `controls-isolated-v1`: oracle 12/12 success; no-op 12/12 failure; zero exceptions |
| Grading isolation | Separate network-disabled verifier, root-only private tests, unprivileged candidate execution, protected service audit state |
| Network compatibility | Outer egress/credential-boundary checks plus actual model-free inner Codex loopback probe |
| Regrading | `baseline-v2-regraded`: all 72/72 statuses and individual check lists identical; fresh offline containers, no model calls |
| Browser report | Desktop/mobile Chromium checks: filtering, detail, search, zero JavaScript errors; nine matched comparison cells checked on saved/regraded evidence |
| Automation | Push/PR unit workflow and manually triggered credential-free Docker controls workflow |

## Artifacts and limitations

- [Shareable measured summary](../examples/baseline-v2.json): configuration/category
  aggregates, per-trial checks, synthetic service evidence and provenance.
- Local complete report: `results/reports/baseline-v2/index.html` and `results.json`.
- Local original evidence: `results/jobs/baseline-v2/`.
- Local offline regrade: `results/jobs/baseline-v2-regraded/`.

Raw logs, artifacts and plans remain local under `results/`, outside version control.
The shareable summary contains synthetic outputs/checks and version fingerprints, not
native prompts, local paths, account credentials or application databases. Credential
matching scans were run without printing credential values. This is not a general
secret-detection certification.

The early shared-verifier prototype and a run with blocked inner API networking were
not used as the final baseline. The interrupted `baseline-isolated-v1` has an explicit
invalidation record, retains its original evidence, and is superseded by `baseline-v2`.
Other development spikes are diagnostic artifacts, not comparable performance runs.

Known scope limits: no independent human review, no live-web research/browser tasks,
no long-horizon coverage, no broad adversarial security claim, and no hard token/dollar
cap. Subscription monetary cost is unknown, not zero. Partial token observations are
not presented as complete totals. Regrading reuses original artifacts/usage and does
not constitute a new independent agent execution.
