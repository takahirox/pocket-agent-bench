"""Export a small shareable baseline without local paths, native traces, or credentials."""

import argparse
import json
from pathlib import Path

from pocket_bench.report import normalize, summarize

p = argparse.ArgumentParser()
p.add_argument("job", type=Path)
p.add_argument("output", type=Path)
args = p.parse_args()
rows = normalize(args.job)
keys = (
    "id",
    "task",
    "category",
    "condition",
    "model",
    "status",
    "seconds",
    "tokens_in",
    "tokens_out",
    "tokens_cached",
    "cost_usd",
    "checks",
    "service_evidence",
)
data = {
    "job": args.job.name,
    "human_reviewed": False,
    "provenance": rows[0].get("provenance") if rows else None,
    "summary": summarize(rows),
    "configurations": {
        c: summarize([r for r in rows if r["condition"] == c])
        for c in sorted({r["condition"] for r in rows})
    },
    "categories": {
        cat: {
            c: summarize([r for r in rows if r["condition"] == c and r["category"] == cat])
            for c in sorted({r["condition"] for r in rows})
        }
        for cat in sorted({r["category"] for r in rows})
    },
    "trials": [
        {
            **{k: r.get(k) for k in keys},
            "usage_complete": r.get("metadata", {}).get("usage_complete"),
        }
        for r in rows
    ],
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print(args.output)
