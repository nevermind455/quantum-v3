"""
Risk Manager - institutional-grade risk control.
ATR-based stop loss, R:R take profit, position sizing,
exposure management, daily loss limits.
"""
import math
from dataclasses import dataclass
from bot.config import config
from bot.logger import log


@dataclass
class TradeSetup:
    entry_price: float = 0.0
    stop_loss: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    quantity: float = 0.0
    risk_pct: float = 0.0
    risk_amount: float = 0.0
    position_value: float = 0.0
    position_pct: float = 0.0  # % of balance
    rr_ratio: float = 0.0      # reward:risk
    valid: bool = False
    reject_reason: str = ""


class RiskManager:
    def __init__(self):
        self.daily_pnl = 0.0
        self.daily_start_balance = 0.0

    def calculate_trade(self, price, atr, direction, balance,
                         regime_factor=1.0, sym_info=None) -> TradeSetup:
        """Calculate complete trade setup with position sizing."""
        t = TradeSetup()
        t.entry_price = price

        if balance <= 0 or atr <= 0 or price <= 0:
            t.reject_reason = "Invalid balance/ATR/price"
            return t

        # === STOP LOSS (ATR-based) ===
        sl_mult = config.SL_ATR_MULTIPLIER
        sl_distance = atr * sl_mult
        sl_pct = (sl_distance / price) * 100

        # Clamp SL between 0.5% and 4%
        sl_pct = max(0.5, min(4.0, sl_pct))
        sl_distance = price * (sl_pct / 100)

        mult = 1 if direction == "LONG" else -1
        t.stop_loss = price - mult * sl_distance
        t.risk_pct = sl_pct

        # === TAKE PROFIT (R:R based) ===
        t.tp1 = price + mult * sl_distance * config.TP_RR_MIN
        t.tp2 = price + mult * sl_distance * 2.5
        t.tp3 = price + mult * sl_distance * config.TP_RR_MAX
        t.rr_ratio = config.TP_RR_MIN

        # === POSITION SIZING ===
        # Risk 1% of balance per trade
        risk_amount = balance * (config.RISK_PER_TRADE / 100)
        t.risk_amount = risk_amount

        # Position size = risk amount / SL distance * leverage
        if sl_distance > 0:
            raw_qty = (risk_amount / sl_distance)
        else:
            t.reject_reason = "SL distance is 0"
            return t

        # Apply regime factor (reduce in volatile markets)
        raw_qty *= regime_factor

        # Notional value check (max exposure)
        notional = raw_qty * price
        max_notional = balance * (config.MAX_PORTFOLIO_EXPOSURE / 100) * config.LEVERAGE
        if notional > max_notional:
            raw_qty = max_notional / price

        # Round to symbol precision
        if sym_info:
            step = sym_info.get("step_size", 0.001)
            prec = sym_info.get("qty_precision", 3)
            max_qty = sym_info.get("max_qty", 999999999)
            min_qty = sym_info.get("min_qty", 0.001)
            raw_qty = min(raw_qty, max_qty * 0.95)
            raw_qty = round(math.floor(raw_qty / step) * step, prec)
            if raw_qty < min_qty:
                t.reject_reason = f"Qty {raw_qty} below min {min_qty}"
                return t
        else:
            if price > 1000: raw_qty = round(raw_qty, 3)
            elif price > 1: raw_qty = round(raw_qty, 2)
            else: raw_qty = round(raw_qty, 1)

        t.quantity = max(0, raw_qty)
        t.position_value = t.quantity * price
        t.position_pct = (t.position_value / balance) * 100 if balance > 0 else 0

        if t.quantity <= 0:
            t.reject_reason = "Calculated quantity is 0"
            return t

        t.valid = True
        return t

    def check_daily_limit(self, balance):
        """Check if daily loss limit is hit."""
        if self.daily_start_balance <= 0:
            self.daily_start_balance = balance
            return False
        loss_pct = (self.daily_pnl / self.daily_start_balance) * 100
        return loss_pct < -config.DAILY_LOSS_LIMIT

    def check_exposure(self, open_positions, balance):
        """Check total portfolio exposure."""
        if not open_positions:
            return True  # can trade
        total_exposure = 0
        for p in open_positions:
            amt = abs(float(p.get("positionAmt", 0)))
            entry = float(p.get("entryPrice", 0))
            total_exposure += amt * entry
        exposure_pct = (total_exposure / balance) * 100 if balance > 0 else 999
        return exposure_pct < config.MAX_PORTFOLIO_EXPOSURE * config.LEVERAGE

    def can_open_position(self, open_positions):
        """Check max position count."""
        if open_positions is None:
            return False
        return len(open_positions) < config.MAX_OPEN_POSITIONS

    def update_daily_pnl(self, pnl):
        self.daily_pnl += pnl

    def reset_daily(self, balance):
        self.daily_pnl = 0
        self.daily_start_balance = balance
