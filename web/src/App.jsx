import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  Brain,
  CheckCircle2,
  CircleDot,
  Clock3,
  DatabaseZap,
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
  { key: "market", label: "Market", agent: "Market Analyst" },
  { key: "news", label: "News", agent: "News Analyst" },
  { key: "social", label: "Sentiment", agent: "Sentiment Analyst" },
  { key: "fundamentals", label: "Fundamentals", agent: "Fundamentals Analyst" }
];

const WORKFLOW = [
  {
    desk: "Analysts",
    icon: BarChart3,
    agents: ["Market Analyst", "News Analyst", "Sentiment Analyst", "Fundamentals Analyst"]
  },
  {
    desk: "Research",
    icon: Brain,
    agents: ["Bull Researcher", "Bear Researcher", "Research Manager"]
  },
  { desk: "Trader", icon: TrendingUp, agents: ["Trader"] },
  {
    desk: "Risk",
    icon: ShieldAlert,
    agents: ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"]
  },
  { desk: "Portfolio", icon: Gauge, agents: ["Portfolio Manager"] }
];

const REPORT_TABS = [
  ["market_report", "Market"],
  ["news_report", "News"],
  ["sentiment_report", "Sentiment"],
  ["fundamentals_report", "Fundamentals"],
  ["investment_plan", "Debate"],
  ["trader_investment_plan", "Trader"],
  ["final_trade_decision", "Final"]
];

function today() {
  return new Date().toISOString().slice(0, 10);
}

