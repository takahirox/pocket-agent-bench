from pathlib import Path
Path('src/solution.py').write_text("import re\ndef slug(text):\n    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n")
