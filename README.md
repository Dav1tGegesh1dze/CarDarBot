# 🚗 CarDarBot — Georgian Used Car Flip & Valuation Telegram Bot

**CarDarBot** (`@CarDar_Georgia_bot` — [t.me/CarDar_Georgia_bot](https://t.me/CarDar_Georgia_bot)) is a configurable Telegram bot and analytical engine that discovers undervalued used vehicles in Georgia (starting with Tbilisi) and evaluates potential buy-and-resell opportunities.

---

## 🌟 Features Overview

- **Full Telegram Control (`/start`)**: Interactive inline keyboards for creating searches, managing saved profiles, browsing deals, saving/dismissing vehicles, viewing market statistics, and adjusting settings—without editing code.
- **17-Step Search Creation Wizard (`/newsearch`)**:
  1. Custom or auto-generated search name
  2. Multi-select manufacturer catalog (Toyota, BMW, Mercedes-Benz, Honda, Hyundai, Kia, Nissan, Volkswagen, Ford, Subaru, Lexus, Mitsubishi, Chevrolet, Mazda, Audi, Porsche, Jeep, + custom makes)
  3. Validated manufacturer/model selection with Georgian & Russian aliases
  4. Fuel & Powertrain convenience groups (`EV` = BEV only, `ICE` = Gasoline/Diesel, `Hybrid` = HEV, `PHEV` = Plug-in Hybrid, `LPG`, `CNG`)
  5. Body Style (`Sedan`, `Coupe`, `Hatchback`, `Wagon`, `SUV / Crossover`, `Pickup`, `Convertible`, `Minivan`, `Van`)
  6. Drivetrain (`FWD`, `RWD`, `AWD`, `4WD`)
  7. Dedicated Off-Road capability filter (never inferred from SUV body style alone)
  8. Transmission (`Automatic`, `Manual`, `CVT`)
  9. USD Budget range (default `$500–$5,000`)
  10. Model year range
  11. Mileage range normalized to kilometers (`km` and `mi` supported)
  12. Location (default `Tbilisi, Georgia`)
  13. Customs status (`Customs-cleared only`, `Include uncleared`, `Any` — unknown status is never treated as cleared)
  14. Minimum expected net profit (default `$500`)
  15. Deal score threshold (default `70/100`)
  16. Scan frequency (`Daily`, `Every 12 hours`, `Every 6 hours`, `Manual only`)
  17. Complete confirmation summary before persistence
- **Natural Language Search**: Send messages like `"Find Toyota Prius under $4000"`, `"Electric cars under $5000"`, `"BMW coupe 2012-2018"`, or `"Find 4x4 under $3000"` to generate a draft search configuration.
- **MyAuto.ge & Import Architecture**:
  - Investigates `https://www.myauto.ge/` and `https://api2.myauto.ge/ka/products`.
  - Respects `robots.txt`, terms of use, and Cloudflare protections (`cf-mitigated: challenge`). Never bypasses CAPTCHA or fabricates listings.
  - Clearly reports source status mode (`live`, `import_only`, `temporarily_unavailable`, `unsupported`) via `/status`.
  - Includes a full **Import Adapter** (`ListingImportAdapter`) supporting `.json`, `.csv`, and `.html` exports via CLI (`cardarbot import-file <path>`) or by uploading files directly into the Telegram chat.
- **Trilingual Spam & Damage Filter**: Rejects `$1` / `$50` placeholder prices, down-payment traps (`პირველი შენატანი`), financing-only ads (`განვადება`), parts-only vehicles (`ნაწილებად`), non-running cars (`არ იქოქება`), and major engine/gearbox problems (`ძრავის პრობლემა`, `კოლოფის პრობლემა`). Urgent-sale wording (`სასწრაფოდ`) alone is never classified as fraud.
- **Conservative Market Valuation, Profit & 0–100 Deal Scoring**:
  - Uses median and 25th-percentile comparable asking prices (minimum 5 comparables by default) with a configurable 10% resale discount.
  - Deducts itemized expenses (inspection, repairs, maintenance, detailing, transport, registration, advertising, contingency).
  - Transparently scores deals 0–100 (`85–100 Exceptional`, `70–84 Strong`, `55–69 Review`, `<55 Ignore`).

---

## 🛠️ Complete macOS Setup Guide (15 Steps)

### 1. Clone the repository
```bash
git clone https://github.com/Dav1tGegesh1dze/CarDarBot.git
cd CarDarBot
```

### 2. Install Python 3.12+
Ensure Homebrew and Python 3.12+ are installed on your Mac:
```bash
brew install python@3.12
```

### 3. Install dependencies & initialize the database
Run the macOS setup script (this creates `.venv`, installs dependencies, copies `.env.example` to `.env` if missing, and runs Alembic migrations—**without** installing any background service automatically):
```bash
./scripts/install_mac.sh
```

### 4. Create `.env` (if not already created by `install_mac.sh`)
```bash
cp -n .env.example .env
chmod 600 .env
```

### 5. Add your newly regenerated Telegram Bot Token locally
1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/revoke` or `/token`, select `@CarDar_Georgia_bot`, and copy the newly generated token.
3. Open `.env` in your local editor (`nano .env`) and set:
```ini
TELEGRAM_BOT_TOKEN=YOUR_NEWLY_GENERATED_TOKEN_HERE
```
*(Never commit `.env` or paste your token into public chats.)*

### 6. Obtain and authorize your Telegram User ID
1. CarDarBot is **private by default**. You can get your numeric Telegram User ID by messaging `@userinfobot` on Telegram, or by starting CarDarBot once and sending `/start`—the bot will reply with your numeric User ID in the access-denied notice.
2. Add your numeric ID to `.env`:
```ini
TELEGRAM_ALLOWED_USER_IDS=123456789
```
3. Verify your configuration safely (secrets are never printed):
```bash
.venv/bin/cardarbot check-config
```

### 7. Start the bot
```bash
./scripts/run_bot.sh
```

### 8. Run `/start` in Telegram
Open [@CarDar_Georgia_bot](https://t.me/CarDar_Georgia_bot) in Telegram and send:
```text
/start
```
You will see the welcome screen and interactive main menu (`🔎 Create Search`, `🚘 My Searches`, `💎 Best Deals`, `⭐ Saved Cars`, `📊 Market Overview`, `⚙️ Settings`, `❓ Help`).

### 9. Create your first search
- Tap **🔎 Create Search** (or send `/newsearch`) to walk through the 17-step wizard, **or**
- Send a natural language message such as:
  `Find Toyota Prius under $4000`
  and tap **✅ Save and Activate**.

### 10. Test listing import, evaluation & notifications
Because MyAuto.ge enforces Cloudflare Turnstile challenges on automated scripts, you can import a JSON/CSV/HTML batch of listings via CLI or by dragging and dropping a `.json` or `.csv` file directly into the Telegram chat with `@CarDar_Georgia_bot`:
```bash
# Optional CLI import & immediate scan test:
.venv/bin/cardarbot import-file path/to/myauto_export.json
```
Or in Telegram, send `/scan` (or tap **🚀 Run Now** inside `/searches`) to evaluate all matching vehicles and receive `💎 POTENTIAL CAR FLIP` notifications.

### 11. Enable daily automated background scans (`launchd`)
When you explicitly want CarDarBot to run automatically in the background on your Mac via `launchd`:
```bash
./scripts/install_mac.sh --install-launchd
```
> **Note on macOS Power & Sleep Limitations**: Because CarDarBot runs locally on your Mac without paid cloud hosting, scheduled scans and Telegram polling run while your Mac is powered on and awake. If your Mac is asleep or powered off at a scheduled interval, `ScanScheduler` and `launchd` will automatically catch up on due profile scans as soon as your Mac wakes up.

### 12. Check operational logs
```bash
tail -f logs/cardarbot.log
# Or if running under launchd:
tail -f logs/launchd.stdout.log logs/launchd.stderr.log
```

### 13. Restart the bot
```bash
# If running manually in terminal: press Ctrl+C, then:
./scripts/run_bot.sh

# If running via macOS launchd:
launchctl kickstart -k "gui/$(id -u)/ge.cardarbot.agent"
```

### 14. Update the application
```bash
git pull origin main
.venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
```

### 15. Stop or uninstall the background service
```bash
./scripts/uninstall_mac.sh
```

---

## 🧪 Running Linting & Automated Tests

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/pytest -v
```
