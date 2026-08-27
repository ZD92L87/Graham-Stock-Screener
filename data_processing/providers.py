"""Alternative market data providers (domestic/China-friendly).

yfinance can be rate-limited or blocked on some networks (e.g. Yahoo returns
HTTP 429 from many Chinese IPs). This module provides a fallback that reads
real-time quotes from Tencent (reliable) and financials from Eastmoney.

Only direct HTTP endpoints are used (no akshare), so engine-level headers can
be controlled and local connectivity quirks worked around.
"""

from __future__ import annotations

import json
import re
import time
from typing import Dict, List, Optional

import requests
from requests.exceptions import ConnectionError as ReqConnError, Timeout as ReqTimeout

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_TENCENT_HEADERS = {"User-Agent": _UA, "Referer": "https://gu.qq.com/"}
_EM_HEADERS = {"User-Agent": _UA, "Referer": "https://quote.eastmoney.com/"}
_SINA_HEADERS = {"User-Agent": _UA, "Referer": "https://finance.sina.com.cn/"}


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        num = float(str(value).strip())
        return num
    except (TypeError, ValueError):
        return None


def _field(fields: List[str], idx: int) -> Optional[str]:
    if 0 <= idx < len(fields):
        return fields[idx]
    return None


def _retry_get(url: str, headers: Dict, params=None, timeout: int = 10, attempts: int = 3):
    """GET with a few retries to ride out transient connection resets."""
    last = None
    for attempt in range(attempts):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp
            last = f"HTTP {resp.status_code}"
        except (ReqConnError, ReqTimeout) as exc:
            last = str(exc)
        except Exception as exc:  # noqa: BLE001 - network layer must not crash
            last = str(exc)
        if attempt < attempts - 1:
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"request failed after {attempts} attempts: {last}")


def _tencent_code(ticker: str) -> Optional[str]:
    """Map an app ticker (601398.SS / 300750.SZ / 0700.HK / AAPL) to Tencent code."""
    t = ticker.strip()
    if t.endswith(".SS"):
        return "sh" + t[:-3]
    if t.endswith(".SZ"):
        return "sz" + t[:-3]
    if t.endswith(".HK"):
        return "hk" + t[:-3].zfill(5)
    if t.endswith(".SH"):
        return "sh" + t[:-3]
    # US symbols have no market suffix in the ticker lists.
    return "us" + t


def _secid(ticker: str) -> Optional[str]:
    """Map an app ticker to Eastmoney secid (market.code)."""
    t = ticker.strip()
    if t.endswith(".SS"):
        return "1." + t[:-3]
    if t.endswith(".SH"):
        return "1." + t[:-3]
    if t.endswith(".SZ"):
        return "0." + t[:-3]
    if t.endswith(".HK"):
        return "116." + t[:-3].zfill(5)
    # US: Eastmoney uses 105/106/107 (AMEX/NASDAQ/NYSE). Try a couple.
    return None


def _em_secucode(ticker: str) -> Optional[str]:
    t = ticker.strip()
    if t.endswith(".SS"):
        return t[:-3] + ".SH"
    if t.endswith(".SH"):
        return t
    if t.endswith(".SZ"):
        return t
    if t.endswith(".HK"):
        return t
    return None


def tencent_quote(ticker: str) -> Optional[Dict]:
    """Fetch a real-time quote from Tencent for A-shares, HK, and US stocks."""
    code = _tencent_code(ticker)
    if not code:
        return None
    try:
        resp = _retry_get("https://qt.gtimg.cn/q=" + code, _TENCENT_HEADERS)
        text = resp.content.decode("gbk", errors="replace")
        if "=" not in text:
            return None
        body = text.split('="', 1)[1].rstrip('"').rstrip(";")
        fields = body.split("~")
        if len(fields) < 4 or not _field(fields, 0):
            return None
        price = _to_float(_field(fields, 3))
        pe = _to_float(_field(fields, 39))
        # f45 is total market cap in 100 million (亿) of the local currency.
        mktcap = _to_float(_field(fields, 45))
        name = _field(fields, 1) or _field(fields, 46)
        # For A-shares f46 is the P/B ratio; for HK/US it is the English name.
        pb = None
        if ticker.lower().endswith((".ss", ".sz", ".sh")):
            pb = _to_float(_field(fields, 46))
        return {
            "Price": price,
            "PE": pe,
            "PB": pb,
            "MarketCap": (mktcap * 1e8) if mktcap else None,
            "Name": name,
            "Source": "tencent",
        }
    except Exception:
        return None


def _em_quote(ticker: str) -> Optional[Dict]:
    """Secondary quote source (Eastmoney) for A-shares and HK stocks."""
    secid = _secid(ticker)
    if not secid:
        return None
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": secid,
        "invt": "2",
        "fltt": "2",
        "fields": "f43,f58,f103,f116,f167,f250,f251",
    }
    try:
        resp = _retry_get(url, _EM_HEADERS, params=params)
        data = (resp.json() or {}).get("data") or {}
        if not data:
            return None
        return {
            "Price": _to_float(data.get("f43")),
            "PE": _to_float(data.get("f250")) or _to_float(data.get("f251")),
            "PB": _to_float(data.get("f167")),
            "MarketCap": _to_float(data.get("f116")) or _to_float(data.get("f103")),
            "Name": data.get("f58"),
            "Source": "eastmoney",
        }
    except Exception:
        return None


