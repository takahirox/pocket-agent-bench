from pathlib import Path
Path('src/solution.py').write_text('from pipeline import aggregate\n\ndef reconcile(records):\n    return aggregate(records)\n')
Path('src/pipeline.py').write_text('from revisions import latest\nfrom totals import totals\n\ndef aggregate(records):\n    return totals(latest(records))\n')
Path('src/revisions.py').write_text("def latest(records):\n    chosen = {}\n    for r in records:\n        if r['id'] not in chosen or r['version'] > chosen[r['id']]['version']:\n            chosen[r['id']] = dict(r)\n    return [chosen[k] for k in sorted(chosen)]\n")
Path('src/totals.py').write_text("def totals(records):\n    result = {}\n    for r in records:\n        if r['status'] != 'canceled':\n            result[r['region']] = result.get(r['region'], 0) + r['cents']\n    return dict(sorted(result.items()))\n")
