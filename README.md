# AI Trading Bots: US stocks, ASX and crypto

Three paper-trading bots that run in the cloud for free on GitHub Actions and
publish a dashboard. **They trade simulated money on real prices.** Nothing
here touches real money unless you deliberately change it.

## How each bot decides

Every run, for every asset, it computes three scores from -1 (sell) to +1 (buy):

| Signal | What it is | Weight |
|---|---|---|
| **Rules** | Price vs 200-day average, 50/200-day "golden cross", 3-month risk-adjusted momentum | 40% |
| **ML** | Gradient-boosted trees (scikit-learn) trained on 12 price features to predict "up in 5 days?" Retrained every run on all assets in that market | 40% |
| **Claude** | Claude reads the latest news headlines and scores sentiment | 20% |

The combined score is the weighted average. The bot holds the top 4 assets
(top 3 for crypto) that score above **0.15**, equal-weighted with at most 30%
in any one asset, and keeps the rest in cash. Fees and slippage are simulated.
Without an Anthropic key, Claude's 20% is shared between Rules and ML.

Everything is tunable in `config.yaml`: symbols, weights, thresholds, fees
and starting cash.

## Run it on your computer

```bash
pip install -r requirements.txt
python run.py backtest          # test Rules + ML on ~4 years of history
python run.py trade             # one live paper-trading run for all 3 bots
open site/index.html            # the dashboard
```

Use `--market us`, `--market asx` or `--market crypto` to run a single bot.
`BOT_SYNTHETIC=1` uses made-up prices if you're offline.

## Put it in the cloud (about 10 minutes, free)

1. **Make a GitHub repo** (public is simplest, because free GitHub Pages
   needs a public repo) and push this folder to it.
2. **Add your Claude API key** (optional but recommended): Settings → Secrets
   and variables → Actions → New secret, named `ANTHROPIC_API_KEY`. Get a key
   at console.anthropic.com. With Haiku, three short calls a day cost cents
   per month.
3. **Turn on the dashboard:** Settings → Pages → Source: **GitHub Actions**.
4. **Allow the bot to save its state:** Settings → Actions → General →
   Workflow permissions → **Read and write**.
5. **Kick it off:** Actions tab → *trading-bots* → Run workflow. Choose
   `backtest` / `all` first, then `trade` / `all`.
   The dashboard URL appears on the run summary (`https://<you>.github.io/<repo>/`).

After that it runs on its own:

| Bot | When (Darwin time) |
|---|---|
| ASX | Weekdays ~1:30pm |
| US | Tue–Sat ~5am (during the US afternoon) |
| Crypto | Daily ~9:45am |
| Backtest refresh | Sundays |

Each run commits its portfolio to `state/`, so you have a full history of
every trade in git. If GitHub ever pauses scheduled runs on a quiet repo,
re-enable them in the Actions tab.

## Optional: a real broker paper account (Alpaca)

The built-in simulator works for all three markets. For US stocks and crypto
you can mirror trades to an [Alpaca](https://alpaca.markets) **paper** account
instead. Add `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` secrets, then set
`broker: alpaca` for `us` or `crypto` in `config.yaml`. The code always
connects with `paper=True`. Check whether Alpaca accepts sign-ups from your
country. The ASX has no free paper-trading API, so it stays simulated.

## Honest caveats

- Backtests only test Rules + ML, because there is no free archive of
  historical headlines. Backtests also flatter strategies: survivorship bias
  (today's big companies were picked with hindsight), no taxes, and simplified
  fills.
- Most strategies, AI-driven ones included, underperform simply holding an
  index after costs. Judge the bot on several months of paper trading against
  the buy-and-hold line on the dashboard, not on the backtest.
- This is a learning project, not financial advice.

## Files

```
config.yaml          markets, symbols, weights, risk settings
run.py               CLI: trade | backtest | dashboard
bot/data.py          prices + headlines (Yahoo Finance via yfinance)
bot/signals.py       rules, ML model, Claude sentiment
bot/strategy.py      combine scores -> target weights
bot/broker.py        paper broker + Alpaca paper broker
bot/engine.py        live run + walk-forward backtest
bot/dashboard.py     builds site/index.html
.github/workflows/   cloud schedule
```
