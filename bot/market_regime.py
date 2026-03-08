"""
Market Regime Detector - classifies current market conditions.
Regimes: TRENDING_BULLISH, TRENDING_BEARISH, RANGING, HIGH_VOLATILITY, LOW_LIQUIDITY
Strategy adapts based on detected regime.
"""
from dataclasses import dataclass
from bot.logger import log


@dataclass
class RegimeAnalysis:
    regime: str = "RANGING"           # current regime
    confidence: float = 0.0           # 0-100
    trend_strength: float = 0.0       # 0-100
    volatility_level: str = "NORMAL"  # LOW, NORMAL, HIGH, EXTREME
    should_trade: bool = True
    position_size_factor: float = 1.0  # multiply position size
    recommended_sl_mult: float = 1.5   # SL ATR multiplier for this regime
    description: str = ""


class MarketRegime:
    @staticmethod
    def detect(indicators_5m, indicators_1h, indicators_4h,
               ob_analysis=None, volatility_score=0) -> RegimeAnalysis:
        """Detect current market regime using multi-timeframe analysis."""
        r = RegimeAnalysis()

        try:
            i5 = indicators_5m
            i1h = indicators_1h
            i4h = indicators_4h

            # === TREND DETECTION ===
            bullish_signals = 0
            bearish_signals = 0

            # EMA alignment across timeframes
            if i4h.ema_trend == "BULLISH": bullish_signals += 3
            elif i4h.ema_trend == "BEARISH": bearish_signals += 3

            if i1h.ema_trend == "BULLISH": bullish_signals += 2
            elif i1h.ema_trend == "BEARISH": bearish_signals += 2

            if i5.ema_trend == "BULLISH": bullish_signals += 1
            elif i5.ema_trend == "BEARISH": bearish_signals += 1

            # RSI across timeframes
            if i4h.rsi > 55: bullish_signals += 1
            elif i4h.rsi < 45: bearish_signals += 1

            if i1h.rsi > 55: bullish_signals += 1
            elif i1h.rsi < 45: bearish_signals += 1

            # MACD
            if i4h.macd_hist > 0: bullish_signals += 1
            else: bearish_signals += 1

            r.trend_strength = abs(bullish_signals - bearish_signals) / max(bullish_signals + bearish_signals, 1) * 100

            # === VOLATILITY ===
            avg_atr_pct = (i5.atr_pct + i1h.atr_pct) / 2
            if avg_atr_pct > 3:
                r.volatility_level = "EXTREME"
            elif avg_atr_pct > 2:
                r.volatility_level = "HIGH"
            elif avg_atr_pct > 0.5:
                r.volatility_level = "NORMAL"
            else:
                r.volatility_level = "LOW"

            # === REGIME CLASSIFICATION ===
            if r.volatility_level == "EXTREME":
                r.regime = "HIGH_VOLATILITY"
                r.confidence = 80
                r.should_trade = True  # can trade but careful
                r.position_size_factor = 0.5  # half size
                r.recommended_sl_mult = 2.5   # wider SL
                r.description = "Extreme volatility - reduce size, widen stops"

            elif ob_analysis and ob_analysis.liquidity_score < 30:
                r.regime = "LOW_LIQUIDITY"
                r.confidence = 70
                r.should_trade = False
                r.position_size_factor = 0.3
                r.description = "Low liquidity - avoid trading"

            elif bullish_signals >= 6 and r.trend_strength >= 50:
                r.regime = "TRENDING_BULLISH"
                r.confidence = min(95, 50 + r.trend_strength * 0.5)
                r.should_trade = True
                r.position_size_factor = 1.2  # can size up in trend
                r.recommended_sl_mult = 1.5
                r.description = f"Strong bullish trend ({bullish_signals} signals aligned)"

            elif bearish_signals >= 6 and r.trend_strength >= 50:
                r.regime = "TRENDING_BEARISH"
                r.confidence = min(95, 50 + r.trend_strength * 0.5)
                r.should_trade = True
                r.position_size_factor = 1.2
                r.recommended_sl_mult = 1.5
                r.description = f"Strong bearish trend ({bearish_signals} signals aligned)"

            else:
                r.regime = "RANGING"
                r.confidence = 60
                r.should_trade = True
                r.position_size_factor = 0.7  # reduce in range
                r.recommended_sl_mult = 1.2   # tighter SL
                r.description = "Ranging/choppy market - trade with caution"

            return r

        except Exception as e:
            log.error(f"Regime detection error: {e}")
            return r
