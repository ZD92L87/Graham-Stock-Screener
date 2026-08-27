import pandas as pd
import os
import yfinance as yf
import requests
from requests.exceptions import HTTPError
from data_processing.providers import (
    get_stock_info,
    get_a_share_snapshot,
    eastmoney_fundamentals,
    tencent_batch_snapshot,
)

def process_ticker(ticker, log_callback=None):
    try:
        stock = yf.Ticker(ticker)
        info = stock.get_info() 
        company_name = info.get("shortName", "") if info else ""

        has_valid_data = any([
            info.get("currentPrice"),
            info.get("trailingPE"),
            info.get("priceToBook"),
            info.get("trailingEps"),
            info.get("dividendYield"),
            info.get("debtToEquity"),
            info.get("currentRatio"),
            info.get("marketCap")
        ])
        
        if has_valid_data:
            if log_callback:
                log_callback(ticker, company_name)
            else:
                print(f"[INFO] Processing {ticker}")
            return {
                "Ticker": ticker,
                "Name": company_name,
                "Price": info.get("currentPrice"),
                "PE": info.get("trailingPE"),
                "PB": info.get("priceToBook"),
                "EPS": info.get("trailingEps"),
                "DividendYield": info.get("dividendYield"),
                "DebtToEquity": info.get("debtToEquity"),
                "CurrentRatio": info.get("currentRatio"),
                "MarketCap": info.get("marketCap"),
                "LastUpdated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        raise ValueError("yfinance returned no usable data")

    except HTTPError as e:
        if e.response.status_code == 404:
            print(f"[INFO] {ticker}: not on Yahoo, trying fallback provider")
        else:
            print(f"[INFO] {ticker}: Yahoo HTTP {e.response.status_code} - trying fallback")
    except Exception as e:
        print(f"[INFO] {ticker}: {type(e).__name__} - trying fallback")

    # Fallback to domestic (China-friendly) providers when yfinance fails.
    try:
        fb = get_stock_info(ticker)
        if fb:
            if log_callback:
                log_callback(ticker, fb.get("Name"))
            else:
                print(f"[INFO] {ticker}: used fallback provider")
            return {
                "Ticker": ticker,
                "Name": fb.get("Name"),
                "Price": fb.get("Price"),
                "PE": fb.get("PE"),
                "PB": fb.get("PB"),
                "EPS": fb.get("EPS"),
                "DividendYield": fb.get("DividendYield"),
                "DebtToEquity": fb.get("DebtToEquity"),
                "CurrentRatio": fb.get("CurrentRatio"),
                "MarketCap": fb.get("MarketCap"),
                "LastUpdated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
    except Exception as e:
        print(f"[ERROR] {ticker}: fallback provider failed - {e}")

    print(f"[ERROR] {ticker}: no data available from any provider")
    return None

def process_data(file_path, market, log_callback=None):
    df = pd.read_csv(file_path, encoding='utf-8')

    if 'Ticker' not in df.columns:
        raise ValueError("CSV must contain a 'Ticker' column.")

    # A-shares: load from a single Sina market snapshot, then enrich only the
    # cheap candidates. This avoids one network call per ticker.
    if market in ('SHA', 'SZ'):
        return _process_a_share(df, market, log_callback)

    # US / HK: fetch quotes in a few batched Tencent calls (price/PE/market cap).
    if market in ('NYSE', 'NASDAQ', 'US_OTC', 'HKG'):
        return _process_batch_quote(df, market, log_callback)

    results = []
    total_tickers = len(df)
    processed_tickers = 0

    for index, ticker in enumerate(df['Ticker'], 1):
        result = process_ticker(ticker, log_callback=lambda t, cn=None: log_callback(t, cn, index, total_tickers) if log_callback else None)
        if result:
            results.append(result)
            if result['Price'] is not None:
                processed_tickers += 1

    result_df = pd.DataFrame(results)
    os.makedirs('data/processed', exist_ok=True)
    result_df.to_csv(f'data/processed/{market}_tickers.csv', index=False, encoding='utf-8')
    success_rate = (processed_tickers / total_tickers) * 100
    print(f"Successfully processed {processed_tickers}/{total_tickers} tickers ({success_rate:.2f}% for {market})")
    return result_df 


def _process_a_share(df, market, log_callback=None):
    total = len(df)
    print("Fetching A-share market snapshot from Sina...")
    snapshot = get_a_share_snapshot()
    results = []
    candidates = []

    for index, (_, row) in enumerate(df.iterrows(), 1):
        ticker = str(row['Ticker']).strip()
        code = ticker.split('.')[0]
        info = snapshot.get(code)
        if info:
            entry = {
                "Ticker": ticker,
                "Name": info.get("Name"),
                "Price": info.get("Price"),
                "PE": info.get("PE"),
                "PB": info.get("PB"),
                "EPS": None,
                "DividendYield": None,
                "DebtToEquity": None,
                "CurrentRatio": None,
                "MarketCap": info.get("MarketCap"),
                "LastUpdated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            results.append(entry)
            pe, pb, price = info.get("PE"), info.get("PB"), info.get("Price")
            # Only enrich the cheap ones that pass a Graham-style valuation
            # pre-filter, so the slow fundamentals are fetched sparingly.
            if (
                pe is not None
                and pb is not None
                and price
                and pe < 15
                and pb < 1.5
                and (pe * pb) < 22.5
            ):
                candidates.append((ticker, entry))
        if log_callback:
            log_callback(ticker, info.get("Name") if info else None, index, total)

    print(f"Enriching {len(candidates)} valuation candidates with fundamentals...")
    for ticker, entry in candidates:
        fund = eastmoney_fundamentals(ticker)
        entry["EPS"] = fund.get("EPS")
        entry["DebtToEquity"] = fund.get("DebtToEquity")
        entry["CurrentRatio"] = fund.get("CurrentRatio")

    result_df = pd.DataFrame(results)
    os.makedirs('data/processed', exist_ok=True)
    result_df.to_csv(f'data/processed/{market}_tickers.csv', index=False, encoding='utf-8')
    print(f"Successfully processed {len(results)}/{total} tickers via A-share snapshot ({market})")
    return result_df


def _process_batch_quote(df, market, log_callback=None):
    """Fast path for US/HK markets using Tencent batched real-time quotes."""
    total = len(df)
    tickers = df['Ticker'].tolist()
    print(f"Fetching {len(tickers)} quotes from Tencent (batched) for {market}...")
    snapshot = tencent_batch_snapshot(tickers)
    results = []
    for index, (_, row) in enumerate(df.iterrows(), 1):
        ticker = str(row['Ticker']).strip()
        info = snapshot.get(ticker)
        if info:
            results.append({
                "Ticker": ticker,
                "Name": info.get("Name"),
                "Price": info.get("Price"),
                "PE": info.get("PE"),
                "PB": info.get("PB"),
                "EPS": None,
                "DividendYield": None,
                "DebtToEquity": None,
                "CurrentRatio": None,
                "MarketCap": info.get("MarketCap"),
                "LastUpdated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        if log_callback:
            log_callback(ticker, info.get("Name") if info else None, index, total)

    result_df = pd.DataFrame(results)
    os.makedirs('data/processed', exist_ok=True)
    result_df.to_csv(f'data/processed/{market}_tickers.csv', index=False, encoding='utf-8')
    print(f"Successfully processed {len(results)}/{total} tickers via Tencent batch ({market})")
    return result_df
