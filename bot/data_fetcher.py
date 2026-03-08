"""
Data Fetcher - collects all market data across multiple timeframes.
Returns structured DataFrames ready for analysis.
"""
import pandas as pd
import numpy as np
from bot.logger import log
from bot.config import config


class DataFetcher:
    def __init__(self, client):
        self.client = client

    def fetch_klines_df(self, interval="5m", limit=500):
        """Fetch klines and return as DataFrame."""
        klines = self.client.get_klines(interval=interval, limit=limit)
        if not klines:
            return None
        df = pd.DataFrame(klines, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        for col in ["open", "high", "low", "close", "volume", "quote_volume",
                     "taker_buy_base", "taker_buy_quote"]:
            df[col] = df[col].astype(float)
        df["trades"] = df["trades"].astype(int)
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df

    def fetch_all_timeframes(self):
        """Fetch klines for all configured timeframes."""
        data = {}
        for tf in config.TIMEFRAMES:
            df = self.fetch_klines_df(interval=tf, limit=config.ML_LOOKBACK)
            if df is not None:
                data[tf] = df
        return data

    def fetch_orderbook(self):
        """Fetch order book depth."""
        return self.client.get_orderbook(limit=config.OB_DEPTH_LEVELS)

    def fetch_recent_trades(self, limit=500):
        """Fetch recent trades for whale detection."""
        return self.client.get_recent_trades(limit=limit)

    def fetch_funding_rate(self, limit=8):
        """Fetch funding rate history."""
        data = self.client.get_funding_rate(limit=limit)
        if not data:
            return []
        return data

    def fetch_open_interest(self):
        """Fetch current open interest."""
        return self.client.get_open_interest()

    def fetch_oi_history(self, period="5m", limit=12):
        """Fetch open interest history."""
        return self.client.get_open_interest_hist(period=period, limit=limit)

    def fetch_market_snapshot(self):
        """Fetch complete market snapshot - all data in one call."""
        snapshot = {
            "klines": self.fetch_all_timeframes(),
            "orderbook": self.fetch_orderbook(),
            "recent_trades": self.fetch_recent_trades(),
            "funding_rate": self.fetch_funding_rate(),
            "open_interest": self.fetch_open_interest(),
            "oi_history": self.fetch_oi_history(),
            "mark_price": self.client.get_mark_price(),
            "ticker": self.client.get_ticker(),
        }
        return snapshot
