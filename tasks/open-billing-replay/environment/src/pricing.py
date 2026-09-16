def price(invoice):
    return {l['id']: round(l['unit']*l['quantity']*l['active']/l['period']*(1+l['tax_bps']/10000)) for l in invoice['lines']}
