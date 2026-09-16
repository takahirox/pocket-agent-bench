"""Fixed open-path repair snapshots. Private exhaustive oracles never enter /app."""

import json
import random


def encode(value):
    return json.dumps(value, indent=2) + "\n"


def task(name, files, cases, solution):
    return {
        "id": name,
        "category": "coding",
        "difficulty": "open-path",
        "decomposition": "mixed",
        "tags": ["open-path", "diagnosis", "integration"],
        "difficulty_basis": "Requires empirical calibration; no multi-agent advantage claimed.",
        "instruction": "Resolve the customer incident in input/incident.md. The checked-in "
        "repository and product records describe the supported behavior. Deliver repaired "
        "sources implementing src/solution.py:solve(request), with src on the import path. "
        "Preserve every input file and do not mutate request arguments. All documented "
        "behavior, not just the reported reproduction, must work. Any implementation "
        "strategy or source-file organization is acceptable. Python standard library only.",
        "files": files,
        "function": "solve",
        "module_imports": True,
        "cases": cases,
        "solution": solution,
        "expected": {},
    }


RESOLVER_REFERENCE = """import itertools

def solve(request):
    names = sorted(request['catalog'])
    options = [[None] + list(request['catalog'][n]) for n in names]
    valid = []
    for values in itertools.product(*options):
        chosen = dict(zip(names, values))
        if any(chosen.get(n) is None or chosen[n]['version'] < minimum for n, minimum in request['roots'].items()):
            continue
        if any(chosen.get(n) is None or chosen[n]['version'] != v for n, v in request.get('pins', {}).items()):
            continue
        if any(r is not None and r.get('yanked', False) for r in values):
            continue
        reachable = set(request['roots'])
        pending = list(reachable)
        good = True
        while pending:
            n = pending.pop()
            r = chosen.get(n)
            if r is None:
                good = False; break
            for dep, interval in r.get('requires', {}).items():
                other = chosen.get(dep)
                if other is None or not interval[0] <= other['version'] <= interval[1]:
                    good = False; break
                if dep not in reachable:
                    reachable.add(dep); pending.append(dep)
            if not good: break
        if not good or reachable != {n for n, r in chosen.items() if r is not None}:
            continue
        if any(chosen.get(other) is not None and lo <= chosen[other]['version'] <= hi
               for r in values if r is not None for other, (lo, hi) in r.get('conflicts', {}).items()):
            continue
        versions = {n: chosen[n]['version'] for n in sorted(reachable)}
        changed = sum(request.get('installed', {}).get(n) != v for n, v in versions.items())
        score = (changed, len(versions), tuple(-versions.get(n, 0) for n in names))
        valid.append((score, versions))
    if not valid: return {'error': 'unsatisfiable'}
    return {'selected': min(valid, key=lambda pair: pair[0])[1]}
"""


def resolver_gold(req):
    """Independent dependency-driven search, unlike exhaustive reference product."""
    answers = []

    def walk(chosen, needed):
        todo = sorted(needed - chosen.keys())
        if todo:
            n = todo[0]
            for r in req["catalog"].get(n, []):
                if not r.get("yanked", False):
                    walk({**chosen, n: r}, needed | r.get("requires", {}).keys())
            return
        for n, r in chosen.items():
            if r["version"] < req["roots"].get(n, 0):
                return
            if n in req.get("pins", {}) and r["version"] != req["pins"][n]:
                return
            for dep, (lo, hi) in r.get("requires", {}).items():
                if not lo <= chosen[dep]["version"] <= hi:
                    return
            for dep, (lo, hi) in r.get("conflicts", {}).items():
                if dep in chosen and lo <= chosen[dep]["version"] <= hi:
                    return
        if not req.get("pins", {}).keys() <= chosen.keys():
            return
        answers.append({n: r["version"] for n, r in sorted(chosen.items())})

    walk({}, set(req["roots"]))
    if not answers:
        return {"error": "unsatisfiable"}

    def cost(v):
        return (
            sum(req.get("installed", {}).get(n) != x for n, x in v.items()),
            len(v),
            tuple(-v.get(n, 0) for n in sorted(req["catalog"])),
        )

    return {"selected": min(answers, key=cost)}


