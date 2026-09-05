import json
from pathlib import Path
Path('output').mkdir(exist_ok=True)
Path('output/result.json').write_text('["A", "B", "C", "D"]')
