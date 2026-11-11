"""Builds site/index.html: one self-contained dashboard page for all three bots."""
import json
from datetime import datetime, timezone

from .config import SITE_DIR, STATE_DIR


def build_dashboard(markets):
    import os
    payload = {"demo": os.environ.get("BOT_SYNTHETIC") == "1", "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "markets": []}
    for key, cfg in markets.items():
        state = _read(STATE_DIR / f"{key}_state.json") or {}
        bt = _read(STATE_DIR / f"{key}_backtest.json")
        payload["markets"].append({
            "key": key, "name": cfg["name"], "currency": cfg["currency"],
            "benchmark": cfg["benchmark"], "start_cash": cfg["starting_cash"],
            "state": {k: state.get(k) for k in
                      ["cash", "positions", "history", "signals", "started", "last_prices", "weights_used"]},
            "trades": (state.get("trades") or [])[-25:][::-1],
            "backtest": bt,
        })
    SITE_DIR.mkdir(exist_ok=True)
    html = TEMPLATE.replace("__DATA__", json.dumps(payload).replace("</", "<\\/"))
    (SITE_DIR / "index.html").write_text(html)
    print(f"dashboard -> {SITE_DIR / 'index.html'}")


def _read(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trading Bots Dashboard</title>
<style>
.viz-root{color-scheme:light;--surface-0:#f4f4f2;--surface-1:#fcfcfb;--border:#e3e2dd;--grid:#ecebe7;
 --text-primary:#0b0b0b;--text-secondary:#52514e;--text-muted:#7a7974;
 --series-1:#2a78d6;--series-2:#eb6834;--good:#0ca30c;--critical:#d03b3b}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;
 --surface-0:#111110;--surface-1:#1a1a19;--border:#2e2e2c;--grid:#262624;--text-primary:#f0efec;
 --text-secondary:#c3c2b7;--text-muted:#8f8e86;--series-1:#3987e5;--series-2:#d95926}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-0:#111110;--surface-1:#1a1a19;--border:#2e2e2c;
 --grid:#262624;--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#8f8e86;--series-1:#3987e5;--series-2:#d95926}
*{box-sizing:border-box}
body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.viz-root{background:var(--surface-0);color:var(--text-primary);min-height:100vh;padding:24px}
.wrap{max-width:1100px;margin:0 auto}
header{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:16px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:0 0 12px}
.muted{color:var(--text-secondary)}.small{font-size:12px}
.tabs{display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap}
.tabs button{font:inherit;padding:7px 14px;border-radius:8px;border:1px solid var(--border);
 background:var(--surface-1);color:var(--text-primary);cursor:pointer}
.tabs button[aria-selected=true]{background:var(--text-primary);color:var(--surface-1);border-color:var(--text-primary)}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.tile .label{font-size:12px;color:var(--text-secondary)}.tile .val{font-size:24px;font-weight:600;margin-top:2px}
.tile .sub{font-size:12px;color:var(--text-secondary)}
.up{color:var(--good)}.down{color:var(--critical)}
.legend{display:flex;gap:16px;font-size:12px;color:var(--text-secondary);margin-bottom:6px}
.sw{display:inline-block;width:12px;height:3px;border-radius:2px;vertical-align:middle;margin-right:6px}
.chart{position:relative}.chart svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--surface-1);border:1px solid var(--border);
 border-radius:8px;padding:8px 10px;font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;white-space:nowrap}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-weight:500;color:var(--text-secondary);border-bottom:1px solid var(--border);padding:6px 8px}