def resolver():
    catalog = {
        "app": [
            {"version": 1, "requires": {"core": [1, 2]}},
            {"version": 2, "requires": {"core": [2, 3]}},
        ],
        "core": [
            {"version": 1},
            {"version": 2, "conflicts": {"addon": [1, 1]}},
            {"version": 3, "requires": {"app": [2, 2]}},
        ],
        "addon": [{"version": 1, "requires": {"core": [1, 2]}}],
    }
    example = {
        "catalog": catalog,
        "roots": {"app": 1, "addon": 1},
        "installed": {"app": 2, "core": 3},
    }
    requests = [example, {"catalog": {}, "roots": {}}]
    rng = random.Random(12001)
    for i in range(34):
        names = ["amber", "birch", "cedar", "dune"]
        cat = {}
        for n in names:
            records = []
            for v in range(1, 4):
                dep = rng.choice(names)
                conflict = rng.choice(names)
                records.append(
                    {
                        "version": v,
                        "requires": {dep: [rng.randint(1, 2), 3]} if rng.random() < 0.65 else {},
                        "conflicts": {conflict: [2, 2]} if rng.random() < 0.25 else {},
                        "yanked": rng.random() < 0.12,
                    }
                )
            rng.shuffle(records)
            cat[n] = records
        requests.append(
            {
                "catalog": cat,
                "roots": {names[i % 4]: i % 2 + 1},
                "installed": {n: rng.randint(1, 3) for n in names[: i % 5]},
                "pins": {names[-1]: 2} if i % 6 == 0 else {},
            }
        )
    files = {
        "input/incident.md": "Deployment INC-412: a valid release is rejected after adding an extension. "
        "Other customers report unnecessary upgrades and a hang on mutually dependent packages. "
        "Restore the resolver without regressing the published selection policy. Reproduction: repro.json.\n",
        "input/repro.json": encode(example),
        "input/api.md": "solve receives {catalog, roots, installed?, pins?}. Catalog maps package names "
        "to release records with unique positive integer version, optional requires and conflicts "
        "(dependency name to inclusive [minimum,maximum]), and optional yanked boolean. "
        "Roots map names to minimum versions. All dependency names occur in catalog. "
        'Return {selected: {name:version}} or {error:"unsatisfiable"}. Empty roots are valid.\n',
        "input/policy.md": "Select exactly the transitive closure of roots under the selected releases. "
        "A package has one version. Every requirement must hold, every conflict must be absent, "
        "and yanked releases are unavailable even if installed. Cycles are valid when constraints "
        "are jointly satisfiable. Pins require the named package to be in the closure at exactly "
        "the pinned version; they do not add roots. No valid closure means unsatisfiable.\n",
        "input/decisions/017.md": "Approved selection policy: first minimize selected packages whose "
        "version differs from installed (newly installed packages count as changes; removals do not). "
        "Then minimize closure size. Finally maximize the version vector over all catalog names "
        "in alphabetical order, assigning zero to absent packages. Input ordering never breaks ties.\n",
        "input/history.md": "Superseded prototype preferred newest releases greedily. Do not use "
        "that policy for production; decision 017 replaced it.\n",
        "src/solution.py": "from resolver import resolve\ndef solve(request):\n    return resolve(request)\n",
        "src/resolver.py": """from selection import choose
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
""",
        "src/selection.py": 'def choose(releases):\n    return max(releases, key=lambda r: r["version"])\n',
        "src/validation.py": """def acceptable(selected, request):
    for r in selected.values():
        for dep, bounds in r.get('requires', {}).items():
            if not bounds[0] <= selected[dep]['version'] <= bounds[1]:
                return False
    return True
""",
    }
    return task(
        "open-release-resolver",
        files,
        [[r, resolver_gold(r)] for r in requests],
        RESOLVER_REFERENCE,
    )


