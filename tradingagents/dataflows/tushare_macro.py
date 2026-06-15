from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests

from .errors import VendorNotConfiguredError

TUSHARE_API_BASE = "http://api.tushare.pro"
REQUEST_TIMEOUT = 20
MAX_ROWS = 40


class TushareNotConfiguredError(VendorNotConfiguredError):
    """Raised when Tushare is selected but no token is configured."""


def get_token() -> str:
    token = os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_API_TOKEN")
    if not token:
        raise TushareNotConfiguredError(
            "TUSHARE_TOKEN environment variable is not set. Get a token at https://tushare.pro/."
        )
    return token


def _request(api_name: str, params: dict, fields: str = "") -> dict:
    payload = {
        "api_name": api_name,
        "token": get_token(),
        "params": params,
        "fields": fields,
    }
    response = requests.post(TUSHARE_API_BASE, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != 0:
        raise ValueError(f"Tushare request failed: {data.get('msg') or data}")
    return data.get("data") or {}


def _rows_to_markdown(fields: list[str], rows: list[list], max_rows: int = MAX_ROWS) -> str:
    shown = rows[-max_rows:] if len(rows) > max_rows else rows
    header = "| " + " | ".join(fields) + " |"
    divider = "| " + " | ".join("---" for _ in fields) + " |"
    body = "\n".join("| " + " | ".join(str(value) for value in row) + " |" for row in shown)
    note = f"\n_(showing latest {len(shown)} of {len(rows)} rows)_\n" if len(rows) > max_rows else "\n"
    return note + "\n".join([header, divider, body]) + "\n"


def _normalize_indicator(indicator: str) -> str:
    return indicator.strip().lower().replace(" ", "_").replace("-", "_")


def get_macro_data(
    indicator: str,
    curr_date: str,
    look_back_days: int | None = None,
) -> str:
    """Fetch China macro data from Tushare Pro.

    Currently maps `yield_curve` and related aliases to Tushare's `yc_cb`
    ChinaBond yield-curve API, which is more relevant for mainland A-share
    analysis than the U.S. FRED Treasury curve.
    """
    if look_back_days is None:
        look_back_days = 365
    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y%m%d")
    end_date = end_dt.strftime("%Y%m%d")

    key = _normalize_indicator(indicator)
    if key not in {
        "yield_curve",
        "china_yield_curve",
        "cn_yield_curve",
        "treasury_yield_curve",
        "bond_yield_curve",
    }:
        raise VendorNotConfiguredError(
            "Tushare macro integration supports ChinaBond yield curve aliases only; "
            f"indicator {indicator!r} should fall through to another macro vendor."
        )

    fields = "trade_date,curve_type,curve_term,yield"
    result = _request(
        "yc_cb",
        {
            "start_date": start_date,
            "end_date": end_date,
        },
        fields=fields,
    )
    field_names = result.get("fields") or fields.split(",")
    rows = result.get("items") or []
    if not rows:
        return (
            "## Tushare ChinaBond yield curve\n"
            f"- Window: {start_dt.strftime('%Y-%m-%d')} to {curr_date}\n"
            "- No rows were returned. The API permission may be missing, the date "
            "window may be too narrow, or the market calendar may not have observations."
        )

    return (
        "## Tushare ChinaBond Yield Curve (`yc_cb`)\n"
        f"- Window: {start_dt.strftime('%Y-%m-%d')} to {curr_date}\n"
        "- Source: Tushare Pro / ChinaBond yield curve\n"
        "- Use this as the China/A-share macro rate reference. Do not treat it "
        "as the U.S. Treasury curve.\n"
        + _rows_to_markdown(field_names, rows)
    )
