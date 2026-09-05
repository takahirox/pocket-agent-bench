import json
from pathlib import Path
Path('output').mkdir(exist_ok=True)
Path('output/result.json').write_text('{"launch_date": "2026-04-09", "owner": "Mira", "budget": null}')
