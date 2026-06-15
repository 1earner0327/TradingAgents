from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import requests

from .errors import VendorNotConfiguredError

CHINABOND_SEARCH_URL = "https://yield.chinabond.com.cn/cbweb-mn/yc/searchYc"
CHINA_GOVERNMENT_BOND_CURVE_ID = "2c9081e50a2f9606010a3068cae70001"
REQUEST_TIMEOUT = 15
MAX_LOOKBACK_DAYS = 10

SUPPORTED_INDICATORS = {
    "china_yield_curve",
    "cn_yield_curve",
    "china_bond_yield_curve",
    "chinabond_yield_curve",
    "bond_yield_curve",
}

DISPLAY_TENORS = (0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30, 50)


def get_macro_data(
    indicator: str,
    curr_date: str,
    look_back_days: int | None = None,
) -> str:
    """Fetch ChinaBond government-bond yield curve from the public web page.

    This vendor intentionally fails softly. If the ChinaBond site changes,
    blocks access, or has no observation for the requested window, return a
    clear no-data note instead of raising into the agent workflow.
    """
    key = _normalize_indicator(indicator)
    if key not in SUPPORTED_INDICATORS:
        raise VendorNotConfiguredError(
            f"ChinaBond web source does not serve indicator {indicator!r}; "
            "fall through to another macro vendor."
        )

    try:
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError:
        return _no_data(indicator, curr_date, "invalid curr_date; expected YYYY-MM-DD")

    max_days = min(look_back_days or MAX_LOOKBACK_DAYS, MAX_LOOKBACK_DAYS)
    last_error = ""
    for offset in range(max_days + 1):
        query_dt = end_dt - timedelta(days=offset)
        query_date = query_dt.strftime("%Y-%m-%d")
        try:
            curve = _fetch_curve_for_date(query_date)
        except Exception as exc:  # noqa: BLE001 - soft-fail by design
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        if curve:
            return _format_curve(curve, requested_date=curr_date, actual_date=query_date)

    detail = f"no curve rows returned in the latest {max_days + 1} calendar days"
    if last_error:
        detail += f"; last error: {last_error}"
    return _no_data(indicator, curr_date, detail)


def _fetch_curve_for_date(work_time: str) -> dict[str, Any] | None:
    params = {
        "xyzSelect": "txy",
        "workTimes": work_time,
        "dxbj": "0",
        "qxll": "0,",
        "yqqxN": "N",
        "yqqxK": "K",
        "ycDefIds": CHINA_GOVERNMENT_BOND_CURVE_ID,
        "locale": "zh_CN",
    }
    response = _request(params)
    data = response.json()
    if not isinstance(data, list) or not data:
        return None

    for item in data:
        if item.get("ycDefId") == CHINA_GOVERNMENT_BOND_CURVE_ID:
            series = item.get("seriesData") or []
            if series:
                return {
                    "name": item.get("ycDefName") or "中债国债收益率曲线(到期)",
                    "worktime": item.get("worktime") or work_time,
                    "series": series,
                }
    return None


def _request(params: dict[str, str]) -> requests.Response:
    last_error: Exception | None = None
    for trust_env in (False, True):
        try:
            session = requests.Session()
            session.trust_env = trust_env
            response = session.post(
                CHINABOND_SEARCH_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "Accept": "application/json,text/javascript,*/*;q=0.01",
                    "Referer": "https://yield.chinabond.com.cn/cbweb-mn/yield_main?locale=zh_CN",
                    "User-Agent": "Mozilla/5.0",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.lower():
                raise ValueError(f"unexpected content type: {content_type}")
            return response
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            continue
    raise RuntimeError(last_error or "ChinaBond request failed")


def _format_curve(curve: dict[str, Any], requested_date: str, actual_date: str) -> str:
    points = _normalize_points(curve.get("series") or [])
    selected = _select_display_points(points)
    latest_note = ""
    if actual_date != requested_date:
        latest_note = f"\n- Requested date had no row; using latest available date: {actual_date}"

    table = "\n".join(
        [
            "| Tenor | Yield (%) |",
            "| --- | ---: |",
            *[f"| {_format_tenor(tenor)} | {value:.4f} |" for tenor, value in selected],
        ]
    )

    return (
        f"## ChinaBond web: {curve.get('name') or '中债国债收益率曲线(到期)'}\n"
        f"- Source: 中国债券信息网 / 中债收益率网页公开接口\n"
        f"- Observation date: {actual_date}{latest_note}\n"
        f"- Curve ID: {CHINA_GOVERNMENT_BOND_CURVE_ID}\n"
        "- Use this as the China/A-share RMB government-bond yield-curve reference. "
        "Do not treat it as the U.S. Treasury curve.\n\n"
        f"{table}\n"
    )


def _normalize_points(series: list[Any]) -> list[tuple[float, float]]:
    points = []
    for row in series:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        try:
            points.append((float(row[0]), float(row[1])))
        except (TypeError, ValueError):
            continue
    return sorted(points)


def _select_display_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not points:
        return []
    selected = []
    for target in DISPLAY_TENORS:
        tenor, value = min(points, key=lambda item, target=target: abs(item[0] - target))
        if selected and selected[-1][0] == tenor:
            continue
        selected.append((tenor, value))
    return selected


def _format_tenor(tenor: float) -> str:
    if tenor < 1:
        months = round(tenor * 12)
        return f"{months}M"
    if float(tenor).is_integer():
        return f"{int(tenor)}Y"
    return f"{tenor:.2f}Y"


def _no_data(indicator: str, curr_date: str, detail: str) -> str:
    return (
        f"## ChinaBond web data not available: {indicator}\n"
        f"- Requested date: {curr_date}\n"
        f"- Source attempted: 中国债券信息网 / 中债收益率网页公开接口\n"
        f"- Result: no usable curve data was retrieved ({detail}).\n\n"
        "Do not invent China yield-curve values. Continue the analysis using "
        "available market, company, news, and U.S./global macro evidence, and "
        "explicitly state that ChinaBond yield-curve data was unavailable for this run."
    )


def _normalize_indicator(indicator: str) -> str:
    return indicator.strip().lower().replace(" ", "_").replace("-", "_")
