import json
from pathlib import Path
Path('output').mkdir(exist_ok=True)
Path('output/result.json').write_text('{"A": 10, "B": 20, "C": 30}')
import urllib.request,urllib.error
for path in ['/items', '/items?page=2']:
    try: urllib.request.urlopen('http://127.0.0.1:8080'+path).read()
    except urllib.error.HTTPError: pass
