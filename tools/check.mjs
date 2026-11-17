// Сверка расчётного модуля страницы с эталоном основного проекта.
import fs from "node:fs";
const html = fs.readFileSync("/home/claude/site/index.html", "utf8");
const code = /<script id="calc">([\s\S]*?)<\/script>/.exec(html)[1];
const Calc = new Function(code + "; return Calc;")();
const site = "/home/claude/site/data/";
const rates = JSON.parse(fs.readFileSync(site + "rates.json"));
const cases = JSON.parse(fs.readFileSync("/home/claude/build/cases.json"));
const SH = { "1": [1n, 1n], "0.5": [1n, 2n], "0.3333333333": [3333333333n, 10000000000n], "0.25": [1n, 4n] };
const cache = {};
let bad = 0, checks = 0;
const eq = (label, c, got, want) => { checks++; if (String(got) !== String(want)) { if (bad++ < 12) console.log("РАСХОЖДЕНИЕ", label, c.d, c.q, c.o, JSON.stringify(c.opt), "получено", String(got), "ожидалось", String(want)); } };
for (const c of cases) {
  cache[c.d] ??= JSON.parse(fs.readFileSync(site + c.d + ".json"));
  const p = Calc.findParcel(cache[c.d], c.q, c.o);
  if (!p) { bad++; console.log("не найден", c.d, c.q, c.o); continue; }
  const [shareNum, shareDen] = SH[c.opt.share];
  const common = { areaC: p.areaC, shareNum, shareDen, months: c.opt.months, deduction: c.opt.deduction };
  const rNow = Calc.rateFor(rates, c.d, p.group, 2020, c.opt.group).rateE4;
  const rNext = Calc.rateFor(rates, c.d, p.group, 2023, c.opt.group).rateE4;
  const now = p.oldKop > 0n ? Calc.calculate({ ...common, valueKop: p.oldKop, rateE4: rNow, prevTax: null }) : null;
  const nextIn = { ...common, valueKop: p.newKop, rateE4: rNext };
  const next = Calc.calculate({ ...nextIn, prevTax: now ? now.payable : null });
  const e = c.exp;
  eq("now", c, now ? now.payable : null, e.now);
  eq("next", c, next.payable, e.next); eq("full", c, next.taxFull, e.full);
  eq("limited", c, next.limited, e.limited); eq("base", c, next.base, e.base); eq("ded", c, next.deduction, e.ded);
  if (e.traj) {
    const t = Calc.project(now.payable, next.taxFull, 2023);
    eq("traj", c, JSON.stringify(t.map(x => [String(x.payable), x.limited])), JSON.stringify(e.traj));
  }
  if (e.pct !== undefined) {
    const diff = next.payable - now.payable, abs = diff < 0n ? -diff : diff;
    const t = Calc.divHalfEven(abs * 1000n, now.payable);
    const s = (diff < 0n && t > 0n ? "-" : "") + (t / 10n) + "." + (t % 10n);
    eq("pct", c, s, e.pct === "-0.0" ? "0.0" : e.pct);
  }
  if (e.appeal) {
    const a = Calc.estimateAppeal(nextIn, BigInt(e.appeal.market), BigInt(c.opt.report) * 100n);
    eq("annual", c, a.annual, e.appeal.annual); eq("total", c, a.total, e.appeal.total);
    eq("net", c, a.netKop, e.appeal.net); eq("worth", c, a.worthwhile, e.appeal.worth);
    eq("payback", c, a.paybackTenths === null ? null : (a.paybackTenths / 10n) + "." + (a.paybackTenths % 10n), e.appeal.payback);
  }
}
// разбор номеров
const nums = [["64:32:024013:790", "64:32:24013:790"], ["64;32;24013;790", "64:32:24013:790"], [" '64:32:0024013:0790 ", "64:32:24013:790"], ["64:32:24013", null], ["abc", null], ["64-32-24013-790", "64:32:24013:790"]];
for (const [raw, want] of nums) { checks++; const g = Calc.parseNumber(raw); if ((g.canonical || null) !== want) { bad++; console.log("номер", raw, g); } }
console.log(`случаев ${cases.length}, сверок ${checks}, расхождений ${bad}`);
process.exit(bad ? 1 : 0);
