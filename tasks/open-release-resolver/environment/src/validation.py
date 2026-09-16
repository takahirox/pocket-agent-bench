def acceptable(selected, request):
    for r in selected.values():
        for dep, bounds in r.get('requires', {}).items():
            if not bounds[0] <= selected[dep]['version'] <= bounds[1]:
                return False
    return True
