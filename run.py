"""Command line entry point.

  python run.py trade      [--market us|asx|crypto|all]   # one live paper-trading run
  python run.py backtest   [--market ...]                 # historical test (Rules + ML)
  python run.py dashboard                                 # rebuild site/index.html
"""
import argparse
import traceback

from bot.config import STATE_DIR, load_config
from bot.dashboard import build_dashboard
from bot.engine import run_backtest, run_live


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["trade", "backtest", "dashboard"])
    ap.add_argument("--market", default="all")
    args = ap.parse_args()

    markets = load_config()
    chosen = markets if args.market == "all" else {args.market: markets[args.market]}
    STATE_DIR.mkdir(exist_ok=True)

    failed = False
    if args.command in ("trade", "backtest"):
        fn = run_live if args.command == "trade" else run_backtest
        for cfg in chosen.values():
            try:  # one market failing shouldn't stop the others
                fn(cfg)
            except Exception:
                failed = True
                traceback.print_exc()
    build_dashboard(markets)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
