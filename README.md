# 📈 Graham Stock Screener

A modern Streamlit application for finding undervalued stocks using Benjamin
Graham's value investing principles. It screens stocks across **100+ global
markets** against Graham's classic defensive-investor criteria.

---

## 🧭 Application Origin

This project originated from
[ZD92L87/Graham-Stock-Screener](https://github.com/ZD92L87/Graham-Stock-Screener).
It is a standalone local web app (Streamlit) that fetches financial data in
real time and filters the market for value opportunities.

### Data Sources

- **Ticker lists** – scraped per market from
  [stockanalysis.com](https://stockanalysis.com/list/) (NYSE, NASDAQ, Shanghai,
  Shenzhen, Hong Kong, and 90+ more).
- **Financial metrics** – fetched on demand via
  [yfinance](https://github.com/ranaroussi/yfinance) (P/E, P/B, dividend yield,
  debt/equity, current ratio, EPS, market cap).
- **Ticker refresher** – Selenium + Chrome automate the per-market list updates.

Pre-populated ticker lists are stored in `data/raw/<MARKET>.csv`.

---

## 🚀 Features

- **Real-time Stock Screening** – screen stocks across 100+ global markets.
- **Graham Criteria** – built-in filters based on Benjamin Graham's original
  criteria.
- **Customizable Filters** – adjust every screening parameter with intuitive
  sliders.
- **Export Results** – download screening results as CSV files.
- **Responsive Design** – clean, modern UI that works on all devices.
- **Live Logging** – real-time progress updates during screening.

---

## ✨ Improvements (this fork)

This fork fixes several issues that prevented the app from running out of the
box on modern / Chinese Windows environments:

1. **UTF-8 file handling** – config and CSV reads/writes now pass
   `encoding='utf-8'`. This fixes the
   `UnicodeDecodeError: 'gbk' codec can't decode byte ...` crash on
   GBK-locale (Chinese) Windows.
2. **Reliable Chrome driver startup** – replaced `webdriver-manager` with
   Selenium's built-in **Selenium Manager**, fixing a ChromeDriver version
   mismatch that caused `session not created: Chrome failed to start`.
3. **Headless-friendly scraping** – Chrome now launches headless with an
   isolated profile by default, so it works in automation without popping up a
   window. Behaviour is configurable via environment variables (see
   [Configuration](#-configuration)).
4. **Robust pagination** – the ticker scraper retries when the target page
   re-renders its table (stale-element errors) and settles the DOM before
   reading rows.
5. **Clean packaging** – added a `.gitignore` and one-command `run.bat` /
   `run.sh` helpers, and tidied `requirements.txt`.

---

## 📁 Project Structure

```
Graham_Stock_Screener/
├── app.py                          # Main Streamlit application
├── requirements.txt                # Python dependencies
├── run.bat / run.sh                # One-command install + launch helpers
├── README.md                       # Project documentation
│
├── core/                           # Core business logic
│   ├── screener.py                 # Main screening orchestration
│   └── screen.py                   # Graham filtering logic
│
├── data_processing/                # Data fetching and processing
│   ├── processer.py                # Stock data processing with yfinance
│   ├── update_market.py            # Market data updates
│   └── fetch_all_tickers.py        # Web scraping for ticker lists
│
├── ui/                             # User interface components
│   └── ui_components.py            # Streamlit UI components
│
├── utils/                          # Utility modules
│   ├── config_loader.py            # Configuration loading
│   └── logger.py                   # Logging utilities
│
├── data/                           # Data files
│   ├── configs/                    # Configuration files
│   │   ├── markets_config.json     # Market definitions
│   │   ├── graham_criteria.json    # Graham's original criteria
│   │   └── markets.json            # Backend market data
│   └── raw/                        # Raw ticker data
│
├── results/                        # Screening results
└── logs/                           # Application logs
```

---

## 🛠️ Installation

### Prerequisites

- Python **3.9+** (tested with 3.14)
- **Google Chrome** (only needed to refresh market ticker lists)
- Internet access (for financial data and, on first run, driver download)

### 1. Quick one-command install & run

- **Windows:** double-click `run.bat` or run
  ```bat
  run.bat
  ```
- **macOS / Linux:**
  ```bash
  chmod +x run.sh
  ./run.sh
  ```

The helper creates a virtual environment (`.venv`), installs dependencies, and
starts the app.

### 2. Manual install

```bash
git clone <repository-url>
cd Graham_Stock_Screener

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

Then open **http://localhost:8501** in your browser.

### 3. Mainland China mirror

If `pip install` is slow or fails from China, use a domestic PyPI mirror:

```bash
pip install -r requirements.txt -i https://mirrors.nju.edu.cn/pypi/web/simple
```

Alternative mirror (Tsinghua):

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 📦 Dependencies

| Package              | Purpose                              |
| -------------------- | ------------------------------------ |
| `streamlit`          | Web UI framework                     |
| `pandas`             | Data processing                      |
| `yfinance`           | Real-time financial data             |
| `requests`           | HTTP requests                        |
| `selenium`           | Market ticker list scraping          |
| `beautifulsoup4`     | HTML parsing                         |
| `lxml`               | Fast HTML/XML parser                 |

> **Note:** ChromeDriver is now managed automatically by **Selenium Manager**
> (bundled with `selenium>=4.6`), so `webdriver-manager` is no longer required.

---

## 🎯 How to Use (Examples)

### 1. Screen a market for undervalued stocks

1. Select a market in the sidebar — e.g. `Shanghai Stock Exchange`,
   `Shenzhen Stock Exchange`, `Hong Kong Stock Exchange`, `NYSE`, `NASDAQ`.
2. Adjust the sliders (defaults match Graham's criteria).
3. Click **🚀 Run Graham Screener**.
4. Watch the live log, then view and **download** the results as CSV.

### 2. Update a market's ticker list

Refresh the ticker list from `stockanalysis.com` either from the UI
(**Update Selected Market**) or via the CLI:

```bash
# Windows
.venv\Scripts\python -c "from data_processing.update_market import update_single_market; print(update_single_market('NYSE'))"

# Unix
.venv/bin/python -c "from data_processing.update_market import update_single_market; print(update_single_market('NYSE'))"
```

Examples:

```bash
update_single_market('Shanghai Stock Exchange')   # SHA
update_single_market('Shenzhen Stock Exchange')   # SZ
update_single_market('Hong Kong Stock Exchange')  # HKG
update_single_market('NASDAQ')                    # NASDAQ
```

Results are written to `data/raw/<MARKET>.csv`.

### 3. Custom scraper behaviour (optional)

The ticker scraper reads these environment variables (all optional):

| Variable                | Default      | Description                          |
| ----------------------- | ------------ | ------------------------------------ |
| `SCRAPER_HEADLESS`      | `1` (true)   | Set `0` to watch the browser scrape. |
| `SCRAPER_NO_SANDBOX`    | `1` (true)   | Set `0` to disable `--no-sandbox`.   |
| `SCRAPER_DISABLE_GPU`   | `1` (true)   | Set `0` to keep GPU acceleration.    |
| `SCRAPER_WINDOW_SIZE`   | `1920,1080`  | Browser window size.                 |
| `SCRAPER_USER_DATA_DIR` | temp dir     | Isolated Chrome profile directory.   |

---

## 📊 Graham's Investment Criteria

Benjamin Graham's original criteria for defensive investors:

1. **Size** – Market cap ≥ $500M.
2. **Financial Strength** – Current ratio ≥ 1.5.
3. **Earnings Stability** – Positive earnings for the past 10 years.
4. **Dividend Record** – Uninterrupted dividends for the past 20 years.
5. **Earnings Growth** – 33% increase in per-share earnings over 10 years.
6. **Moderate P/E** – P/E ratio ≤ 15.
7. **Moderate P/B** – P/B ratio ≤ 1.5.
8. **Price Safety** – P/E × P/B ≤ 22.5.

---

## 🔧 Configuration

- **Add a market** – edit `data/configs/markets_config.json`:
  ```json
  { "markets": { "Market Name": "MARKET_CODE" } }
  ```
- **Adjust default criteria** – edit `data/configs/graham_criteria.json`:
  ```json
  { "graham_criteria": { "pe_max": 15.0, "pb_max": 1.5, "pe_pb_max": 22.5 } }
  ```

---

## 🤝 Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Test thoroughly.
5. Submit a pull request.

---

## 📝 License

No License — use freely. 🎉

---

## 🙏 Acknowledgments

- **Benjamin Graham** — for the original value investing principles.
- **Streamlit** — for the web app framework.
- **yfinance** — for reliable financial data.
- **stockanalysis.com** — for market ticker lists used by the scraper.
- **Pandas** — for data manipulation.

**Built with ❤️ for value investors everywhere.**
