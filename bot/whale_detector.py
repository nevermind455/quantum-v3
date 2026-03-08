"""
Whale Activity Detector - identifies abnormal large trades and volume spikes.
Tracks large market orders, sudden volume surges, and creates a whale activity score.
"""
from dataclasses import dataclass, field
from collections import deque
from bot.config import config
from bot.logger import log


@dataclass
class WhaleAnalysis:
    whale_score: float = 0.0          # 0-100
    large_buys: int = 0               # count of whale buy orders
    large_sells: int = 0              # count of whale sell orders
    total_whale_volume: float = 0.0   # total $ volume of whale trades
    buy_whale_volume: float = 0.0
    sell_whale_volume: float = 0.0
    whale_bias: float = 0.0           # -1 (selling) to +1 (buying)
    volume_spike_detected: bool = False
    signal: str = "NEUTRAL"           # BULLISH, BEARISH, NEUTRAL


class WhaleDetector:
    def __init__(self):
        self._recent_whale_trades = deque(maxlen=100)
        self._avg_trade_size = 0
        self._volume_history = deque(maxlen=50)

    def analyze(self, recent_trades: list, current_price: float = 0) -> WhaleAnalysis:
        """Analyze recent trades for whale activity."""
        r = WhaleAnalysis()
        if not recent_trades or not current_price:
            return r

        try:
            threshold = config.WHALE_TRADE_THRESHOLD  # $50K default
            trade_sizes = []

            for t in recent_trades:
                qty = float(t.get("qty", 0))
                price = float(t.get("price", current_price))
                value = qty * price
                is_buyer = t.get("isBuyerMaker", False) == False  # taker = buyer
                trade_sizes.append(value)

                # Detect whale trades
                if value >= threshold:
                    if is_buyer:
                        r.large_buys += 1
                        r.buy_whale_volume += value
                    else:
                        r.large_sells += 1
                        r.sell_whale_volume += value
                    r.total_whale_volume += value
                    self._recent_whale_trades.append({
                        "value": value, "is_buy": is_buyer, "price": price
                    })

            # Average trade size
            if trade_sizes:
                current_avg = sum(trade_sizes) / len(trade_sizes)
                if self._avg_trade_size > 0:
                    # Volume spike = current avg much higher than historical
                    if current_avg > self._avg_trade_size * 2:
                        r.volume_spike_detected = True
                self._avg_trade_size = current_avg * 0.1 + self._avg_trade_size * 0.9  # EMA

            # Whale bias
            total_whale = r.buy_whale_volume + r.sell_whale_volume
            if total_whale > 0:
                r.whale_bias = (r.buy_whale_volume - r.sell_whale_volume) / total_whale
            else:
                r.whale_bias = 0

            # === WHALE SCORE ===
            score = 0

            # Number of whale trades
            total_whales = r.large_buys + r.large_sells
            if total_whales >= 5: score += 30
            elif total_whales >= 3: score += 20
            elif total_whales >= 1: score += 10

            # Whale volume magnitude
            if r.total_whale_volume > 500_000: score += 25
            elif r.total_whale_volume > 200_000: score += 15
            elif r.total_whale_volume > 100_000: score += 10

            # Directional bias strength
            score += abs(r.whale_bias) * 25

            # Volume spike
            if r.volume_spike_detected: score += 20

            r.whale_score = min(100, score)

            # Signal
            if r.whale_score >= 40:
                if r.whale_bias > 0.3:
                    r.signal = "BULLISH"
                elif r.whale_bias < -0.3:
                    r.signal = "BEARISH"
                else:
                    r.signal = "NEUTRAL"
            else:
                r.signal = "NEUTRAL"

            return r

        except Exception as e:
            log.error(f"Whale detection error: {e}")
            return r
