"""
Binance Futures API client wrapper.
Handles connection, timestamp sync, order execution, and data fetching.
"""
import time, math
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
from bot.config import config
from bot.logger import log, C

# Retries for transient API errors (rate limit, network)
API_RETRIES = 3
API_RETRY_DELAY = 2.0


def _with_retry(func, *args, **kwargs):
    """Call func with retries on transient failures."""
    last_err = None
    for attempt in range(API_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < API_RETRIES - 1:
                time.sleep(API_RETRY_DELAY)
    raise last_err


class BinanceClient:
    def __init__(self):
        self.client = None
        self.symbol_info = {}
        self._connect()

    def _connect(self):
        try:
            self.client = Client(config.API_KEY, config.API_SECRET, testnet=config.TESTNET)
            # Timestamp sync
            try:
                st = self.client.get_server_time()
                self.client.timestamp_offset = st['serverTime'] - int(time.time() * 1000)
                off = self.client.timestamp_offset / 1000
                if abs(off) > 1:
                    log.info(f"Clock offset: {C.yellow(f'{off:.1f}s')} corrected")
            except: pass
            # Load symbol rules
            try:
                info = self.client.futures_exchange_info()
                for s in info["symbols"]:
                    filt = {f["filterType"]: f for f in s.get("filters", [])}
                    lot = filt.get("LOT_SIZE", {})
                    mlot = filt.get("MARKET_LOT_SIZE", {})
                    self.symbol_info[s["symbol"]] = {
                        "min_qty": float(lot.get("minQty", 0.001)),
                        "max_qty": float(mlot.get("maxQty", 0) or lot.get("maxQty", 999999999)),
                        "step_size": float(lot.get("stepSize", 0.001)),
                        "price_precision": s.get("pricePrecision", 2),
                        "qty_precision": s.get("quantityPrecision", 3),
                        "onboard_date": s.get("onboardDate", 0),
                    }
                log.info(f"Loaded {C.white(str(len(self.symbol_info)))} symbol rules")
            except Exception as e:
                log.warning(f"Symbol info failed: {e}")

            tag = C.yellow("TESTNET") if config.TESTNET else C.green("LIVE")
            log.info(f"Binance connected [{tag}]")
        except Exception as e:
            log.error(f"Binance connection failed: {e}")

    def get_sym_info(self, sym=None):
        sym = sym or config.SYMBOL
        return self.symbol_info.get(sym, {
            "min_qty": 0.001, "max_qty": 999999999, "step_size": 0.001,
            "qty_precision": 3, "price_precision": 2
        })

    # --- Data Fetching ---
    def get_klines(self, interval="5m", limit=500, symbol=None, start_time=None, end_time=None):
        sym = symbol or config.SYMBOL
        try:
            kwargs = {"symbol": sym, "interval": interval, "limit": limit}
            if start_time is not None:
                kwargs["startTime"] = start_time
            if end_time is not None:
                kwargs["endTime"] = end_time
            return self.client.futures_klines(**kwargs)
        except Exception as e:
            log.error(f"Klines {sym} {interval}: {e}")
            return None

    def get_orderbook(self, limit=20, symbol=None):
        sym = symbol or config.SYMBOL
        try:
            return self.client.futures_order_book(symbol=sym, limit=limit)
        except Exception as e:
            log.warning(f"Orderbook {sym}: {e}")
            return None

    def get_recent_trades(self, limit=100, symbol=None):
        sym = symbol or config.SYMBOL
        try:
            return self.client.futures_recent_trades(symbol=sym, limit=limit)
        except Exception as e:
            log.warning(f"Recent trades {sym}: {e}")
            return []

    def get_ticker(self, symbol=None):
        sym = symbol or config.SYMBOL
        try:
            return self.client.futures_ticker(symbol=sym)
        except Exception as e:
            log.warning(f"Ticker {sym}: {e}")
            return None

    def get_funding_rate(self, limit=8, symbol=None):
        sym = symbol or config.SYMBOL
        try:
            return self.client.futures_funding_rate(symbol=sym, limit=limit)
        except Exception as e:
            log.warning(f"Funding rate {sym}: {e}")
            return []

    def get_open_interest(self, symbol=None):
        sym = symbol or config.SYMBOL
        try:
            return float(self.client.futures_open_interest(symbol=sym).get("openInterest", 0))
        except Exception as e:
            log.warning(f"Open interest {sym}: {e}")
            return 0.0

    def get_open_interest_hist(self, period="5m", limit=12, symbol=None):
        sym = symbol or config.SYMBOL
        try:
            return self.client.futures_open_interest_hist(symbol=sym, period=period, limit=limit)
        except Exception as e:
            log.warning(f"OI history {sym}: {e}")
            return []

    def get_mark_price(self, symbol=None):
        sym = symbol or config.SYMBOL
        try:
            return float(self.client.futures_mark_price(symbol=sym)["markPrice"])
        except Exception as e:
            log.warning(f"Mark price {sym}: {e}")
            return 0.0

    # --- Account ---
    def get_balance(self):
        if not self.client:
            return 0.0
        try:
            account = _with_retry(self.client.futures_account)
            for a in account["assets"]:
                if a["asset"] == "USDT":
                    return float(a["availableBalance"])
            return 0.0
        except Exception as e:
            log.error(f"Balance: {e}")
            return 0.0

    def get_total_balance(self):
        if not self.client:
            return 0.0
        try:
            account = _with_retry(self.client.futures_account)
            for a in account["assets"]:
                if a["asset"] == "USDT":
                    return float(a["walletBalance"])
            return 0.0
        except Exception as e:
            log.warning(f"Total balance: {e}")
            return 0.0

    def get_open_positions(self):
        if not self.client:
            return None
        try:
            positions = _with_retry(self.client.futures_position_information)
            return [p for p in positions if float(p["positionAmt"]) != 0]
        except Exception as e:
            log.warning(f"Open positions: {e}")
            return None

    # --- Order Execution ---
    def set_leverage(self, leverage=None, symbol=None):
        sym = symbol or config.SYMBOL
        lev = leverage or config.LEVERAGE
        try:
            self.client.futures_change_leverage(symbol=sym, leverage=lev)
        except Exception as e:
            log.warning(f"Set leverage {sym}: {e}")

    def set_margin_type(self, margin_type=None, symbol=None):
        sym = symbol or config.SYMBOL
        mt = margin_type or config.MARGIN_TYPE
        try:
            self.client.futures_change_margin_type(symbol=sym, marginType=mt)
        except Exception as e:
            log.warning(f"Set margin type {sym}: {e}")

    def cancel_all_orders(self, symbol=None):
        sym = symbol or config.SYMBOL
        try:
            self.client.futures_cancel_all_open_orders(symbol=sym)
        except Exception as e:
            log.warning(f"Cancel orders {sym}: {e}")

    def market_order(self, side, quantity, symbol=None):
        sym = symbol or config.SYMBOL
        try:
            return self.client.futures_create_order(
                symbol=sym, side=side, type="MARKET", quantity=quantity
            )
        except Exception as e:
            log.error(f"Market order {sym} {side}: {e}")
            return None

    def stop_loss_order(self, side, stop_price, symbol=None):
        sym = symbol or config.SYMBOL
        si = self.get_sym_info(sym)
        pp = si.get("price_precision", 2)
        try:
            return self.client.futures_create_order(
                symbol=sym, side=side, type="STOP_MARKET",
                stopPrice=str(round(stop_price, pp)), closePosition="true"
            )
        except Exception as e:
            log.error(f"SL {sym}: {e}")
            return None

    def take_profit_order(self, side, stop_price, quantity, symbol=None):
        sym = symbol or config.SYMBOL
        si = self.get_sym_info(sym)
        pp = si.get("price_precision", 2)
        qp = si.get("qty_precision", 3)
        try:
            return self.client.futures_create_order(
                symbol=sym, side=side, type="TAKE_PROFIT_MARKET",
                stopPrice=str(round(stop_price, pp)),
                quantity=str(round(quantity, qp))
            )
        except Exception as e:
            log.error(f"TP {sym}: {e}")
            return None

    # --- Utility ---
    def round_qty(self, qty, symbol=None):
        si = self.get_sym_info(symbol)
        step = si["step_size"]
        prec = si["qty_precision"]
        return round(math.floor(qty / step) * step, prec)

    def round_price(self, price, symbol=None):
        si = self.get_sym_info(symbol)
        return round(price, si["price_precision"])
