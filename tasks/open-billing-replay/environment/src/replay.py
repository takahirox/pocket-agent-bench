def visible(request):
    chosen = {}
    for e in request['events']:
        if e['at'] <= request['as_of'] and not e.get('deleted'):
            if e['id'] not in chosen or e['revision'] > chosen[e['id']]['revision']:
                chosen[e['id']] = e
    return sorted(chosen.values(), key=lambda e: e['at'])
