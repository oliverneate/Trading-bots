"""Price + news data. Uses Yahoo Finance (via yfinance), which covers US
stocks, ASX (.AX tickers) and crypto (-USD tickers) for free.

Set BOT_SYNTHETIC=1 to use generated prices instead (offline testing)."""
import os

import numpy as np
import pandas as pd


def get_prices(symbols, days=1500):
    """Return a DataFrame of daily closes: index=date, columns=symbols."""
    if os.environ.get("BOT_SYNTHETIC") == "1":
        return _synthetic(symbols, days)
    import yfinance as yf

    period_days = int(days * 1.5)  # calendar days to cover enough trading days
    df = yf.download(
        symbols, period=f"{period_days}d", interval="1d",
        auto_adjust=True, progress=False, group_by="column", threads=True,
    )
    closes = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]]
    if not isinstance(df.columns, pd.MultiIndex):
        closes.columns = symbols
    closes = closes.dropna(how="all").ffill()
    missing = [s for s in symbols if s not in closes or closes[s].isna().all()]
    if missing:
        print(f"  warning: no data for {missing}; skipping them")
        closes = closes.drop(columns=[m for m in missing if m in closes])
    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    return closes.tail(days)


def get_headlines(symbol, limit=8):
    """Recent news headlines for a symbol (list of strings)."""
    if os.environ.get("BOT_SYNTHETIC") == "1":
        return []
    try:
        import yfinance as yf
        items = yf.Ticker(symbol).news or []
    except Exception as e:  # news is best-effort
        print(f"  news fetch failed for {symbol}: {e}")
        return []
    titles = []
    for it in items[:limit]:
        title = (it.get("content") or {}).get("title") or it.get("title")
        if title:
            titles.append(title)
    return titles


def _synthetic(symbols, days):
    rng = np.random.default_rng(42)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    out = {}
    for i, s in enumerate(symbols):
        drift = rng.normal(0.0004, 0.0003)
        vol = rng.uniform(0.012, 0.035)
        # regime-switching drift so trend signals have something to find
        regime = np.sign(np.sin(np.arange(days) / rng.uniform(60, 140) + i))
        r = rng.normal(drift + regime * 0.0008, vol, days)
        out[s] = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame(out, index=idx)