td{padding:6px 8px;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums}
td.num,th.num{text-align:right}
.bar{display:inline-block;height:8px;border-radius:2px;vertical-align:middle}
.scroll{overflow-x:auto}
.empty{padding:28px;text-align:center;color:var(--text-secondary)}
.grid2{display:grid;grid-template-columns:2fr 1fr;gap:16px}@media(max-width:800px){.grid2{grid-template-columns:1fr}}
.note{font-size:12px;color:var(--text-muted);margin-top:8px}
</style></head>
<body><div class="viz-root"><div class="wrap">
<header><div><h1>Trading Bots</h1><div class="muted small">Paper trading only: simulated money, real prices</div></div>
<div class="muted small" id="gen"></div></header>
<div class="tabs" role="tablist" id="tabs"></div>
<div id="view"></div>
<p class="note">Signals: <b>Rules</b> = trend and momentum rules · <b>ML</b> = gradient-boosted model trained on past prices ·
<b>Claude</b> = news-headline sentiment. Backtests cover Rules + ML only, because there are no historical headlines to test the news signal on.
Past performance in a backtest doesn't predict future returns. This is not financial advice.</p>
</div></div>
<script>
const DATA = __DATA__;
const $ = (s, el=document) => el.querySelector(s);
const pct = (x, d=1) => x==null||isNaN(x) ? "–" : (x>=0?"+":"") + (x*100).toFixed(d) + "%";
const money = (x, c) => x==null ? "–" : new Intl.NumberFormat("en-AU",{style:"currency",currency:c,maximumFractionDigits:0}).format(x);
const cls = x => x>0 ? "up" : x<0 ? "down" : "";
const esc = s => String(s??"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
$("#gen").textContent = "Updated " + DATA.generated;
if (DATA.demo) $("header").insertAdjacentHTML("afterend", `<div class="card" style="border-color:var(--critical)"><b>Demo data.</b> These numbers come from made-up prices so the layout can be previewed. Real numbers appear once the bot runs in the cloud.</div>`);

const tabs = $("#tabs");
DATA.markets.forEach((m, i) => {
  const b = document.createElement("button");
  b.textContent = m.name; b.setAttribute("role","tab");
  b.onclick = () => show(i); tabs.appendChild(b);
});
show(0);

function show(i) {
  [...tabs.children].forEach((b,j) => b.setAttribute("aria-selected", i===j));
  const m = DATA.markets[i], st = m.state || {}, c = m.currency;
  const hist = st.history || [];
  const last = hist[hist.length-1], first = hist[0];
  const eq = last ? last.equity : m.start_cash;
  const ret = last ? eq / m.start_cash - 1 : null;
  const bret = (last && first) ? last.benchmark / first.benchmark - 1 : null;
  const pos = st.positions || {}, lp = st.last_prices || {};
  const bt = m.backtest;
  let h = `<div class="tiles">
    ${tile("Paper portfolio value", money(eq,c), st.started ? "since "+st.started : "not started yet")}
    ${tile("Bot return", `<span class="${cls(ret)}">${pct(ret)}</span>`, "live paper trading")}
    ${tile("Buy & hold "+esc(m.benchmark), `<span class="${cls(bret)}">${pct(bret)}</span>`, "same period")}
    ${tile("Holdings", Object.keys(pos).length, "cash " + money(st.cash ?? m.start_cash, c))}
  </div>`;
  h += `<div class="card"><h2>Live: bot vs buy & hold ${esc(m.benchmark)}</h2>`;
  if (hist.length >= 2) {
    const s = hist.map(p => ({d:p.date, a:p.equity, b:p.benchmark/first.benchmark*first.equity}));
    h += legend(m.benchmark) + `<div class="chart" id="live"></div>`;
    setTimeout(() => lineChart($("#live"), s, c), 0);
  } else h += `<div class="empty">The chart fills in as the bot runs. It needs at least two runs.</div>`;
  h += `</div><div class="grid2"><div class="card"><h2>Today's signals</h2><div class="scroll">${signalTable(st.signals, pos, lp, c)}</div></div>`;
  h += `<div class="card"><h2>Recent trades</h2><div class="scroll">${tradeTable(m.trades, c)}</div></div></div>`;
  h += `<div class="card"><h2>Backtest: Rules + ML vs buy & hold ${esc(m.benchmark)}</h2>`;
  if (bt) {
    h += `<p class="muted small" style="margin-top:-6px">${bt.start} → ${bt.end} · ${bt.trades} trades · on average ${(bt.avg_invested*100).toFixed(0)}% invested</p>`;
    h += legend(m.benchmark) + `<div class="chart" id="bt"></div>` + metricsTable(bt);
    setTimeout(() => lineChart($("#bt"), bt.curve.map(p => ({d:p.date, a:p.bot, b:p.bench})), c), 0);
  } else h += `<div class="empty">No backtest yet. Run <code>python run.py backtest</code>.</div>`;
  h += `</div>`;
  $("#view").innerHTML = h;
}
function tile(l, v, s) { return `<div class="card tile" style="margin:0"><div class="label">${l}</div><div class="val">${v}</div><div class="sub">${s}</div></div>`; }
function legend(b) { return `<div class="legend"><span><span class="sw" style="background:var(--series-1)"></span>Bot</span><span><span class="sw" style="background:var(--series-2)"></span>Buy & hold ${esc(b)}</span></div>`; }
function scoreCell(v) {
  if (v==null) return `<td class="num muted">–</td>`;
  const w = Math.round(Math.abs(v)*28);
  return `<td class="num">${v>0?"+":""}${v.toFixed(2)} <span class="bar" style="width:${w}px;background:${v>=0?"var(--good)":"var(--critical)"}"></span><span style="display:inline-block;width:${28-w}px"></span></td>`;
}
function signalTable(sig, pos, lp, c) {
  if (!sig || !Object.keys(sig).length) return `<div class="empty">No signals yet.</div>`;
  const rows = Object.entries(sig).sort((a,b) => (b[1].score??-9) - (a[1].score??-9));
  return `<table><thead><tr><th>Asset</th><th class="num">Rules</th><th class="num">ML</th><th class="num">Claude</th><th class="num">Combined</th><th class="num">Target</th></tr></thead><tbody>` +
    rows.map(([s,v]) => `<tr title="${esc(v.reason)}"><td><b>${esc(s)}</b>${v.reason?`<div class="small muted">${esc(v.reason)}</div>`:""}</td>
      ${scoreCell(v.rules)}${scoreCell(v.ml)}${scoreCell(v.llm)}${scoreCell(v.score)}
      <td class="num">${v.target ? (v.target*100).toFixed(0)+"%" : "–"}</td></tr>`).join("") + `</tbody></table>`;
}
function tradeTable(t, c) {
  if (!t || !t.length) return `<div class="empty">No trades yet.</div>`;
  return `<table><thead><tr><th>Date</th><th>Side</th><th>Asset</th><th class="num">Value</th></tr></thead><tbody>` +
    t.map(x => `<tr><td>${esc(x.time.slice(0,10))}</td><td class="${x.side==="BUY"?"up":"down"}">${x.side==="BUY"?"▲ Buy":"▼ Sell"}</td><td>${esc(x.symbol)}</td><td class="num">${money(x.value,c)}</td></tr>`).join("") + `</tbody></table>`;
}
function metricsTable(bt) {
  const r = (k, f) => `<tr><td>${k}</td><td class="num">${f(bt.bot)}</td><td class="num">${f(bt.buy_and_hold)}</td></tr>`;
  return `<table style="margin-top:12px"><thead><tr><th></th><th class="num">Bot</th><th class="num">Buy & hold</th></tr></thead><tbody>
   ${r("Total return", m => `<span class="${cls(m.total_return)}">${pct(m.total_return)}</span>`)}
   ${r("Per year (CAGR)", m => pct(m.cagr))}
   ${r("Worst drop (max drawdown)", m => pct(m.max_drawdown))}
   ${r("Sharpe ratio (risk-adjusted)", m => m.sharpe.toFixed(2))}</tbody></table>`;
}
function lineChart(el, pts, cur) {
  const W = 900, H = 300, L = 64, R = 16, T = 12, B = 28;
  const ys = pts.flatMap(p => [p.a, p.b]);
  let lo = Math.min(...ys), hi = Math.max(...ys); const pad = (hi-lo)*0.06 || 1; lo -= pad; hi += pad;
  const x = i => L + (W-L-R) * i / Math.max(pts.length-1, 1);
  const y = v => T + (H-T-B) * (1 - (v-lo)/(hi-lo));
  const ticks = niceTicks(lo, hi, 5);
  const path = k => pts.map((p,i) => (i?"L":"M") + x(i).toFixed(1) + "," + y(p[k]).toFixed(1)).join("");
  const nx = Math.min(6, pts.length);
  const xt = [...Array(nx).keys()].map(j => Math.round(j*(pts.length-1)/Math.max(nx-1,1)));
  const span = (new Date(pts[pts.length-1].d) - new Date(pts[0].d)) / 864e5;
  const dlab = d => new Date(d+"T00:00").toLocaleDateString("en-AU", span < 200 ? {day:"numeric",month:"short"} : {month:"short",year:"numeric"});
  const fmt = v => new Intl.NumberFormat("en-AU",{notation:"compact",maximumFractionDigits:1}).format(v);
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Portfolio value over time, bot versus buy and hold">
    ${ticks.map(t => `<line x1="${L}" x2="${W-R}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${L-8}" y="${y(t)+4}" text-anchor="end" font-size="11" fill="var(--text-muted)">${fmt(t)}</text>`).join("")}
    ${xt.map((i,j) => `<text x="${x(i)}" y="${H-8}" text-anchor="${j===0?"start":j===xt.length-1?"end":"middle"}" font-size="11" fill="var(--text-muted)">${dlab(pts[i].d)}</text>`).join("")}
    <path d="${path("b")}" fill="none" stroke="var(--series-2)" stroke-width="2" stroke-linejoin="round"/>
    <path d="${path("a")}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round"/>
    <line id="xh" y1="${T}" y2="${H-B}" stroke="var(--text-muted)" stroke-dasharray="3 3" visibility="hidden"/>
    <circle id="da" r="4" fill="var(--series-1)" stroke="var(--surface-1)" stroke-width="2" visibility="hidden"/>
    <circle id="db" r="4" fill="var(--series-2)" stroke="var(--surface-1)" stroke-width="2" visibility="hidden"/>
    <rect x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="transparent" id="hit"/></svg><div class="tip"></div>`;
  const svg = $("svg", el), tip = $(".tip", el);
  const move = e => {
    const r = svg.getBoundingClientRect(), sx = (e.clientX - r.left) * W / r.width;
    const i = Math.max(0, Math.min(pts.length-1, Math.round((sx-L)/(W-L-R)*(pts.length-1))));
    const p = pts[i];
    for (const [id, cx, cy] of [["xh"],["da",x(i),y(p.a)],["db",x(i),y(p.b)]]) {
      const n = $("#"+id, svg); n.setAttribute("visibility","visible");
      if (id==="xh") { n.setAttribute("x1",x(i)); n.setAttribute("x2",x(i)); } else { n.setAttribute("cx",cx); n.setAttribute("cy",cy); }
    }
    tip.style.display = "block";
    tip.innerHTML = `<b>${p.d}</b><br><span class="sw" style="background:var(--series-1)"></span>Bot ${money(p.a,cur)}<br><span class="sw" style="background:var(--series-2)"></span>Buy & hold ${money(p.b,cur)}`;
    const px = x(i) * r.width / W;
    tip.style.left = (px > r.width*0.6 ? px - tip.offsetWidth - 12 : px + 12) + "px"; tip.style.top = "10px";
  };
  const hit = $("#hit", svg);
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerleave", () => { tip.style.display="none"; ["xh","da","db"].forEach(id => $("#"+id,svg).setAttribute("visibility","hidden")); });
}
function niceTicks(lo, hi, n) {
  const step0 = (hi-lo)/n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1,2,2.5,5,10].map(s => s*mag).find(s => s >= step0);
  const out = []; for (let v = Math.ceil(lo/step)*step; v <= hi; v += step) out.push(v); return out;
}
</script></body></html>"""
