# Validation and initial measurements

## Native generic-interface diagnostic (2026-09-06)

`employee-native-v1-20260906` exercised all twelve tasks through the new generic
`pocket-agent-v1` host-controller interface and the product-owned Fleet adapter.
One attempt per task, concurrency 1, `gpt-5.6-luna`, effort `low`, 180 seconds per
agent phase. The run took 12m42s. No hidden grader, task input or instruction was
changed from the separately preserved corrected baseline (`4fad7ae`).

| Category | Success | Failure | Unscorable |
| --- | ---: | ---: | ---: |
| Data | 3 | 0 | 0 |
| Research | 1 | 2 | 0 |
| Coding | 0 | 3 | 0 |
| API | 0 | 3 | 0 |
| Total | 4 | 8 | 0 |

These are **raw integration-diagnostic results, not a fair capability score**.
Every failed trial returned Fleet status `failed`, with no accepted candidate
exported. A later model-free product-side reproduction found that its public-check
command wrote bytecode in a protected directory; running that command could cause
Fleet to reject an otherwise valid candidate. The product now disables that
side effect and records its stable graph failure code. The original trial metadata
does not identify each rejection cause, so not all eight failures can conclusively
be assigned to that defect. No model rerun or retrospective grade rewriting occurred.

Evaluated benchmark commit: `3230575`; product commit: `b64b808`. Product implementation
digest: `f886f07ea03f3a543c2702b08386e12030066467b8993e12fc9ec6972e9032ff`.
Task/verifier runtime:
`sha256:2446176326e8dfdf83d730bd9bafc696799d75f13fa5b469ea8adea672d50010`.
Product worker runtime (Linux arm64, Codex 0.144.4):
`sha256:d71061257e875361e1bf9baf2f0c2db51c0fb88828c33d53b00ee97ee3783993`.
The old Fleet package embedded in the task image was not used. The product's
`docs/benchmark-adapter.md` documents its settings and post-run fix. Local operator
paths/authentication stay private; the benchmark contains no product controller.

All twelve cleanups were confirmed. Median agent phase: 48.7s. Observed input tokens:
878,729 (including 653,568 cached); output tokens: 13,227. Dollar cost is unknown.
No reset tickets, purchases, model/provider fallback or automatic score-improving
reruns were used. One trial per task, a changed product runtime and a known connection
defect preclude superiority claims against the historical single/team baselines.

Before this run, model-free CLI and host-controller Docker probes both produced a
deliberately wrong output and were independently graded failure rather than
unscorable, validating the transport/grader distinction. Interface unit tests also
cover profile identity, protected inputs, timeout cleanup and fail-closed quota gates.
See [all twelve sanitized results](../examples/employee-native-v1.json) and
[connection instructions](AGENT-INTERFACE.md). Agent success is never a reward input.

## Earlier diagnostic measurements

Validation date: 2026-09-05. This is an automatically validated **initial diagnostic
suite**, not a human-certified benchmark or a statistically reliable leaderboard.

## Correction: the initial API comparison is invalid

A follow-up audit found three **benchmark-side** integration defects, not six
independent demonstrations of product incapability:

1. Fleet's actual worker used `--sandbox read-only`. The adapter set only
   `sandbox_workspace_write.network_access=true`, which does not enable network in
   that mode. Its preflight incorrectly exercised workspace-write instead. Native
   tool logs show `PermissionError: [Errno 1] Operation not permitted` on loopback
   sockets. A credential-free reproduction in the exact runtime confirmed it.
2. Fleet's active proposal schema accepts edits/dependency installs, not general
   process execution. The adapter exposed only structural smoke verification and
   had no explicit program execution transport. Scripts could be accepted without
   ever operating the service or producing the required result file.
3. Smoke accepted `src/solution.py` specially, but a valid `src/main.py` fell back
   to requiring a result file before the program could execute.

All six Fleet API trials in `baseline-v2` and its offline regrade now carry a
selective invalidation overlay. Original raw grades/checks and logs are unchanged.
Regrading consistency never established that the original tool environment was
correct. The old headline **17/24 must not be used as a fair product score**.

