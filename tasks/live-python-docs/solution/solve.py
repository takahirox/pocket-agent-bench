import json, urllib.request, urllib.error
from pathlib import Path
Path('output').mkdir(exist_ok=True)
base = 'http://127.0.0.1:8080'
def get(path):
    return json.loads(urllib.request.urlopen(base + path, timeout=30).read())
snapshot = get('/live')
Path('output/result.json').write_text(json.dumps({k: snapshot[k] for k in ('url', 'title', 'sha256')}))
