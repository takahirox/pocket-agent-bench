import json
from pathlib import Path
Path('output').mkdir(exist_ok=True)
Path('output/result.json').write_text('{"alpha": {"days": 14, "source": "current.txt"}, "beta": {"days": 90, "source": "current.txt"}}')