The corrected adapter preserves Fleet's read-only command filesystem, enables
loopback access through a named permission profile, and probes that same policy.
OpenAI Docs informed this setting: legacy `--sandbox` overrides named profiles,
so the wrapper replaces the known read-only flag rather than combining both.
See [official permission documentation](https://developers.openai.com/codex/permissions).
Docker's existing internal network/model-only proxy remains the egress boundary.

All three configurations now receive the same optional `pocket-python-v1` manifest
contract on API tasks. The agent authors its own program and explicit execution
manifest; the adapter executes it once within remaining time, after materializing
Fleet's accepted parent candidate. It does not infer a program, solve a task, or
bypass rejected Fleet proposals. Structural smoke parses arbitrary Python source
names and the manifest without executing side effects. My AI Employee's source,
runtime image and repair policy are unchanged.

The new task interface has a new task/suite fingerprint. `api-corrected-v1` reruns
only the API subset for all three configurations, not just Fleet. Do not splice
the new six API trials and old non-API trials into a supposedly uniform new baseline.
The development probe `api-transport-spike-v1` succeeded on retry (three trusted
service requests, result 42); it is not included in comparative scores.

## Corrected API comparison

`api-corrected-v1`: three API tasks × three configurations × two repetitions;
`gpt-5.6-luna`, effort low, 180 aggregate agent-seconds, concurrency 3. Same immutable
runtime and Fleet source as the historical experiment. Total wall time: 5m09s.

| Configuration | Success | Failure | Unscorable | Median agent phase |
| --- | ---: | ---: | ---: | ---: |
| Codex single | 5/6 | 1 | 0 | 16.0 s |
| Codex team | 6/6 | 0 | 0 | 34.4 s |
| My AI Employee single + corrected adapter | 3/6 | 3 | 0 | 40.7 s |

Each Fleet API task succeeded once and failed once. All three successes used the
agent-authored manifest/program; the trusted service history records pagination
requests, three retry requests, or approval reads respectively. All 18 policy and
outer-boundary preflights passed. The four remaining failures are trace-backed:

- Fleet `api-approval__7uLHtqp` and `api-retry__vFen5Gf`: the worker prefixed the
  **second file's diff headers with an extra `+`**, making them added text in the
  first Python file. Only one file is actually described, while two paths are
  declared. Fleet correctly rejects this with `INVALID_REQUEST: unified diff paths
  must exactly match declared edit paths`, then `NODE_EXECUTION_FAILED`. A plain
  `git apply --check` can accept these as one-file edits; that does not validate
  the two-file intent. No parent candidate/manifest reached the execution phase.
- Fleet `api-pagination__7P7HWRd`: the first hunk's declared new-line count is 34,
  inconsistent with its body before the next file header. Fleet's normalizer
  reports `header-less unified diff requires an adjacent file pair`, recorded as
  `WORKER_ENVELOPE_MALFORMED` / `WORKER_PROTOCOL_ERROR`. Independent `git apply
  --check` rejects a corrupt patch at line 37; `--recount --check` accepts it.
  No candidate was extracted around Fleet's rejection or repaired by this adapter.
- Codex single `api-retry__R3bvcbw`: the API was called three times correctly, but
  the generated program wrapped an already-object response again, delivering
  `{"value":{"value":42}}` instead of `{"value":42}`. The execution transport
  succeeded; the independent result check correctly failed.

Fleet's recorded effective worker budget is **one turn**, with the fixed-node
graph's repair budget zero, despite the harness requesting three worker turns.
The native built-in policy caps worker turns at one (`cli.py`), and `one_node_graph`
uses single-attempt/default-zero-repair budgets. Thus malformed generated patches
end the run with over 140 seconds of the outer budget still unused. This is a
remaining integration/recovery limitation, not the old network failure. The
benchmark did not modify this native policy or retry until obtaining a good score.

All 18/18 statuses **and individual check lists** matched in the fresh offline
`api-corrected-v1-regraded` run. `api-corrected-controls-v1`: oracle 3/3 success,
NOP 3/3 failure, zero exceptions. The corrected implementation has 75 passing unit
tests, including shared policy flags, opt-in execution, arbitrary source names,
timeouts, symlink/path rejection, and selective invalidation.
The 36-row original/regrade browser report passed desktop/mobile filtering,
detail/search and all 18 matched comparisons with zero JavaScript errors. Credential
value matching found no matches in the saved results or shareable summaries.

This shows that the blanket API failure was confounded by the benchmark adapter,
and that a reproducible patch-transport/recovery weakness remains in this Fleet
configuration. Six trials per configuration do not establish general superiority.
The optional manifest changes what the **system + adapter** can do; it is not proof
that unmodified standalone Fleet can execute arbitrary process proposals.

Historical command for the corrected API subset (requires the archived adapter
revision and runtime; `fleet-single` is no longer an active built-in profile):

```sh
uv run pocket-bench run --name my-corrected-api \
  --tasks api-pagination,api-retry,api-approval \
  --profiles codex-single,codex-team,fleet-single \
  --attempts 2 --concurrency 3 --agent-seconds 180 \
  --model gpt-5.6-luna --effort low
```

See [shareable corrected results](../examples/api-corrected-v1.json), or the local
`results/reports/api-corrected-v1/index.html`. Development probes are excluded.

## Initial real comparison (historical, partially invalidated)

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
| My AI Employee single | 17 | 1 | 6 | not comparable as a full score | 32.2 s |

All 72 scheduled trials completed with zero Harbor exceptions, but the later audit
invalidated six initially failed API trials. After the overlay: 64 successes,
2 failures and 6 unscorable trials. The job took approximately 21 minutes. The lack
of Harbor exceptions did not mean the adapter environment was correct.

| Task category | Codex single | Codex team | My AI Employee single |
| --- | ---: | ---: | ---: |
| Data | 6/6 | 6/6 | 6/6 |
| Coding | 6/6 | 6/6 | 5/6 |
| Local-document research | 6/6 | 5/6 | 6/6 |
| Mock API workflows | 6/6 | 6/6 | invalidated: 6/6 |

Observed input/output usage was 4,497,705 / 76,480 tokens, including 3,637,504
cached input tokens. Some team analysts hit their sub-budgets without final usage
events; those aggregate observations are lower bounds, not complete totals. Monetary
cost is null because these were subscription-authenticated sessions.

Do not infer that a particular orchestration architecture is generally better from
two repetitions on twelve short tasks. The full system, including output transport,
internal verification, tool policies and orchestration, is what is evaluated.

Run a new full comparison with the corrected adapter (not a reproduction of the
historical defective adapter) using:

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

Examples from the historical experiment; the API examples are now invalidated:

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
results were confounded by the adapter defects above and cannot establish
product-wide capability.

## Acceptance evidence

| Requirement | Evidence |
| --- | --- |
| Generic task format and execution | Native Harbor tasks, optional Fleet adapter; base runtime independently built without `ai_employee` installed |
| Single and multi-agent execution | Native single session and two concurrent native analysts with an integrating coordinator; actual handoffs and role timing retained |
| Two real systems | Native Codex and actual My AI Employee fixed-routing runtime; neither replaced by reference scripts |
| Verifier correctness checks | 75 passing unit tests, including independent gold recomputation, alternate/wrong answers, input preservation and all 24 dependency permutations |
| Positive/negative Docker controls | `controls-isolated-v1`: oracle 12/12 success; no-op 12/12 failure; zero exceptions |
| Grading isolation | Separate network-disabled verifier, root-only private tests, unprivileged candidate execution, protected service audit state |
| Network compatibility | Corrected API run: 18/18 outer and worker-policy-specific preflights pass; original Fleet API preflight mismatch is explicitly invalidated |
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
invalidation record and retains its original evidence. The subsequent `baseline-v2`
also had defective Fleet API integration, now selectively invalidated as described above.
Other development spikes are diagnostic artifacts, not comparable performance runs.

Known scope limits: no independent human review, no live-web research/browser tasks,
no long-horizon coverage, no broad adversarial security claim, and no hard token/dollar
cap. Subscription monetary cost is unknown, not zero. Partial token observations are
not presented as complete totals. Regrading reuses original artifacts/usage and does
not constitute a new independent agent execution.