BILLING_REFERENCE = """from fractions import Fraction

def solve(request):
    seen = {}
    for e in request['events']:
        key = (e['tenant'], e['id'])
        if key not in seen or e['revision'] > seen[key]['revision']:
            seen[key] = e
    amounts = {}
    invoices = {}
    for e in sorted(seen.values(), key=lambda e: (e['at'], e['tenant'], e['id'])):
        if e.get('deleted', False) or e['at'] > request['as_of']:
            continue
        tenant = e['tenant']
        amounts.setdefault(tenant, 0)
        if e['kind'] == 'invoice':
            lines = sorted(e['lines'], key=lambda l: l['id'])
            raw = [Fraction(l['unit'] * l['quantity'] * l['active'], l['period']) for l in lines]
            floors = [int(x) for x in raw]
            total = sum(raw)
            target = (2 * total.numerator + total.denominator) // (2 * total.denominator)
            order = sorted(range(len(lines)), key=lambda i: (-(raw[i]-floors[i]), lines[i]['id']))
            for i in order[:target-sum(floors)]: floors[i] += 1
            discount = min(e.get('discount', 0), sum(floors))
            cuts = [0] * len(lines)
            if sum(floors):
                shares = [Fraction(discount * x, sum(floors)) for x in floors]
                cuts = [int(x) for x in shares]
                order = sorted(range(len(lines)), key=lambda i: (-(shares[i]-cuts[i]), lines[i]['id']))
                for i in order[:discount-sum(cuts)]: cuts[i] += 1
            charged = {}
            for i, line in enumerate(lines):
                net = floors[i] - cuts[i]
                tax = (net * line['tax_bps'] * 2 + 10000) // 20000
                charged[line['id']] = net + tax
            invoices[(tenant, e['id'])] = {'charged': charged, 'refunded': set()}
            amounts[tenant] += sum(charged.values())
        else:
            invoice = invoices.get((tenant, e['invoice']))
            if invoice:
                for line in set(e['line_ids']):
                    if line in invoice['charged'] and line not in invoice['refunded']:
                        amounts[tenant] -= invoice['charged'][line]
                        invoice['refunded'].add(line)
    return dict(sorted(amounts.items()))
"""


