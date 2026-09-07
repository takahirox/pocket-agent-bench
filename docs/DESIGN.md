# Evaluation design and decisions

## Boundaries

Each trial has a fresh task container and an internal Docker network. Only a
CONNECT-only gateway on that network has an external route, and it accepts exactly
`chatgpt.com`, `auth.openai.com`, and `api.openai.com`, port 443. No API request body,
authorization header or credential is logged by the gateway. Local mock APIs are
loopback-only, synthetic services; no real business accounts are used.

Harbor 0.22.0's nftables allowlist requires CONFIG_NFT_FIB_INET, unavailable on the
tested Docker Desktop kernel. Therefore `task.toml` uses Harbor's `public` baseline
while **the custom Compose internal network and gateway enforce actual restrictions**.
This is not unrestricted task networking. The model endpoints remain accessible to
agent tools as well as the model client: this is destination restriction, not strict
per-process separation of the two planes. Providers supporting stronger egress
controls can implement them without changing task semantics.

Codex runs as uid 1000 with its native read-only/workspace sandbox. Docker's default
seccomp filter blocks the nested user namespace required by that sandbox. Only the
disposable task container uses `seccomp=unconfined`; no extra capabilities, privileged
mode, Docker socket mount or user-repository mount is granted. The gateway retains
its default seccomp filter, drops all capabilities, and has a read-only root filesystem.

Before real-agent execution, a probe checks the unprivileged UID, hidden verifier,
root-owned mock state, blocked direct egress and explicit denial of a non-model host.
An additional model-free probe starts an ephemeral loopback service and connects to
it through the actual native Codex command sandbox, using the same shared policy
builder as the corresponding worker. It checks both loopback access and filesystem
write permission (denied for Fleet; allowed for native workspace workers). Fleet's
read-only filesystem uses a named network-enabled permission profile, not the
ineffective workspace-write network flag. The Docker boundary remains the egress
authority. Read-only team analysts do not operate APIs.
Subscription auth is injected using Harbor file upload, mode 0600, and is not included
in logs, artifacts, build context or version control. It is removed when the trial
container is destroyed. Default tool filesystem visibility is still the disposable
container; these trusted synthetic tasks are not an adversarial credential benchmark.

## Independent grading

Docker Desktop bind-mounted log ownership is not a trustworthy access-control boundary.
The initial shared-verifier prototype exposed this during preflight. Final tasks use
Harbor's **separate verifier environment**: the agent's container is stopped before
artifacts are copied into a clean container. The verifier container has `network_mode:
none`, no agent credential, and root-only tests. The root-owned API state is collected
directly from the task container, not from an agent-authored account of events.

The verifier removes any existing reward/check files before grading, including
`reward.json` (which Harbor would otherwise prefer to `reward.txt`). The report requires
Harbor's verifier result; an arbitrary `checks.json` file alone is never a grade.
Candidate Python is run as uid 1000 with a per-case timeout. Expected values stay in
the parent verifier. The host never executes downloaded candidate code.

All initial inputs are fixed and inspectable. Data/research reference outputs are
small hand-inspectable constants, while the coding references are executable solutions.
Oracle success proves a task is solvable; NOP and deliberately wrong answers test
some false positives. Alternate outputs check some false negatives. These checks
do not prove grader correctness, resistance to every exploit, or human agreement.
There is no human-review certification and no LLM judge in the initial suite.

Additional gold-audit tests recompute the data answers from public inputs, select
the effective policy revision, check confirmed facts, exhaust all 24 dependency
orderings, and independently verify coding case properties. These are independent
implementations of checks, not independent human authorship or certification.

## What is measured

API tasks offer a public opt-in execution manifest to every configuration:
`output/execute.json` containing exactly `{"script":"src/any_name.py"}`. It runs
the explicitly declared agent-authored program once, as uid 1000 in the disposable
task, after the final candidate is available and within remaining aggregate time.
Missing manifests never cause guessed script execution. Invalid/missing/out-of-src
or symlinked targets are rejected. Smoke checks parse all Python sources and validate
the declaration but never run it. Execution exit status/stdout/stderr are retained;
the private grader checks the resulting artifact and root-owned service history.
This is an adapter capability, not a claim that Fleet's native proposal schema can
execute arbitrary process requests. Native agents can alternatively use direct
tools without a manifest. No hidden answer or agent-specific reference code is used.

The system includes prompts, orchestration, model, tools and agent policies. The
single/team comparison keeps the model/effort and task constant. Team invocation
time limits sum to the single-agent limit; this does not equate token usage or actual
cost. CLI backends do not expose a trustworthy hard total-token or dollar limit, so
the initial release does not claim one. Tokens and cost must be interpreted separately.

Task correctness and engine status are separate. A structurally valid candidate may
fail private correctness checks. Fleet's refusal to produce a parent candidate is
recorded, not bypassed by extracting an arbitrary child patch. Missing infrastructure
or grader evidence is unscorable. Time-budget exhaustion after execution starts is
a task failure. Root-cause labels remain observations/hypotheses, with raw evidence.

Two repetitions per task establish that the workflow repeats; they are too few for
strong statistical inference. The suite intentionally emphasizes short tasks. It
does not evaluate general research on the live internet, browser interaction,
long-horizon planning, broad multi-agent scaling, adversarial robustness or production
safety. Report differences from concurrent runs are subject to shared-host contention.

## Existing work and reuse decision

- Harbor native task/agent interfaces and lifecycle are reused directly:
  https://www.harborframework.com/docs/core-concepts
  https://www.harborframework.com/docs/tasks
- The official Harbor tutorial's SSH-key task was considered as a format example:
  https://www.harborframework.com/docs/tasks/task-tutorial
- Terminal-Bench and SWE-bench remain useful larger external benchmarks. Their scores
  are not interchangeable with this small suite and are not claimed by this project.
- Human curation of instructions/tests in SWE-bench Verified informs our validation:
  https://openai.com/index/introducing-swe-bench-verified/
- Native CLI execution/JSON usage follows the official documentation:
  https://developers.openai.com/codex/noninteractive
- Native command network settings are explicit and exercised by preflight:
  https://developers.openai.com/codex/permissions

The initial dataset is original synthetic material: this avoids attributing our
modified graders to an upstream benchmark or implying upstream human review. Existing
dataset reuse should retain exact version, license, attribution and scoring protocol.
The core benefit reused immediately is Harbor's engine. Broader third-party datasets
can be evaluated directly with Harbor and their own dependencies; compatibility and
license review are per dataset, not assumed for the whole registry.

## Reproduction

`uv.lock` pins Python dependencies. Runtime builds pin Codex CLI; built image and Fleet
source digests are recorded. Task checksums are stored by Harbor; the suite manifest
identifies the catalog, grader and public execution transport. Base tags and apt/runtime dependencies can change
on rebuild; the recorded immutable image ID identifies the image actually used.
Model IDs can be server-side aliases, so an identical ID cannot guarantee
identical future provider behavior. Every run records requested conditions and evidence.
Adapter/preflight source fingerprints are recorded in the plan. Runs verify the
runtime tag still resolves to the recorded image ID and request task image rebuilds
so an older cached task image does not silently retain a superseded runtime.

Reports embed all data and need no server or external assets. Raw trial artifacts are
kept for regrading. Invalidations preserve the original result and attach an explicit
reason instead of silently rewriting history.

## Expanded evaluation

The initial-suite limitations above describe historical measurements. Named workload
selection, extended tasks, optional browser/live-source workflows, conservative comparison
gating and explicit uncertainty/efficiency calculations are documented in
[SUITES.md](SUITES.md). Expanded workload support is not an empirical capability ranking.
