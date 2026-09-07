import json, urllib.request, urllib.error
from pathlib import Path
Path('output').mkdir(exist_ok=True)
base = 'http://127.0.0.1:8080'
def get(path):
    return json.loads(urllib.request.urlopen(base + path, timeout=30).read())
import subprocess, re, html
page = subprocess.check_output(['chromium', '--headless', '--no-sandbox', '--disable-gpu',
    '--virtual-time-budget=3000', '--dump-dom', base + '/release'], text=True, timeout=30)
match = re.search(r'<pre id="result">(.*?)</pre>', page, re.S)
result = json.loads(html.unescape(match.group(1)))
Path('output/result.json').write_text(json.dumps(result))