function compact(n) {
  if (!n) return "0";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function statusLabel(status) {
  if (status === "completed") return "Complete";
  if (status === "in_progress") return "Active";
  if (status === "error") return "Error";
  return "Queued";
}

function MarkdownBlock({ text, empty = "No memo has been published yet." }) {
  if (!text) return <p className="empty-text">{empty}</p>;
  return (
    <div className="markdown-block">
      {text.split("\n").map((line, index) => {
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
      <span>{live ? "Streaming" : "Ready"}</span>
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
          <Icon size={19} />
        </div>
        <div>
          <h3>{group.desk}</h3>
          <span>{active ? "In motion" : completed ? "Cleared" : "Waiting"}</span>
        </div>
      </div>
      <div className="agent-list">
        {group.agents.map((agent) => {
          const status = agentStatus[agent] || "pending";
          return (
            <div className="agent-row" key={agent}>
              <span className={`dot ${status}`} />
              <span>{agent}</span>
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
          <span className="eyeline">Live tape</span>
          <h2>Signal feed</h2>
        </div>
        <Activity size={18} />
      </div>
      <div className="feed-list">
        {events.length === 0 ? (
          <p className="empty-text">Run a task to watch model messages and tool calls stream in.</p>
        ) : (
          events.map((event) => (
            <article className={`feed-item ${event.type}`} key={`${event.seq}-${event.ts}`}>
              <div className="feed-kind">{event.type === "tool" ? "Tool" : event.message_type || event.type}</div>
              <p>{event.type === "tool" ? `${event.tool} ${JSON.stringify(event.args || {})}` : event.content || event.error}</p>
              <time>{event.ts?.slice(11, 19)}</time>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function ConfigRail({ form, setForm, config, onRun, running }) {
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
          <Layers3 size={24} />
        </div>
        <div>
          <h1>TradingAgents</h1>
          <span>Research console</span>
        </div>
      </div>

      <div className="form-stack">
        <label>
          <span>Ticker</span>
          <input
            value={form.ticker}
            onChange={(event) => setForm({ ...form, ticker: event.target.value.toUpperCase() })}
            placeholder="NVDA"
          />
        </label>
        <label>
          <span>Analysis date</span>
          <input
            type="date"
            value={form.analysis_date}
            onChange={(event) => setForm({ ...form, analysis_date: event.target.value })}
          />
        </label>
        <label>
          <span>Research depth</span>
          <select value={form.depth} onChange={(event) => setForm({ ...form, depth: Number(event.target.value) })}>
            <option value={1}>Focused - 1 round</option>
            <option value={3}>Balanced - 3 rounds</option>
            <option value={5}>Deep - 5 rounds</option>
          </select>
        </label>

        <div className="analyst-picker">
          <span>Analyst desk</span>
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

        <div className="mode-switch">
          <button
            className={form.mode === "real" ? "selected" : ""}
            type="button"
            onClick={() => setForm({ ...form, mode: "real" })}
          >
            Real run
          </button>
          <button
            className={form.mode === "demo" ? "selected" : ""}
            type="button"
            onClick={() => setForm({ ...form, mode: "demo" })}
          >
            Demo
          </button>
        </div>

        <div className="provider-card">
          <div>
            <span>Provider</span>
            <strong>{config.provider || "deepseek"}</strong>
          </div>
          <div>
            <span>API key</span>
            <strong className={config.api_key_present ? "ok" : "warn"}>
              {config.api_key_present ? "Detected" : "Missing"}
            </strong>
          </div>
          <div>
            <span>Data</span>
            <strong className="vendor-chain">{config.data_vendor_chain || "yfinance"}</strong>
          </div>
          <div>
            <span>AV key</span>
            <strong className={config.alpha_vantage_key_present ? "ok" : "warn"}>
              {config.alpha_vantage_key_present ? "Detected" : "Missing"}
            </strong>
          </div>
          <div>
            <span>Macro</span>
            <strong className="vendor-chain">{config.macro_vendor_chain || "chinabond_web,tushare,fred,local_note"}</strong>
          </div>
          <div>
            <span>Tushare</span>
            <strong className={config.tushare_key_present ? "ok" : "muted"}>
              {config.tushare_key_present ? "Detected" : "Optional"}
            </strong>
          </div>
          <div>
            <span>FRED</span>
            <strong className={config.fred_key_present ? "ok" : "muted"}>
              {config.fred_key_present ? "Detected" : "Optional"}
            </strong>
          </div>
          <small>{config.quick_model || "deepseek-chat"} / {config.deep_model || "deepseek-chat"}</small>
        </div>
      </div>

      <button className="run-button" type="button" disabled={running} onClick={onRun}>
        {running ? <Square size={17} /> : <Play size={17} />}
        {running ? "Analysis running" : "Run analysis"}
      </button>
    </aside>
  );
}

export default function App() {
  const eventSource = useRef(null);
  const terminalRef = useRef(false);
  const [config, setConfig] = useState({});
  const [form, setForm] = useState({
    ticker: "NVDA",
    analysis_date: today(),
    depth: 1,
    mode: "demo",
    analysts: ["market", "news", "social", "fundamentals"]
  });
  const [runStatus, setRunStatus] = useState("idle");
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

  const running = runStatus === "running" || runStatus === "queued";

  const visibleEvents = useMemo(
    () => events.filter((event) => event.type === "message" || event.type === "tool" || event.type === "error"),
    [events]
  );

  const activeReport = reports[activeTab];
  const completedAgents = Object.values(agentStatus).filter((status) => status === "completed").length;
  const totalAgents = Object.keys(agentStatus).length || 1;

  function ingest(event) {
    setEvents((current) => [event, ...current].slice(0, 180));
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
    eventSource.current?.close();
    terminalRef.current = false;
    setRunStatus("queued");
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
      setError(data.error || "Unable to start analysis.");
      return;
    }
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
          setError(snapshot.error || "Run failed.");
          setRunStatus("error");
          return;
        }
        setRunStatus(snapshot.status || "running");
      } catch {
        setRunStatus("running");
      }
    };
  }

  return (
    <main className="app-shell">
      <ConfigRail form={form} setForm={setForm} config={config} onRun={startRun} running={running} />

      <section className="workspace">
        <header className="topbar">
          <div>
            <span className="eyeline">Institutional multi-agent research</span>
            <h2>{runMeta ? `${runMeta.ticker} / ${runMeta.analysis_date}` : "Research Command Center"}</h2>
          </div>
          <div className="topbar-actions">
            <ConnectionPill config={config} runStatus={runStatus} />
            <div className="stat-chip">
              <Zap size={15} />
              LLM {stats.llm_calls}
            </div>
            <div className="stat-chip">
              <DatabaseZap size={15} />
              Tools {stats.tool_calls}
            </div>
          </div>
        </header>

        <div className="metrics-row">
          <article>
            <span>Agent progress</span>
            <strong>{completedAgents}/{totalAgents}</strong>
            <div className="meter"><i style={{ width: `${(completedAgents / totalAgents) * 100}%` }} /></div>
          </article>
          <article>
            <span>Token flow</span>
            <strong>{compact(stats.tokens_in)} in / {compact(stats.tokens_out)} out</strong>
            <div className="meter cyan"><i style={{ width: stats.tokens_out ? "68%" : "12%" }} /></div>
          </article>
          <article>
            <span>Run state</span>
            <strong>{runStatus}</strong>
            <div className="meter amber"><i style={{ width: running ? "54%" : runStatus === "completed" ? "100%" : "10%" }} /></div>
          </article>
        </div>

        <div className="main-grid">
          <section className="panel workflow-panel">
            <div className="panel-title">
              <div>
                <span className="eyeline">Agent orchestration</span>
                <h2>Workflow board</h2>
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
                <h2>Live memo</h2>
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
                <h2>Final verdict</h2>
              </div>
              <CircleDot size={18} />
            </div>
            {error ? (
              <div className="error-box">
                <strong>Run failed</strong>
                <p>{error}</p>
              </div>
            ) : (
              <>
                <div className="verdict-score">
                  <span>{final?.decision || "Awaiting decision"}</span>
                  <strong>{final ? "Ready" : "Pending"}</strong>
                </div>
                <MarkdownBlock
                  text={reports.final_trade_decision}
                  empty="The portfolio manager decision will appear after risk review."
                />
              </>
            )}
          </aside>
        </section>
      </section>
    </main>
  );
}
