# Review rubric (separate from automated correctness)

No LLM judge is required. A maintainer records each item as pass/fail/not reviewed,
with a concrete file or browser observation. Automated reward is reported
separately and must never be represented as a completed human review.

1. **Scope:** the diff implements R1–R8 without unrelated rewrites or changes to
   the supplied regression/evaluation configuration. No reference patch, private
   verifier files, agent credential files or runtime artifacts are submitted.
2. **Real workflows:** the locator map points to ordinary user-facing controls,
   uses the same management controls for all actors, and does not hide enabled
   controls with an actor-specific selector. No test-only page or special case
   for fixture users, names, counts, browser fingerprints or test runners exists.
3. **Test quality:** added tests exercise authorization, membership changes and
   populated migration, rather than merely asserting implementation details.
   `BENCHMARK_NOTES.md` accurately describes actual validation and limitations.
4. **Product integration:** layout fits the existing application, team identity
   is understandable, permitted teams are discoverable, localization uses the
   existing conventions, and failure/empty/success states are understandable.
5. **Accessibility:** new controls have meaningful accessible names, visible focus
   and a usable keyboard path. Automated activation of save/edit/delete does not
   replace inspecting the entire new workflow.
6. **Lifecycle and data:** inspect migration and deletion code for broad data loss,
   accidental visibility expansion, unsupported ownership reassignment and
   suspicious hardcoding that finite fixtures cannot rule out.

Visual preferences do not retroactively change the published functional contract.
If a protocol or environment defect is discovered, report the attempt as
inconclusive, fix/version the evaluator, and rerun affected comparisons. Do not
silently change requirements or credit a successful partial run as complete.