def _em_datacenter(report_name: str, secucode: str) -> Optional[Dict]:
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "filter": '(SECUCODE="%s")' % secucode,
        "pageNumber": 1,
        "pageSize": 1,
        "sortTypes": -1,
        "sortColumns": "REPORT_DATE",
        "source": "HSF10",
        "client": "PC",
    }
    try:
        resp = _retry_get(url, _EM_HEADERS, params=params)
        rows = (resp.json().get("result") or {}).get("data") or []
        return rows[0] if rows else None
    except Exception:
        return None


def eastmoney_fundamentals(ticker: str) -> Dict:
    """Best-effort financials for A-shares from Eastmoney F10 reports."""
    out: Dict = {"EPS": None, "DebtToEquity": None, "CurrentRatio": None}
    secucode = _em_secucode(ticker)
    if not secucode:
        return out
    # Main indicators: EPSJB (basic EPS), CQBL (debt/equity ratio).
    main = _em_datacenter("RPT_F10_FINANCE_MAINFINADATA", secucode)
    if main:
        out["EPS"] = _to_float(main.get("EPSJB"))
        out["DebtToEquity"] = _to_float(main.get("CQBL"))
    # Balance ratios: CURRENT_RATIO (current ratio), DEBT_ASSET_RATIO.
    bal = _em_datacenter("RPT_DMSK_FN_BALANCE", secucode)
    if bal and out["DebtToEquity"] is None and bal.get("DEBT_ASSET_RATIO") is not None:
        dar = _to_float(bal.get("DEBT_ASSET_RATIO"))
        if dar is not None and dar < 100:
            out["DebtToEquity"] = dar / (100.0 - dar)
    if bal:
        cr = _to_float(bal.get("CURRENT_RATIO"))
        # Eastmoney reports the current ratio as a percentage (e.g. 155.95 for
        # a 1.56x ratio). Normalise to a plain ratio when it looks like a %.
        out["CurrentRatio"] = (cr / 100.0) if (cr is not None and cr >= 10) else cr
    return out


def get_stock_info(ticker: str) -> Optional[Dict]:
    """Unified fallback info for a single ticker (quote + fundamentals)."""
    quote = tencent_quote(ticker) or _em_quote(ticker)
    if not quote:
        return None
    fund = eastmoney_fundamentals(ticker) if _em_secucode(ticker) else {}
    quote.update(fund)
    quote["Ticker"] = ticker
    quote["LastUpdated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return quote


def get_a_share_snapshot(max_pages: int = 80, page_size: int = 100) -> Dict[str, Dict]:
    """Fetch the whole A-share market snapshot from Sina in one paginated pass.

    Returns {6-digit-code: {Price, PE, PB, MarketCap, Name}}. MarketCap is
    converted from 万元 to yuan (x1e4). A single call replaces thousands of
    per-ticker quote lookups for A-share screening.
    """
    url = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "Market_Center.getHQNodeData"
    )
    snapshot: Dict[str, Dict] = {}
    for page in range(1, max_pages + 1):
        params = {
            "page": page,
            "num": page_size,
            "sort": "symbol",
            "asc": 1,
            "node": "hs_a",
        }
        try:
            resp = _retry_get(url, _SINA_HEADERS, params=params)
            rows = json.loads(resp.text)
        except Exception:
            break
        if not rows:
            break
        for row in rows:
            code = str(row.get("code", "")).strip()
            if not code:
                continue
            price = _to_float(row.get("trade"))
            mktcap = _to_float(row.get("mktcap"))
            snapshot[code] = {
                "Price": price if price else None,
                "PE": _to_float(row.get("per")),
                "PB": _to_float(row.get("pb")),
                "MarketCap": (mktcap * 1e4) if mktcap else None,
                "Name": row.get("name"),
            }
        if len(rows) < page_size:
            break
        time.sleep(0.2)
    return snapshot


def tencent_batch_snapshot(tickers, batch_size: int = 60) -> Dict[str, Dict]:
    """Fetch quotes for many US/HK tickers from Tencent in a few batched calls.

    Returns {original_ticker: {Price, PE, PB, MarketCap, Name}}. MarketCap is
    expressed in the base currency (USD/HKD); Tencent reports it in 亿 units.
    US/HK quotes carry price, PE, market cap and name, but not the P/B ratio.
    """
    codes = []
    code_map: Dict[str, str] = {}
    for t in tickers:
        raw = str(t).strip()
        code = _tencent_code(raw)
        if code:
            codes.append(code)
            code_map[code] = raw

    result: Dict[str, Dict] = {}
    for i in range(0, len(codes), batch_size):
        chunk = codes[i : i + batch_size]
        try:
            resp = _retry_get("https://qt.gtimg.cn/q=" + ",".join(chunk), _TENCENT_HEADERS)
            text = resp.content.decode("gbk", errors="replace")
        except Exception:
            continue
        for line in text.split(";"):
            line = line.strip()
            if "=" not in line:
                continue
            key = line.split("=")[0].replace("v_", "").strip()
            body = line.split('="', 1)[1].rstrip('"')
            fields = body.split("~")
            raw = code_map.get(key)
            if not raw or len(fields) < 46:
                continue
            price = _to_float(fields[3])
            pe = _to_float(fields[39])
            mktcap = _to_float(fields[45])
            result[raw] = {
                "Price": price,
                "PE": pe,
                "PB": None,
                "MarketCap": (mktcap * 1e8) if mktcap else None,
                "Name": fields[1] or fields[46],
            }
    return result
