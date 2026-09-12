# Issue #10 implementation review

The change separates measured efficiency from emergency termination. A correct
artifact is graded by the independent verifier regardless of elapsed time. Active
work uses a configurable 3600-second wall-clock guard; the former 180-second
default and 1/6, 1/6, 2/3 role allocations no longer stop ordinary work early.

| Issue requirement | Implementation / review evidence |
| --- | --- |
| Observe wall time and total trial time | Existing report `seconds` and `total_seconds` retained; no elapsed-time grading threshold. A simulated 600-second successful trial stays successful. |
| Observe aggregate invocation and role time | Native workers use monotonic durations, summed independently of parallel wall time. A simulated team records 720 worker-seconds in 480 wall-seconds. Connected controllers can supply measured timings; unknown aggregate time remains null. |
| Preserve token counts and completeness | Native/connected usage collection retained, with cancelled workers recorded and partial usage kept partial. Declared transport timeout does not invalidate already complete native token measurements. |
| Retain retry/recovery evidence | Harness retry configuration remains zero and is recorded in the timing policy. Worker/native logs and controller cleanup recovery evidence remain available. No new retries are introduced. |
| Independent correctness | Trusted verifier grades are preserved even alongside timeout termination. Ungraded timeout is `timed_out`, not an inferred incorrect answer. Tests cover absent, failing, and passing grades. |
| Generous independent safety timeout | `--hard-timeout-seconds`; finite-positive validation; shared wall-clock guard for native roles and connected work. Outer watchdogs allow bounded cleanup. Control profiles also honor the configured limit. Generated task defaults no longer impose 240 seconds. |
| Distinct safety termination | New runs record `hard_timeout`; historical timeout evidence is labeled `legacy_timeout`. Reports show timeout incidence separately, including graded trials, and keep every trial in overall-rate denominators. |
| Explicit task deadlines | Documented as task/grader semantics. No new deadline requirement is imposed on ordinary tasks. |

Scope review: no suite expansion, new fixed-budget evaluation mode, model changes,
retry policy changes, or grader correctness changes. Generated task changes are
limited to the execution contract/helper and fallback safety timeout. The deprecated
`--agent-seconds` alias emits a warning about changed wall-clock semantics. Plans
record the new timing policy so it is not confused with historical role budgets.

Review fixes include routing connected CLI timeouts through Harbor's timeout path
so independent verification can run; retaining cancellation timings; stopping native
task-user processes before grading; preserving invalidation of grades; and applying
the configured safety limit to oracle/no-op control profiles.

Validation: unit/integration tests and Ruff checks; deterministic task rebuild;
JavaScript syntax check; six real, disposable, networkless Docker adapter checks
(single, team, CLI, each normal and hung), using a local fixture executable with no
model calls or credentials. Docker checks confirmed artifacts on normal completion
and cleanup plus timeout metadata on interruption. Real-model speed distributions
were not benchmarked; 3600 seconds is a configurable initial guard, not a measured
universal upper bound for normal work.
