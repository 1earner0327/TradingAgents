from __future__ import annotations

import html
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import requests
from parsel import Selector

from .eastmoney import normalize_a_share_code

GUBA_URLS = (
    "https://guba.eastmoney.com/list,{code}.html",
    "http://guba.eastmoney.com/list,{code}.html",
)
MOBILE_GUBA_URLS = (
    "https://mguba.eastmoney.com/mguba/list/{code}%2Cf_2990",
    "http://mguba.eastmoney.com/mguba/list/{code}%2Cf_2990",
)
THS_MOBILE_URL = "https://m.10jqka.com.cn/stockpage/hs_{code}/"
TUSHARE_URL = "http://api.tushare.pro"
REQUEST_TIMEOUT = 12
MAX_POST_DETAILS = 8


def fetch_cn_sentiment_sources(
    ticker: str,
    start_date: str,
    end_date: str,
    limit: int = 40,
) -> str:
    """Fetch China A-share sentiment inputs from domestic sources.

    East Money Guba is used as the default no-key retail forum source.
    The 10jqka mobile page is only an auxiliary public-page snapshot because
    it does not expose a stable no-key forum post list. Tushare Pro news is
    tried when a token is configured, but many accounts need extra permissions
    for the news endpoints, so it always degrades to a note.
    """
    code = normalize_a_share_code(ticker)
    if not code:
        return f"<cn sentiment unavailable: {ticker} is not a mainland China A-share code>"

    guba_block, company_name = _fetch_eastmoney_guba(code, start_date, end_date, limit)
    mobile_guba_block = _fetch_eastmoney_mobile_guba(code, limit=max(8, min(limit, 24)))
    ths_block = _fetch_10jqka_snapshot(code)
    tushare_block = _fetch_tushare_news(code, company_name, start_date, end_date)

    return "\n\n".join(
        [
            f"## Domestic China sentiment sources for {ticker} ({company_name or code})",
            guba_block,
            mobile_guba_block,
            ths_block,
            tushare_block,
            "Data note: East Money Guba is a public web source and is not a look-ahead-safe "
            "historical archive. East Money mobile Guba is a live public forum snapshot. "
            "10jqka is only a public-page auxiliary snapshot unless stable post rows are "
            "explicitly listed above; do not weight it as forum-post sentiment otherwise.",
        ]
    )


def _fetch_eastmoney_guba(
    code: str,
    start_date: str,
    end_date: str,
    limit: int,
) -> tuple[str, str | None]:
    last_error: Exception | None = None
    text = ""
    final_url = ""
    for url_template in GUBA_URLS:
        url = url_template.format(code=code)
        for trust_env in (False, True):
            try:
                session = requests.Session()
                session.trust_env = trust_env
                response = session.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Referer": "https://guba.eastmoney.com/",
                        "User-Agent": "Mozilla/5.0",
                    },
                )
                response.raise_for_status()
                text = response.text
                final_url = url
                break
            except requests.RequestException as exc:
                last_error = exc
                continue
        if text:
            break

    if not text:
        return (
            "### East Money Guba\n"
            f"<eastmoney guba unavailable for {code}: {type(last_error).__name__ if last_error else 'unknown error'}>",
            None,
        )

    selector = Selector(text=text)
    title = selector.css("title::text").get() or ""
    company_name = _company_name_from_title(title, code)
    rows = selector.css("tr.listitem")
    posts: list[dict[str, Any]] = []
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    for row in rows:
        post = _parse_guba_row(row, final_url, end_date)
        if not post or not post.get("title"):
            continue
        post_dt = post.get("datetime")
        if post_dt is not None and not (start_dt <= post_dt <= end_dt):
            continue
        posts.append(post)
        if len(posts) >= limit:
            break

    for post in posts[:MAX_POST_DETAILS]:
        href = str(post.get("link") or "")
        if "guba.eastmoney.com/news," not in href:
            continue
        post["excerpt"] = _fetch_guba_excerpt(href)
        time.sleep(0.15)

    if not posts:
        return (
            "### East Money Guba\n"
            f"<no East Money Guba posts found for {code} between {start_date} and {end_date}>",
            company_name,
        )

    total_reads = sum(int(post.get("reads") or 0) for post in posts)
    total_replies = sum(int(post.get("replies") or 0) for post in posts)
    top_discussed = sorted(posts, key=lambda item: int(item.get("replies") or 0), reverse=True)[:5]

    lines = [
        "### East Money Guba (domestic retail forum, no API key)",
        f"Source URL: {final_url}",
        f"Parsed posts: {len(posts)} / raw rows: {len(rows)}",
        f"Engagement in parsed sample: reads={total_reads}, comments={total_replies}",
        "",
        "Most discussed posts:",
    ]
    for post in top_discussed:
        lines.append(
            "- "
            f"{post.get('time_label', '')} | comments={post.get('replies', 0)} | "
            f"reads={post.get('reads', 0)} | {post.get('title', '')} "
            f"(author: {post.get('author', 'unknown')})"
        )

    lines.extend(["", "Recent post sample:"])
    for index, post in enumerate(posts[:limit], 1):
        lines.append(
            f"{index}. [{post.get('time_label', '')}] {post.get('title', '')} "
            f"| author: {post.get('author', 'unknown')} | reads: {post.get('reads', 0)} "
            f"| comments: {post.get('replies', 0)}"
        )
        if post.get("excerpt"):
            lines.append(f"   Excerpt: {post['excerpt']}")
        if post.get("link"):
            lines.append(f"   Link: {post['link']}")

    return "\n".join(lines), company_name


