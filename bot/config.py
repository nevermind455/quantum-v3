"""
Configuration module - loads .env and provides all system settings.
"""
import os
from dataclasses import dataclass, field
from typing import List

def _load_env():
    placeholders = ("", "YOUR_BINANCE_API_KEY_HERE", "YOUR_BINANCE_API_SECRET_HERE",
                    "YOUR_TELEGRAM_BOT_TOKEN_HERE", "YOUR_TELEGRAM_CHAT_ID_HERE")
    script_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cwd = os.getcwd()
    for base in (script_root, cwd):
        if not base:
            continue
        for name in (".env", ".env.example"):
            env_path = os.path.join(base, name)
            if not os.path.exists(env_path):
                continue
            try:
                with open(env_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if key and (key not in os.environ or os.environ[key] in placeholders):
                                os.environ[key] = val
            except Exception:
                pass

_load_env()

def _clean_key(s: str) -> str:
    """Strip whitespace, newlines, quotes - Binance -2014 often from hidden chars."""
    if not s:
        return s
    return s.strip().strip('"').strip("'").replace("\r", "").replace("\n", "")


def _get_symbols() -> List[str]:
    """Parse TRADING_SYMBOLS / TRADING_SYMBOL / SYMBOL from env. Default: BTC, ETH, SOL, XRP, BNB."""
    _default = "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT"
    _sym_env = os.environ.get("TRADING_SYMBOLS", os.environ.get("TRADING_SYMBOL", os.environ.get("SYMBOL", _default)))
    syms = [s.strip().upper() for s in _sym_env.replace(",", " ").split() if s.strip()]
    return syms if syms else ["BTCUSDT"]


@dataclass
class Config:
    # Binance API
    API_KEY: str = _clean_key(os.environ.get("BINANCE_API_KEY", ""))
    API_SECRET: str = _clean_key(os.environ.get("BINANCE_API_SECRET", ""))
    TESTNET: bool = os.environ.get("BINANCE_TESTNET", "false").lower() == "true"

    # Trading: one or more symbols. Default: BTC, ETH, SOL, XRP, BNB.
    SYMBOLS: List[str] = field(default_factory=_get_symbols)
    SYMBOL: str = field(default_factory=lambda: _get_symbols()[0])
    LEVERAGE: int = int(os.environ.get("LEVERAGE", "10"))
    MARGIN_TYPE: str = os.environ.get("MARGIN_TYPE", "CROSSED")
    TIMEFRAMES: List[str] = field(default_factory=lambda: ["1m", "5m", "15m", "1h", "4h"])

    # Risk Management
    RISK_PER_TRADE: float = 10.0          # 10% of balance per trade
    MAX_PORTFOLIO_EXPOSURE: float = 10.0  # max 10% total exposure
    MAX_OPEN_POSITIONS: int = int(os.environ.get("MAX_OPEN_POSITIONS", "4"))
    DAILY_LOSS_LIMIT: float = float(os.environ.get("DAILY_LOSS_LIMIT", "0"))  # 0 = unlimited; e.g. 5 = stop at 5% daily loss
    SL_ATR_MULTIPLIER: float = 1.5
    TP_RR_MIN: float = 2.0               # minimum 2:1 reward:risk
    TP_RR_MAX: float = 3.0               # target 3:1 reward:risk

    # Position Management
    TRAILING_SL: bool = True
    TRAILING_SL_PCT: float = 1.0
    PARTIAL_TP_PCT: float = 50.0          # close 50% at TP1
    MOVE_SL_TO_BE: bool = True            # move SL to breakeven after TP1
    TAKE_PROFIT_USD: float = float(os.environ.get("TAKE_PROFIT_USD", "15"))  # close when profit >= this (0 = disabled)

    # ML Model
    ML_LOOKBACK: int = 500                # candles for training
    ML_RETRAIN_HOURS: int = 6             # retrain every 6 hours
    ML_MIN_CONFIDENCE: float = 60.0       # minimum ML confidence to trade
    ML_MIN_TEST_ACCURACY: float = float(os.environ.get("ML_MIN_TEST_ACCURACY", "0.48"))  # lower = use ML more (more trades)

    # AI Engine (lower = more trades, higher = fewer/safer). Tuned for ~50 trades/day.
    MIN_CONFIDENCE: float = float(os.environ.get("MIN_CONFIDENCE", "52"))
    MAX_TRADES_PER_DAY: int = int(os.environ.get("MAX_TRADES_PER_DAY", "50"))  # 0 = no limit
    SIGNAL_WEIGHTS: dict = field(default_factory=lambda: {
        "technical": 0.25,
        "ml_prediction": 0.25,
        "orderbook": 0.20,
        "whale_activity": 0.15,
        "market_regime": 0.15,
    })

    # Orderbook
    OB_DEPTH_LEVELS: int = 20
    WHALE_TRADE_THRESHOLD: float = 50000  # $50K+ = whale trade

    # Scan
    SCAN_INTERVAL: int = 15               # seconds between scans

    # Telegram
    TG_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TG_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")
    TG_ENABLED: bool = bool(os.environ.get("TELEGRAM_BOT_TOKEN", "") and os.environ.get("TELEGRAM_CHAT_ID", ""))
    # Advanced Telegram: rate limit (msgs/min), inline buttons, optional trade confirmation
    TG_RATE_LIMIT_PER_MINUTE: int = min(30, max(5, int(os.environ.get("TG_RATE_LIMIT_PER_MINUTE", "20"))))
    TG_INLINE_BUTTONS: bool = os.environ.get("TG_INLINE_BUTTONS", "true").lower() == "true"
    TG_CONFIRM_TRADES: bool = os.environ.get("TG_CONFIRM_TRADES", "false").lower() == "true"

    # Logging
    LOG_FILE: str = "trading.log"


config = Config()
