from __future__ import annotations

from .cn_sentiment import fetch_cn_sentiment_sources
from .eastmoney import normalize_a_share_code


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Return A-share company news/forum highlights from East Money.

    This no-key source is intentionally used only for mainland China A-share
    symbols. It gives the news analyst a domestic company-specific input when
    Yahoo/Alpha Vantage have no coverage for A-shares.
    """
    code = normalize_a_share_code(ticker)
    if not code:
        return f"<eastmoney news unavailable: {ticker} is not a mainland China A-share code>"

    block = fetch_cn_sentiment_sources(code, start_date, end_date, limit=24)
    return (
        f"## East Money company news and forum highlights for {ticker}\n"
        f"Date window: {start_date} to {end_date}\n\n"
        f"{block}\n\n"
        "Use official-info posts and cited media items as company/news evidence. "
        "Use ordinary forum posts only as retail-attention context, not as verified facts."
    )
