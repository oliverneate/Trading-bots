"""Combine the three signals into target portfolio weights."""
import numpy as np
import pandas as pd


def effective_weights(cfg, have_llm: bool):
    w = dict(cfg["weights"])
    if not have_llm:
        llm = w.pop("llm", 0)
        total = w["rules"] + w["ml"]
        w = {"rules": w["rules"] + llm * w["rules"] / total,
             "ml": w["ml"] + llm * w["ml"] / total, "llm": 0.0}
    return w


def combine(rules: pd.Series, ml: pd.Series, llm: pd.Series, w) -> pd.Series:
    parts = pd.DataFrame({"rules": rules, "ml": ml, "llm": llm})
    weights = pd.Series(w)
    present = parts.notna()
    # if a signal is missing for a symbol, renormalise over the ones we have
    num = (parts.fillna(0) * weights).sum(axis=1)
    den = (present * weights).sum(axis=1).replace(0, np.nan)
    return (num / den).fillna(-1)


def target_weights(score: pd.Series, cfg, held=()) -> pd.Series:
    """Equal-weight the top N assets whose score clears the threshold.
    Assets already held get a small bonus (`hold_bonus`, default 0.25) so the bot doesn't
    churn between near-identical scores and rack up fees."""
    bonus = cfg.get("hold_bonus", 0.25)
    adj = score + pd.Series({s: bonus for s in held if s in score.index}, dtype=float).reindex(score.index).fillna(0)
    picks = adj[adj >= cfg["buy_threshold"]].sort_values(ascending=False)
    picks = picks.head(cfg["max_positions"])
    tw = pd.Series(0.0, index=score.index)
    if len(picks):
        # e.g. 4 picks -> 25% each; 2 picks -> capped at max_weight, rest stays cash
        tw[picks.index] = min(1.0 / len(picks), cfg["max_weight"])
    return tw
