"""
Live Terminal Dashboard - displays all trading information.
"""
from bot.logger import log, C


class Dashboard:
    def __init__(self):
        self.last_signal = None
        self.last_regime = None

    def display(self, portfolio_stats, ai_decision=None, regime=None,
                ml_prediction=None, ob_analysis=None, scan_count=0):
        """Display full dashboard."""
        s = portfolio_stats

        # Stats bar
        wr = C.green(f"{s.win_rate:.0f}%") if s.win_rate >= 50 else C.red(f"{s.win_rate:.0f}%")
        streak = C.green(f"{s.current_streak:+d}") if s.current_streak > 0 else C.red(f"{s.current_streak:+d}") if s.current_streak < 0 else C.dim("+0")
        dd = C.red(f"{s.max_drawdown:.1f}%") if s.max_drawdown > 3 else C.yellow(f"{s.max_drawdown:.1f}%")

        log.info(C.line("=", 80))
        log.info(
            f"  {C.bold(C.cyan('QUANTUM v3.0'))} | "
            f"Bal: {C.green(f'${s.balance:.2f}')} | "
            f"PnL: {C.pnl(s.total_pnl)} | "
            f"Daily: {C.pnl(s.daily_pnl)} ({s.daily_pnl_pct:+.1f}%) | "
            f"DD: {dd}"
        )
        log.info(
            f"  W:{C.green(str(s.wins))} L:{C.red(str(s.losses))} "
            f"WR:{wr} | RR:{C.white(f'{s.avg_rr:.1f}')} | "
            f"Streak:{streak} | "
            f"Open:{C.yellow(str(s.open_positions))}/{C.dim('3')} | "
            f"Scans:{C.dim(str(scan_count))}"
        )

        # AI Decision
        if ai_decision:
            sig = ai_decision.signal
            if sig == "LONG":
                sig_display = C.bg_green(f" {sig} ")
            elif sig == "SHORT":
                sig_display = C.bg_red(f" {sig} ")
            else:
                sig_display = C.dim(f"[{sig}]")

            log.info(
                f"  AI: {sig_display} Conf: {C.white(f'{ai_decision.confidence:.0f}%')} | "
                f"Tech:{ai_decision.technical_score:.0f} ML:{ai_decision.ml_score:.0f} "
                f"OB:{ai_decision.orderbook_score:.0f} Whale:{ai_decision.whale_score:.0f}"
            )

        # Regime
        if regime:
            regime_colors = {
                "TRENDING_BULLISH": C.green,
                "TRENDING_BEARISH": C.red,
                "RANGING": C.yellow,
                "HIGH_VOLATILITY": C.magenta,
                "LOW_LIQUIDITY": C.red,
            }
            rc = regime_colors.get(regime.regime, C.dim)
            log.info(f"  Regime: {rc(regime.regime)} ({regime.confidence:.0f}%) | {C.dim(regime.description)}")

        # ML
        if ml_prediction and ml_prediction.confidence > 0:
            up = ml_prediction.up_probability
            pred_color = C.green if up > 0.55 else C.red if up < 0.45 else C.yellow
            log.info(f"  ML: {pred_color(ml_prediction.prediction)} | Up: {pred_color(f'{up:.0%}')} | Acc: {C.dim(f'{ml_prediction.model_accuracy:.0%}')}")

        # Orderbook
        if ob_analysis:
            ob_color = C.green if ob_analysis.signal == "BULLISH" else C.red if ob_analysis.signal == "BEARISH" else C.dim
            log.info(
                f"  OB: {ob_color(ob_analysis.signal)} | "
                f"Spread: {C.cyan(f'{ob_analysis.spread_pct:.4f}%')} | "
                f"Depth: {C.cyan(f'${ob_analysis.total_depth_usdt/1000:.0f}K')} | "
                f"Imbal: {C.yellow(f'{ob_analysis.imbalance_ratio:+.2f}')}"
            )

        log.info(C.line("=", 80))
