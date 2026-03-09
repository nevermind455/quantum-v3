# Quantum Trading Bot v3

BTCUSDT perpetual futures bot: ML + orderbook + whale detection + Telegram alerts.

## Push to GitHub (first time)

1. **Create a new repo on GitHub**
   - Go to [github.com/new](https://github.com/new)
   - Repository name: `quantum-v3` (or any name)
   - **Add a README: OFF** (leave unchecked) — you already have a README and code locally; if you turn it ON, GitHub creates a default README and you can get merge conflicts when you push.
   - Create repository

2. **Connect and push** (replace `YOUR_USERNAME` with your GitHub username)
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/quantum-v3.git
   git branch -M main
   git push -u origin main
   ```

Your `.env` is **not** in the repo (see `.gitignore`), so your keys stay local.

## Deploy / update on VPS

See **[DEPLOY.md](DEPLOY.md)** for first-time VPS setup and how to update with `git pull`.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # then edit .env with your keys
python main.py
```

## Strategy: small profit and quit ($15)

With **TAKE_PROFIT_USD=15** (default), the bot:

- Takes trades when the AI signal is strong enough.
- Keeps the **full position** (no partial TP1 on the exchange).
- **Closes the entire position** when unrealized profit reaches **$15**.
- Uses the same stop loss to limit losses.

So the goal is: take a trade → make about $15 profit → quit the position. Set `TAKE_PROFIT_USD=0` in `.env` to use the original behavior (TP1/TP2/TP3 and trailing SL instead).

## More trades per day (tuning)

The bot is conservative by default. If you want **more than a couple of trades per day** on BTC, add to your `.env`:

| Variable | Default | More trades | Fewer / safer |
|----------|---------|-------------|----------------|
| `MIN_CONFIDENCE` | 58 | 52–55 | 62–65 |
| `ML_MIN_TEST_ACCURACY` | 0.50 | 0.48 | 0.52–0.55 |

Example for more signals (still filtered by risk/position limits):

```env
MIN_CONFIDENCE=54
ML_MIN_TEST_ACCURACY=0.48
```

Then restart the bot. Lower values = more trades, higher risk; raise them if you get too many bad trades.
