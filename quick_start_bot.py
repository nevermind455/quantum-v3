#!/usr/bin/env python3
"""
Quick Start Runner for QUANTUM v3
=================================

Simple entrypoint that:
- Uses existing QUANTUM v3 modules
- Scans the market every 15 seconds
- Trades with 10% risk per trade (configured in bot/config.py)

Run:
    python quick_start_bot.py
"""

import os
import sys


def main():
    # Ensure project root is on sys.path
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from bot.config import config
    from main import QuantumBot

    # Just a safety print so the user sees key settings
    print("\n=== QUICK START BOT ===")
    print(f"Symbol: {config.SYMBOL}")
    print(f"Risk per trade: {config.RISK_PER_TRADE}% of balance")
    print(f"Scan interval: {config.SCAN_INTERVAL} seconds")
    print("=======================\n")

    bot = QuantumBot()
    bot.run()


if __name__ == "__main__":
    main()

