"""The three signals. Each returns scores in [-1, 1]: +1 = strong buy, -1 = strong sell."""
import json
import os
import re
from datetime import date

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

HORIZON = 5  # ML predicts whether price is higher in 5 trading days


# ---------------------------------------------------------------- 1. rules
def rules_scores(closes: pd.DataFrame) -> pd.DataFrame:
    """Trend + momentum rules, the kind traders have used for decades.
      +0.4 if price above its 200-day average (long-term uptrend), else -0.4
      +0.3 if 50-day average above 200-day ("golden cross"), else -0.3
      +/-0.3 scaled by risk-adjusted 3-month momentum
    """
    sma50 = closes.rolling(50).mean()
    sma200 = closes.rolling(200).mean()
    trend = np.where(closes > sma200, 0.4, -0.4)
    cross = np.where(sma50 > sma200, 0.3, -0.3)
    ret63 = closes.pct_change(63)
    vol63 = closes.pct_change().rolling(63).std() * np.sqrt(63)
    mom = (ret63 / vol63).clip(-1, 1) * 0.3
    score = pd.DataFrame(trend + cross, index=closes.index, columns=closes.columns) + mom
    score[sma200.isna()] = np.nan
    return score.clip(-1, 1)


# ---------------------------------------------------------------- 2. machine learning
def _rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def build_features(closes: pd.DataFrame) -> pd.DataFrame:
    """Long-format features indexed by (date, symbol), plus the label."""
    rets = closes.pct_change()
    feats = {
        "r1": rets, "r5": closes.pct_change(5), "r10": closes.pct_change(10),
        "r21": closes.pct_change(21), "r63": closes.pct_change(63),
        "vol21": rets.rolling(21).std(), "vol63": rets.rolling(63).std(),
        "rsi14": _rsi(closes) / 100,
        "d_sma50": closes / closes.rolling(50).mean() - 1,
        "d_sma200": closes / closes.rolling(200).mean() - 1,
        "hi_252": closes / closes.rolling(252).max() - 1,
        # relative strength vs the average of the basket
        "rel21": closes.pct_change(21).sub(closes.pct_change(21).mean(axis=1), axis=0),
    }
    fwd = closes.shift(-HORIZON) / closes - 1
    feats["fwd"] = fwd
    long = pd.concat({k: v.stack(future_stack=True) for k, v in feats.items()}, axis=1)
    long.index.names = ["date", "symbol"]
    return long


FEATURES = ["r1", "r5", "r10", "r21", "r63", "vol21", "vol63", "rsi14",
            "d_sma50", "d_sma200", "hi_252", "rel21"]


class MLSignal:
    """Gradient-boosted trees predicting P(price up in 5 days).
    Trained on all symbols in the market pooled together."""

    def __init__(self):
        self.model = None

    def fit(self, feats: pd.DataFrame, cutoff):
        # only rows whose 5-day future is already known at `cutoff` (no lookahead)
        dates = feats.index.get_level_values("date")
        uniq = np.sort(dates.unique())
        pos = np.searchsorted(uniq, np.datetime64(cutoff), side="right") - 1 - HORIZON
        if pos < 0:
            return self
        last_known = uniq[pos]
        train = feats[(dates <= last_known)].dropna(subset=FEATURES + ["fwd"])
        if len(train) < 500:
            return self
        y = (train["fwd"] > 0).astype(int)
        self.model = HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.05, max_iter=150,
            min_samples_leaf=50, l2_regularization=1.0, random_state=0,
        ).fit(train[FEATURES], y)
        return self

    def score(self, feats_on_day: pd.DataFrame) -> pd.Series:
        """feats_on_day: rows indexed by symbol. Returns score per symbol."""
        if self.model is None:
            return pd.Series(np.nan, index=feats_on_day.index)
        X = feats_on_day[FEATURES]
        ok = X.notna().all(axis=1)
        out = pd.Series(np.nan, index=X.index)
        if ok.any():
            p = self.model.predict_proba(X[ok])[:, 1]
            # probabilities cluster near 0.5; stretch so 0.625 -> +1
            out[ok] = np.clip((p - 0.5) * 8, -1, 1)
        return out


# ---------------------------------------------------------------- 3. Claude news sentiment
PROMPT = """You are helping a trading bot. For each asset below, read the recent
news headlines and judge whether the news is likely good or bad for the price
over the next week. Be sceptical: most headlines are noise, so scores near 0 are
normal. Return ONLY JSON like:
{{"SYMBOL": {{"score": 0.2, "reason": "max 15 words"}}, ...}}
score is -1 (very bearish) to 1 (very bullish). Use 0 when there is no news.

{blocks}"""


def llm_scores(symbols, headlines_fn, cache_path, model, market_name=""):
    """Ask Claude to score news sentiment. Cached once per day to keep costs tiny.
    Returns {symbol: {"score": float, "reason": str}} or {} if unavailable."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {}
    today = date.today().isoformat()
    cache = {}
    if os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path))
        except Exception:
            cache = {}
    if cache.get("date") == today and set(symbols) <= set(cache.get("scores", {})):
        return cache["scores"]

    blocks = []
    for s in symbols:
        hl = headlines_fn(s)
        lines = "\n".join(f"- {h}" for h in hl) if hl else "- (no recent news)"
        blocks.append(f"## {s}\n{lines}")
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=model, max_tokens=1500,
            messages=[{"role": "user", "content": PROMPT.format(blocks="\n\n".join(blocks))}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    except Exception as e:
        print(f"  Claude sentiment unavailable: {e}")
        return {}
    scores = {}
    for s in symbols:
        v = data.get(s) or {}
        try:
            scores[s] = {"score": float(np.clip(float(v.get("score", 0)), -1, 1)),
                         "reason": str(v.get("reason", ""))[:140]}
        except (TypeError, ValueError):
            scores[s] = {"score": 0.0, "reason": ""}
    json.dump({"date": today, "scores": scores}, open(cache_path, "w"), indent=1)
    return scores
