# Connecting an agent

`pocket-agent-v1` separates connection mechanics from tasks and grading. A profile
identifies an agent, `single` or `team` topology, and a transport. No task, expected
answer, scoring rule, service privilege, or task category depends on that identity.
The existing twelve tasks and their graders are unchanged by this interface.

## Ordinary CLI: configuration only

An executable already installed in the task runtime needs a JSON profile, not a
Python adapter. For example (replace the executable and flags with its actual CLI):

```json
{
  "protocol": "pocket-agent-v1",
  "profiles": {
    "my-cli-single": {
      "agent": "my-cli",
      "mode": "single",
      "execution": "cli",
      "input": "argument",
      "argv": ["my-cli", "run", "--model", "{model}", "--effort", "{effort}", "--prompt", "{instruction}"]
    }
  }
}
```

Run `pocket-bench run --profile-file local/connections.json --profiles my-cli-single
--attempts 1 --concurrency 1`. A multi-agent orchestrator can be another profile with
`mode: "team"`; this label describes the actual system, it does not create a team.

The process runs as the task's unprivileged `agent` user in `/app`. It writes `src/`
and `output/`. Input modes are `argument`, `stdin` (instruction on stdin), or
`request` (JSON request at the `{request}` argv element). Argument and request modes
receive EOF on stdin so clients cannot wait for an additional piped prompt.
Placeholders are substituted
only when they occupy a whole argv element; shell text is not evaluated. Other
available placeholders are `{workspace}`, `{model}`, and `{effort}`. `setup_argv`
is an optional array of argv arrays, also executed unprivileged.

Optional `credentials` bindings have `source_env` (an explicitly supplied host
environment variable naming a file) and `target` (under `/home/agent`). No automatic
host credential discovery takes place. Credential bytes are never profile metadata.
Native CLI logs can contain sensitive output; keep raw local results private.

Optional `usage_jsonl` defines `event_key`, `event_value`, and `fields`, mapping
normalized `input_tokens`, `output_tokens`, `cached_input_tokens` to dotted native
event paths. Missing observations remain unknown, not zero. Configure
`usage_limit_markers` for the CLI's quota errors. No reset, purchase, or provider
switch is implemented. The existing Codex single/team adapters remain optional
legacy integrations for reproducing old runs, not a requirement for other agents.

## External orchestrator: explicitly trusted host controller

An agent system that owns its own isolated environments or speaks an unusual API
can implement the same file protocol in its own repository. Select
`execution: "host-controller"` and provide operator-owned argv containing whole
`{request}` and `{response}` elements. Launch requires `--allow-host-controller`.
This grants trust to the controller's host code, **not** to model-generated tools.
The controller must isolate those tools itself. The benchmark does not sandbox
arbitrary host controller code; its trust is equivalent to a custom Harbor adapter.

Request fields:

| Field | Contract |
| --- | --- |
| `protocol` | `pocket-agent-v1` |
| `operation` | `run` or `cleanup` |
| `instruction` | Unchanged public task instruction |
| `workspace` | Private disposable snapshot of `input/`, `src/`, `output/` only |
| `public_checks` | Public `smoke.py` and `execution.py`; no expected answers |
| `control_dir` | Private controller state and crash-recovery records |
| `writable_roots` | `src`, `output` |
| `seconds` | Remaining run allowance; setup and return transport consume time too |
| `model`, `effort` | Fixed experimental model selection |
| `settings` | Opaque operator configuration; core never interprets product settings |

Write a new response JSON file with `protocol`, `outcome`, optional `usage`, and
bounded normalized `details`. Outcomes are `completed` (attempt returned, **not**
correctness), `failed` (connection failed), `usage_limit`, and `cleaned` (cleanup).
There is no agent-supplied reward field. A returned unsuccessful attempt may still
be graded with its actual artifacts. Protocol/transport failures are unscorable.

Only bounded regular files in the two writable roots are returned. Input mutation,
symlinks, hardlinks, devices, path traversal and file/directory collisions are
rejected. Hidden `/tests`, `/solution`, private task specs, grader expectations and
trusted service state are never exported. Cleanup runs after success, failure,
timeout or cancellation; it must be idempotent and confirm removal of all owned
external resources. Host process groups are stopped separately. An unavailable
cleanup mechanism is an error, not implicit success. Unconfirmed cleanup preserves
the private control directory and a local `controller-recovery.json` pointer, so
resource ledgers are not lost before an operator can recover the exact resources.

API tasks retain their existing `pocket-python-v1` route: an agent may declare a
Python script and the benchmark executes it once, in the task's original unprivileged
environment, within remaining wall time. This does not grant an offline controller
interactive API access. Compare this system-plus-transport condition honestly.

Connected profiles currently require concurrency 1. Once quota is reported, the
shared job gate prevents subsequent setup/model calls; scheduled but unrun trials
remain in the report. Unconfirmed controller cleanup also stops subsequent trials
and retains recovery evidence. This is not a token or dollar cap. Native model retries
inside a CLI remain that CLI's responsibility. Unknown usage/cost remains unknown.

Reports use exact profile identities (even two profiles of the same system), retain
missing trials, and group by task/category as before. Plans retain a profile digest
and non-secret identity, not controller argv/settings/credential contents. Private
profile file paths may be present in Harbor config. Configuration changes after
planning invalidate a connected trial.

## Migration

Product-specific host adapters belong to the product/plugin repository. The old
embedded My AI Employee adapter and wrapper have moved to its product repository;
`fleet-single` is no longer an active built-in benchmark profile. Archived reports
retain historical labels. `build_runtime.py --install-project PATH` can include an
explicit generic Python agent project; this replaces the old product-named option.
It copies only the selected project metadata and `src`, never credentials/state.

The user-owned pre-existing benchmark corrections were preserved separately from
this interface work. Do not compare a newly connected run against an older task or
runtime revision without checking the recorded provenance.

## Execution timing

Request `seconds` is the remaining wall-clock **safety allowance**, not a desired
completion time or an aggregate worker budget. The default trial guard is 3600
seconds (`--hard-timeout-seconds`). Controllers must stop within the allowance;
mandatory cleanup has its own bounded allowance, including on timeout. Ordinary
correctness is determined by the independent grader, not by a short runtime target.

Host controllers may return optional measured timings:

```json
"timings": {
  "aggregate_agent_seconds": 42.5,
  "events": [{"role": "worker", "started_at": 1780000000.0, "duration_seconds": 42.5}]
}
```

`started_at` is Unix time; durations are finite nonnegative seconds measured with
a monotonic clock. Aggregate time sums all agent invocations, including retries and
parallel workers, and excludes harness transport/cleanup. Omit unknown measurements;
the harness does not infer aggregate worker time from a controller's wall duration.
CLI connections retain native logs and report aggregate worker time as unknown.
Token counts and their completeness remain independent of timing measurements.
