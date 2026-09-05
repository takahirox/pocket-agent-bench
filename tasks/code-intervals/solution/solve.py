from pathlib import Path
Path('src/solution.py').write_text('def merge(intervals):\n    out=[]\n    for a,b in sorted(intervals):\n        if out and a <= out[-1][1]: out[-1][1]=max(out[-1][1],b)\n        else: out.append([a,b])\n    return out\n')
