import json, urllib.request, urllib.error
from pathlib import Path
Path('output').mkdir(exist_ok=True)
base = 'http://127.0.0.1:8080'
def get(path):
    return json.loads(urllib.request.urlopen(base + path, timeout=30).read())
jobs = get('/workflow')['jobs']
committed = []
total = 0
for job in jobs:
    if not job['approved']:
        continue
    payload = json.dumps({'id': job['id'], 'key': job['id'], 'amount': job['amount']}).encode()
    for attempt in range(3):
        try:
            urllib.request.urlopen(urllib.request.Request(base + '/commit', data=payload,
                headers={'Content-Type': 'application/json'}), timeout=10).read()
            break
        except urllib.error.HTTPError as error:
            if error.code != 503:
                raise
    committed.append(job['id'])
    total += job['amount']
Path('output/result.json').write_text(json.dumps({'committed': committed, 'total': total}))
