"""
Trade Executor - handles all order execution and position management.
Market orders, SL/TP placement, trailing stops, partial profit taking.
"""
import time
from dataclasses import dataclass, field
from typing import List
from bot.config import config
from bot.logger import log, C


@dataclass
class TrackedPosition:
    symbol: str = ""
    direction: str = ""
    entry_price: float = 0.0
    quantity: float = 0.0
    stop_loss: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    tp1_hit: bool = False
    highest_price: float = 0.0
    lowest_price: float = 0.0
    opened_at: str = ""
    order_id: str = ""
    risk_pct: float = 0.0


class TradeExecutor:
    def __init__(self, client):
        self.client = client
        self.positions: List[TrackedPosition] = []

    def open_trade(self, signal, trade_setup):
        """Execute a new trade."""
        symbol = config.SYMBOL
        direction = signal

        # Check existing position on this pair
        existing = self.client.get_open_positions()
        if existing:
            for p in existing:
                if p["symbol"] == symbol and float(p["positionAmt"]) != 0:
                    log.info(f"  {C.yellow(symbol)} already has position. Skip.")
                    return None

        # Cancel stale orders
        self.client.cancel_all_orders(symbol)
        time.sleep(0.3)

        # Set margin and leverage
        try:
            self.client.client.futures_change_margin_type(symbol=symbol, marginType=config.MARGIN_TYPE)
        except: pass
        self.client.set_leverage()

        # Place market order
        from binance.enums import SIDE_BUY, SIDE_SELL
        side = SIDE_BUY if direction == "LONG" else SIDE_SELL
        order = self.client.market_order(side, trade_setup.quantity)
        if not order:
            log.error(f"  {C.bg_red(' ORDER FAILED ')}")
            return None

        log.info(f"  {C.bg_green(' ORDER FILLED ')} {symbol} {direction} | ID: {order.get('orderId')}")

        # Place SL
        sl_side = SIDE_SELL if direction == "LONG" else SIDE_BUY
        self.client.stop_loss_order(sl_side, trade_setup.stop_loss)

        # Place TP1 (partial - 50%)
        si = self.client.get_sym_info()
        tp1_qty = self.client.round_qty(trade_setup.quantity * (config.PARTIAL_TP_PCT / 100))
        min_qty = si.get("min_qty", 0.001)
        if tp1_qty < min_qty:
            tp1_qty = trade_setup.quantity
        self.client.take_profit_order(sl_side, trade_setup.tp1, tp1_qty)

        # Track position
        pos = TrackedPosition(
            symbol=symbol, direction=direction,
            entry_price=trade_setup.entry_price,
            quantity=trade_setup.quantity,
            stop_loss=trade_setup.stop_loss,
            tp1=trade_setup.tp1, tp2=trade_setup.tp2, tp3=trade_setup.tp3,
            highest_price=trade_setup.entry_price,
            lowest_price=trade_setup.entry_price,
            opened_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            order_id=str(order.get("orderId", "")),
            risk_pct=trade_setup.risk_pct,
        )
        self.positions.append(pos)
        return pos

    def monitor_positions(self):
        """Monitor and manage open positions."""
        from binance.enums import SIDE_BUY, SIDE_SELL

        binance_positions = self.client.get_open_positions()
        if binance_positions is None:
            return []  # API error, don't act

        active_symbols = {p["symbol"] for p in binance_positions}
        closed = []

        # Detect closed positions
        for pos in list(self.positions):
            if pos.symbol not in active_symbols:
                closed.append(pos)
                self.positions.remove(pos)

        # Sync: if Binance has 0 but we track some
        if len(binance_positions) == 0 and len(self.positions) > 0:
            log.info(f"  {C.yellow('Sync: clearing stale positions')}")
            self.positions.clear()

        # Monitor active positions
        for bp in binance_positions:
            symbol = bp["symbol"]
            mark = self.client.get_mark_price(symbol)
            pnl = float(bp.get("unRealizedProfit", 0))

            for pos in self.positions:
                if pos.symbol == symbol:
                    is_long = pos.direction == "LONG"
                    sl_side = SIDE_SELL if is_long else SIDE_BUY
                    si = self.client.get_sym_info(symbol)
                    pp = si.get("price_precision", 2)

                    # TP1 check - move SL to breakeven
                    if not pos.tp1_hit and config.MOVE_SL_TO_BE:
                        if (is_long and mark >= pos.tp1) or (not is_long and mark <= pos.tp1):
                            pos.tp1_hit = True
                            pos.stop_loss = pos.entry_price
                            try:
                                self.client.cancel_all_orders(symbol)
                                time.sleep(0.3)
                                self.client.stop_loss_order(sl_side, round(pos.entry_price, pp), symbol)
                            except: pass
                            log.info(f"  {C.bg_green(' TP1 HIT ')} {symbol} - SL -> breakeven")
                            continue

                    # Trailing stop loss
                    if config.TRAILING_SL and pos.tp1_hit:
                        if is_long:
                            pos.highest_price = max(pos.highest_price, mark)
                            new_sl = pos.highest_price * (1 - config.TRAILING_SL_PCT / 100)
                            new_sl = max(pos.stop_loss, new_sl)
                        else:
                            pos.lowest_price = min(pos.lowest_price, mark)
                            new_sl = pos.lowest_price * (1 + config.TRAILING_SL_PCT / 100)
                            new_sl = min(pos.stop_loss, new_sl)

                        diff = abs(new_sl - pos.stop_loss) / pos.stop_loss * 100 if pos.stop_loss > 0 else 0
                        if diff > 0.1:
                            old_sl = pos.stop_loss
                            pos.stop_loss = new_sl
                            try:
                                self.client.cancel_all_orders(symbol)
                                time.sleep(0.3)
                                self.client.stop_loss_order(sl_side, round(new_sl, pp), symbol)
                                log.info(f"  {C.yellow('TRAIL')} {symbol} ${old_sl:.2f} -> {C.green(f'${new_sl:.2f}')}")
                            except:
                                pos.stop_loss = old_sl

        return closed

    def close_all(self):
        """Close all positions on shutdown."""
        from binance.enums import SIDE_BUY, SIDE_SELL
        import math

        positions = self.client.get_open_positions()
        if not positions:
            log.info(f"  {C.dim('No positions to close.')}")
            return []

        closed_pnls = []
        log.info(f"  Closing {C.white(str(len(positions)))} positions...")

        for p in positions:
            sym = p["symbol"]
            amt = float(p["positionAmt"])
            try:
                self.client.cancel_all_orders(sym)
                time.sleep(0.3)
                si = self.client.get_sym_info(sym)
                step = si.get("step_size", 0.001)
                prec = si.get("qty_precision", 3)
                cq = round(math.floor(abs(amt) / step) * step, prec)
                if cq <= 0: continue

                if amt > 0:
                    self.client.market_order(SIDE_SELL, cq, sym)
                else:
                    self.client.market_order(SIDE_BUY, cq, sym)

                pnl = float(p.get("unRealizedProfit", 0))
                closed_pnls.append(pnl)
                if pnl >= 0:
                    log.info(f"  {C.bg_green(' CLOSED ')} {sym} {C.green(f'+${pnl:.2f}')}")
                else:
                    log.info(f"  {C.bg_red(' CLOSED ')} {sym} {C.red(f'-${abs(pnl):.2f}')}")
            except Exception as e:
                log.error(f"  Close failed {sym}: {e}")

        self.positions.clear()
        return closed_pnls

    def get_position_count(self):
        """Get total open positions from Binance."""
        positions = self.client.get_open_positions()
        if positions is None:
            return len(self.positions)
        if len(positions) == 0 and len(self.positions) > 0:
            self.positions.clear()
        return len(positions)
