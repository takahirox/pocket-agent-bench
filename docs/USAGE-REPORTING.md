# CLI usage completeness

A JSONL usage event selected by a profile's `usage_jsonl` mapping may include
`"complete": false`. The adapter retains any reported numeric subtotals but marks
the trial usage incomplete, including when the controller returns exit code zero
to allow grading after an internal worker interruption. A later complete event
cannot clear this flag. Omitted `complete` preserves existing event behavior.

A controller may emit an event with empty usage fields solely to report
completeness. Timeouts and nonzero controller exits always remain incomplete.
Completeness metadata does not establish a benchmark grade.
