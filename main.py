#!/usr/bin/env python3
"""
QUANTUM TRADING BOT v3.0 - Institutional Grade
================================================
BTCUSDT Perpetual Futures | ML + Order Book + Whale Detection

Components:
  - Multi-timeframe Technical Analysis (1m/5m/15m/1h/4h)
  - Machine Learning Price Prediction (RF + GB ensemble)
  - Order Book Intelligence (depth, spread, imbalance, walls)
  - Whale Activity Detection (large trades, volume spikes)
  - Market Regime Detection (trending, ranging, volatile)
  - AI Decision Engine (weighted signal combination)
  - ATR-based Risk Management (adaptive SL, R:R TP)
  - Position Management (trailing SL, partial TP)
  - Portfolio Analytics (PnL, win rate, drawdown)
  - Telegram Integration (alerts, commands, inline buttons, rate limit, optional trade confirm)
  - Live Terminal Dashboard

Run:
  python main.py              (LIVE trading)
  python main.py --scan-only  (signals only, no trades)
  python backtest.py --days 30   (historical backtest, 1h bars)
"""

import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.config import config
from bot.logger import log, C
from bot.binance_client import BinanceClient
from bot.data_fetcher import DataFetcher
from bot.indicators import Indicators
from bot.orderbook_analyzer import OrderBookAnalyzer
from bot.whale_detector import WhaleDetector
from bot.market_regime import MarketRegime
from bot.ml_model import MLModel
from bot.ai_engine import AIEngine
from bot.risk_manager import RiskManager
from bot.trade_executor import TradeExecutor
from bot.portfolio import Portfolio
from bot.dashboard import Dashboard
from bot.telegram_alerts import TelegramAlerts


