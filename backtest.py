#!/usr/bin/env python3
"""
QUANTUM v3.0 - Backtest scaffold.
Runs the same pipeline (indicators, ML, regime, AI decision, risk) on historical 1h data
and simulates trades with ATR-based SL/TP. Reports PnL, win rate, drawdown.

Uses 1h bars only (no orderbook/whale in history), so signals are tech + ML + regime.
Use --min-confidence 50 to see more trades; default 65% may yield few or none.

Requires at least ~25 days of data (600+ bars). More days = more trades.

Usage:
  python backtest.py                    # last 30 days
  python backtest.py --days 60          # last 60 days
  python backtest.py --days 90 --min-confidence 55
  python backtest.py --balance 5000
"""
import sys
import os
import argparse
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np

from bot.config import config
from bot.logger import log, C
from bot.binance_client import BinanceClient
from bot.indicators import Indicators
from bot.market_regime import MarketRegime
from bot.ml_model import MLModel
from bot.ai_engine import AIEngine
from bot.risk_manager import RiskManager


def fetch_historical_klines(client, interval="1h", days=30):
    """Fetch historical klines in chunks (Binance limit 1000 per request)."""
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    all_klines = []
    while start_ms < end_ms:
        chunk = client.get_klines(interval=interval, limit=1000, start_time=start_ms, end_time=end_ms)
        if not chunk:
            break
        all_klines.extend(chunk)
        start_ms = chunk[-1][0] + 1
        if len(chunk) < 1000:
            break
    if not all_klines:
        return None
    df = pd.DataFrame(all_klines, columns=[
        "time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])
    for col in ["open", "high", "low", "close", "volume", "taker_buy_base"]:
        df[col] = df[col].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df.drop_duplicates(subset=["time"]).reset_index(drop=True)


def run_backtest(days=30, initial_balance=10000.0, min_confidence=None):
    min_confidence = min_confidence or config.MIN_CONFIDENCE
    log.info(f"Backtest: last {days} days, balance ${initial_balance:.0f}, min confidence {min_confidence}%")

    client = BinanceClient()
    if not client.client:
        log.error("No Binance connection. Check .env")
        return

    df = fetch_historical_klines(client, interval="1h", days=days)
    if df is None or len(df) < 600:
        log.error(f"Not enough data: got {len(df) if df is not None else 0} bars (need 600+)")
        return

    log.info(f"Loaded {len(df)} bars (1h) from {df['time'].iloc[0]} to {df['time'].iloc[-1]}")

    ml = MLModel()
    ai = AIEngine()
    risk = RiskManager()
    sym_info = client.get_sym_info()

    balance = initial_balance
    equity_curve = [balance]
    trades = []
    lookback = min(500, config.ML_LOOKBACK)
    train_start = lookback

    for i in range(train_start, len(df) - 20):
        # Train ML on past bars (rolling)
        train_df = df.iloc[i - lookback : i]
        if len(train_df) < lookback:
            continue
        ml.train(train_df)

        # Indicators at current bar (use history up to and including i)
        df_slice = df.iloc[: i + 1]
        i1h = Indicators.calculate(df_slice)
        if i1h is None or i1h.atr <= 0:
            continue

        # Regime from 1h only (simplified: use same TF for 5m/1h/4h in backtest)
        regime = MarketRegime.detect(i1h, i1h, i1h, volatility_score=i1h.volatility_score)

        # ML prediction on current bar
        ml_pred = ml.predict(df_slice)
        indicators_mtf = {"5m": i1h, "15m": i1h, "1h": i1h, "4h": i1h}

        # OB/Whale: neutral in backtest (no historical OB/trades)
        decision = ai.decide(indicators_mtf, ml_pred, None, None, regime)

        if decision.signal not in ("LONG", "SHORT") or decision.confidence < min_confidence:
            equity_curve.append(balance)
            continue

        # Entry at next bar open
        entry_price = float(df.iloc[i + 1]["open"])
        atr_val = i1h.atr
        trade_setup = risk.calculate_trade(
            entry_price, atr_val, decision.signal, balance, regime.position_size_factor, sym_info
        )
        if not trade_setup.valid:
            equity_curve.append(balance)
            continue

        # Simulate exit: scan bars until TP1 or SL hit
        pnl = 0.0
        exit_reason = "TIMEOUT"
        for j in range(i + 2, min(i + 48, len(df))):
            bar = df.iloc[j]
            high, low = float(bar["high"]), float(bar["low"])
            if decision.signal == "LONG":
                if high >= trade_setup.tp1:
                    pnl = (trade_setup.tp1 - entry_price) * trade_setup.quantity
                    exit_reason = "TP1"
                    break
                if low <= trade_setup.stop_loss:
                    pnl = (trade_setup.stop_loss - entry_price) * trade_setup.quantity
                    exit_reason = "SL"
                    break
            else:
                if low <= trade_setup.tp1:
                    pnl = (entry_price - trade_setup.tp1) * trade_setup.quantity
                    exit_reason = "TP1"
                    break
                if high >= trade_setup.stop_loss:
                    pnl = (entry_price - trade_setup.stop_loss) * trade_setup.quantity
                    exit_reason = "SL"
                    break
        else:
            # Timeout: exit at last bar close
            close_price = float(df.iloc[min(i + 47, len(df) - 1)]["close"])
            if decision.signal == "LONG":
                pnl = (close_price - entry_price) * trade_setup.quantity
            else:
                pnl = (entry_price - close_price) * trade_setup.quantity

        balance += pnl
        equity_curve.append(balance)
        trades.append({
            "signal": decision.signal,
            "entry": entry_price,
            "pnl": pnl,
            "exit": exit_reason,
            "conf": decision.confidence,
        })

    # --- Report ---
    trades = trades
    n = len(trades)
    if n == 0:
        log.info("No trades taken in backtest period.")
        return

    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = n - wins
    total_pnl = balance - initial_balance
    win_rate = (wins / n * 100) if n else 0
    eq = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)
    drawdown = (peak - eq) / np.where(peak > 0, peak, 1) * 100
    max_dd = float(np.max(drawdown))

    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit or 0)

    print()
    print(C.line("=", 60))
    print(f"  {C.bold(C.cyan('BACKTEST RESULTS'))} ({days} days, 1h bars)")
    print(C.line("=", 60))
    print(f"  Trades:       {n}  (W: {wins}  L: {losses})")
    print(f"  Win rate:     {C.green(f'{win_rate:.1f}%')}")
    print(f"  Total PnL:    {C.pnl(total_pnl)} (${total_pnl:+.2f})")
    print(f"  Return:       {(total_pnl / initial_balance) * 100:+.1f}%")
    print(f"  Profit factor:{C.green(f'{profit_factor:.2f}')}" if profit_factor >= 1 else f"  Profit factor: {C.red(f'{profit_factor:.2f}')}")
    print(f"  Max drawdown: {C.red(f'{max_dd:.1f}%')}")
    print(f"  Final balance: ${balance:.2f}")
    print(C.line("=", 60))


def main():
    parser = argparse.ArgumentParser(description="QUANTUM v3.0 Backtest")
    parser.add_argument("--days", type=int, default=30, help="Number of days of 1h history")
    parser.add_argument("--balance", type=float, default=10000.0, help="Initial balance (USDT)")
    parser.add_argument("--min-confidence", type=float, default=None, help="Min AI confidence (default: config)")
    args = parser.parse_args()
    run_backtest(days=args.days, initial_balance=args.balance, min_confidence=args.min_confidence)


if __name__ == "__main__":
    main()
