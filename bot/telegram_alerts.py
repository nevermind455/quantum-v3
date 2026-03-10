"""
Telegram Alert System - sends trade notifications and supports commands.
Advanced: message queue, rate limiting, inline keyboards, callback buttons, optional trade confirmation.
"""
import json
import time
from collections import deque
from threading import Thread, Lock
from bot.config import config
from bot.logger import log

try:
    import requests as tg_requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import urllib.request
    import urllib.parse
except ImportError:
    pass


def _api_post(base_url, method, payload, timeout=10):
    """POST to Telegram API with optional retry."""
    url = f"{base_url}/{method}"
    for attempt in range(3):
        try:
            if HAS_REQUESTS:
                r = tg_requests.post(url, json=payload, timeout=timeout)
                if r.status_code == 200:
                    return r.json()
            else:
                req = urllib.request.Request(
                    url, json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode())
        except Exception as e:
            log.debug("Telegram API %s: %s", method, e)
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    return None


class TelegramAlerts:
    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{config.TG_TOKEN}"
        self.last_update_id = 0
        self._bot_ref = None
        self._running = False
        # Advanced: message queue + rate limiting
        self._queue = deque()
        self._queue_lock = Lock()
        self._send_timestamps = deque(maxlen=config.TG_RATE_LIMIT_PER_MINUTE * 2)
        self._sender_running = False
        # Pending trade for confirmation flow
        self._pending_trade = None  # (symbol, trade_setup, decision) when TG_CONFIRM_TRADES

    def set_bot_ref(self, bot):
        self._bot_ref = bot

    def _send_raw(self, text, parse_mode="HTML", reply_markup=None):
        """Send one message immediately (used by queue worker and answer_callback)."""
        if not config.TG_ENABLED:
            return
        p = {
            "chat_id": config.TG_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            p["reply_markup"] = reply_markup
        return _api_post(self.base_url, "sendMessage", p)

    def send(self, text, parse_mode="HTML", reply_markup=None):
        if not config.TG_ENABLED:
            return
        if reply_markup is not None and not getattr(config, "TG_INLINE_BUTTONS", True):
            reply_markup = None
        with self._queue_lock:
            self._queue.append((text, parse_mode, reply_markup))
        # If not using queue (no rate limit in practice), send immediately for backward compat
        if not getattr(config, "TG_RATE_LIMIT_PER_MINUTE", 20) or len(self._queue) == 1:
            self._drain_one()

    def _drain_one(self):
        """Send at most one message from queue respecting rate limit."""
        with self._queue_lock:
            if not self._queue:
                return
            now = time.monotonic()
            limit = getattr(config, "TG_RATE_LIMIT_PER_MINUTE", 20)
            while self._send_timestamps and self._send_timestamps[0] < now - 60:
                self._send_timestamps.popleft()
            if limit and len(self._send_timestamps) >= limit:
                return
            item = self._queue.popleft()
        text, parse_mode, reply_markup = item
        out = self._send_raw(text, parse_mode=parse_mode, reply_markup=reply_markup)
        if out and out.get("ok"):
            self._send_timestamps.append(time.monotonic())
        elif not out or not out.get("ok"):
            with self._queue_lock:
                self._queue.appendleft(item)

    def _sender_loop(self):
        """Worker that drains queue with rate limiting."""
        self._sender_running = True
        while self._sender_running:
            self._drain_one()
            time.sleep(0.5 if self._queue else 2.0)
        self._sender_running = False

    def _inline_keyboard(self, rows):
        """Build reply_markup for inline keyboard. rows = [[{text, callback_data}, ...], ...]"""
        return json.dumps({"inline_keyboard": rows})

    def _quick_buttons(self):
        """Default quick action buttons for status/control."""
        return [
            [{"text": "📊 Status", "callback_data": "status"}, {"text": "⏸ Pause", "callback_data": "pause"}],
            [{"text": "▶ Resume", "callback_data": "resume"}, {"text": "📋 Positions", "callback_data": "positions"}],
        ]

    # --- Notifications ---
    def notify_startup(self, balance):
        msg = (
            f"<b>🚀 QUANTUM v3.0 STARTED</b>\n"
            f"----\n{', '.join(getattr(config, 'SYMBOLS', [config.SYMBOL]))} | {config.LEVERAGE}x | Risk: {config.RISK_PER_TRADE}%\n"
            f"SL: ATR x{config.SL_ATR_MULTIPLIER} | TP R:R: {config.TP_RR_MIN}/{config.TP_RR_MAX}\n"
            f"Max positions: {config.MAX_OPEN_POSITIONS}\nML + OB + Whale + Regime\n"
            f"Balance: <code>${balance:.2f}</code>\n----\n/help for commands"
        )
        reply_markup = self._inline_keyboard(self._quick_buttons()) if getattr(config, "TG_INLINE_BUTTONS", True) else None
        self.send(msg, reply_markup=reply_markup)

    def notify_shutdown(self):
        self.send("<b>🛑 BOT STOPPED</b>")

    def notify_trade_open(self, direction, entry, qty, sl, tp1, confidence, reason, symbol=None):
        sym = (symbol or config.SYMBOL).strip().upper()
        f = lambda v: f"{v:.2f}"
        self.send(
            f"<b>✅ TRADE OPENED</b>\n{sym} {direction}\n"
            f"Entry: <code>${f(entry)}</code> | Qty: {qty}\nSL: <code>${f(sl)}</code> | TP1: <code>${f(tp1)}</code>\n"
            f"Conf: {confidence:.0f}% | {reason[:200]}"
        )

    def request_trade_confirm(self, trade_setup, decision, symbol=None):
        """Send trade confirmation request with Approve/Cancel buttons. Stores pending for callback."""
        sym = (symbol or config.SYMBOL).strip().upper()
        self._pending_trade = (sym, trade_setup, decision)
        f = lambda v: f"{v:.2f}"
        msg = (
            f"<b>⚠️ CONFIRM TRADE</b>\n{sym} {decision.signal}\n"
            f"Entry: <code>${f(trade_setup.entry_price)}</code> | Qty: {trade_setup.quantity}\n"
            f"SL: <code>${f(trade_setup.stop_loss)}</code> | TP1: <code>${f(trade_setup.tp1)}</code>\n"
            f"Conf: {decision.confidence:.0f}%\n{decision.reason[:150]}"
        )
        reply_markup = self._inline_keyboard([
            [{"text": "✅ Approve", "callback_data": "confirm_yes"}, {"text": "❌ Cancel", "callback_data": "confirm_no"}]
        ])
        self.send(msg, reply_markup=reply_markup)

    def notify_trade_close(self, pair, reason, pnl):
        self.send(f"<b>TRADE CLOSED</b>\n{pair} | {reason}\nPnL: ${pnl:.2f}")

    def notify_tp_hit(self, pair, level, price):
        self.send(f"<b>{level} HIT</b> {pair} @ ${price:.2f}")

    def notify_daily_limit(self):
        self.send(f"<b>DAILY LOSS LIMIT</b>\nTrading paused. Loss > {config.DAILY_LOSS_LIMIT}%")

    def notify_pnl_update(self, balance, daily_pnl, daily_pct, total_pnl):
        """Periodic PnL snapshot (e.g. every 12 cycles)."""
        self.send(
            f"<b>PnL UPDATE</b>\n"
            f"Balance: <code>${balance:.2f}</code>\n"
            f"Daily: <code>${daily_pnl:+.2f}</code> ({daily_pct:+.1f}%)\n"
            f"Total PnL: <code>${total_pnl:+.2f}</code>"
        )

    def notify_daily_report(self, stats, perf_24h):
        wr = stats.win_rate
        self.send(
            f"<b>DAILY REPORT</b>\n----\n"
            f"Balance: ${stats.total_balance:.2f}\n"
            f"Daily PnL: ${stats.daily_pnl:.2f} ({stats.daily_pnl_pct:+.1f}%)\n"
            f"Total PnL: ${stats.total_pnl:.2f}\n"
            f"W: {stats.wins} L: {stats.losses} WR: {wr:.0f}%\n"
            f"Streak: {stats.current_streak:+d}\n"
            f"Drawdown: {stats.max_drawdown:.1f}%\n"
            f"----\n24H: {perf_24h.get('trades', 0)} trades, ${perf_24h.get('pnl', 0):.2f}"
        )

    def _answer_callback(self, callback_query_id, text=None):
        """Answer callback query to remove loading state."""
        p = {"callback_query_id": callback_query_id}
        if text:
            p["text"] = text[:200]
        _api_post(self.base_url, "answerCallbackQuery", p)

    # --- Command Handling ---
    def poll_commands(self):
        if not config.TG_ENABLED:
            return
        try:
            params = {"offset": self.last_update_id + 1, "timeout": 1}
            if HAS_REQUESTS:
                data = tg_requests.get(f"{self.base_url}/getUpdates", params=params, timeout=5).json()
            else:
                with urllib.request.urlopen(
                    urllib.request.Request(f"{self.base_url}/getUpdates?{urllib.parse.urlencode(params)}"), timeout=5
                ) as r:
                    data = json.loads(r.read().decode())
            if not data.get("ok"):
                return
            for u in data.get("result", []):
                self.last_update_id = u["update_id"]
                cq = u.get("callback_query")
                if cq:
                    cid = str(cq.get("message", {}).get("chat", {}).get("id", ""))
                    if cid != config.TG_CHAT_ID:
                        continue
                    cb_id = cq.get("id")
                    data_val = (cq.get("data") or "").strip()
                    toast = {"confirm_yes": "Trade approved", "confirm_no": "Cancelled"}.get(data_val)
                    self._answer_callback(cb_id, toast)
                    if data_val in ("status", "pause", "resume", "positions"):
                        self._handle("/" + data_val)
                    elif data_val == "confirm_yes":
                        if self._pending_trade and self._bot_ref:
                            pt = self._pending_trade
                            self._pending_trade = None
                            if len(pt) == 3:
                                sym, setup, dec = pt
                            else:
                                setup, dec = pt
                                sym = config.SYMBOL
                            if getattr(self._bot_ref, "execute_confirmed_trade", None):
                                self._bot_ref.execute_confirmed_trade(sym, setup, dec)
                    elif data_val == "confirm_no":
                        self._pending_trade = None
                        self.send("❌ Trade cancelled.")
                    continue
                msg = u.get("message", {})
                txt = msg.get("text", "").strip()
                cid = str(msg.get("chat", {}).get("id", ""))
                if cid != config.TG_CHAT_ID:
                    continue
                self._handle(txt)
        except Exception as e:
            log.debug("Telegram getUpdates: %s", e)

    def _handle(self, t):
        cmd = t.lower().split()[0] if t else ""
        b = self._bot_ref
        if not b:
            return
        use_buttons = getattr(config, "TG_INLINE_BUTTONS", True)
        kb = self._inline_keyboard(self._quick_buttons()) if use_buttons else None
        if cmd == "/help":
            self.send(
                "<b>QUANTUM v3.0</b>\n/status /positions /stats /journal /balance /regime /pause /resume /help",
                reply_markup=kb,
            )
        elif cmd == "/status":
            s = b.portfolio.stats
            self.send(
                f"<b>📊 STATUS</b> {'⏸ PAUSED' if b._paused else '▶ RUNNING'}\n"
                f"Bal: <code>${s.balance:.2f}</code> | PnL: <code>${s.total_pnl:.2f}</code>\n"
                f"W:{s.wins} L:{s.losses} WR:{s.win_rate:.0f}%\n"
                f"Open: {s.open_positions}/{config.MAX_OPEN_POSITIONS} | Streak: {s.current_streak:+d}",
                reply_markup=kb,
            )
        elif cmd == "/positions":
            positions = b.executor.positions
            if not positions:
                self.send("No open positions", reply_markup=kb)
                return
            lines = []
            for p in positions:
                lines.append(f"<b>{p.symbol}</b> {p.direction}\nEntry: ${p.entry_price:.2f} SL: ${p.stop_loss:.2f}")
            self.send("\n".join(lines), reply_markup=kb)
        elif cmd == "/stats":
            s = b.portfolio.stats
            self.send(
                f"<b>📈 STATS</b>\nW:{s.wins} L:{s.losses} WR:{s.win_rate:.0f}%\n"
                f"RR: {s.avg_rr:.1f} | PnL: ${s.total_pnl:.2f}\n"
                f"Best: ${s.best_trade:.2f} | Worst: ${s.worst_trade:.2f}\nDD: {s.max_drawdown:.1f}%",
                reply_markup=kb,
            )
        elif cmd == "/journal":
            p = b.portfolio.get_24h_performance()
            self.send(
                f"<b>24H JOURNAL</b>\nTrades: {p.get('trades',0)}\nPnL: ${p.get('pnl',0):.2f}\nW: {p.get('wins',0)} L: {p.get('losses',0)}",
                reply_markup=kb,
            )
        elif cmd == "/balance":
            self.send(f"Balance: <b>${b.portfolio.stats.balance:.2f}</b> USDT", reply_markup=kb)
        elif cmd == "/regime":
            if b._last_regime:
                r = b._last_regime
                self.send(f"<b>REGIME</b>\n{r.regime} ({r.confidence:.0f}%)\n{r.description}", reply_markup=kb)
            else:
                self.send("No regime data yet", reply_markup=kb)
        elif cmd == "/pause":
            b._paused = True
            self.send("<b>⏸ PAUSED</b>", reply_markup=kb)
        elif cmd == "/resume":
            b._paused = False
            b._daily_limit_hit = False  # also clear daily limit so trading can resume
            self.send("<b>▶ RESUMED</b> (pause and daily limit cleared)", reply_markup=kb)

    def start_polling(self):
        if not config.TG_ENABLED:
            return
        self._running = True
        if getattr(config, "TG_RATE_LIMIT_PER_MINUTE", 20):
            Thread(target=self._sender_loop, daemon=True).start()
        Thread(target=self._loop, daemon=True).start()

    def stop_polling(self):
        self._running = False
        self._sender_running = False

    def _loop(self):
        while self._running:
            try:
                self.poll_commands()
            except Exception as e:
                log.debug("Telegram poll: %s", e)
            time.sleep(2)
