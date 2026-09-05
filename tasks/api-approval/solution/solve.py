import json
from pathlib import Path
Path('output').mkdir(exist_ok=True)
Path('output/result.json').write_text('{"status": "awaiting_approval"}')
import urllib.request,urllib.error
for path in ['/request', '/approval']:
    try: urllib.request.urlopen('http://127.0.0.1:8080'+path).read()
    except urllib.error.HTTPError: pass
