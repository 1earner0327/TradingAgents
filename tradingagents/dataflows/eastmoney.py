from __future__ import annotations

import re
import time
from datetime import datetime
from io import StringIO

import pandas as pd
import requests

from .errors import NoMarketDataError, VendorError

API_BASE_URLS = (
    "http://push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
)
REQUEST_TIMEOUT = 12
MAX_RETRIES = 3

_A_SHARE_RE = re.compile(r"^(?:SH|SZ)?(?P<code>\d{6})(?:\.(?:SH|SS|SZ))?$", re.IGNORECASE)


class EastMoneyError(VendorError):
    """Raised when East Money cannot return usable A-share OHLCV data."""


def normalize_a_share_code(symbol: str) -> str | None:
    """Return a six-digit mainland China A-share code, or None if unsupported."""
    if not isinstance(symbol, str):
        return None
    compact = symbol.strip().upper().replace(" ", "")
    match = _A_SHARE_RE.fullmatch(compact)
    if not match:
        return None
    return match.group("code")


def is_a_share_symbol(symbol: str) -> bool:
    return normalize_a_share_code(symbol) is not None


def eastmoney_secid(symbol: str) -> str:
    """Map a six-digit A-share code to East Money's secid format."""
    code = normalize_a_share_code(symbol)
    if not code:
        raise NoMarketDataError(symbol, symbol, "not a mainland China A-share code")
    # East Money market prefix: 1 = Shanghai, 0 = Shenzhen/Beijing in common A-share usage.
    market = "1" if code.startswith(("5", "6", "9")) else "0"
    return f"{market}.{code}"


def _request_klines(symbol: str, start_date: str, end_date: str) -> dict:
    params = {
        "secid": eastmoney_secid(symbol),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": start_date.replace("-", ""),
        "end": end_date.replace("-", ""),
    }
    last_error: Exception | None = None
    payload = None
    for attempt in range(MAX_RETRIES):
        for base_url in API_BASE_URLS:
            for trust_env in (False, True):
                try:
                    session = requests.Session()
                    session.trust_env = trust_env
                    response = session.get(
                        base_url,
                        params=params,
                        timeout=REQUEST_TIMEOUT,
                        headers={
                            "Accept": "application/json,text/plain,*/*",
                            "Referer": "https://quote.eastmoney.com/",
                            "User-Agent": "Mozilla/5.0",
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    break
                except requests.RequestException as exc:
                    last_error = exc
                    continue
                except ValueError as exc:
                    raise EastMoneyError(f"East Money returned invalid JSON for {symbol}") from exc
            if payload is not None:
                break
        if payload is not None:
            break
        if attempt < MAX_RETRIES - 1:
            time.sleep(1.5 * (attempt + 1))

    if payload is None:
        raise EastMoneyError(f"East Money request failed for {symbol}: {last_error}") from last_error

    data = payload.get("data")
    if not data or not data.get("klines"):
        code = normalize_a_share_code(symbol) or symbol
        raise NoMarketDataError(symbol, code, "East Money returned no rows")
    return data


def _klines_to_frame(symbol: str, data: dict) -> pd.DataFrame:
    """Convert an East Money kline payload to Date/Open/High/Low/Close/Volume."""
    rows = []
    for item in data.get("klines", []):
        parts = item.split(",")
        if len(parts) < 7:
            continue
        rows.append(
            {
                "Date": parts[0],
                "Open": parts[1],
                "Close": parts[2],
                "High": parts[3],
                "Low": parts[4],
                "Volume": parts[5],
                "Amount": parts[6],
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        code = normalize_a_share_code(symbol) or symbol
        raise NoMarketDataError(symbol, code, "East Money returned empty parsed rows")
    return df


def load_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Load daily A-share OHLCV from East Money as Date/Open/High/Low/Close/Volume."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")
    data = _request_klines(symbol, start_date, end_date)
    return _klines_to_frame(symbol, data)


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Return formatted CSV daily A-share OHLCV from East Money."""
    data = _request_klines(symbol, start_date, end_date)
    df = _klines_to_frame(symbol, data)
    for column in ("Open", "High", "Low", "Close", "Volume", "Amount"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    code = normalize_a_share_code(symbol) or symbol
    name = (data.get("name") or code).strip()
    csv_string = df.to_csv(index=False)
    header = f"# East Money A-share data for {name} ({code}) from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_string


def read_ohlcv_csv(csv_data: str) -> pd.DataFrame:
    """Parse the CSV body produced by get_stock, ignoring comment headers."""
    clean = "\n".join(line for line in csv_data.splitlines() if not line.startswith("#"))
    return pd.read_csv(StringIO(clean))
