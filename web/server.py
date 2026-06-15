from __future__ import annotations

import json
import os
import sys
import threading
import traceback
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass


HOST = os.getenv("TRADINGAGENTS_WEB_HOST", "127.0.0.1")
PORT = int(os.getenv("TRADINGAGENTS_WEB_PORT", "8765"))

RUNS: dict[str, dict[str, Any]] = {}
RUNS_LOCK = threading.Lock()

ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
ANALYST_REPORT_MAP = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}
FIXED_AGENTS = {
    "Research": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading": ["Trader"],
    "Risk": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
    "Portfolio": ["Portfolio Manager"],
}
SECTION_TITLES = {
    "market_report": "Market",
    "sentiment_report": "Sentiment",
    "news_report": "News",
    "fundamentals_report": "Fundamentals",
    "investment_plan": "Debate",
    "trader_investment_plan": "Trader",
    "final_trade_decision": "Final Decision",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_run(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    run = {
        "id": run_id,
        "created_at": now_iso(),
        "status": "queued",
        "payload": payload,
        "events": [],
        "condition": threading.Condition(),
        "seq": 0,
        "agent_status": {},
        "reports": {},
        "stats": {"llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0},
        "final": None,
        "error": None,
    }
    with RUNS_LOCK:
        RUNS[run_id] = run
    return run


def append_event(run: dict[str, Any], event_type: str, data: dict[str, Any]) -> None:
    with run["condition"]:
        run["seq"] += 1
        event = {
            "seq": run["seq"],
            "type": event_type,
            "ts": now_iso(),
            **data,
        }
        run["events"].append(event)
        run["condition"].notify_all()


def init_agent_status(run: dict[str, Any], analysts: list[str]) -> None:
    status = {}
    for key in analysts:
        name = ANALYST_AGENT_NAMES.get(key)
        if name:
            status[name] = "pending"
    for agents in FIXED_AGENTS.values():
        for agent in agents:
            status[agent] = "pending"
    run["agent_status"] = status
    append_event(run, "state", {"agent_status": status, "stats": run["stats"]})


def set_agent(run: dict[str, Any], agent: str, status: str) -> None:
    if agent in run["agent_status"] and run["agent_status"][agent] != status:
        run["agent_status"][agent] = status
        append_event(
            run,
            "agent",
            {"agent": agent, "status": status, "agent_status": run["agent_status"]},
        )


def update_report(run: dict[str, Any], section: str, content: str) -> None:
    if not content:
        return
    run["reports"][section] = content
    append_event(
        run,
        "report",
        {
            "section": section,
            "title": SECTION_TITLES.get(section, section),
            "content": content,
            "reports": run["reports"],
        },
    )


def extract_content_string(content: Any) -> str | None:
    if content is None or content == "":
        return None
    if isinstance(content, str):
        text = content.strip()
        return text or None
    if isinstance(content, dict):
        text = str(content.get("text", "")).strip()
        return text or None
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")).strip())
            elif isinstance(item, str):
                parts.append(item.strip())
        text = " ".join(part for part in parts if part)
        return text or None
    return str(content).strip() or None


def classify_message(message: Any) -> tuple[str, str | None]:
    try:
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        content = extract_content_string(getattr(message, "content", None))
        if isinstance(message, HumanMessage):
            return ("Control" if content == "Continue" else "User", content)
        if isinstance(message, ToolMessage):
            return ("Data", content)
        if isinstance(message, AIMessage):
            return ("Agent", content)
        return ("System", content)
    except Exception:
        return ("System", extract_content_string(getattr(message, "content", None)))


def normalize_ticker(ticker: str) -> str:
    try:
        from tradingagents.dataflows.eastmoney import normalize_a_share_code

        return normalize_a_share_code(ticker) or ""
    except Exception:
        value = (ticker or "").strip().upper()
        return value if value.isdigit() and len(value) == 6 else ""


def validate_a_share_ticker(ticker: str) -> tuple[bool, str, str | None]:
    code = normalize_ticker(ticker)
    if code:
        return True, code, None
    return (
        False,
        "",
        "当前版本专注中国大陆 A 股分析。请输入 6 位 A 股代码，例如 300308、688017；暂不支持 MU.O、AAPL 等美股代码。",
    )


def selected_analysts_from_payload(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("analysts") or ["market", "social", "news", "fundamentals"]
    selected = [a for a in ANALYST_ORDER if a in set(raw)]
    return selected or ["market", "news"]


def update_analyst_statuses(run: dict[str, Any], selected: list[str], chunk: dict[str, Any]) -> None:
    found_active = False
    for key in ANALYST_ORDER:
        if key not in selected:
            continue
        agent_name = ANALYST_AGENT_NAMES[key]
        report_key = ANALYST_REPORT_MAP[key]
        if chunk.get(report_key):
            update_report(run, report_key, chunk[report_key])
        has_report = bool(run["reports"].get(report_key))
        if has_report:
            set_agent(run, agent_name, "completed")
        elif not found_active:
            set_agent(run, agent_name, "in_progress")
            found_active = True
        else:
            set_agent(run, agent_name, "pending")
    if not found_active and selected:
        set_agent(run, "Bull Researcher", "in_progress")


def provider_backend_url(provider: str) -> str | None:
    provider = provider.lower()
    defaults = {
        "deepseek": "https://api.deepseek.com",
        "openai": "https://api.openai.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "qwen-cn": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "glm": "https://open.bigmodel.cn/api/paas/v4/",
        "glm-cn": "https://open.bigmodel.cn/api/paas/v4/",
        "minimax": "https://api.minimax.io/v1",
        "minimax-cn": "https://api.minimaxi.com/v1",
    }
    return defaults.get(provider)


def market_data_vendor_chain() -> str:
    explicit = os.getenv("TRADINGAGENTS_DATA_VENDOR_CHAIN")
    if explicit:
        vendors = [item.strip().lower() for item in explicit.split(",") if item.strip()]
        if "eastmoney" in vendors:
            return "eastmoney"
    return "eastmoney"


def market_data_vendor_overrides() -> dict[str, str]:
    chain = market_data_vendor_chain()
    macro_chain = os.getenv("TRADINGAGENTS_MACRO_VENDOR_CHAIN") or "chinabond_web,tushare,fred,local_note"
    return {
        "core_stock_apis": chain,
        "technical_indicators": chain,
        "fundamental_data": chain,
        "news_data": chain,
        "capital_flow": os.getenv("TRADINGAGENTS_CAPITAL_FLOW_VENDOR") or "eastmoney",
        "macro_data": macro_chain,
    }


def build_run_docx(run: dict[str, Any]) -> bytes:
    payload = run.get("payload") or {}
    ticker = normalize_ticker(str(payload.get("ticker") or "")) or str(payload.get("ticker") or "")
    analysis_date = payload.get("analysis_date") or ""
    title = f"TradingAgents A股分析报告 - {ticker or '未命名标的'}"

    body: list[str] = []
    body.append(_docx_para(title, style="Title"))
    body.append(_docx_para(f"生成时间：{now_iso()}"))
    body.append(_docx_para(f"分析日期：{analysis_date}"))
    body.append(_docx_para(f"运行状态：{run.get('status') or 'unknown'}"))
    body.append(_docx_para(f"数据源：{market_data_vendor_chain()}；资金流：eastmoney"))
    if run.get("error"):
        body.append(_docx_para("运行错误", style="Heading1"))
        body.append(_docx_para(str(run["error"])))

    final = run.get("final") or {}
    if final.get("decision"):
        body.append(_docx_para("最终结论", style="Heading1"))
        body.append(_docx_para(str(final["decision"])))

    reports = run.get("reports") or {}
    ordered_sections = [
        "market_report",
        "news_report",
        "sentiment_report",
        "fundamentals_report",
        "investment_plan",
        "trader_investment_plan",
        "final_trade_decision",
    ]
    for section in ordered_sections:
        content = reports.get(section)
        if not content:
            continue
        body.append(_docx_para(SECTION_TITLES.get(section, section), style="Heading1"))
        body.extend(_markdown_to_docx_paragraphs(str(content)))

    stats = run.get("stats") or {}
    body.append(_docx_para("运行统计", style="Heading1"))
    for label, key in [
        ("LLM 调用", "llm_calls"),
        ("工具调用", "tool_calls"),
        ("输入 Token", "tokens_in"),
        ("输出 Token", "tokens_out"),
    ]:
        body.append(_docx_para(f"{label}：{stats.get(key, 0)}"))

    body.append(_docx_para("分析过程流水", style="Heading1"))
    for event in run.get("events", []):
        event_type = event.get("type")
        if event_type not in {"message", "tool", "error", "run"}:
            continue
        ts = str(event.get("ts", ""))[11:19]
        if event_type == "tool":
            text = f"[{ts}] TOOL {event.get('tool')}: {json.dumps(event.get('args') or {}, ensure_ascii=False)}"
        elif event_type == "error":
            text = f"[{ts}] ERROR {event.get('error')}"
        elif event_type == "run":
            text = f"[{ts}] RUN {event.get('ticker')} / {event.get('analysis_date')}"
        else:
            text = f"[{ts}] {event.get('message_type') or 'MESSAGE'}: {event.get('content') or ''}"
        body.append(_docx_para(text[:1800]))

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(body)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            "</Types>",
        )
        docx.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/styles.xml", _docx_styles())
    return buffer.getvalue()


def _markdown_to_docx_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            paragraphs.append(_docx_para(""))
            continue
        if line.startswith("### "):
            paragraphs.append(_docx_para(line[4:].strip(), style="Heading3"))
        elif line.startswith("## "):
            paragraphs.append(_docx_para(line[3:].strip(), style="Heading2"))
        elif line.startswith("# "):
            paragraphs.append(_docx_para(line[2:].strip(), style="Heading1"))
        elif line.startswith("- "):
            paragraphs.append(_docx_para("• " + line[2:].strip()))
        else:
            paragraphs.append(_docx_para(line))
    return paragraphs


def _docx_para(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    safe_text = escape(str(text), quote=False)
    preserve = ' xml:space="preserve"' if safe_text.startswith(" ") or safe_text.endswith(" ") else ""
    return f"<w:p>{style_xml}<w:r><w:t{preserve}>{safe_text}</w:t></w:r></w:p>"


def _docx_styles() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title">'
        '<w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1">'
        '<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2">'
        '<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading3">'
        '<w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
        "</w:styles>"
    )


def run_real_analysis(run: dict[str, Any]) -> None:
    from cli.stats_handler import StatsCallbackHandler
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    payload = run["payload"]
    ok, ticker, validation_error = validate_a_share_ticker(payload.get("ticker", ""))
    if not ok:
        raise ValueError(validation_error)
    asset_type = "stock"
    analysis_date = payload.get("analysis_date") or datetime.now().strftime("%Y-%m-%d")
    selected = selected_analysts_from_payload(payload)

    depth = int(payload.get("depth", 1))
    provider = payload.get("provider") or os.getenv("TRADINGAGENTS_LLM_PROVIDER") or "deepseek"
    quick_model = payload.get("quick_model") or os.getenv("TRADINGAGENTS_QUICK_THINK_LLM") or "deepseek-chat"
    deep_model = payload.get("deep_model") or os.getenv("TRADINGAGENTS_DEEP_THINK_LLM") or quick_model

    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "llm_provider": provider.lower(),
            "quick_think_llm": quick_model,
            "deep_think_llm": deep_model,
            "backend_url": payload.get("backend_url") or provider_backend_url(provider),
            "output_language": payload.get("output_language") or os.getenv("TRADINGAGENTS_OUTPUT_LANGUAGE") or "Chinese",
            "max_debate_rounds": depth,
            "max_risk_discuss_rounds": depth,
            "checkpoint_enabled": False,
        }
    )
    config["data_vendors"] = {
        **config.get("data_vendors", {}),
        **market_data_vendor_overrides(),
    }

    stats_handler = StatsCallbackHandler()
    run["status"] = "running"
    append_event(
        run,
        "run",
        {
            "status": "running",
            "ticker": ticker,
            "analysis_date": analysis_date,
            "asset_type": asset_type,
            "provider": provider,
            "quick_model": quick_model,
            "deep_model": deep_model,
            "analysts": selected,
        },
    )
    init_agent_status(run, selected)
    append_event(run, "message", {"message_type": "System", "content": f"Starting analysis for {ticker} on {analysis_date}."})
    append_event(run, "message", {"message_type": "System", "content": "A-share-only mode: mainland China six-digit tickers are supported."})
    append_event(run, "message", {"message_type": "System", "content": f"Market data vendors: {market_data_vendor_chain()}; capital flow: eastmoney."})

    graph = TradingAgentsGraph(
        selected,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )
    first = ANALYST_AGENT_NAMES.get(selected[0])
    if first:
        set_agent(run, first, "in_progress")

    instrument_context = graph.resolve_instrument_context(ticker, asset_type)
    init_state = graph.propagator.create_initial_state(
        ticker,
        analysis_date,
        asset_type=asset_type,
        instrument_context=instrument_context,
    )
    args = graph.propagator.get_graph_args(callbacks=[stats_handler])
    trace: list[dict[str, Any]] = []
    processed_ids: set[str] = set()

    for chunk in graph.graph.stream(init_state, **args):
        for message in chunk.get("messages", []):
            msg_id = getattr(message, "id", None)
            if msg_id and msg_id in processed_ids:
                continue
            if msg_id:
                processed_ids.add(msg_id)

            msg_type, content = classify_message(message)
            if content:
                append_event(run, "message", {"message_type": msg_type, "content": content[:2500]})

            for tool_call in getattr(message, "tool_calls", []) or []:
                if isinstance(tool_call, dict):
                    tool_name = tool_call.get("name", "tool")
                    tool_args = tool_call.get("args", {})
                else:
                    tool_name = getattr(tool_call, "name", "tool")
                    tool_args = getattr(tool_call, "args", {})
                append_event(run, "tool", {"tool": tool_name, "args": tool_args})

        update_analyst_statuses(run, selected, chunk)

        debate = chunk.get("investment_debate_state")
        if debate:
            bull = (debate.get("bull_history") or "").strip()
            bear = (debate.get("bear_history") or "").strip()
            judge = (debate.get("judge_decision") or "").strip()
            if bull or bear:
                for agent in FIXED_AGENTS["Research"]:
                    set_agent(run, agent, "in_progress")
            if bull:
                update_report(run, "investment_plan", f"### Bull Researcher Analysis\n{bull}")
            if bear:
                update_report(run, "investment_plan", f"### Bear Researcher Analysis\n{bear}")
            if judge:
                update_report(run, "investment_plan", f"### Research Manager Decision\n{judge}")
                for agent in FIXED_AGENTS["Research"]:
                    set_agent(run, agent, "completed")
                set_agent(run, "Trader", "in_progress")

        if chunk.get("trader_investment_plan"):
            update_report(run, "trader_investment_plan", chunk["trader_investment_plan"])
            set_agent(run, "Trader", "completed")
            set_agent(run, "Aggressive Analyst", "in_progress")

        risk = chunk.get("risk_debate_state")
        if risk:
            parts = []
            for key, agent in [
                ("aggressive_history", "Aggressive Analyst"),
                ("conservative_history", "Conservative Analyst"),
                ("neutral_history", "Neutral Analyst"),
            ]:
                content = (risk.get(key) or "").strip()
                if content:
                    set_agent(run, agent, "in_progress")
                    parts.append(f"### {agent} Analysis\n{content}")
            judge = (risk.get("judge_decision") or "").strip()
            if judge:
                parts.append(f"### Portfolio Manager Decision\n{judge}")
                for agent in FIXED_AGENTS["Risk"] + FIXED_AGENTS["Portfolio"]:
                    set_agent(run, agent, "completed")
            if parts:
                update_report(run, "final_trade_decision", "\n\n".join(parts))

        run["stats"] = stats_handler.get_stats()
        append_event(run, "stats", {"stats": run["stats"]})
        trace.append(chunk)

    final_state: dict[str, Any] = {}
    for chunk in trace:
        final_state.update(chunk)

    final_decision = final_state.get("final_trade_decision") or run["reports"].get("final_trade_decision") or ""
    try:
        signal = graph.process_signal(final_decision) if final_decision else "No final signal"
    except Exception:
        signal = "Final signal unavailable"
    for agent in list(run["agent_status"]):
        set_agent(run, agent, "completed")
    run["final"] = {"decision": signal, "reports": run["reports"], "stats": run["stats"]}
    run["status"] = "completed"
    append_event(run, "complete", {"status": "completed", "final": run["final"]})


def run_worker(run: dict[str, Any]) -> None:
    try:
        run_real_analysis(run)
    except Exception as exc:
        run["status"] = "error"
        run["error"] = str(exc)
        append_event(
            run,
            "error",
            {
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(limit=8),
            },
        )
    finally:
        with run["condition"]:
            run["condition"].notify_all()


def response_json(handler: BaseHTTPRequestHandler, status: int, data: dict[str, Any]) -> None:
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def response_binary(
    handler: BaseHTTPRequestHandler,
    status: int,
    body: bytes,
    content_type: str,
    filename: str | None = None,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    if filename:
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.end_headers()
    handler.wfile.write(body)


class TradingAgentsWebHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/config":
            self.handle_config()
            return
        if path.startswith("/api/runs/") and path.endswith("/report.docx"):
            run_id = path.split("/")[3]
            self.handle_report_docx(run_id)
            return
        if path.startswith("/api/runs/") and path.endswith("/events"):
            run_id = path.split("/")[3]
            self.handle_events(run_id)
            return
        if path.startswith("/api/runs/"):
            run_id = path.split("/")[3]
            self.handle_run(run_id)
            return
        response_json(self, 404, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/runs":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                response_json(self, 400, {"error": "Invalid JSON"})
                return
            ok, normalized, validation_error = validate_a_share_ticker(str(payload.get("ticker") or ""))
            if not ok:
                response_json(self, 400, {"error": validation_error})
                return
            payload["ticker"] = normalized
            payload["mode"] = "real"
            run = make_run(payload)
            thread = threading.Thread(target=run_worker, args=(run,), daemon=True)
            thread.start()
            response_json(self, 201, {"run_id": run["id"], "status": run["status"]})
            return
        response_json(self, 404, {"error": "Not found"})

    def handle_config(self) -> None:
        try:
            from tradingagents.default_config import DEFAULT_CONFIG
        except Exception:
            DEFAULT_CONFIG = {}
        provider = os.getenv("TRADINGAGENTS_LLM_PROVIDER") or DEFAULT_CONFIG.get("llm_provider", "deepseek")
        key_env = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "qwen": "DASHSCOPE_API_KEY",
            "qwen-cn": "DASHSCOPE_CN_API_KEY",
            "glm": "ZHIPU_API_KEY",
            "glm-cn": "ZHIPU_CN_API_KEY",
        }.get(str(provider).lower(), "DEEPSEEK_API_KEY")
        response_json(
            self,
            200,
            {
                "provider": provider,
                "quick_model": os.getenv("TRADINGAGENTS_QUICK_THINK_LLM") or DEFAULT_CONFIG.get("quick_think_llm", "deepseek-chat"),
                "deep_model": os.getenv("TRADINGAGENTS_DEEP_THINK_LLM") or DEFAULT_CONFIG.get("deep_think_llm", "deepseek-chat"),
                "output_language": os.getenv("TRADINGAGENTS_OUTPUT_LANGUAGE") or DEFAULT_CONFIG.get("output_language", "Chinese"),
                "data_vendor_chain": market_data_vendor_chain(),
                "macro_vendor_chain": os.getenv("TRADINGAGENTS_MACRO_VENDOR_CHAIN") or "chinabond_web,tushare,fred,local_note",
                "capital_flow_vendor": os.getenv("TRADINGAGENTS_CAPITAL_FLOW_VENDOR") or "eastmoney",
                "supported_market": "中国大陆 A 股",
                "app_mode": "a_share_only",
                "alpha_vantage_key_present": bool(os.getenv("ALPHA_VANTAGE_API_KEY")),
                "fred_key_present": bool(os.getenv("FRED_API_KEY")),
                "tushare_key_present": bool(os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_API_TOKEN")),
                "api_key_env": key_env,
                "api_key_present": bool(os.getenv(key_env)),
            },
        )

    def handle_report_docx(self, run_id: str) -> None:
        run = RUNS.get(run_id)
        if not run:
            response_json(self, 404, {"error": "Run not found"})
            return
        body = build_run_docx(run)
        payload = run.get("payload") or {}
        ticker = normalize_ticker(str(payload.get("ticker") or "")) or "Ashare"
        date = str(payload.get("analysis_date") or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
        response_binary(
            self,
            200,
            body,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"TradingAgents_{ticker}_{date}.docx",
        )

    def handle_run(self, run_id: str) -> None:
        run = RUNS.get(run_id)
        if not run:
            response_json(self, 404, {"error": "Run not found"})
            return
        response_json(
            self,
            200,
            {
                "id": run["id"],
                "status": run["status"],
                "created_at": run["created_at"],
                "payload": run["payload"],
                "agent_status": run["agent_status"],
                "reports": run["reports"],
                "stats": run["stats"],
                "final": run["final"],
                "error": run["error"],
            },
        )

    def handle_events(self, run_id: str) -> None:
        run = RUNS.get(run_id)
        if not run:
            response_json(self, 404, {"error": "Run not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        index = 0
        while True:
            with run["condition"]:
                if index >= len(run["events"]) and run["status"] not in ("completed", "error"):
                    run["condition"].wait(timeout=15)
                pending = run["events"][index:]
                index = len(run["events"])
                done = run["status"] in ("completed", "error") and not pending
            if not pending:
                if done:
                    break
                try:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    break
                continue
            for event in pending:
                try:
                    payload = json.dumps(event, ensure_ascii=False)
                    frame = f"id: {event['seq']}\nevent: {event['type']}\ndata: {payload}\n\n"
                    self.wfile.write(frame.encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request: Any, client_address: Any) -> None:
        exc_type, _, _ = sys.exc_info()
        if exc_type in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        super().handle_error(request, client_address)


def main() -> None:
    server = QuietThreadingHTTPServer((HOST, PORT), TradingAgentsWebHandler)
    print(f"TradingAgents web backend running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
