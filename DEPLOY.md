# Deploy to VPS (GitHub → replace/update easily)

## DigitalOcean: push your code to a Droplet

You don’t push *to* the VPS with git. You keep pushing to **GitHub** from your PC; on the **VPS** you **clone** (first time) then **pull** (updates).

### Step 1: Create a Droplet (if you don’t have one)

1. Go to [cloud.digitalocean.com](https://cloud.digitalocean.com) → **Create** → **Droplets**.
2. Choose **Ubuntu 22.04** (or 24.04).
3. Pick a plan (e.g. Basic $4–6/mo is enough).
4. Add your **SSH key** (or create one and download it).
5. Create Droplet. Note the **IP address** (e.g. `164.92.xxx.xxx`).

### Step 2: SSH into the VPS

From your PC (PowerShell or terminal):

```bash
ssh root@YOUR_DROPLET_IP
```

(Replace `YOUR_DROPLET_IP` with the IP from the DigitalOcean dashboard. Use the same username if you created a non-root user.)

### Step 3: First-time setup on the VPS

Run these on the **VPS** (after SSH):

```bash
# Clone your repo (your code from GitHub)
git clone https://github.com/nevermind455/quantum-v3.git
cd quantum-v3

# Install Python 3 and venv if needed (Ubuntu)
apt update && apt install -y python3 python3-pip python3-venv

# Create virtual env and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env (secrets stay only on VPS)
cp .env.example .env
nano .env
# Paste your BINANCE_API_KEY, BINANCE_API_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, etc. Save: Ctrl+O, Enter, Ctrl+X.

# Run the bot (foreground test)
python main.py
```

If it runs OK, stop it with `Ctrl+C`, then run in background:

```bash
# Option A: nohup (simple)
nohup python main.py > run.log 2>&1 &

# Option B: screen (can reattach later)
screen -S bot
python main.py
# Detach: Ctrl+A then D. Reattach later: screen -r bot
```

### Step 4: Update the VPS after you push to GitHub

From your **PC** you push as usual:

```bash
git add .
git commit -m "Your changes"
git push origin main
```

Then on the **VPS** (SSH in and run):

```bash
cd ~/quantum-v3
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt   # if you changed dependencies
# Restart the bot: kill the old process, then run again (e.g. nohup python main.py > run.log 2>&1 &)
```

Your `.env` is not in git, so it stays on the VPS. Only code is updated when you `git pull`.

---

## How to stop the bot on the VPS

**If the bot is in the foreground** (you ran `python main.py` and see output):
- Press **Ctrl+C** once. The bot will finish the current step (or wait at most a few seconds) then shut down and send the shutdown message to Telegram.
- If nothing happens: press **Ctrl+C** again, or wait up to ~15 seconds (it may be in the middle of an API call). If it still doesn’t stop, use `pkill -f main.py` from another terminal.

**If the bot is in the background** (you started it with `nohup ... &` or inside `screen`):

1. **Find the process**
   ```bash
   pgrep -af main.py
   ```
   You’ll see something like `12345 python main.py`. The number is the **PID**.

2. **Stop the bot** (replace `12345` with your PID)
   ```bash
   kill 12345
   ```
   Or stop all `main.py` processes:
   ```bash
   pkill -f main.py
   ```

3. **If you used `screen`**
   - Reattach: `screen -r bot`
   - Stop the bot: **Ctrl+C**
   - Detach again: **Ctrl+A** then **D** (or type `exit` to close the screen).

After a normal `kill`, the bot exits and can send the shutdown notice to Telegram. To start it again, run your usual command (e.g. `nohup python main.py > run.log 2>&1 &`).

---

## Quick reference (any VPS)

| Action        | Where  | Command |
|---------------|--------|---------|
| **Stop bot**  | VPS   | `pkill -f main.py` or `kill <PID>` |
| Push new code | Your PC | `git push origin main` |
| Get latest code | VPS   | `cd quantum-v3 && git pull origin main` |
| Run bot (background) | VPS | `cd quantum-v3 && source .venv/bin/activate && nohup python main.py > run.log 2>&1 &` |
| View log      | VPS   | `tail -f quantum-v3/run.log` or `tail -f quantum-v3/trading.log` |