def _fetch_eastmoney_mobile_guba(code: str, limit: int) -> str:
    last_error: Exception | None = None
    text = ""
    final_url = ""
    for url_template in MOBILE_GUBA_URLS:
        url = url_template.format(code=code)
        for trust_env in (False, True):
            try:
                session = requests.Session()
                session.trust_env = trust_env
                response = session.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Referer": "https://mguba.eastmoney.com/",
                        "User-Agent": "Mozilla/5.0",
                    },
                )
                response.raise_for_status()
                text = response.text
                final_url = url
                break
            except requests.RequestException as exc:
                last_error = exc
                continue
        if text:
            break

    if not text:
        return (
            "### East Money Mobile Guba\n"
            f"<eastmoney mobile guba unavailable for {code}: "
            f"{type(last_error).__name__ if last_error else 'unknown error'}>"
        )

    selector = Selector(text=text)
    posts: list[dict[str, Any]] = []
    for row in selector.css("#items > li"):
        title = _clean_text(" ".join(row.css("p.content ::text, p.content::text").getall()))
        title = re.sub(r"^(资讯|公告|问董秘)\s*", "", title).strip()
        if not title:
            continue
        time_label = _clean_text(" ".join(row.css("p.time ::text, p.time::text").getall()))
        reads = _parse_int(" ".join(row.css("p.time span::text").getall()))
        href = row.css("a::attr(href)").get() or ""
        posts.append(
            {
                "title": title,
                "time_label": time_label,
                "reads": reads,
                "likes": _parse_int(" ".join(row.css(".like_count::text").getall())),
                "link": urljoin(final_url, href.replace("//", "https://", 1) if href.startswith("//") else href),
            }
        )
        if len(posts) >= limit:
            break

    if not posts:
        return (
            "### East Money Mobile Guba\n"
            f"<no East Money mobile Guba rows found for {code}>"
        )

    lines = [
        "### East Money Mobile Guba (second public forum entry, no API key)",
        f"Source URL: {final_url}",
        f"Parsed rows: {len(posts)}",
        "",
        "Recent mobile forum/news sample:",
    ]
    for index, post in enumerate(posts, 1):
        lines.append(
            f"{index}. {post['title']} | {post['time_label']} | "
            f"reads: {post['reads']} | likes: {post['likes']}"
        )
        if post.get("link"):
            lines.append(f"   Link: {post['link']}")
    return "\n".join(lines)


def _fetch_10jqka_snapshot(code: str) -> str:
    url = THS_MOBILE_URL.format(code=code)
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://m.10jqka.com.cn/",
                "User-Agent": "Mozilla/5.0",
            },
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return (
            "### 10jqka public page (auxiliary, not a stable forum source)\n"
            f"<10jqka unavailable for {code}: {type(exc).__name__}. "
            "No 10jqka forum-post data was used.>"
        )

    selector = Selector(text=response.text)
    title = _clean_text(selector.css("title::text").get() or "")
    description = _clean_text(selector.css("meta[name=description]::attr(content)").get() or "")
    keywords = ("资金", "主力", "点评", "新闻", "研报", "行业", "财务", "风险", "热度", "舆情")
    candidates: list[str] = []
    for raw in selector.css("body ::text").getall():
        text = _clean_text(raw)
        if len(text) < 8 or len(text) > 120:
            continue
        if any(keyword in text for keyword in keywords) and text not in candidates:
            candidates.append(text)
        if len(candidates) >= 10:
            break

    lines = [
        "### 10jqka public page (auxiliary, not a stable forum source)",
        f"Source URL: {url}",
        "Forum-post status: no stable no-key post list was found; this source is not weighted as forum sentiment.",
    ]
    if title:
        lines.append(f"Page title: {title}")
    if description:
        lines.append(f"Description: {_truncate(description, 320)}")
    if candidates:
        lines.extend(["", "Extracted public-page signals:"])
        for index, item in enumerate(candidates, 1):
            lines.append(f"{index}. {item}")
    else:
        lines.append(
            "<10jqka page loaded, but no stable forum-post rows or usable public-page signals were found>"
        )
    return "\n".join(lines)


