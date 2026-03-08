"""
AI Decision Engine - the brain of the trading system.
Combines technical indicators, ML prediction, order book pressure,
whale activity, and market regime into a final trading decision.
"""
from dataclasses import dataclass
from bot.config import config
from bot.logger import log, C


@dataclass
class AIDecision:
    signal: str = "NO_TRADE"        # LONG, SHORT, NO_TRADE
    confidence: float = 0.0          # 0-100
    reason: str = ""
    # Component scores
    technical_score: float = 0.0
    ml_score: float = 0.0
    orderbook_score: float = 0.0
    whale_score: float = 0.0
    regime_score: float = 0.0
    # Details
    components: dict = None


class AIEngine:
    def __init__(self):
        self.weights = config.SIGNAL_WEIGHTS

    def decide(self, indicators_mtf: dict, ml_prediction, ob_analysis,
               whale_analysis, regime_analysis) -> AIDecision:
        """Generate final trading decision."""
        d = AIDecision()
        d.components = {}
        reasons = []

        try:
            # Get primary timeframe indicators
            i5 = indicators_mtf.get("5m")
            i15 = indicators_mtf.get("15m")
            i1h = indicators_mtf.get("1h")
            i4h = indicators_mtf.get("4h")

            if not i5 or not i1h:
                d.reason = "Insufficient indicator data"
                return d

            # === 1. TECHNICAL SCORE (0-100, centered at 50) ===
            tech_bull = 0
            tech_bear = 0

            # Multi-timeframe trend alignment
            for tf, ind in indicators_mtf.items():
                weight = {"1m": 0.5, "5m": 1, "15m": 1.5, "1h": 2, "4h": 3}.get(tf, 1)
                if ind.ema_trend == "BULLISH": tech_bull += weight
                elif ind.ema_trend == "BEARISH": tech_bear += weight

            # RSI
            if i5.rsi > 55 and i1h.rsi > 50: tech_bull += 2
            elif i5.rsi < 45 and i1h.rsi < 50: tech_bear += 2

            # MACD
            if i5.macd_hist > 0 and i1h.macd_hist > 0: tech_bull += 2
            elif i5.macd_hist < 0 and i1h.macd_hist < 0: tech_bear += 2

            # VWAP
            if i5.price_vs_vwap > 0: tech_bull += 1
            else: tech_bear += 1

            # Volume
            if i5.buy_pressure > 0.55: tech_bull += 1.5
            elif i5.sell_pressure > 0.55: tech_bear += 1.5

            # StochRSI
            if i5.stoch_rsi_signal == "OVERSOLD": tech_bull += 1  # bounce potential
            elif i5.stoch_rsi_signal == "OVERBOUGHT": tech_bear += 1

            total_tech = tech_bull + tech_bear
            if total_tech > 0:
                d.technical_score = (tech_bull / total_tech) * 100
            else:
                d.technical_score = 50

            tech_direction = "LONG" if d.technical_score > 55 else "SHORT" if d.technical_score < 45 else "NEUTRAL"
            reasons.append(f"Tech: {tech_direction} ({d.technical_score:.0f})")
            d.components["technical"] = {"bull": tech_bull, "bear": tech_bear, "direction": tech_direction}

            # === 2. ML SCORE (0-100) ===
            if ml_prediction and ml_prediction.confidence > 0:
                # Only use ML signal if test-set accuracy is above threshold (avoid overfit)
                if getattr(ml_prediction, "model_accuracy", 0) < config.ML_MIN_TEST_ACCURACY:
                    d.ml_score = 50
                    reasons.append(f"ML: neutral (test acc {getattr(ml_prediction, 'model_accuracy', 0):.1%} < {config.ML_MIN_TEST_ACCURACY:.0%})")
                else:
                    if ml_prediction.prediction == "UP":
                        d.ml_score = 50 + ml_prediction.confidence * 0.5
                    elif ml_prediction.prediction == "DOWN":
                        d.ml_score = 50 - ml_prediction.confidence * 0.5
                    else:
                        d.ml_score = 50
                    ml_dir = "LONG" if d.ml_score > 55 else "SHORT" if d.ml_score < 45 else "NEUTRAL"
                    reasons.append(f"ML: {ml_dir} ({ml_prediction.up_probability:.0%} up)")
            else:
                d.ml_score = 50
                reasons.append("ML: no prediction")

            # === 3. ORDERBOOK SCORE (0-100) ===
            if ob_analysis:
                d.orderbook_score = ob_analysis.pressure_score
                reasons.append(f"OB: {ob_analysis.signal} ({ob_analysis.pressure_score:.0f})")
            else:
                d.orderbook_score = 50

            # === 4. WHALE SCORE (0-100) ===
            if whale_analysis and whale_analysis.whale_score > 0:
                if whale_analysis.whale_bias > 0:
                    d.whale_score = 50 + whale_analysis.whale_score * 0.5
                elif whale_analysis.whale_bias < 0:
                    d.whale_score = 50 - whale_analysis.whale_score * 0.5
                else:
                    d.whale_score = 50
                reasons.append(f"Whale: {whale_analysis.signal} (bias {whale_analysis.whale_bias:+.2f})")
            else:
                d.whale_score = 50

            # === 5. REGIME SCORE (0-100) ===
            if regime_analysis:
                if regime_analysis.regime == "TRENDING_BULLISH":
                    d.regime_score = 75
                elif regime_analysis.regime == "TRENDING_BEARISH":
                    d.regime_score = 25
                elif regime_analysis.regime == "HIGH_VOLATILITY":
                    d.regime_score = 50  # neutral but cautious
                elif regime_analysis.regime == "LOW_LIQUIDITY":
                    d.regime_score = 50
                else:
                    d.regime_score = 50
                reasons.append(f"Regime: {regime_analysis.regime}")

                # Don't trade in bad regimes
                if not regime_analysis.should_trade:
                    d.signal = "NO_TRADE"
                    d.confidence = 0
                    d.reason = f"Regime: {regime_analysis.regime} - {regime_analysis.description}"
                    return d
            else:
                d.regime_score = 50

            # === WEIGHTED COMBINATION ===
            w = self.weights
            combined = (
                d.technical_score * w["technical"] +
                d.ml_score * w["ml_prediction"] +
                d.orderbook_score * w["orderbook"] +
                d.whale_score * w["whale_activity"] +
                d.regime_score * w["market_regime"]
            )

            # Confidence = how far from neutral (50)
            d.confidence = abs(combined - 50) * 2  # 0-100

            # === FINAL DECISION ===
            if combined >= 60 and d.confidence >= config.MIN_CONFIDENCE:
                d.signal = "LONG"
            elif combined <= 40 and d.confidence >= config.MIN_CONFIDENCE:
                d.signal = "SHORT"
            else:
                d.signal = "NO_TRADE"

            d.reason = " | ".join(reasons)

            return d

        except Exception as e:
            log.error(f"AI Engine error: {e}")
            d.reason = f"Error: {e}"
            return d

    def explain(self, decision: AIDecision) -> str:
        """Human-readable explanation of the decision."""
        lines = [
            f"Signal: {decision.signal} (Confidence: {decision.confidence:.0f}%)",
            f"Tech: {decision.technical_score:.0f} | ML: {decision.ml_score:.0f} | "
            f"OB: {decision.orderbook_score:.0f} | Whale: {decision.whale_score:.0f} | "
            f"Regime: {decision.regime_score:.0f}",
            f"Reason: {decision.reason}"
        ]
        return "\n".join(lines)
