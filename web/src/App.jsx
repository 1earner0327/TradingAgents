import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  Brain,
  CheckCircle2,
  CircleDot,
  Clock3,
  DatabaseZap,
  FileDown,
  Gauge,
  Layers3,
  Play,
  Radio,
  ShieldAlert,
  Square,
  TerminalSquare,
  TrendingUp,
  Zap
} from "lucide-react";

const ANALYSTS = [
  { key: "market", label: "技术面", agent: "Market Analyst" },
  { key: "news", label: "新闻面", agent: "News Analyst" },
  { key: "social", label: "情绪面", agent: "Sentiment Analyst" },
  { key: "fundamentals", label: "基本面", agent: "Fundamentals Analyst" }
];

const AGENT_LABELS = {
  "Market Analyst": "技术面分析员",
  "News Analyst": "新闻分析员",
  "Sentiment Analyst": "情绪分析员",
  "Fundamentals Analyst": "基本面分析员",
  "Bull Researcher": "多头研究员",
  "Bear Researcher": "空头研究员",
  "Research Manager": "研究经理",
  Trader: "交易员",
  "Aggressive Analyst": "激进风控",
  "Neutral Analyst": "中性风控",
  "Conservative Analyst": "保守风控",
  "Portfolio Manager": "组合经理"
};

const WORKFLOW = [
  {
    desk: "分析组",
    icon: BarChart3,
    agents: ["Market Analyst", "News Analyst", "Sentiment Analyst", "Fundamentals Analyst"]
  },
  {
    desk: "研究组",
    icon: Brain,
    agents: ["Bull Researcher", "Bear Researcher", "Research Manager"]
  },
  { desk: "交易员", icon: TrendingUp, agents: ["Trader"] },
  {
    desk: "风控组",
    icon: ShieldAlert,
    agents: ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"]
  },
  { desk: "组合经理", icon: Gauge, agents: ["Portfolio Manager"] }
];

const REPORT_TABS = [
  ["market_report", "技术面"],
  ["news_report", "新闻面"],
  ["sentiment_report", "情绪面"],
  ["fundamentals_report", "基本面"],
  ["investment_plan", "多空辩论"],
  ["trader_investment_plan", "交易计划"],
  ["final_trade_decision", "最终结论"]
];

