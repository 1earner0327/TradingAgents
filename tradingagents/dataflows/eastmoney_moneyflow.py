from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import requests

from .eastmoney import eastmoney_secid, normalize_a_share_code

API_BASE_URLS = (
    "http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
    "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
)
REQUEST_TIMEOUT = 12
MAX_RETRIES = 3


def get_capital_flow(
    symbol: str,
    curr_date: str,
    look_back_days: int = 20,
) -> str:
    """Return East Money A-share capital-flow data as a markdown report."""
    code = normalize_a_share_code(symbol)
    if not code:
        return f"<capital flow unavailable: {symbol} is not a mainland China A-share code>"

    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError:
        return f"<capital flow unavailable: invalid curr_date {curr_date!r}, expected YYYY-mm-dd>"

    try:
        payload = _request_money_flow(code, int(max(1, min(look_back_days, 60))))
    except Exception as exc:  # noqa: BLE001 - this source should never stop a full run
        return f"<capital flow unavailable for {code}: {type(exc).__name__}: {exc}>"

    data = payload.get("data") or {}
    rows = [_parse_kline(item) for item in data.get("klines") or []]
    rows = [row for row in rows if row and row["date"] <= curr_date]
    if not rows:
        return f"<capital flow unavailable for {code}: East Money returned no rows on or before {curr_date}>"

    rows = rows[-int(max(1, min(look_back_days, 60))):]
    latest = rows[-1]
    main_total = sum(row["main_net"] for row in rows)
    super_total = sum(row["super_large_net"] for row in rows)
    large_total = sum(row["large_net"] for row in rows)
    positive_days = sum(1 for row in rows if row["main_net"] > 0)
    name = (data.get("name") or code).strip()

    lines = [
        f"## A-share capital flow from East Money for {name} ({code})",
        "",
        f"- Requested analysis date: {curr_date}",
        f"- Latest capital-flow row used: {latest['date']}",
        f"- Sample window: last {len(rows)} trading rows on or before the analysis date",
        f"- Main-force net flow in window: {_fmt_money(main_total)} ({positive_days}/{len(rows)} positive days)",
        f"- Super-large order net flow in window: {_fmt_money(super_total)}",
        f"- Large order net flow in window: {_fmt_money(large_total)}",
        "",
        "### Latest row",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| Close | {_fmt_number(latest['close'])} |",
        f"| Change pct | {_fmt_pct(latest['change_pct'])} |",
        f"| Main-force net flow | {_fmt_money(latest['main_net'])} |",
        f"| Main-force net pct | {_fmt_pct(latest['main_pct'])} |",
        f"| Super-large order net flow | {_fmt_money(latest['super_large_net'])} |",
        f"| Large order net flow | {_fmt_money(latest['large_net'])} |",
        f"| Medium order net flow | {_fmt_money(latest['medium_net'])} |",
        f"| Small order net flow | {_fmt_money(latest['small_net'])} |",
        "",
        "### Recent rows",
        "",
        "| Date | Close | Chg % | Main net | Main % | Super-large | Large | Medium | Small |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows[-10:]:
        lines.append(
            f"| {row['date']} | {_fmt_number(row['close'])} | {_fmt_pct(row['change_pct'])} "
            f"| {_fmt_money(row['main_net'])} | {_fmt_pct(row['main_pct'])} "
            f"| {_fmt_money(row['super_large_net'])} | {_fmt_money(row['large_net'])} "
            f"| {_fmt_money(row['medium_net'])} | {_fmt_money(row['small_net'])} |"
        )

    lines += [
        "",
        "Use this as an A-share liquidity and chip-structure signal. Positive main-force "
        "flow can support price action, but do not treat it as a standalone buy signal; "
        "cross-check it with price trend, volume, fundamentals, and news quality.",
    ]
    return "\n".join(lines)


def _request_money_flow(code: str, look_back_days: int) -> dict[str, Any]:
    params = {
        "lmt": str(max(look_back_days + 8, 20)),
        "klt": "101",
        "secid": eastmoney_secid(code),
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
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
                    last_error = exc
                    continue
            if payload is not None:
                break
        if payload is not None:
            break
        if attempt < MAX_RETRIES - 1:
            time.sleep(1.2 * (attempt + 1))
    if payload is None:
        raise RuntimeError(f"East Money capital-flow request failed: {last_error}")
    return payload


def _parse_kline(item: str) -> dict[str, float | str] | None:
    parts = item.split(",")
    if len(parts) < 13:
        return None
    try:
        return {
            "date": parts[0],
            "main_net": float(parts[1]),
            "small_net": float(parts[2]),
            "medium_net": float(parts[3]),
            "large_net": float(parts[4]),
            "super_large_net": float(parts[5]),
            "main_pct": float(parts[6]),
            "small_pct": float(parts[7]),
            "medium_pct": float(parts[8]),
            "large_pct": float(parts[9]),
            "super_large_pct": float(parts[10]),
            "close": float(parts[11]),
            "change_pct": float(parts[12]),
        }
    except ValueError:
        return None


def _fmt_money(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 100_000_000:
        return f"{value / 100_000_000:.2f}亿"
    if abs_value >= 10_000:
        return f"{value / 10_000:.1f}万"
    return f"{value:.0f}"


def _fmt_pct(value: float) -> str:
    return f"{value:.2f}%"


def _fmt_number(value: float) -> str:
    return f"{value:.2f}"