def billing_gold(req):
    """Decimal-independent rational specification, using remainder cross-products."""
    from fractions import Fraction

    def allocate(values, target):
        result = [v.numerator // v.denominator for v in values]
        ranks = sorted(range(len(values)), key=lambda i: (result[i] - values[i], i))
        for i in ranks[: target - sum(result)]:
            result[i] += 1
        return result

    winners = [
        e
        for e in req["events"]
        if not any(
            x["tenant"] == e["tenant"] and x["id"] == e["id"] and x["revision"] > e["revision"]
            for x in req["events"]
        )
    ]
    unique = {(e["tenant"], e["id"]): e for e in winners}
    chronological = sorted(unique.values(), key=lambda e: (e["at"], e["tenant"], e["id"]))
    balances, credits = {}, {}
    for e in chronological:
        if e.get("deleted") or e["at"] > req["as_of"]:
            continue
        t = e["tenant"]
        balances.setdefault(t, 0)
        if e["kind"] == "invoice":
            ls = sorted(e["lines"], key=lambda l: l["id"])
            values = [Fraction(l["unit"] * l["quantity"] * l["active"], l["period"]) for l in ls]
            total = sum(values, Fraction(0))
            rounded = (total + Fraction(1, 2)).numerator // (total + Fraction(1, 2)).denominator
            gross = allocate(values, rounded)
            discount = min(e.get("discount", 0), rounded)
            cuts = (
                allocate([Fraction(discount * g, rounded) for g in gross], discount)
                if rounded
                else [0] * len(ls)
            )
            for l, g, d in zip(ls, gross, cuts):
                tax = Fraction((g - d) * l["tax_bps"], 10000) + Fraction(1, 2)
                charge = g - d + tax.numerator // tax.denominator
                credits[t, e["id"], l["id"]] = charge
                balances[t] += charge
        else:
            for key in {(t, e["invoice"], line) for line in e["line_ids"]}:
                balances[t] -= credits.pop(key, 0)
    return dict(sorted(balances.items()))


def billing():
    rng = random.Random(12002)
    requests = []
    for i in range(36):
        events = []
        for tenant in ["north", "south"]:
            for j in range(3):
                inv = {
                    "tenant": tenant,
                    "id": f"i{j}",
                    "revision": 1,
                    "at": j * 10,
                    "kind": "invoice",
                    "discount": rng.randint(0, 130),
                    "lines": [
                        {
                            "id": f"l{k}",
                            "unit": rng.randint(0, 300),
                            "quantity": rng.randint(1, 3),
                            "active": rng.randint(0, 29),
                            "period": 30,
                            "tax_bps": rng.choice([0, 500, 825]),
                        }
                        for k in range(4)
                    ],
                }
                events.append(inv)
                corrected = json.loads(encode(inv))
                corrected["revision"] = 2
                corrected["lines"][0]["unit"] += 11
                corrected["deleted"] = (i + j) % 7 == 0
                corrected["at"] += 4 if i % 3 else 50
                events.extend([corrected, corrected.copy()])
                for k in range(2):
                    events.append(
                        {
                            "tenant": tenant,
                            "id": f"r{j}-{k}",
                            "revision": 1,
                            "at": j * 10 + 6 + k,
                            "kind": "refund",
                            "invoice": f"i{j}",
                            "line_ids": ["l0", "l0", "l2", "missing"],
                        }
                    )
        rng.shuffle(events)
        requests.append({"events": events, "as_of": [15, 40, 100][i % 3]})
    requests.extend(
        [
            {"events": [], "as_of": 0},
            {
                "events": [
                    {
                        "tenant": "n",
                        "id": "empty",
                        "revision": 1,
                        "at": 0,
                        "kind": "invoice",
                        "lines": [],
                        "discount": 99,
                    }
                ],
                "as_of": 0,
            },
        ]
    )
    files = {
        "input/incident.md": "FIN-209: after replaying corrected invoices, balances differ across tenants "
        "and partial refunds sometimes over-credit. Repair the billing projection against the "
        "approved accounting records. The attached reproduction is only one affected batch.\n",
        "input/repro.json": encode(requests[0]),
        "input/api.md": "solve({events, as_of}) returns {tenant: integer_balance}. Do not mutate arguments. "
        "Events have tenant, id, positive revision, integer at, kind (invoice/refund), optional deleted. "
        "Copies with the same tenant/id/revision are identical. Invoice lines have unique id, nonnegative "
        "integer unit cents, quantity, active and positive period; 0 <= active <= period. tax_bps is "
        "nonnegative integer basis points; invoice discount is optional nonnegative integer cents. "
        "Refunds have invoice (id) and line_ids (possibly duplicated or unknown). Empty lines are valid.\n",
        "input/storage/replay.md": "Revision winner is selected by (tenant,id) over the entire input, "
        "BEFORE filtering deleted or at > as_of. Never fall back to an older revision. Replay winners "
        "in ascending (at,tenant,id) order. Include a zero balance for every tenant with a surviving "
        "event, even an ineffective refund; exclude tenants with none. Inputs can be shuffled.\n",
        "input/accounting/proration.md": "Approved: unit*quantity*active/period uses exact rational cents. "
        "Round the SUM of invoice line amounts half up. Allocate its cents to lines: floor each exact "
        "amount, distribute remaining cents by descending fractional remainder, ties by line id ascending. "
        "Do not round each line independently.\n",
        "input/accounting/discount.md": "Cap invoice discount at the allocated invoice gross. Allocate "
        "discount proportionally to the integer gross line amounts, using floors then largest fractional "
        "remainders (line id ascending ties). Zero gross receives zero discount.\n",
        "input/accounting/tax.md": "Each line tax is half-up-rounded (gross minus allocated discount) "
        "* tax_bps / 10000. Charge = net + tax. All rounding is exact, no binary floating point.\n",
        "input/support/refunds.md": "A refund reverses the original charged cents including tax for each "
        "named line at most once across all refunds of an invoice. Unknown invoice/line has no effect. "
        "Only an invoice already replayed for the SAME tenant is eligible. Refunds before an invoice "
        "are not deferred. Do not recalculate tax or redistribute discounts when refunding.\n",
        "input/history.md": "Retired 2024 implementation rounded each line and used global event IDs. "
        "Accounting and storage records supersede this historical behavior.\n",
        "src/solution.py": "from projection import project\ndef solve(request):\n    return project(request)\n",
        "src/replay.py": """def visible(request):
    chosen = {}
    for e in request['events']:
        if e['at'] <= request['as_of'] and not e.get('deleted'):
            if e['id'] not in chosen or e['revision'] > chosen[e['id']]['revision']:
                chosen[e['id']] = e
    return sorted(chosen.values(), key=lambda e: e['at'])
""",
        "src/pricing.py": """def price(invoice):
    return {l['id']: round(l['unit']*l['quantity']*l['active']/l['period']*(1+l['tax_bps']/10000)) for l in invoice['lines']}
""",
        "src/projection.py": """from replay import visible
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
""",
    }
    return task(
        "open-billing-replay", files, [[r, billing_gold(r)] for r in requests], BILLING_REFERENCE
    )


def catalog():
    return [resolver(), billing()]
