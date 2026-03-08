import threading
import time


def run_quantum_bot() -> None:
    """
    Start the existing Binance Quantum v3 bot.
    """
    from main import QuantumBot  # import from your existing project root

    bot = QuantumBot()
    bot.run()


def run_polymarket_bot() -> None:
    """
    Start the Polymarket sniper bot (paper mode by default).
    """
    from polymarket.main import run_embedded

    # By default: live (non-backtest) + paper trading to be safe.
    run_embedded(paper=True, backtest=False, market_id="")


def main() -> None:
    qt_thread = threading.Thread(target=run_quantum_bot, name="quantum-bot", daemon=True)
    pm_thread = threading.Thread(target=run_polymarket_bot, name="polymarket-bot", daemon=True)

    qt_thread.start()
    pm_thread.start()

    try:
        # Keep main thread alive while both bots run in background threads.
        while True:
            if not qt_thread.is_alive() and not pm_thread.is_alive():
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Stopping both bots (threads will exit with process).")


if __name__ == "__main__":
    main()

