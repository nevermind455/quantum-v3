"""
Technical Indicators - calculates all indicators across timeframes.
RSI, MACD, EMA 20/50/200, ATR, Bollinger Bands, VWAP, Stochastic RSI,
volume delta, buy/sell pressure, volatility score.
"""
import pandas as pd
import numpy as np
import ta
from dataclasses import dataclass
from bot.logger import log


@dataclass
class IndicatorResult:
    # Trend
    ema_20: float = 0.0
    ema_50: float = 0.0
    ema_200: float = 0.0
    ema_trend: str = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL
    macd_hist: float = 0.0
    macd_signal_cross: int = 0  # 1=bullish cross, -1=bearish, 0=none

    # Momentum
    rsi: float = 50.0
    stoch_rsi_k: float = 50.0
    stoch_rsi_d: float = 50.0
    stoch_rsi_signal: str = "NEUTRAL"  # OVERBOUGHT, OVERSOLD, NEUTRAL

    # Volatility
    atr: float = 0.0
    atr_pct: float = 0.0  # ATR as % of price
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    bb_width: float = 0.0
    bb_position: float = 0.0  # -1 to 1
    volatility_score: float = 0.0  # 0-100

    # Volume
    vwap: float = 0.0
    price_vs_vwap: float = 0.0  # % above/below VWAP
    volume_spike: float = 1.0
    volume_delta: float = 0.0  # buy vol - sell vol
    buy_pressure: float = 0.5  # 0-1
    sell_pressure: float = 0.5

    # Combined
    trend_score: float = 50.0  # 0-100
    momentum_score: float = 50.0
    overall_score: float = 50.0


class Indicators:
    @staticmethod
    def calculate(df: pd.DataFrame) -> IndicatorResult:
        """Calculate all indicators from a klines DataFrame."""
        if df is None or len(df) < 50:
            return IndicatorResult()

        try:
            r = IndicatorResult()
            close = df["close"]
            high = df["high"]
            low = df["low"]
            volume = df["volume"]
            price = close.iloc[-1]

            # === TREND ===
            r.ema_20 = ta.trend.EMAIndicator(close, window=20).ema_indicator().iloc[-1]
            r.ema_50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1]
            if len(close) >= 200:
                r.ema_200 = ta.trend.EMAIndicator(close, window=200).ema_indicator().iloc[-1]
            else:
                r.ema_200 = r.ema_50

            # EMA trend
            if r.ema_20 > r.ema_50 > r.ema_200:
                r.ema_trend = "BULLISH"
            elif r.ema_20 < r.ema_50 < r.ema_200:
                r.ema_trend = "BEARISH"
            else:
                r.ema_trend = "NEUTRAL"

            # MACD
            macd = ta.trend.MACD(close)
            r.macd_hist = macd.macd_diff().iloc[-1]
            macd_diff = macd.macd_diff()
            if len(macd_diff) >= 2:
                if macd_diff.iloc[-1] > 0 and macd_diff.iloc[-2] <= 0:
                    r.macd_signal_cross = 1  # bullish cross
                elif macd_diff.iloc[-1] < 0 and macd_diff.iloc[-2] >= 0:
                    r.macd_signal_cross = -1  # bearish cross

            # === MOMENTUM ===
            r.rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]

            # Stochastic RSI
            stoch = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
            r.stoch_rsi_k = stoch.stochrsi_k().iloc[-1] * 100
            r.stoch_rsi_d = stoch.stochrsi_d().iloc[-1] * 100
            if r.stoch_rsi_k > 80:
                r.stoch_rsi_signal = "OVERBOUGHT"
            elif r.stoch_rsi_k < 20:
                r.stoch_rsi_signal = "OVERSOLD"

            # === VOLATILITY ===
            atr_ind = ta.volatility.AverageTrueRange(high, low, close, window=14)
            r.atr = atr_ind.average_true_range().iloc[-1]
            r.atr_pct = (r.atr / price) * 100

            bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
            r.bb_upper = bb.bollinger_hband().iloc[-1]
            r.bb_lower = bb.bollinger_lband().iloc[-1]
            r.bb_width = ((r.bb_upper - r.bb_lower) / price) * 100
            mid = bb.bollinger_mavg().iloc[-1]
            if r.bb_upper != r.bb_lower:
                r.bb_position = (price - mid) / ((r.bb_upper - r.bb_lower) / 2)

            # Volatility score (0-100)
            r.volatility_score = min(100, r.atr_pct * 20 + r.bb_width * 10)

            # === VOLUME ===
            # VWAP
            typical = (high + low + close) / 3
            cum_vol = volume.cumsum()
            r.vwap = ((typical * volume).cumsum() / cum_vol).iloc[-1]
            r.price_vs_vwap = ((price - r.vwap) / r.vwap) * 100

            # Volume spike
            avg_vol = volume.rolling(20).mean().iloc[-1]
            r.volume_spike = volume.iloc[-1] / avg_vol if avg_vol > 0 else 1.0

            # Volume delta (buy vs sell)
            taker_buy = df["taker_buy_base"].astype(float)
            taker_sell = volume - taker_buy
            r.volume_delta = (taker_buy.iloc[-5:].sum() - taker_sell.iloc[-5:].sum())
            total_recent = volume.iloc[-5:].sum()
            r.buy_pressure = taker_buy.iloc[-5:].sum() / total_recent if total_recent > 0 else 0.5
            r.sell_pressure = 1 - r.buy_pressure

            # === COMBINED SCORES ===
            # Trend score (0-100)
            trend_pts = 50
            if r.ema_trend == "BULLISH": trend_pts += 20
            elif r.ema_trend == "BEARISH": trend_pts -= 20
            if r.macd_hist > 0: trend_pts += 15
            else: trend_pts -= 15
            if price > r.vwap: trend_pts += 15
            else: trend_pts -= 15
            r.trend_score = max(0, min(100, trend_pts))

            # Momentum score (0-100)
            mom_pts = 50
            if 55 < r.rsi < 70: mom_pts += 20
            elif 30 < r.rsi < 45: mom_pts -= 10
            elif r.rsi >= 70: mom_pts -= 15  # overbought
            elif r.rsi <= 30: mom_pts += 10   # oversold bounce
            if r.volume_spike > 2: mom_pts += 15
            elif r.volume_spike > 1.3: mom_pts += 8
            if abs(r.bb_position) > 0.8: mom_pts += 10
            r.momentum_score = max(0, min(100, mom_pts))

            # Overall
            r.overall_score = (r.trend_score * 0.5 + r.momentum_score * 0.5)

            return r

        except Exception as e:
            log.error(f"Indicators error: {e}")
            return IndicatorResult()

    @staticmethod
    def calculate_multi_timeframe(klines_dict: dict) -> dict:
        """Calculate indicators for all timeframes."""
        results = {}
        for tf, df in klines_dict.items():
            results[tf] = Indicators.calculate(df)
        return results