class QuantumBot:
    def __init__(self):
        self.scan_mode = "--scan-only" in sys.argv
        if self.scan_mode:
            config.mode = "scan_only"

        # Initialize all components
        log.info(f"{C.bold(C.cyan('Initializing QUANTUM v3.0...'))}")
        self.client = BinanceClient()
        self.data = DataFetcher(self.client)
        self.ob_analyzer = OrderBookAnalyzer()
        self.whale_detector = WhaleDetector()
        self.ml = MLModel()
        self.ai = AIEngine()
        self.risk = RiskManager()
        self.executor = TradeExecutor(self.client)
        self.portfolio = Portfolio(self.client)
        self.dashboard = Dashboard()
        self.telegram = TelegramAlerts()
        self.telegram.set_bot_ref(self)

        self.scan_count = 0
        self._paused = False
        self._daily_limit_hit = False
        self._last_regime = None
        self._last_decision = None
        self._last_ml = None
        self._last_ob = None

    def execute_confirmed_trade(self, trade_setup, decision):
        """Execute a trade after Telegram confirmation (when TG_CONFIRM_TRADES is True)."""
        if self.scan_mode:
            return
        price = trade_setup.entry_price
        pos = self.executor.open_trade(decision.signal, trade_setup)
        if pos:
            self.portfolio.record_open(
                config.SYMBOL, decision.signal, price,
                trade_setup.quantity, decision.confidence
            )
            self.telegram.notify_trade_open(
                decision.signal, price, trade_setup.quantity,
                trade_setup.stop_loss, trade_setup.tp1,
                decision.confidence, decision.reason[:200]
            )
            time.sleep(1)

    def print_banner(self):
        print(f"\n{C.line('=', 70)}")
        print(f"  {C.bold(C.cyan('QUANTUM TRADING BOT v3.0'))} - {C.white('Institutional Grade')}")
        print(f"{C.line('=', 70)}")
        print(f"  Symbol:       {C.white(config.SYMBOL)}")
        print(f"  Mode:         {C.bg_yellow(' SCAN ONLY ') if self.scan_mode else C.bg_red(' LIVE TRADING ')}")
        print(f"  Leverage:     {C.yellow(f'{config.LEVERAGE}x')} {C.cyan(config.MARGIN_TYPE)}")
        print(f"  Risk/Trade:   {C.red(f'{config.RISK_PER_TRADE}%')} of balance")
        print(f"  Max Exposure: {C.yellow(f'{config.MAX_PORTFOLIO_EXPOSURE}%')}")
        print(f"  Max Positions:{C.white(str(config.MAX_OPEN_POSITIONS))}")
        print(f"  Stop Loss:    ATR x {C.red(str(config.SL_ATR_MULTIPLIER))}")
        print(f"  Take Profit:  {C.green(f'{config.TP_RR_MIN}R')} / {C.green(f'{config.TP_RR_MAX}R')}")
        print(f"  Trailing SL:  {C.green('ON') if config.TRAILING_SL else C.red('OFF')}")
        print(f"  ML Model:     {C.green('RF + Gradient Boosting')}")
        print(f"  Orderbook:    {C.green('Depth + Walls + Imbalance')}")
        print(f"  Whale Detect: {C.green('ON')}")
        print(f"  Timeframes:   {C.cyan(' '.join(config.TIMEFRAMES))}")
        print(f"  Daily Limit:  {C.yellow(f'{config.DAILY_LOSS_LIMIT}%')}")
        if config.TESTNET:
            print(f"  {C.bg_yellow(' TESTNET ')}")
        print(f"{C.line('=', 70)}\n")

    def run_cycle(self):
        """Execute one full trading cycle."""
        self.scan_count += 1
        log.info(C.line("-", 60))
        log.info(f"{C.bold(C.cyan(f'CYCLE #{self.scan_count}'))} - {time.strftime('%H:%M:%S UTC')}")

        # === STEP 1: Fetch all market data ===
        log.info(f"  {C.dim('1.')} Fetching market data...")
        snapshot = self.data.fetch_market_snapshot()
        klines = snapshot["klines"]
        if not klines or "5m" not in klines:
            log.warning("  No market data. Skipping cycle.")
            return

        price = snapshot["mark_price"]
        if price <= 0:
            price = klines["5m"]["close"].iloc[-1]

        # === STEP 2: Analyze order book ===
        log.info(f"  {C.dim('2.')} Analyzing order book...")
        ob = self.ob_analyzer.analyze(snapshot["orderbook"], price)
        self._last_ob = ob

        # === STEP 3: Detect whale activity ===
        log.info(f"  {C.dim('3.')} Detecting whale activity...")
        whales = self.whale_detector.analyze(snapshot["recent_trades"], price)

        # === STEP 4: Calculate indicators ===
        log.info(f"  {C.dim('4.')} Calculating indicators...")
        indicators = Indicators.calculate_multi_timeframe(klines)

        # === STEP 5: Detect market regime ===
        log.info(f"  {C.dim('5.')} Detecting market regime...")
        i5 = indicators.get("5m")
        i1h = indicators.get("1h")
        i4h = indicators.get("4h")
        if i5 and i1h and i4h:
            regime = MarketRegime.detect(i5, i1h, i4h, ob, i5.volatility_score)
        else:
            regime = MarketRegime.detect(i5 or indicators.get("5m"),
                                         i1h or i5, i4h or i5, ob)
        self._last_regime = regime

        # === STEP 6: ML Prediction ===
        log.info(f"  {C.dim('6.')} Running ML prediction...")
        if self.ml.should_retrain():
            log.info(f"  {C.yellow('Retraining ML model...')}")
            df_1h = klines.get("1h")
            if df_1h is not None and len(df_1h) >= 100:
                self.ml.train(df_1h)
        ml_pred = self.ml.predict(klines.get("5m"))
        self._last_ml = ml_pred

        # === STEP 7: AI Decision Engine ===
        log.info(f"  {C.dim('7.')} Running AI decision engine...")
        decision = self.ai.decide(indicators, ml_pred, ob, whales, regime)
        self._last_decision = decision

        # === STEP 8-9: Position sizing + Execute ===
        if decision.signal != "NO_TRADE" and decision.confidence >= config.MIN_CONFIDENCE:
            log.info(f"  {C.dim('8.')} Calculating position size...")

            # Check if we can trade
            pos_count = self.executor.get_position_count()
            if pos_count >= config.MAX_OPEN_POSITIONS:
                log.info(f"  {C.yellow(f'[{pos_count}/{config.MAX_OPEN_POSITIONS}]')} Max positions. Skip.")
            elif self._daily_limit_hit:
                log.info(f"  {C.red('Daily limit hit.')} Skip.")
            elif not self.risk.check_exposure(self.client.get_open_positions(), self.portfolio.stats.balance):
                log.info(f"  {C.yellow('Max exposure reached.')} Skip.")
            elif ob.liquidity_score < 30:
                log.info(f"  {C.red('Low liquidity.')} Skip.")
            elif ob.spread_pct > 0.3:
                log.info(f"  {C.red(f'Spread too wide: {ob.spread_pct:.3f}%')} Skip.")
            else:
                atr = i5.atr if i5 else 0
                atr_raw = i5.atr if i5 else 0
                # Get raw ATR value
                if i5 and price > 0:
                    atr_raw = price * (i5.atr_pct / 100) if hasattr(i5, 'atr_pct') else i5.atr

                balance = self.portfolio.stats.balance
                sym_info = self.client.get_sym_info()
                trade_setup = self.risk.calculate_trade(
                    price, atr_raw, decision.signal, balance,
                    regime.position_size_factor, sym_info
                )

                if trade_setup.valid:
                    log.info(f"\n  {C.bold('EXECUTING')} {C.bg_blue(' TRADE ')}")
                    log.info(f"  Signal:  {C.bg_green(f' {decision.signal} ') if decision.signal == 'LONG' else C.bg_red(f' {decision.signal} ')} Conf: {C.white(f'{decision.confidence:.0f}%')}")
                    log.info(f"  Entry:   {C.white(f'${trade_setup.entry_price:.2f}')} | Qty: {C.cyan(str(trade_setup.quantity))}")
                    log.info(f"  SL:      {C.red(f'${trade_setup.stop_loss:.2f}')} ({trade_setup.risk_pct:.1f}%)")
                    log.info(f"  TP1:     {C.green(f'${trade_setup.tp1:.2f}')} ({config.TP_RR_MIN}R)")
                    log.info(f"  TP3:     {C.green(f'${trade_setup.tp3:.2f}')} ({config.TP_RR_MAX}R)")
                    log.info(f"  Reason:  {C.dim(decision.reason[:100])}")

                    if not self.scan_mode:
                        if getattr(config, "TG_CONFIRM_TRADES", False) and config.TG_ENABLED:
                            self.telegram.request_trade_confirm(trade_setup, decision)
                            log.info(f"  {C.yellow('Trade awaiting Telegram confirmation...')}")
                        else:
                            pos = self.executor.open_trade(decision.signal, trade_setup)
                            if pos:
                                self.portfolio.record_open(
                                    config.SYMBOL, decision.signal, price,
                                    trade_setup.quantity, decision.confidence
                                )
                                self.telegram.notify_trade_open(
                                    decision.signal, price, trade_setup.quantity,
                                    trade_setup.stop_loss, trade_setup.tp1,
                                    decision.confidence, decision.reason[:200]
                                )
                                time.sleep(1)
                    else:
                        log.info(f"  {C.yellow('[SCAN ONLY - no execution]')}")
                else:
                    log.info(f"  {C.yellow(f'Trade rejected: {trade_setup.reject_reason}')}")

        # === STEP 10: Monitor positions ===
        closed = self.executor.monitor_positions()
        for pos in closed:
            # Get realized PnL
            pnl = 0.0
            try:
                if self.client.client:
                    open_ts = 0
                    trades = self.client.client.futures_account_trades(symbol=pos.symbol, limit=20)
                    for t in trades:
                        pnl += float(t.get("realizedPnl", 0))
            except: pass
            reason = "WIN" if pnl >= 0 else "LOSS"
            self.portfolio.record_trade(pos.symbol, pos.direction, pos.entry_price, 0, pnl, reason)
            self.risk.update_daily_pnl(pnl)
            self.telegram.notify_trade_close(pos.symbol, reason, pnl)
            if pnl >= 0:
                log.info(f"  {C.bg_green(' WIN ')} {pos.symbol} | {C.green(f'+${pnl:.2f}')}")
            else:
                log.info(f"  {C.bg_red(' LOSS ')} {pos.symbol} | {C.red(f'-${abs(pnl):.2f}')}")

        # === STEP 11: Update dashboard ===
        self.portfolio.update()
        if self.risk.check_daily_limit(self.portfolio.stats.balance):
            self._daily_limit_hit = True
            self.telegram.notify_daily_limit()

        self.dashboard.display(
            self.portfolio.stats, decision, regime, ml_pred, ob, self.scan_count
        )

    def run(self):
        """Main loop."""
        self.print_banner()

        if not self.client.client:
            log.error(f"{C.bg_red(' ERROR ')} No Binance API! Check .env")
            return

        # Initialize
        self.portfolio.update()
        balance = self.portfolio.stats.balance
        self.risk.reset_daily(balance)

        log.info(f"Balance: {C.green(f'${balance:.2f}')} USDT")

        # Telegram
        self.telegram.notify_startup(balance)
        self.telegram.start_polling()
        if config.TG_ENABLED:
            log.info(f"Telegram: {C.green('ON')}")
        else:
            log.info(f"Telegram: {C.red('OFF')}")

        # Initial ML training
        log.info(f"Training ML model...")
        df_1h = self.data.fetch_klines_df(interval="1h", limit=500)
        if df_1h is not None:
            self.ml.train(df_1h)

        log.info(f"Press {C.yellow('Ctrl+C')} to stop.\n")

        try:
            while True:
                if self._paused or self._daily_limit_hit:
                    reason = "DAILY LIMIT" if self._daily_limit_hit else "PAUSED"
                    log.info(f"{C.bg_yellow(f' {reason} ')} Waiting...")
                    time.sleep(10)
                    continue

                try:
                    self.run_cycle()
                except Exception as e:
                    log.error(f"Cycle error: {C.red(str(e))}")
                    self.telegram.send(f"<b>ERROR</b>\n<code>{str(e)[:500]}</code>")

                # Periodic PnL notification to Telegram every 12 cycles (~12 min)
                if config.TG_ENABLED and self.scan_count > 0 and self.scan_count % 12 == 0:
                    s = self.portfolio.stats
                    self.telegram.notify_pnl_update(
                        s.total_balance, s.daily_pnl, s.daily_pnl_pct, s.total_pnl
                    )

                log.info(f"\n{C.dim(f'Next cycle in {config.SCAN_INTERVAL}s...')}\n")
                time.sleep(config.SCAN_INTERVAL)

        except KeyboardInterrupt:
            log.info(f"\n\n{C.bg_yellow(' SHUTTING DOWN ')}")
            try:
                pnls = self.executor.close_all()
                for pnl in pnls:
                    self.risk.update_daily_pnl(pnl)
                self.portfolio.update()
            except Exception as e:
                log.warning(f"Shutdown API call failed (using cached stats): {e}")

            # Final stats (use cached if update failed)
            s = self.portfolio.stats
            log.info(C.line("=", 60))
            log.info(f"  {C.bold('FINAL STATS')}")
            log.info(f"  Balance: {C.green(f'${s.total_balance:.2f}')}")
            log.info(f"  Total PnL: {C.pnl(s.total_pnl)}")
            log.info(f"  W: {s.wins} L: {s.losses} WR: {s.win_rate:.1f}%")
            log.info(f"  Avg R:R: {s.avg_rr:.1f}")
            log.info(f"  Max Drawdown: {s.max_drawdown:.1f}%")
            log.info(C.line("=", 60))

            # Daily report
            perf = self.portfolio.get_24h_performance()
            self.telegram.notify_daily_report(s, perf)
            self.telegram.notify_shutdown()
            self.telegram.stop_polling()

            log.info(f"{C.bg_red(' BOT STOPPED ')}")


if __name__ == "__main__":
    bot = QuantumBot()
    bot.run()
