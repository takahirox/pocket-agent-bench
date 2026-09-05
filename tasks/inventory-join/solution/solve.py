import json
from pathlib import Path
Path('output').mkdir(exist_ok=True)
Path('output/result.json').write_text('{"A": 3, "B": 2, "C": 0}')
