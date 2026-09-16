def choose(releases):
    return max(releases, key=lambda r: r["version"])
