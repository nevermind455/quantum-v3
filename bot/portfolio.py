"""
Portfolio Manager - tracks all trading performance.
Balance, daily PnL, win rate, average R:R, trade history, exposure.
"""
import json, os, time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from bot.logger import log, C


@dataclass
class PortfolioStats:
    balance: float = 0.0
    total_balance: float = 0.0
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    total_pnl: float = 0.0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    current_streak: int = 0
    max_drawdown: float = 0.0
    open_positions: int = 0


class Portfolio:
    def __init__(self, client):
        self.client = client
        self.stats = PortfolioStats()
        self.trade_history = []
        self.daily_start_balance = 0
        self.peak_balance = 0
        self._load_history()

    def _load_history(self):
        try:
            if os.path.exists("trade_history.json"):
                with open("trade_history.json") as f:
                    self.trade_history = json.load(f)
                # Reconstruct stats
                for t in self.trade_history:
                    if t.get("type") == "close":
                        pnl = t.get("pnl", 0)
                        self.stats.total_pnl += pnl
                        self.stats.total_trades += 1
                        if pnl >= 0: self.stats.wins += 1
                        else: self.stats.losses += 1
        except: pass

    def _save_history(self):
        try:
            with open("trade_history.json", "w") as f:
                json.dump(self.trade_history[-500:], f, indent=2)
        except: pass

    def update(self):
        """Update portfolio stats from Binance."""
        self.stats.balance = self.client.get_balance()
        self.stats.total_balance = self.client.get_total_balance()

        if self.daily_start_balance == 0:
            self.daily_start_balance = self.stats.total_balance
        if self.peak_balance == 0:
            self.peak_balance = self.stats.total_balance

        # Daily PnL
        if self.daily_start_balance > 0:
            self.stats.daily_pnl = self.stats.total_balance - self.daily_start_balance
            self.stats.daily_pnl_pct = (self.stats.daily_pnl / self.daily_start_balance) * 100

        # Drawdown
        self.peak_balance = max(self.peak_balance, self.stats.total_balance)
        if self.peak_balance > 0:
            self.stats.max_drawdown = ((self.peak_balance - self.stats.total_balance) / self.peak_balance) * 100

        # Win rate
        total = self.stats.wins + self.stats.losses
        self.stats.win_rate = (self.stats.wins / total * 100) if total > 0 else 0

        # Open positions
        positions = self.client.get_open_positions()
        self.stats.open_positions = len(positions) if positions else 0

    def record_trade(self, pair, direction, entry, exit_price, pnl, reason, **kwargs):
        """Record a completed trade."""
        self.stats.total_trades += 1
        self.stats.total_pnl += pnl

        if pnl >= 0:
            self.stats.wins += 1
            self.stats.current_streak = max(1, self.stats.current_streak + 1)
            self.stats.best_trade = max(self.stats.best_trade, pnl)
        else:
            self.stats.losses += 1
            self.stats.current_streak = min(-1, self.stats.current_streak - 1)
            self.stats.worst_trade = min(self.stats.worst_trade, pnl)

        # Average win/loss
        wins = [t["pnl"] for t in self.trade_history if t.get("type") == "close" and t.get("pnl", 0) > 0]
        losses = [t["pnl"] for t in self.trade_history if t.get("type") == "close" and t.get("pnl", 0) < 0]
        if wins: self.stats.avg_win = sum(wins) / len(wins)
        if losses: self.stats.avg_loss = sum(losses) / len(losses)
        if self.stats.avg_loss != 0:
            self.stats.avg_rr = abs(self.stats.avg_win / self.stats.avg_loss)

        # Save
        self.trade_history.append({
            "type": "close",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pair": pair, "direction": direction,
            "entry": entry, "exit": exit_price,
            "pnl": pnl, "reason": reason,
            "streak": self.stats.current_streak,
            **kwargs
        })
        self._save_history()

    def record_open(self, pair, direction, entry, quantity, score, **kwargs):
        """Record a trade open."""
        self.trade_history.append({
            "type": "open",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pair": pair, "direction": direction,
            "entry": entry, "quantity": quantity,
            "score": score, **kwargs
        })
        self._save_history()

    def get_24h_performance(self):
        """Get last 24 hours trading performance."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = [t for t in self.trade_history
                  if t.get("type") == "close" and
                  datetime.fromisoformat(t["timestamp"]) > cutoff]
        if not recent:
            return {"trades": 0, "pnl": 0, "wins": 0, "losses": 0}
        pnls = [t.get("pnl", 0) for t in recent]
        return {
            "trades": len(recent),
            "pnl": sum(pnls),
            "wins": sum(1 for p in pnls if p > 0),
            "losses": sum(1 for p in pnls if p <= 0),
            "avg": sum(pnls) / len(pnls),
            "best": max(pnls),
            "worst": min(pnls),
        }
