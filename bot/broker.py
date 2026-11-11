"""Brokers. PaperBroker simulates trades with fees + slippage and keeps its
state in a JSON file (committed back to the repo by the cloud job).
AlpacaBroker places real orders on an Alpaca *paper* account (US + crypto)."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class PaperBroker:
    def __init__(self, state_path, cfg, fresh=False):
        self.path = Path(state_path) if state_path else None
        self.cfg = cfg
        if not fresh and self.path and self.path.exists():
            self.state = json.loads(self.path.read_text())
        else:
            self.state = {"cash": float(cfg["starting_cash"]), "positions": {},
                          "trades": [], "history": [], "signals": {}, "started": None}

    def equity(self, prices):
        return self.state["cash"] + sum(q * prices.get(s, 0) for s, q in self.state["positions"].items())

    def rebalance(self, targets: dict, prices: dict, when=None):
        """targets: {symbol: weight}. Sells first, then buys."""
        eq = self.equity(prices)
        fee, slip = self.cfg["fee_pct"], self.cfg["slippage_pct"]
        band = self.cfg["rebalance_band"]
        now = when or datetime.now(timezone.utc).isoformat(timespec="seconds")
        pos = self.state["positions"]
        orders = []
        for s in set(pos) | set(targets):
            if s not in prices:
                continue
            cur_val = pos.get(s, 0) * prices[s]
            tgt_val = targets.get(s, 0) * eq
            diff = tgt_val - cur_val
            closing = targets.get(s, 0) == 0 and pos.get(s, 0) > 0
            if abs(diff) / eq >= band or closing:
                orders.append((s, diff))
        orders.sort(key=lambda o: o[1])  # sells (negative) first
        for s, diff in orders:
            px = prices[s] * (1 + slip if diff > 0 else 1 - slip)
            if diff > 0:
                spend = min(diff, self.state["cash"] / (1 + fee))
                if spend <= 1:
                    continue
                qty = spend / px
                self.state["cash"] -= spend * (1 + fee)
                pos[s] = pos.get(s, 0) + qty
                side, notional = "BUY", spend
            else:
                qty = min(-diff / px, pos.get(s, 0))
                if targets.get(s, 0) == 0:
                    qty = pos.get(s, 0)
                notional = qty * px
                self.state["cash"] += notional * (1 - fee)
                pos[s] = pos.get(s, 0) - qty
                if pos[s] < 1e-9:
                    pos.pop(s)
                side = "SELL"
            self.state["trades"].append({"time": now, "symbol": s, "side": side,
                                         "qty": round(qty, 6), "price": round(px, 4),
                                         "value": round(notional, 2)})
        return orders

    def record(self, prices, benchmark_price, signals, when=None):
        when = when or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        eq = self.equity(prices)
        hist = self.state["history"]
        point = {"date": when, "equity": round(eq, 2), "benchmark": round(benchmark_price, 4)}
        if hist and hist[-1]["date"] == when:
            hist[-1] = point  # re-run on same day overwrites
        else:
            hist.append(point)
        self.state["started"] = self.state["started"] or when
        self.state["signals"] = signals
        self.state["last_prices"] = {s: round(p, 4) for s, p in prices.items()}
        self.state["trades"] = self.state["trades"][-500:]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=1))


class AlpacaBroker(PaperBroker):
    """Mirrors target weights onto an Alpaca paper account. Local state is still
    kept (for the dashboard), but positions/cash come from Alpaca."""

    def __init__(self, state_path, cfg):
        super().__init__(state_path, cfg)
        from alpaca.trading.client import TradingClient
        self.client = TradingClient(os.environ["ALPACA_API_KEY"],
                                    os.environ["ALPACA_SECRET_KEY"], paper=True)
        self.crypto = cfg["key"] == "crypto"

    def _alpaca_sym(self, s):
        return s.replace("-USD", "/USD") if self.crypto else s

    def _sync(self):
        acct = self.client.get_account()
        self.state["cash"] = float(acct.cash)
        back = {self._alpaca_sym(s).replace("/", ""): s for s in self.cfg["symbols"]}
        self.state["positions"] = {back.get(p.symbol, p.symbol): float(p.qty)
                                   for p in self.client.get_all_positions()
                                   if p.symbol in back}

    def rebalance(self, targets, prices, when=None):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest
        self._sync()
        eq = self.equity(prices)
        tif = TimeInForce.GTC if self.crypto else TimeInForce.DAY
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for s in set(self.state["positions"]) | set(targets):
            if s not in prices:
                continue
            diff = targets.get(s, 0) * eq - self.state["positions"].get(s, 0) * prices[s]
            if abs(diff) / eq < self.cfg["rebalance_band"] and targets.get(s, 0) > 0:
                continue
            if abs(diff) < 1:
                continue
            try:
                if targets.get(s, 0) == 0:
                    self.client.close_position(self._alpaca_sym(s).replace("/", ""))
                else:
                    self.client.submit_order(MarketOrderRequest(
                        symbol=self._alpaca_sym(s), notional=round(abs(diff), 2),
                        side=OrderSide.BUY if diff > 0 else OrderSide.SELL, time_in_force=tif))
                self.state["trades"].append({"time": now, "symbol": s,
                                             "side": "BUY" if diff > 0 else "SELL",
                                             "qty": None, "price": round(prices[s], 4),
                                             "value": round(abs(diff), 2)})
            except Exception as e:
                print(f"  Alpaca order failed for {s}: {e}")
        self._sync()


def make_broker(cfg, state_path):
    if cfg.get("broker") == "alpaca":
        if os.environ.get("ALPACA_API_KEY"):
            return AlpacaBroker(state_path, cfg)
        print("  broker=alpaca but no ALPACA_API_KEY set; using built-in paper broker")
    return PaperBroker(state_path, cfg)
