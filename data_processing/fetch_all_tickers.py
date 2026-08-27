import os
import json
import time
import csv
import tempfile
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

# Force UTF-8 stdout/stderr so emoji-flagged log messages don't crash
# on consoles that default to GBK (e.g. Chinese Windows).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# This file was used to populate the raw folder

def _env_flag(name: str, default: bool = True) -> bool:
    """Read a boolean from an env var; anything that isn't a falsey value is True."""
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no", "off")

def _build_chrome_options() -> Options:
    """Build Chrome options, configurable via environment variables.

    Defaults are chosen so the scraper works out of the box (headless, keeps
    Chrome off the desktop, uses an isolated profile). Override with:
      SCRAPER_HEADLESS=0        -> show the browser while scraping
      SCRAPER_NO_SANDBOX=0      -> disable the --no-sandbox flag
      SCRAPER_DISABLE_DEV_SHM=0 -> disable --disable-dev-shm-usage
      SCRAPER_DISABLE_GPU=0     -> disable --disable-gpu
      SCRAPER_WINDOW_SIZE=1600,1200
      SCRAPER_USER_DATA_DIR=/path/to/profile
    """
    options = Options()
    if _env_flag("SCRAPER_HEADLESS", True):
        options.add_argument("--headless=new")
    if _env_flag("SCRAPER_NO_SANDBOX", True):
        options.add_argument("--no-sandbox")
    if _env_flag("SCRAPER_DISABLE_DEV_SHM", True):
        options.add_argument("--disable-dev-shm-usage")
    if _env_flag("SCRAPER_DISABLE_GPU", True):
        options.add_argument("--disable-gpu")
    window_size = os.environ.get("SCRAPER_WINDOW_SIZE", "1920,1080")
    options.add_argument(f"--window-size={window_size}")
    user_data_dir = os.environ.get(
        "SCRAPER_USER_DATA_DIR",
        os.path.join(tempfile.gettempdir(), "graham_screener_chrome"),
    )
    options.add_argument(f"--user-data-dir={user_data_dir}")
    # Reduce automated-browser detection so the page table renders normally.
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options

def fetch_tickers_and_companies(market, url, suffix, log_callback=None):
    def log(message, level="INFO"):
        print(message)
        if log_callback and "⚠️" not in message:
            log_callback(message)

    # Use Selenium Manager's automatic driver management instead of
    # webdriver-manager, which downloaded a mismatched ChromeDriver.
    driver = webdriver.Chrome(options=_build_chrome_options())
    driver.get(url)
    all_data = []
    ticker_idx = None
    company_idx = None

    def handle_popups():
        try:
            cookie_buttons = driver.find_elements(By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') or " +
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'i agree') or " +
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'got it') or " +
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'consent')]"
            )
            for btn in cookie_buttons:
                if btn.is_displayed():
                    log("  🍪 Clicking cookie consent.")
                    btn.click()
                    time.sleep(1)
                    break
        except Exception as e:
            log(f"  ⚠️ Cookie popup not handled: {e}")

        try:
            close_buttons = driver.find_elements(By.XPATH,
                "//button[contains(., '×') or @aria-label='Close'] | " +
                "//div[contains(@class, 'close') or contains(@class, 'dismiss')] | " +
                "//button[contains(@class, 'close')]"
            )
            for btn in close_buttons:
                if btn.is_displayed():
                    log("  ❌ Closing modal or sign-up popup.")
                    btn.click()
                    time.sleep(1)
                    break
        except Exception as e:
            log(f"  ⚠️ Modal popup not handled: {e}")

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        handle_popups() 

        table = driver.find_element(By.TAG_NAME, "table")
        thead = table.find_element(By.TAG_NAME, "thead")
        headers = [th.text.strip().lower() for th in thead.find_elements(By.TAG_NAME, "th")]

        log(f"  Table columns: {headers}")

        for i, h in enumerate(headers):
            if h in ["symbol", "ticker"]:
                ticker_idx = i
            if h in ["company name", "name", "company"]:
                company_idx = i

        if ticker_idx is None or company_idx is None:
            log("  ❌ Required columns not found. Skipping market.")
            return []

        page_count = 0
        max_pages = 1000
        while page_count < max_pages:
            page_count += 1
            log(f"  Processing page {page_count} ...")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
            )
            handle_popups()  

            # Scroll to bottom and give lazy-rendered rows a moment to settle.
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.4)
            # Some pages re-render the table with JS, which invalidates row
            # references mid-read. Retry the whole page read if that happens.
            for attempt in range(3):
                try:
                    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
                    for row in rows:
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) > max(ticker_idx, company_idx):
                            ticker = cols[ticker_idx].text.strip()
                            company = cols[company_idx].text.strip()
                            if ticker:
                                all_data.append([ticker + suffix, company])
                    break
                except StaleElementReferenceException:
                    log("  ↻ Table re-rendered, retrying page read...")
                    time.sleep(1)

            try:
                next_button = driver.find_element(By.XPATH, "//button[contains(., 'Next') or contains(., '›')] | //a[contains(., 'Next') or contains(., '›')]")
                if not next_button.is_enabled() or 'disabled' in next_button.get_attribute("class").lower():
                    log("  ✅ Reached last page.")
                    break
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(1.5)
            except Exception as e:
                log(f"  ⚠️ No more pages or next button issue: {e}")
                break
    finally:
        driver.quit()

    return all_data

def save_tickers_and_companies(all_data, market):
    os.makedirs("data/raw", exist_ok=True)
    out_path = f"data/raw/{market}.csv"
    with open(out_path, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Ticker", "Company"])
        writer.writerows(all_data)
    print(f"✅ Saved {len(all_data)} rows to {out_path}")

def main():
    with open("data/configs/markets.json", "r", encoding="utf-8") as f:
        markets = json.load(f)

    for market, (url, suffix) in markets.items():
        if market not in ["NASDAQ", "NYSE"]:
            break
        print(f"\n🔎 Scraping {market} from {url} ...")
        try:
            all_data = fetch_tickers_and_companies(market, url, suffix)
            if all_data:
                save_tickers_and_companies(all_data, market)
            else:
                print(f"❌ No data found for {market}")
        except Exception as e:
            print(f"❌ Failed to scrape {market}: {e}")


if __name__ == "__main__":
    main()
