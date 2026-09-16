from selection import choose
from validation import acceptable

def resolve(request):
    selected = {}
    pending = list(request['roots'])
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        release = choose(request['catalog'][name])
        selected[name] = release
        pending.extend(release.get('requires', {}))
    if not acceptable(selected, request):
        return {'error': 'unsatisfiable'}
    return {'selected': {n: r['version'] for n, r in selected.items()}}
