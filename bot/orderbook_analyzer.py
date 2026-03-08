"""
Order Book Analyzer - deep analysis of order book structure.
Detects liquidity walls, bid/ask imbalance, sudden liquidity removal,
market pressure score, and slippage estimation.
"""
from dataclasses import dataclass
from bot.logger import log


@dataclass
class OrderBookAnalysis:
    spread_pct: float = 0.0
    bid_depth_usdt: float = 0.0
    ask_depth_usdt: float = 0.0
    total_depth_usdt: float = 0.0
    imbalance_ratio: float = 0.0       # -1 (sell heavy) to +1 (buy heavy)
    pressure_score: float = 50.0        # 0-100 (>50 = buy pressure)
    slippage_est: float = 0.0           # estimated slippage %
    largest_bid_wall: float = 0.0       # largest single bid in USDT
    largest_ask_wall: float = 0.0       # largest single ask in USDT
    bid_wall_price: float = 0.0
    ask_wall_price: float = 0.0
    liquidity_score: float = 50.0       # 0-100 (higher = more liquid)
    signal: str = "NEUTRAL"             # BULLISH, BEARISH, NEUTRAL


class OrderBookAnalyzer:
    def __init__(self):
        self._prev_bid_depth = 0
        self._prev_ask_depth = 0

    def analyze(self, orderbook: dict, price: float = 0, order_size_usdt: float = 5000) -> OrderBookAnalysis:
        """Full order book analysis."""
        r = OrderBookAnalysis()
        if not orderbook or not price:
            return r

        try:
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            if not bids or not asks:
                return r

            # === SPREAD ===
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mid = (best_bid + best_ask) / 2
            r.spread_pct = ((best_ask - best_bid) / mid) * 100 if mid > 0 else 999

            # === DEPTH ===
            bid_levels = [(float(b[0]), float(b[1])) for b in bids[:20]]
            ask_levels = [(float(a[0]), float(a[1])) for a in asks[:20]]

            r.bid_depth_usdt = sum(p * q for p, q in bid_levels)
            r.ask_depth_usdt = sum(p * q for p, q in ask_levels)
            r.total_depth_usdt = r.bid_depth_usdt + r.ask_depth_usdt

            # === IMBALANCE ===
            if r.total_depth_usdt > 0:
                r.imbalance_ratio = (r.bid_depth_usdt - r.ask_depth_usdt) / r.total_depth_usdt
            else:
                r.imbalance_ratio = 0

            # === LIQUIDITY WALLS ===
            # Find largest single order on each side
            for bp, bq in bid_levels:
                val = bp * bq
                if val > r.largest_bid_wall:
                    r.largest_bid_wall = val
                    r.bid_wall_price = bp

            for ap, aq in ask_levels:
                val = ap * aq
                if val > r.largest_ask_wall:
                    r.largest_ask_wall = val
                    r.ask_wall_price = ap

            # === SLIPPAGE ESTIMATION ===
            remaining = order_size_usdt
            total_cost = 0
            for ap, aq in ask_levels:
                level_usdt = ap * aq
                fill = min(remaining, level_usdt)
                total_cost += fill * (ap / best_ask)
                remaining -= fill
                if remaining <= 0:
                    break
            if order_size_usdt > 0 and total_cost > 0:
                r.slippage_est = (total_cost / order_size_usdt - 1) * 100
            else:
                r.slippage_est = 0

            # === LIQUIDITY REMOVAL DETECTION ===
            # Compare with previous depth
            depth_change = 0
            if self._prev_bid_depth > 0:
                bid_change = (r.bid_depth_usdt - self._prev_bid_depth) / self._prev_bid_depth
                ask_change = (r.ask_depth_usdt - self._prev_ask_depth) / self._prev_ask_depth if self._prev_ask_depth > 0 else 0
                depth_change = bid_change - ask_change  # positive = bids growing faster
            self._prev_bid_depth = r.bid_depth_usdt
            self._prev_ask_depth = r.ask_depth_usdt

            # === PRESSURE SCORE ===
            score = 50
            # Imbalance
            score += r.imbalance_ratio * 25
            # Wall analysis
            if r.largest_bid_wall > r.largest_ask_wall * 1.5:
                score += 10  # strong bid support
            elif r.largest_ask_wall > r.largest_bid_wall * 1.5:
                score -= 10  # strong ask resistance
            # Depth change
            score += depth_change * 10
            # Spread
            if r.spread_pct < 0.02:
                score += 5  # tight spread = healthy
            elif r.spread_pct > 0.1:
                score -= 5
            r.pressure_score = max(0, min(100, score))

            # === LIQUIDITY SCORE ===
            liq = 50
            if r.spread_pct < 0.02: liq += 20
            elif r.spread_pct < 0.05: liq += 10
            elif r.spread_pct > 0.3: liq -= 30
            if r.total_depth_usdt > 1_000_000: liq += 20
            elif r.total_depth_usdt > 500_000: liq += 10
            elif r.total_depth_usdt < 50_000: liq -= 20
            if r.slippage_est < 0.01: liq += 10
            elif r.slippage_est > 0.1: liq -= 10
            r.liquidity_score = max(0, min(100, liq))

            # === SIGNAL ===
            if r.pressure_score >= 60:
                r.signal = "BULLISH"
            elif r.pressure_score <= 40:
                r.signal = "BEARISH"
            else:
                r.signal = "NEUTRAL"

            return r

        except Exception as e:
            log.error(f"Orderbook analysis error: {e}")
            return r