def _parse_guba_row(row: Selector, base_url: str, end_date: str) -> dict[str, Any] | None:
    title_node = row.css("div.title a")
    title = _clean_text(" ".join(title_node.css("::text").getall()))
    if not title:
        return None

    href = title_node.attrib.get("href", "")
    link = urljoin(base_url, href.replace("//", "https://", 1) if href.startswith("//") else href)
    time_label = _clean_text(" ".join(row.css("div.update::text").getall()))
    return {
        "title": title,
        "author": _clean_text(" ".join(row.css("div.author ::text").getall())) or "unknown",
        "reads": _parse_int(" ".join(row.css("div.read::text").getall())),
        "replies": _parse_int(" ".join(row.css("div.reply::text").getall())),
        "time_label": time_label,
        "datetime": _parse_guba_time(time_label, end_date),
        "link": link,
    }


def _fetch_guba_excerpt(url: str) -> str:
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://guba.eastmoney.com/",
                "User-Agent": "Mozilla/5.0",
            },
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    selector = Selector(text=response.text)
    text = " ".join(selector.css("div.newstext *::text, div.newstext::text").getall())
    return _truncate(_clean_text(text), 260)


def _fetch_tushare_news(
    code: str,
    company_name: str | None,
    start_date: str,
    end_date: str,
) -> str:
    enabled = os.getenv("TRADINGAGENTS_ENABLE_TUSHARE_NEWS", "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return (
            "### Tushare Pro news\n"
            "<tushare news disabled: set TRADINGAGENTS_ENABLE_TUSHARE_NEWS=1 "
            "only if your account has paid news/major_news permissions>"
        )

    token = os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_API_TOKEN")
    if not token:
        return "### Tushare Pro news\n<tushare news unavailable: TUSHARE_TOKEN is not set>"

    keywords = {code}
    if company_name:
        keywords.add(company_name)
    start = f"{start_date} 00:00:00"
    end = f"{end_date} 23:59:59"
    probes = (
        ("news", {"src": "sina", "start_date": start, "end_date": end}, "datetime,title,content,channels"),
        ("news", {"src": "10jqka", "start_date": start, "end_date": end}, "datetime,title,content,channels"),
        ("major_news", {"src": "sina", "start_date": start, "end_date": end}, "title,content,pub_time,src"),
        ("major_news", {"src": "eastmoney", "start_date": start, "end_date": end}, "title,content,pub_time,src"),
    )

    collected: list[dict[str, Any]] = []
    permission_notes: list[str] = []
    for api_name, params, fields in probes:
        try:
            response = requests.post(
                TUSHARE_URL,
                json={"api_name": api_name, "token": token, "params": params, "fields": fields},
                timeout=20,
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            permission_notes.append(f"{api_name}/{params.get('src')}: {type(exc).__name__}")
            continue

        code_value = payload.get("code")
        if code_value != 0:
            msg = _truncate(_clean_text(str(payload.get("msg") or "")), 160)
            permission_notes.append(f"{api_name}/{params.get('src')}: code={code_value}, {msg}")
            continue

        data = payload.get("data") or {}
        fields_out = data.get("fields") or []
        for item in data.get("items") or []:
            record = dict(zip(fields_out, item, strict=False))
            text_blob = f"{record.get('title', '')} {record.get('content', '')}"
            if any(keyword and keyword in text_blob for keyword in keywords):
                collected.append(record)

    if not collected:
        note = "; ".join(permission_notes[:4]) if permission_notes else "no keyword-matched rows"
        return (
            "### Tushare Pro news (optional domestic API)\n"
            f"<tushare news unavailable or empty for {code}: {note}>"
        )

    lines = [
        "### Tushare Pro news (optional domestic API)",
        f"Keyword-matched articles: {len(collected)}",
        "",
    ]
    for index, record in enumerate(collected[:12], 1):
        title = _clean_text(str(record.get("title") or "Untitled"))
        published = record.get("datetime") or record.get("pub_time") or ""
        content = _truncate(_clean_text(str(record.get("content") or "")), 260)
        lines.append(f"{index}. [{published}] {title}")
        if content:
            lines.append(f"   Summary: {content}")
    return "\n".join(lines)


def _company_name_from_title(title: str, code: str) -> str | None:
    match = re.search(rf"(.+?)\({re.escape(code)}\)", title)
    if match:
        return _clean_text(match.group(1))
    return None


def _parse_guba_time(value: str, end_date: str) -> datetime | None:
    if not value:
        return None
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    try:
        parsed = datetime.strptime(f"{end_dt.year}-{value}", "%Y-%m-%d %H:%M")
        if parsed > end_dt + timedelta(days=2):
            parsed = parsed.replace(year=parsed.year - 1)
        return parsed
    except ValueError:
        return None


def _parse_int(value: str) -> int:
    cleaned = _clean_text(value).replace(",", "")
    if not cleaned:
        return 0
    match = re.search(r"\d+", cleaned)
    return int(match.group(0)) if match else 0


def _clean_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."
