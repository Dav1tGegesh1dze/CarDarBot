# 🚗 CarDarBot

**CarDarBot** (`@CarDar_Georgia_bot`) is a configurable Telegram bot for discovering undervalued used cars in Georgia (starting with Tbilisi) and evaluating potential buy-and-resell opportunities.

## Key Features
- **Interactive Telegram UI**: Full 17-step Search Creation Wizard, Natural Language Search parser, Deal Browser, Saved Cars, Market Overview, and Settings.
- **Granular Vehicle Filtering**: Manufacturers, Models (with aliases), Fuel/Powertrain (EV, ICE, HEV, PHEV, LPG, CNG), Body Style, Drivetrain, separate Off-Road capability filter, Transmission, Budget, Year, Mileage, Location, Customs Status, Minimum Profit, and Deal Score threshold.
- **MyAuto.ge & Import Architecture**: Live Permitted Collector with automatic Cloudflare challenge detection + JSON/CSV/HTML Import Adapter so you can always evaluate listings without bypassing website security controls.
- **Trilingual Spam & Condition Engine**: Detects placeholder prices ($1, $50), down-payment/financing traps (`პირველი შენატანი`, `განვადება`), non-running/parts-only vehicles (`ნაწილებად`, `არ იქოქება`), and engine/gearbox damage (`ძრავის პრობლემა`, `კოლოფის პრობლემა`) across Georgian, English, and Russian.
- **Conservative Market Valuation & Profit Engine**: Calculates median & 25th-percentile comparable prices, applies a resale discount, deducts itemized expenses, and scores deals from 0 to 100.
- **macOS Local Automation**: Coordinated `APScheduler` and `launchd` scripts with PID locking to prevent duplicate polling.

*(Full macOS setup and operational instructions are maintained in this README as phases progress.)*