const EVENT_LABELS = {
  System: "系统",
  User: "用户",
  Agent: "智能体",
  Tool: "工具",
  Data: "数据",
  error: "错误"
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

function compact(n) {
  if (!n) return "0";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function normalizeATicker(value) {
  const raw = (value || "").trim().toUpperCase().replace(/\s+/g, "");
  const match = raw.match(/^(?:SH|SZ)?(\d{6})(?:\.(?:SH|SS|SZ))?$/i);
  return match ? match[1] : "";
}

function validateATicker(value) {
  const code = normalizeATicker(value);
  if (code) return { ok: true, code, message: "" };
  return {
    ok: false,
    code: "",
    message: "当前版本只支持中国大陆 A 股六位代码，例如 300308、688017。"
  };
}

function statusLabel(status) {
  if (status === "completed") return "完成";
  if (status === "in_progress") return "进行中";
  if (status === "error") return "错误";
  return "等待";
}

function runStateLabel(status) {
  if (status === "completed") return "已完成";
  if (status === "running") return "分析中";
  if (status === "queued") return "排队中";
  if (status === "error") return "出错";
  return "待开始";
}

function MarkdownBlock({ text, empty = "暂无内容。" }) {
  if (!text) return <p className="empty-text">{empty}</p>;
  const normalized = text.replace(/<br\s*\/?>/gi, "\n");
  return (
    <div className="markdown-block">
      {normalized.split("\n").map((line, index) => {
        const key = `${index}-${line}`;
        if (!line.trim()) return <div key={key} className="md-space" />;
        if (line.startsWith("### ")) return <h3 key={key}>{line.replace("### ", "")}</h3>;
        if (line.startsWith("## ")) return <h2 key={key}>{line.replace("## ", "")}</h2>;
        if (line.startsWith("# ")) return <h1 key={key}>{line.replace("# ", "")}</h1>;
        if (line.startsWith("- ")) return <li key={key}>{line.replace("- ", "")}</li>;
        return <p key={key}>{line}</p>;
      })}
    </div>
  );
}

function ConnectionPill({ config, runStatus }) {
  const live = runStatus === "running";
  return (
    <div className={`connection-pill ${live ? "live" : ""}`}>
      <Radio size={15} />
      <span>{live ? "运行中" : "就绪"}</span>
      <strong>{config.provider || "provider"}</strong>
    </div>
  );
}

function AgentCard({ group, agentStatus }) {
  const Icon = group.icon;
  const states = group.agents.map((agent) => agentStatus[agent]).filter(Boolean);
  const active = states.includes("in_progress");
  const completed = states.length > 0 && states.every((state) => state === "completed");
  return (
    <section className={`agent-card ${active ? "active" : ""} ${completed ? "done" : ""}`}>
      <div className="agent-card-top">
        <div className="agent-icon">
          <Icon size={18} />
        </div>
        <div>
          <h3>{group.desk}</h3>
          <span>{active ? "正在处理" : completed ? "已完成" : "等待中"}</span>
        </div>
      </div>
      <div className="agent-list">
        {group.agents.map((agent) => {
          const status = agentStatus[agent] || "pending";
          return (
            <div className="agent-row" key={agent}>
              <span className={`dot ${status}`} />
              <span>{AGENT_LABELS[agent] || agent}</span>
              <em>{statusLabel(status)}</em>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function EventFeed({ events }) {
  return (
    <section className="panel feed-panel">
      <div className="panel-title">
        <div>
          <span className="eyeline">过程流水</span>
          <h2>Signal feed</h2>
        </div>
        <Activity size={18} />
      </div>
      <div className="feed-list">
        {events.length === 0 ? (
          <p className="empty-text">开始真实分析后，这里会显示工具调用和智能体消息。</p>
        ) : (
          events.map((event) => {
            const kind = event.type === "tool" ? "Tool" : event.message_type || event.type;
            return (
              <article className={`feed-item ${event.type}`} key={`${event.seq}-${event.ts}`}>
                <div className="feed-kind">{EVENT_LABELS[kind] || kind}</div>
                <p>{event.type === "tool" ? `${event.tool} ${JSON.stringify(event.args || {})}` : event.content || event.error}</p>
                <time>{event.ts?.slice(11, 19)}</time>
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}

function ConfigRail({ form, setForm, config, onRun, running, validation }) {
  const toggleAnalyst = (key) => {
    setForm((current) => {
      const exists = current.analysts.includes(key);
      const analysts = exists
        ? current.analysts.filter((item) => item !== key)
        : [...current.analysts, key];
      return { ...current, analysts: analysts.length ? analysts : current.analysts };
    });
  };

  return (
    <aside className="config-rail">
      <div className="brand-block">
        <div className="brand-mark">
          <Layers3 size={23} />
        </div>
        <div>
          <h1>A 股研究台</h1>
          <span>TradingAgents 本地控制台</span>
        </div>
      </div>

      <div className="form-stack">
        <label>
          <span>股票代码</span>
          <input
            value={form.ticker}
            onChange={(event) => setForm({ ...form, ticker: event.target.value.toUpperCase() })}
            placeholder="例如 300308"
          />
          {!validation.ok && form.ticker ? <small className="field-error">{validation.message}</small> : null}
        </label>
        <label>
          <span>分析日期</span>
          <input
            type="date"
            value={form.analysis_date}
            onChange={(event) => setForm({ ...form, analysis_date: event.target.value })}
          />
        </label>
        <label>
          <span>研究深度</span>
          <select value={form.depth} onChange={(event) => setForm({ ...form, depth: Number(event.target.value) })}>
            <option value={1}>快速 - 1 轮辩论</option>
            <option value={3}>均衡 - 3 轮辩论</option>
            <option value={5}>深入 - 5 轮辩论</option>
          </select>
        </label>

        <div className="analyst-picker">
          <span>分析模块</span>
          {ANALYSTS.map((analyst) => (
            <button
              className={form.analysts.includes(analyst.key) ? "selected" : ""}
              key={analyst.key}
              type="button"
              onClick={() => toggleAnalyst(analyst.key)}
            >
              <CheckCircle2 size={15} />
              {analyst.label}
            </button>
          ))}
        </div>

        <div className="provider-card">
          <div>
            <span>市场范围</span>
            <strong>{config.supported_market || "中国大陆 A 股"}</strong>
          </div>
          <div>
            <span>模型</span>
            <strong>{config.provider || "deepseek"}</strong>
          </div>
          <div>
            <span>API key</span>
            <strong className={config.api_key_present ? "ok" : "warn"}>
              {config.api_key_present ? "已检测" : "缺失"}
            </strong>
          </div>
          <div>
            <span>行情</span>
            <strong className="vendor-chain">{config.data_vendor_chain || "eastmoney"}</strong>
          </div>
          <div>
            <span>资金流</span>
            <strong className="vendor-chain">{config.capital_flow_vendor || "eastmoney"}</strong>
          </div>
          <div>
            <span>宏观</span>
            <strong className="vendor-chain">{config.macro_vendor_chain || "chinabond_web,local_note"}</strong>
          </div>
          <small>{config.quick_model || "deepseek-chat"} / {config.deep_model || "deepseek-chat"}</small>
        </div>
      </div>

      <button className="run-button" type="button" disabled={running || !validation.ok} onClick={onRun}>
        {running ? <Square size={17} /> : <Play size={17} />}
        {running ? "正在分析" : "开始真实分析"}
      </button>
    </aside>
  );
}

export default function App() {
  const eventSource = useRef(null);
  const terminalRef = useRef(false);
  const [config, setConfig] = useState({});
  const [form, setForm] = useState({
    ticker: "300308",
    analysis_date: today(),
    depth: 1,
    analysts: ["market", "news", "social", "fundamentals"]
  });
  const [runStatus, setRunStatus] = useState("idle");
  const [runId, setRunId] = useState(null);
  const [runMeta, setRunMeta] = useState(null);
  const [agentStatus, setAgentStatus] = useState({});
  const [events, setEvents] = useState([]);
  const [reports, setReports] = useState({});
  const [stats, setStats] = useState({ llm_calls: 0, tool_calls: 0, tokens_in: 0, tokens_out: 0 });
  const [final, setFinal] = useState(null);
  const [activeTab, setActiveTab] = useState("market_report");
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/config")
      .then((res) => res.json())
      .then(setConfig)
      .catch(() => setConfig({ provider: "offline", api_key_present: false }));
    return () => eventSource.current?.close();
  }, []);

  const validation = useMemo(() => validateATicker(form.ticker), [form.ticker]);
  const running = runStatus === "running" || runStatus === "queued";

  const visibleEvents = useMemo(
    () => events.filter((event) => event.type === "message" || event.type === "tool" || event.type === "error"),
    [events]
  );

  const activeReport = reports[activeTab];
  const completedAgents = Object.values(agentStatus).filter((status) => status === "completed").length;
  const totalAgents = Object.keys(agentStatus).length || 1;

  function ingest(event) {
    setEvents((current) => [event, ...current].slice(0, 220));
    if (event.status) setRunStatus(event.status);
    if (event.agent_status) setAgentStatus({ ...event.agent_status });
    if (event.reports) setReports({ ...event.reports });
    if (event.stats) setStats({ ...event.stats });
    if (event.type === "run") setRunMeta(event);
    if (event.type === "report") setActiveTab(event.section);
    if (event.type === "complete") {
      terminalRef.current = true;
      setFinal(event.final);
      setRunStatus("completed");
      eventSource.current?.close();
    }
    if (event.type === "error") {
      terminalRef.current = true;
      setError(event.error);
      setRunStatus("error");
      eventSource.current?.close();
    }
  }

  async function startRun() {
    const validated = validateATicker(form.ticker);
    if (!validated.ok) {
      setRunStatus("error");
      setError(validated.message);
      return;
    }

    eventSource.current?.close();
    terminalRef.current = false;
    setRunStatus("queued");
    setRunId(null);
    setRunMeta(null);
    setAgentStatus({});
    setEvents([]);
    setReports({});
    setFinal(null);
    setError(null);
    setStats({ llm_calls: 0, tool_calls: 0, tokens_in: 0, tokens_out: 0 });

    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...form,
        ticker: validated.code,
        provider: config.provider || "deepseek",
        quick_model: config.quick_model || "deepseek-chat",
        deep_model: config.deep_model || "deepseek-chat",
        output_language: config.output_language || "Chinese"
      })
    });
    const data = await response.json();
    if (!response.ok) {
      terminalRef.current = true;
      setRunStatus("error");
      setError(data.error || "无法开始分析。");
      return;
    }
    setRunId(data.run_id);
    const source = new EventSource(`/api/runs/${data.run_id}/events`);
    eventSource.current = source;
    ["run", "state", "agent", "message", "tool", "report", "stats", "complete", "error"].forEach((type) => {
      source.addEventListener(type, (message) => ingest(JSON.parse(message.data)));
    });
    source.onerror = async () => {
      if (terminalRef.current) return;
      try {
        const snapshotResponse = await fetch(`/api/runs/${data.run_id}`);
        if (!snapshotResponse.ok) return;
        const snapshot = await snapshotResponse.json();
        if (snapshot.agent_status) setAgentStatus({ ...snapshot.agent_status });
        if (snapshot.reports) setReports({ ...snapshot.reports });
        if (snapshot.stats) setStats({ ...snapshot.stats });
        if (snapshot.status === "completed") {
          terminalRef.current = true;
          source.close();
          setFinal(snapshot.final);
          setRunStatus("completed");
          return;
        }
        if (snapshot.status === "error") {
          terminalRef.current = true;
          source.close();
          setError(snapshot.error || "分析失败。");
          setRunStatus("error");
          return;
        }
        setRunStatus(snapshot.status || "running");
      } catch {
        setRunStatus("running");
      }
    };
  }

  function downloadReport() {
    if (!runId || running) return;
    window.open(`/api/runs/${runId}/report.docx`, "_blank", "noopener,noreferrer");
  }

  return (
    <main className="app-shell">
      <ConfigRail
        form={form}
        setForm={setForm}
        config={config}
        onRun={startRun}
        running={running}
        validation={validation}
      />

      <section className="workspace">
        <header className="topbar">
          <div>
            <span className="eyeline">A 股多智能体投研流程</span>
            <h2>{runMeta ? `${runMeta.ticker} / ${runMeta.analysis_date}` : "等待输入 A 股标的"}</h2>
          </div>
          <div className="topbar-actions">
            <ConnectionPill config={config} runStatus={runStatus} />
            <div className="stat-chip">
              <Zap size={15} />
              LLM {stats.llm_calls}
            </div>
            <div className="stat-chip">
              <DatabaseZap size={15} />
              工具 {stats.tool_calls}
            </div>
            <button className="download-button" type="button" disabled={!runId || running} onClick={downloadReport}>
              <FileDown size={16} />
              下载 Word
            </button>
          </div>
        </header>

        <div className="metrics-row">
          <article>
            <span>智能体进度</span>
            <strong>{completedAgents}/{totalAgents}</strong>
            <div className="meter"><i style={{ width: `${(completedAgents / totalAgents) * 100}%` }} /></div>
          </article>
          <article>
            <span>Token 流量</span>
            <strong>{compact(stats.tokens_in)} in / {compact(stats.tokens_out)} out</strong>
            <div className="meter teal"><i style={{ width: stats.tokens_out ? "68%" : "12%" }} /></div>
          </article>
          <article>
            <span>运行状态</span>
            <strong>{runStateLabel(runStatus)}</strong>
            <div className="meter amber"><i style={{ width: running ? "54%" : runStatus === "completed" ? "100%" : "10%" }} /></div>
          </article>
        </div>

        <div className="main-grid">
          <section className="panel workflow-panel">
            <div className="panel-title">
              <div>
                <span className="eyeline">Agent orchestration</span>
                <h2>工作流看板</h2>
              </div>
              <TerminalSquare size={18} />
            </div>
            <div className="workflow-grid">
              {WORKFLOW.map((group) => (
                <AgentCard group={group} agentStatus={agentStatus} key={group.desk} />
              ))}
            </div>
          </section>

          <EventFeed events={visibleEvents} />
        </div>

        <section className="memo-grid">
          <article className="panel memo-panel">
            <div className="panel-title">
              <div>
                <span className="eyeline">Research output</span>
                <h2>实时备忘录</h2>
              </div>
              <Clock3 size={18} />
            </div>
            <div className="tab-row">
              {REPORT_TABS.map(([key, label]) => (
                <button className={activeTab === key ? "active" : ""} key={key} onClick={() => setActiveTab(key)}>
                  <span className={reports[key] ? "tab-dot ready" : "tab-dot"} />
                  {label}
                </button>
              ))}
            </div>
            <MarkdownBlock text={activeReport} />
          </article>

          <aside className="panel verdict-panel">
            <div className="panel-title">
              <div>
                <span className="eyeline">Portfolio desk</span>
                <h2>最终意见</h2>
              </div>
              <CircleDot size={18} />
            </div>
            {error ? (
              <div className="error-box">
                <strong>分析未完成</strong>
                <p>{error}</p>
              </div>
            ) : (
              <>
                <div className="verdict-score">
                  <span>{final?.decision || "等待组合经理决策"}</span>
                  <strong>{final ? "可下载" : "生成中"}</strong>
                </div>
                <MarkdownBlock
                  text={reports.final_trade_decision}
                  empty="风控评审结束后，这里会显示组合经理的最终意见。"
                />
              </>
            )}
          </aside>
        </section>
      </section>
    </main>
  );
}
