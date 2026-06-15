from __future__ import annotations

from datetime import datetime, timedelta


def get_macro_note(
    indicator: str,
    curr_date: str,
    look_back_days: int | None = None,
) -> str:
    """Return a non-fatal macro-data note when configured vendors are unavailable."""
    if look_back_days is None:
        look_back_days = 365
    try:
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_date = (end_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    except ValueError:
        start_date = "unknown"

    return (
        f"## Macro data unavailable: {indicator}\n"
        f"- Window: {start_date} to {curr_date}\n"
        "- No configured macro data vendor returned usable data.\n"
        "- For China/A-share macro rates, the no-key ChinaBond web source may "
        "be temporarily unavailable; Tushare Pro's `yc_cb` is an optional paid fallback.\n"
        "- For U.S. macro data, configure `FRED_API_KEY` to use FRED.\n\n"
        "Do not invent macro values. Continue the analysis using available market, "
        "news, and company-specific evidence, and explicitly state that macro "
        "time-series data was unavailable for this run."
    )
