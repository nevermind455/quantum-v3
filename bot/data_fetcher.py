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

    def fetch_klines_df(self, interval="5m", limit=500, symbol=None):
        """Fetch klines and return as DataFrame."""
        klines = self.client.get_klines(interval=interval, limit=limit, symbol=symbol)
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

    def fetch_all_timeframes(self, symbol=None):
        """Fetch klines for all configured timeframes."""
        data = {}
        for tf in config.TIMEFRAMES:
            df = self.fetch_klines_df(interval=tf, limit=config.ML_LOOKBACK, symbol=symbol)
            if df is not None:
                data[tf] = df
        return data

    def fetch_orderbook(self, symbol=None):
        """Fetch order book depth."""
        return self.client.get_orderbook(limit=config.OB_DEPTH_LEVELS, symbol=symbol)

    def fetch_recent_trades(self, limit=500, symbol=None):
        """Fetch recent trades for whale detection."""
        return self.client.get_recent_trades(limit=limit, symbol=symbol)

    def fetch_funding_rate(self, limit=8, symbol=None):
        """Fetch funding rate history."""
        data = self.client.get_funding_rate(limit=limit, symbol=symbol)
        if not data:
            return []
        return data

    def fetch_open_interest(self, symbol=None):
        """Fetch current open interest."""
        return self.client.get_open_interest(symbol=symbol)

    def fetch_oi_history(self, period="5m", limit=12, symbol=None):
        """Fetch open interest history."""
        return self.client.get_open_interest_hist(period=period, limit=limit, symbol=symbol)

    def fetch_market_snapshot(self, symbol=None):
        """Fetch complete market snapshot for one symbol."""
        sym = symbol or config.SYMBOL
        snapshot = {
            "klines": self.fetch_all_timeframes(symbol=sym),
            "orderbook": self.fetch_orderbook(symbol=sym),
            "recent_trades": self.fetch_recent_trades(symbol=sym),
            "funding_rate": self.fetch_funding_rate(symbol=sym),
            "open_interest": self.fetch_open_interest(symbol=sym),
            "oi_history": self.fetch_oi_history(symbol=sym),
            "mark_price": self.client.get_mark_price(symbol=sym),
            "ticker": self.client.get_ticker(symbol=sym),
        }
        return snapshot
