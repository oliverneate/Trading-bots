"""Live trading run and historical backtest for one market."""
import json

import numpy as np
import pandas as pd

from .broker import PaperBroker, make_broker
from .config import STATE_DIR
from .data import get_headlines, get_prices
from .signals import MLSignal, build_features, llm_scores, rules_scores
from .strategy import combine, effective_weights, target_weights


def _load(cfg):
    syms = list(dict.fromkeys(cfg["symbols"] + [cfg["benchmark"]]))
    closes = get_prices(syms, cfg["history_days"])
    bench = closes[cfg["benchmark"]] if cfg["benchmark"] in closes else closes.mean(axis=1)
    tradable = [s for s in cfg["symbols"] if s in closes]
    return closes[tradable], bench


# ------------------------------------------------------------------ live
def run_live(cfg):
    key = cfg["key"]
    print(f"== {cfg['name']} live run ==")
    closes, bench = _load(cfg)
    today = closes.index[-1]
    prices = closes.iloc[-1].to_dict()

    rules = rules_scores(closes).iloc[-1]
    feats = build_features(closes)
    ml_model = MLSignal().fit(feats, today)
    ml = ml_model.score(feats.xs(today, level="date"))

    llm_raw = llm_scores(list(closes.columns), get_headlines,
                         STATE_DIR / f"{key}_llm_cache.json", cfg["llm_model"], cfg["name"])
    llm = pd.Series({s: v["score"] for s, v in llm_raw.items()}, dtype=float).reindex(closes.columns)
    w = effective_weights(cfg, bool(llm_raw))
    score = combine(rules, ml, llm, w)
    broker = make_broker(cfg, STATE_DIR / f"{key}_state.json")
    targets = target_weights(score, cfg, held=list(broker.state["positions"]))
    broker.rebalance({s: v for s, v in targets.items() if v > 0}, prices, when=str(today.date()))
    signals = {s: {"rules": _r(rules.get(s)), "ml": _r(ml.get(s)), "llm": _r(llm.get(s)),
                   "reason": (llm_raw.get(s) or {}).get("reason", ""),
                   "score": _r(score.get(s)), "target": _r(targets.get(s))}
               for s in closes.columns}
    broker.record(prices, float(bench.iloc[-1]), signals, when=str(today.date()))
    broker.state["weights_used"] = w
    broker.save()
    eq = broker.equity(prices)
    print(f"  equity {eq:,.2f} {cfg['currency']} | holding: "
          f"{', '.join(s for s, v in targets.items() if v > 0) or 'cash'}")


def _r(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 3)


# ------------------------------------------------------------------ backtest
def run_backtest(cfg, retrain_every=21, warmup=504):
    """Walk-forward test of rules + ML (news sentiment can't be backtested:
    we don't have historical headlines). The model is retrained every
    `retrain_every` days using only data available at that point."""
    key = cfg["key"]
    print(f"== {cfg['name']} backtest ==")
    closes, bench = _load(cfg)
    rules_all = rules_scores(closes)
    feats = build_features(closes)
    w = effective_weights(cfg, have_llm=False)
    by_date = {d: g.droplevel("date") for d, g in feats.groupby(level="date")}

    broker = PaperBroker(None, cfg, fresh=True)
    dates = closes.index[warmup:]
    model = MLSignal()
    n_trades, invested = 0, []
    for i, d in enumerate(dates):
        if i % retrain_every == 0:
            model = MLSignal().fit(feats, d)
        prices = closes.loc[d].dropna().to_dict()
        ml = model.score(by_date[d])
        score = combine(rules_all.loc[d], ml, pd.Series(np.nan, index=closes.columns), w)
        targets = target_weights(score, cfg, held=list(broker.state["positions"]))
        before = len(broker.state["trades"])
        broker.rebalance({s: v for s, v in targets.items() if v > 0}, prices, when=str(d.date()))
        n_trades += len(broker.state["trades"]) - before
        broker.state["trades"] = broker.state["trades"][-50:]
        broker.state["history"].append({"date": str(d.date()), "equity": round(broker.equity(prices), 2),
                                        "benchmark": round(float(bench.loc[d]), 4)})
        invested.append(1 - broker.state["cash"] / max(broker.equity(prices), 1e-9))

    hist = pd.DataFrame(broker.state["history"]).set_index("date")
    ppy = 365 if key == "crypto" else 252
    bench_eq = hist["benchmark"] / hist["benchmark"].iloc[0] * cfg["starting_cash"]
    result = {
        "market": key, "name": cfg["name"], "currency": cfg["currency"],
        "benchmark": cfg["benchmark"], "start": hist.index[0], "end": hist.index[-1],
        "signals_used": {k: round(v, 2) for k, v in w.items()},
        "bot": _metrics(hist["equity"], ppy),
        "buy_and_hold": _metrics(bench_eq, ppy),
        "trades": n_trades, "avg_invested": round(float(np.mean(invested)), 3),
        "curve": [{"date": d, "bot": float(e), "bench": round(float(b), 2)}
                  for d, e, b in zip(hist.index, hist["equity"], bench_eq)],
    }
    (STATE_DIR / f"{key}_backtest.json").write_text(json.dumps(result))
    b, h = result["bot"], result["buy_and_hold"]
    print(f"  bot  {b['total_return']:+.1%} total, {b['cagr']:+.1%}/yr, max drawdown {b['max_drawdown']:.1%}, Sharpe {b['sharpe']}")
    print(f"  hold {h['total_return']:+.1%} total, {h['cagr']:+.1%}/yr, max drawdown {h['max_drawdown']:.1%}, Sharpe {h['sharpe']}")
    return result


def _metrics(eq: pd.Series, ppy):
    r = eq.pct_change().dropna()
    years = len(eq) / ppy
    total = eq.iloc[-1] / eq.iloc[0] - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = r.mean() / r.std() * np.sqrt(ppy) if r.std() > 0 else 0
    return {"total_return": round(float(total), 4),
            "cagr": round(float((1 + total) ** (1 / years) - 1), 4) if years > 0 else 0,
            "max_drawdown": round(float(dd), 4), "sharpe": round(float(sharpe), 2)}
