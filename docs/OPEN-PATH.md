# Open-path capability tasks (Issue #12)

Run `pocket-bench run --suite open-path --profiles codex-single --model gpt-5.6-sol --effort high --attempts 1 --name open-path-check`.
The default is ten attempts per task, with the existing independent 3600-second safety timeout.
Regression remains the default suite. There are two new unique tasks (26 total).

## Scope and contracts

This first release implements two representative tasks, not every candidate task type
listed in the issue. Both use original fixed Python repositories and product records:

- `open-release-resolver`: a deployment incident requires diagnosing a release resolver.
  Validity involves version intervals, cyclic dependencies, conflicts, yanked versions,
  pins, and exact reachability. Selection has a documented three-level objective.
  The root instruction identifies the public interface, not the faulty modules or an algorithm.
- `open-billing-replay`: a replay incident requires reconstructing behavior from storage,
  accounting, support, and superseded historical notes. Revision visibility, tenant
  isolation, exact proration/discount/tax rounding, and refund history interact.

The starting code is executable and plausible but wrong. Product records disclose all
scored requirements. Historical records are explicitly marked superseded, not equally
credible contradictory requirements. Agents can investigate, design experiments, repair
multiple modules, or replace the public implementation. No internal function, file layout,
reasoning trace, particular tool sequence, or number of agents is graded. Only public
behavior and input/argument preservation are checked. There are no live dependencies.

Workstreams (diagnosis, constraint/rounding analysis, test design, integration) can be
split among agents, but a single agent has every required capability and piece of evidence.
These are behavioral repair tasks, not a claim to have implemented a trusted service or
database incident-recovery environment, an optimization benchmark, or all five examples.

## Grading and reproducibility

`src/pocket_bench/open_path.py` defines snapshots and private cases with fixed local seeds
12001 and 12002. Reference implementations use exhaustive enumeration/rational arithmetic;
independent gold functions use dependency-driven search/a separate accounting fold.
Unit tests cross-check both and exercise no-op, alternative correct implementations,
plausible partial repairs, input preservation, and the build boundary.

The existing separate verifier receives fixed cases and executes candidate code as an
unprivileged child without expected outputs. `/tests` and `/solution` are absent from
the agent workspace. The grader checks all hidden cases, including cases beyond the
public reproduction. A short per-case execution guard bounds malformed candidate code;
this is not an agent planning deadline. New task verifier deadlines allow three seconds
per case plus 15 seconds of overhead, including offline regrading. A case timeout ends
further probing and records failure, followed by final preservation checks. Agent
safety deadlines remain unchanged.

These cases are hidden from the executing agent, **not held out from the public repository**.
Task definitions (including all cases, references, and public files) contribute to per-task
and suite fingerprints. The review pilot used version 1.0. Version 1.1 adds explicit billing boundary checks
without changing public instructions; semantic changes require a
suite version bump and new calibration records. Do not edit generated tasks directly.

## Acceptance and interpretation

| Issue requirement | Evidence |
| --- | --- |
| Precise goal, undisclosed solution path | Incident instructions, dispersed authoritative records, public API only |
| Reproducible initial state and dependencies | Fixed generated snapshots, local seeds, standard library; no external service |
| Independent outcome checks | Existing isolated verifier; two independently implemented gold algorithms |
| Positive and negative controls | Reference/alternative passes, no-op and partial-fix failures |
| Preservation and route neutrality | Input/argument checks; entire public implementation may be replaced |
| Single-agent feasibility | Executable single-process references; no role permissions or simultaneous actions |
| Version/fingerprint identity | New named versioned suite and existing task-content fingerprints |
| Harder empirical behavior | Calibration record below; observations must not be represented as stable rankings |

Calibration is separate from final comparison. One attempt per system is a pilot,
not a stable success-rate estimate. Record every failure and unscorable trial, model,
effort, timing, and usage. A successful fast run is evidence that the task may need more
work, not a reason to shorten its time limit. Multi-agent advantage requires a subsequent
matched comparison and is not implied by task structure alone.

Verifier version 2 checks protected files after candidate execution as well as before.
This closes a review-discovered gap where code could alter an input during grading.
The shared verifier source change updates existing task fingerprints too; old and new
verifier results must remain distinct. Agent deadlines and outcome requirements are unchanged.
