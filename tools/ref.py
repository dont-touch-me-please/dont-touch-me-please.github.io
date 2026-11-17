"""Эталон: расчёт модулем taxes.py основного проекта для случайной выборки участков."""
import json, random, sys
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, "/home/claude/gko")
from valuation.taxes import TaxInput, calculate, project, estimate_appeal, RATE_CEILING

random.seed(20261116)
site = Path("/home/claude/site/data")
rates = json.load(open(site / "rates.json"))
GROUPS = ["residential", "garden", "agricultural", "preferential", "general"]
cases = []
for d in json.load(open(site / "meta.json"))["districts"]:
    data = json.load(open(site / f"{d}.json"))
    flat = [(q, r) for q, rows in data.items() for r in rows]
    for q, r in random.sample(flat, min(len(flat), 120)):
        o, new, old, area, seg, g = r
        if not new:
            continue
        opt = dict(
            group=random.choice(["", "", "", "residential", "garden", "agricultural", "general"]),
            share=random.choice(["1", "1", "0.5", "0.3333333333", "0.25"]),
            months=random.choice([12, 12, 12, 7, 1]),
            deduction=random.random() < 0.3,
            market=random.choice([0, 0.5, 0.8, 1.2]),
            report=random.choice([15000, 20000, 30000]),
        )
        def rate(year):
            group = opt["group"] or (GROUPS[g] if g < 5 else None)
            if group is None:
                return Decimal("1.5")
            found = rates["districts"].get(str(d), {}).get("r", {}).get(str(year), {}).get(group)
            return Decimal(found[0]) if found else RATE_CEILING[group]
        kw = dict(area=Decimal(area) / 100 if area else None, ownership_share=Decimal(opt["share"]),
                  months_owned=opt["months"], apply_deduction=opt["deduction"])
        newv, oldv = Decimal(new) / 100, Decimal(old) / 100
        now = calculate(TaxInput(cadastral_value=oldv, rate_percent=rate(2020), **kw)) if old else None
        nxt = calculate(TaxInput(cadastral_value=newv, rate_percent=rate(2023),
                                 previous_year_tax=now.tax_payable if now else None, **kw))
        exp = dict(now=str(now.tax_payable) if now else None, next=str(nxt.tax_payable),
                   full=str(nxt.tax_full), limited=nxt.growth_limited,
                   base=str(int(nxt.tax_base * 100)), ded=str(int(nxt.deduction * 100)))
        if now:
            exp["traj"] = [[str(p.tax_payable), p.growth_limited]
                           for p in project(now.tax_payable, nxt.tax_full, 2023)]
            if now.tax_payable > 0:
                exp["pct"] = str(((nxt.tax_payable - now.tax_payable) / now.tax_payable * 100)
                                 .quantize(Decimal("0.1")))
        if opt["market"]:
            mk = (newv * Decimal(str(opt["market"]))).quantize(Decimal("0.01"))
            a = estimate_appeal(newv, mk, rate(2023), Decimal(opt["report"]), 4, **kw)
            exp["appeal"] = dict(market=str(int(mk * 100)), annual=str(a.annual_saving),
                                 total=str(a.total_saving), net=str(int(a.net_benefit * 100)),
                                 payback=str(a.payback_years) if a.payback_years is not None else None,
                                 worth=a.worthwhile)
        cases.append(dict(d=d, q=q, o=o, opt=opt, exp=exp))
json.dump(cases, open("/home/claude/build/cases.json", "w"))
print("эталонных случаев:", len(cases))
