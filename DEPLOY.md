# Deploy to VPS (GitHub → replace/update easily)

## First-time setup on VPS

1. **Clone from GitHub**
   ```bash
   git clone https://github.com/YOUR_USERNAME/quantum-v3.git
   cd quantum-v3
   ```

2. **Python environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Linux/Mac
   # .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

3. **Configure secrets (do not commit)**
   ```bash
   cp .env.example .env
   nano .env   # or vim – add your BINANCE_* and TELEGRAM_* keys
   ```

4. **Run**
   ```bash
   python main.py
   ```
   Or in background: `nohup python main.py > run.log 2>&1 &` or use `screen`/`tmux`.

---

## Update / replace on VPS (after you push to GitHub)

```bash
cd quantum-v3
git pull origin main
pip install -r requirements.txt   # if dependencies changed
# Restart the bot (kill old process, then run again)
```

Your `.env` is not in git, so it stays on the VPS. Only code and config examples are updated.
