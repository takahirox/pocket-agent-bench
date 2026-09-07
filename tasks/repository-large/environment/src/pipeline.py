from revisions import latest
from totals import totals

def aggregate(records):
    return totals(latest(records))
