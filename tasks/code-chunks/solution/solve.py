from pathlib import Path
Path('src/solution.py').write_text("def chunks(items, size):\n    if size <= 0: raise ValueError('size')\n    return [items[i:i+size] for i in range(0, len(items), size)]\n")
