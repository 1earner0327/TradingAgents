from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from .eastmoney import eastmoney_secid, normalize_a_share_code
from .errors import NoMarketDataError, VendorError

REQUEST_TIMEOUT = 12


class EastMoneyFundamentalsError(VendorError):
    """Raised when East Money F10 fundamentals cannot be loaded."""


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    """Return East Money F10 company profile and key financial indicators."""
    code = normalize_a_share_code(ticker)
    if not code:
        raise NoMarketDataError(ticker, ticker, "not a mainland China A-share code")

    exchange = _exchange_prefix(code)
    survey = _get_json(
        f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax?code={exchange}{code}",
        referer="https://emweb.securities.eastmoney.com/",
    )
    finance = _get_json(
        f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code={exchange}{code}",
        referer="https://emweb.securities.eastmoney.com/",
    )
    quote = _get_quote_json(code)

    profile = survey.get("jbzl") or {}
    rows = finance.get("data") or []
    quote_data = quote.get("data") or {}
    if not profile and not rows and not quote_data:
        raise NoMarketDataError(ticker, code, "East Money F10 returned no usable fields")

    lines = [
        f"# East Money A-share fundamentals for {profile.get('agjc') or quote_data.get('f58') or code} ({code})",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "# Source: East Money public F10/quote endpoints (no API key)",
        "",
    ]

    if profile:
        lines.extend(
            [
                "## Company profile",
                f"- Full name: {_clean(profile.get('gsmc'))}",
                f"- Short name: {_clean(profile.get('agjc'))}",
                f"- Exchange/listing board: {_clean(profile.get('ssjys'))} / {_clean(profile.get('zqlb'))}",
                f"- Industry: {_clean(profile.get('sshy'))}; CSRC industry: {_clean(profile.get('sszjhhy'))}",
                f"- Chair/legal representative: {_clean(profile.get('dsz') or profile.get('frdb'))}",
                f"- Website: {_clean(profile.get('gswz'))}",
                f"- Employees: {_clean(profile.get('gyrs'))}",
                f"- Registered capital: {_clean(profile.get('zczb'))}",
                "",
                "Business summary:",
                _clean(profile.get("gsjj")),
                "",
            ]
        )

    if quote_data:
        lines.extend(
            [
                "## Quote valuation snapshot",
                f"- Total market cap: {_money(quote_data.get('f116'))}",
                f"- Float market cap: {_money(quote_data.get('f117'))}",
                f"- Dynamic P/E: {_ratio(quote_data.get('f162'), scale=100)}",
                f"- P/B: {_ratio(quote_data.get('f167'), scale=100)}",
                f"- ROE/reference field: {_ratio(quote_data.get('f173'))}",
                "",
            ]
        )

    if rows:
        lines.extend(["## Key financial indicators", _finance_table(rows[:8]), ""])

    return "\n".join(lines)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return _statement_note(ticker, "balance sheet", curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return _statement_note(ticker, "cash flow", curr_date)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return _statement_note(ticker, "income statement", curr_date)


def _statement_note(ticker: str, statement: str, curr_date: str | None) -> str:
    fundamentals = get_fundamentals(ticker, curr_date)
    return (
        f"# East Money {statement} detail\n"
        "Detailed standardized statement mapping is not enabled yet. "
        "Use the key financial indicators below as the available East Money F10 "
        "fundamental snapshot.\n\n"
        f"{fundamentals}"
    )


def _get_json(url: str, params: dict[str, str] | None = None, referer: str = "") -> dict[str, Any]:
    last_error: Exception | None = None
    for trust_env in (False, True):
        try:
            session = requests.Session()
            session.trust_env = trust_env
            response = session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": referer,
                    "User-Agent": "Mozilla/5.0",
                },
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            continue
    raise EastMoneyFundamentalsError(f"East Money F10 request failed: {last_error}") from last_error


def _get_quote_json(code: str) -> dict[str, Any]:
    params = {
        "secid": eastmoney_secid(code),
        "fields": "f57,f58,f116,f117,f162,f167,f168,f169,f170,f173,f187,f189,f190,f191",
    }
    for base_url in (
        "http://push2.eastmoney.com/api/qt/stock/get",
        "https://push2.eastmoney.com/api/qt/stock/get",
    ):
        try:
            return _get_json(base_url, params=params, referer="https://quote.eastmoney.com/")
        except EastMoneyFundamentalsError:
            continue
    return {}


def _exchange_prefix(code: str) -> str:
    return "SH" if code.startswith(("5", "6", "9")) else "SZ"


def _finance_table(rows: list[dict[str, Any]]) -> str:
    fields = [
        ("REPORT_DATE_NAME", "Report"),
        ("NOTICE_DATE", "Notice"),
        ("EPSJB", "EPS"),
        ("BPS", "BPS"),
        ("TOTALOPERATEREVE", "Revenue"),
        ("TOTALOPERATEREVETZ", "Revenue YoY %"),
        ("PARENTNETPROFIT", "Net profit"),
        ("PARENTNETPROFITTZ", "Net profit YoY %"),
        ("ROEJQ", "ROE %"),
        ("XSMLL", "Gross margin %"),
        ("XSJLL", "Net margin %"),
        ("ZCFZL", "Debt/assets %"),
        ("LD", "Current ratio"),
        ("SD", "Quick ratio"),
    ]
    header = "| " + " | ".join(label for _, label in fields) + " |"
    separator = "| " + " | ".join("---" for _ in fields) + " |"
    body = []
    for row in rows:
        values = []
        for key, _ in fields:
            value = row.get(key)
            if key in {"TOTALOPERATEREVE", "PARENTNETPROFIT"}:
                values.append(_money(value))
            elif key == "NOTICE_DATE":
                values.append(str(value or "")[:10])
            else:
                values.append(_clean(value))
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, separator, *body])


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


def _money(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿"
    if abs(number) >= 10_000:
        return f"{number / 10_000:.2f}万"
    return f"{number:.2f}"


def _ratio(value: Any, scale: float = 1.0) -> str:
    try:
        number = float(value) / scale
    except (TypeError, ValueError):
        return ""
    return f"{number:.2f}"
