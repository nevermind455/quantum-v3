# Quantum Trading Bot v3

BTCUSDT perpetual futures bot: ML + orderbook + whale detection + Telegram alerts.

## Push to GitHub (first time)

1. **Create a new repo on GitHub**
   - Go to [github.com/new](https://github.com/new)
   - Repository name: `quantum-v3` (or any name)
   - Leave "Add a README" unchecked (you already have code)
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
