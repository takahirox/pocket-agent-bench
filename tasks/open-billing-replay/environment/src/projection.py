from replay import visible
from pricing import price

def project(request):
    balances, invoices = {}, {}
    for e in visible(request):
        t=e['tenant']; balances.setdefault(t, 0)
        if e['kind']=='invoice':
            charges=price(e); invoices[e['id']]=charges
            balances[t]+=sum(charges.values())
        else:
            balances[t]-=sum(invoices.get(e['invoice'], {}).get(l,0) for l in e['line_ids'])
    return balances
