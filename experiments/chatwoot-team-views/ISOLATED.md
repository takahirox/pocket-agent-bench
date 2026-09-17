# Immutable submission and isolated qualification

**Historical partial runner.** The current integrated pipeline is `task.py`;
see [README.md](README.md) and the [execution guide](../../docs/ENGINEERING.md).
The unscored evidence below remains a record of the earlier isolated experiment.

This adds an executable **qualification path**, not a final scored benchmark.
It exercises submission transfer, a populated upgrade, black-box API checks,
restart and optional mapped browser workflows. All reports remain `unscored`.

## Submit source

From the PocketAgentBench root:

```sh
python3 experiments/chatwoot-team-views/artifact.py /path/to/candidate local/candidate.zip
```

The collector includes current contents of Git-tracked files, including staged
new files and working-tree edits/deletions. **Add new source files to Git before
collection** (`git add -N path` is sufficient). Untracked files are deliberately
excluded; check the manifest's file list before submitting. No commit is required.
The collector does not copy the Git repository, untracked credentials, dependency
directories, application logs or generated builds. Checked-in `.env.example`
and upstream `log/.keep` / `tmp/.keep` placeholders are allowed. Do not stage
secrets in any source file; this is not a general-purpose secret scanner.

The ZIP contains a versioned manifest with file sizes, modes and SHA-256 hashes.
The verifier rejects duplicate/unsafe paths, oversized entries, mismatched hashes,
unexpected contents and external/cyclic symlinks before Docker transfer. Internal
symlinks to included regular files are retained. The entire submission also has
a SHA-256 identity recorded in the run manifest; hashes detect changed bytes,
not authorship or correctness. No submitted archive is extracted on the host.

`--base` exports the pinned upstream commit for the missing-feature control.
Submission limits are 30,000 files, 96 MiB/file, 384 MiB total uncompressed; the
upstream source includes a 69 MB model fixture. These are packaging limits, not
task efficiency scores.

## Prepare and run

Use a fresh directory/project for each attempt. Required local images are the
dependency image from `README.md`, PostgreSQL, Redis and nginx. Preparation
resolves installed images to immutable IDs; it does not pull tags during a run.
The current dependency cache requires unchanged Gemfile/Gemfile.lock and
package.json/pnpm-lock.yaml. Changed dependencies are an unsupported preparation
case requiring a new image, **not an incorrect product implementation**.

```sh
python3 experiments/chatwoot-team-views/isolated.py prepare \
  --source /path/to/trusted/upstream-clone \
  --artifact local/candidate.zip \
  --destination local/isolated-example --project pocket-tv-isolated-example \
  --port 33085 --vite-port 33341

NODE_PATH="$PWD/local/team-views-browser-tools/node_modules" \
python3 experiments/chatwoot-team-views/isolated.py run local/isolated-example \
  --ui-map /path/to/submitted-ui-map.json --browser /path/to/chromium
```

Omitting browser arguments runs the API/upgrade/restart path only. The public
[UI protocol](../../docs/task-proposals/chatwoot-team-views/ui-evaluation.md)
describes the declarative locator map. The runner copies and hashes that map
before execution. Playwright remains pinned to 1.56.1; the local browser version
is recorded, but its executable is not yet packaged/pinned for scored trials.

## Isolation and result interpretation

- Baseline and candidate source occupy **different named Docker volumes**. Only
  the pinned baseline receives/runs the trusted synthetic fixture initializer.
  The candidate receives no fixture script, reference patch, grading code, Git
  history, agent credential files, Docker socket or host directory mount.
- The candidate runs as uid/gid 1000 with all capabilities dropped and
  `no-new-privileges`, on an internal network. Only the trusted proxy publishes
  loopback ports. Its app container's actual mount/user/network configuration is
  inspected and reported. The app has its disposable DB credentials and its own
  random Rails secret; it has no external service credentials.
- Vite's disposable dependency volume is assigned to uid 1000 **before candidate
  source transfer** using a fixed image command. Candidate migrations/builds do
  not run as root. The candidate may write its own disposable source/runtime
  volumes; it cannot modify the host copy of the submitted artifact or reports.
- API expectations and legacy-record snapshots remain in the host verifier.
  App code is never imported into the host Python/Node verifier process. The UI
  map supplies locator data, not executable browser-driver code.
- Stage reports distinguish assertion failures (`fail`), process/environment
  errors (`error`) and elapsed-time stops (`timeout`). In particular, an arbitrary
  migration crash is reported for diagnosis instead of automatically labeled an
  assertion failure. Timeouts do not award or deny a final correctness score.
- Attempts cannot be rerun/reset implicitly. After a run, all running containers
  belonging to that unique project are stopped, including one-off commands left
  after a CLI timeout. Volumes and logs remain for diagnosis. No unrelated project
  is stopped or deleted.

This is a local Docker execution boundary, not a claim of protection against
container/browser engine exploits. The current browser is a disposable host
Chrome profile with application requests restricted to this attempt's local
ports; a packaged verifier/browser environment is still required for final runs.
Assertions execute outside the candidate, but malicious benchmark-specific
behavior still requires review; passing finite tests never proves all behavior.

The next integration work is the remaining R1–R8 coverage, existing regression
suites/build/lint, pinned browser packaging, and valid/invalid controls through
the complete runner. In-process RSpec qualification from `REFERENCE.md` is not
silently counted as isolated black-box verification.
