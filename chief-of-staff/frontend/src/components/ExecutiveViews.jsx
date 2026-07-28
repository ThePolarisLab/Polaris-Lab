import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Database,
  FileCheck2,
  Gauge,
  Link2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import "./ExecutiveViews.css";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const QUICKBOOKS_AUTHORIZE_URL = `${API_BASE_URL}/api/v1/connectors/quickbooks/oauth/authorize`;

function ViewHeader({ kicker, title, description, action }) {
  return <header className="executive-view-header"><div><p>{kicker}</p><h1>{title}</h1><span>{description}</span></div>{action}</header>;
}

function StateBanner({ children }) {
  return <div className="governance-banner"><ShieldCheck size={19} aria-hidden="true" /><span>{children}</span></div>;
}

const money = (value, currency = "CAD") => value == null
  ? "Not available"
  : new Intl.NumberFormat("en-CA", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);

export function DailyBriefView() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/qbo/executive-summary`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`Executive summary failed with HTTP ${response.status}`);
      setSummary(await response.json());
    } catch (requestError) {
      setError(requestError.message || "Unable to load financial summary.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function syncNow() {
    setSyncing(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/qbo/sync`, { method: "POST", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`QuickBooks sync failed with HTTP ${response.status}`);
      await load();
    } catch (requestError) {
      setError(requestError.message || "Unable to synchronize QuickBooks.");
    } finally {
      setSyncing(false);
    }
  }

  const metrics = summary?.metrics;
  const cards = [
    ["Revenue", metrics?.revenue], ["Total expenses", metrics?.expenses],
    ["Gross profit", metrics?.gross_profit], ["Net income", metrics?.net_income],
    ["Cash position", metrics?.cash], ["Accounts receivable", metrics?.accounts_receivable],
    ["Accounts payable", metrics?.accounts_payable],
  ];

  return (
    <section className="executive-view" aria-labelledby="daily-brief-title">
      <ViewHeader
        kicker="POLARIS v0.9.3 · FINANCIAL COMMAND CENTER"
        title="Executive financial dashboard"
        description="A live, Polaris-owned financial view synchronized from QuickBooks Online."
        action={<button className="view-action" type="button" onClick={syncNow} disabled={syncing}><RefreshCw size={16} className={syncing ? "spin" : ""} />{syncing ? "Syncing…" : "Sync now"}</button>}
      />
      {error && <div className="dashboard-error"><AlertTriangle size={18} />{error}</div>}
      {loading ? <StateBanner>Loading the latest synchronized financial snapshot…</StateBanner> : !metrics ? (
        <div className="dashboard-empty"><Database size={28} /><h2>Financial snapshot required</h2><p>QuickBooks is connected, but Polaris has not stored its first financial snapshot yet.</p><button className="connector-action" type="button" onClick={syncNow} disabled={syncing}>Create first snapshot</button></div>
      ) : (
        <>
          <div className="dashboard-meta">
            <span className={`connector-status ${summary.status === "success" ? "connected" : "not-connected"}`}>{summary.status === "success" ? "QuickBooks synchronized" : summary.status}</span>
            <span>{summary.period?.start || "Start"} → {summary.period?.end || "Current"} · {summary.period?.basis || "Accrual"}</span>
            <span>Last sync: {summary.last_sync ? new Date(summary.last_sync).toLocaleString("en-CA") : "Never"}</span>
          </div>
          <div className="financial-kpi-grid">
            {cards.map(([label, value]) => <article className="financial-kpi-card" key={label}><span>{label}</span><strong>{money(value, summary.currency)}</strong></article>)}
          </div>
        </>
      )}
    </section>
  );
}

export function EvidenceView() {
  const items = [
    ["Polaris Runtime", "Available", "Runtime and workspace configuration are verifiable."],
    ["QuickBooks Online", "Available", "Company, accounts, reports, and stored snapshots are available."],
    ["Motive", "Planned", "Production adapter tracked in Issue #62."],
  ];
  return <section className="executive-view"><ViewHeader kicker="MISSION 003 · EVIDENCE" title="Evidence explorer" description="Trace every recommendation back to its source." /><StateBanner>Evidence is read-only and source-labelled.</StateBanner><div className="evidence-table">{items.map(([source,status,detail])=><div className="evidence-row" key={source}><strong><Database size={17}/>{source}</strong><span className={`status-pill ${status.toLowerCase()}`}>{status}</span><p>{detail}</p></div>)}</div></section>;
}

export function DecisionCenterView() {
  const decisions = [["Executive Workspace sequencing","Approved","Complete the governed workspace before production connectors."],["Production data mutations","Restricted","Observer/advisory mode remains the operating boundary."],["Connector rollout","Pending","QuickBooks financial foundation is active; Motive follows."]];
  return <section className="executive-view"><ViewHeader kicker="MISSION 003 · DECISIONS" title="Decision center" description="Separate recommendations, approvals, restrictions, and rationale." /><StateBanner>Polaris may advise and explain. External-system action requires explicit authority.</StateBanner><div className="decision-list">{decisions.map(([title,status,rationale])=><article className="decision-card" key={title}><div className="decision-icon"><FileCheck2 size={20}/></div><div><span className="card-eyebrow">Governance decision</span><h3>{title}</h3><p>{rationale}</p></div><span className={`decision-status ${status.toLowerCase()}`}>{status}</span></article>)}</div></section>;
}

function connectorPresentation(connector) {
  if (connector.status === "healthy") return ["Connected", connector.message || "Connector health verified."];
  if (connector.status === "degraded" || connector.status === "sync_error") return ["Degraded", connector.message || "Connector requires attention."];
  return ["Not connected", connector.message || "Connector authorization is required."];
}

export function ConnectorsView() {
  const [quickBooks, setQuickBooks] = useState({ status: "loading", message: "Checking the hosted QuickBooks connection…" });
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/api/v1/connectors/quickbooks`, { signal: controller.signal, headers: { Accept: "application/json" } })
      .then((response) => { if (!response.ok) throw new Error(); return response.json(); })
      .then(setQuickBooks)
      .catch((error) => { if (error.name !== "AbortError") setQuickBooks({ status: "disconnected", message: "Unable to read QuickBooks status." }); });
    return () => controller.abort();
  }, []);
  const [status, detail] = quickBooks.status === "loading" ? ["Checking", quickBooks.message] : connectorPresentation(quickBooks);
  const connectors = [
    { name: "Polaris Runtime", status: "Connected", detail: "Core runtime contract is available." },
    { name: "QuickBooks Online", status, detail, action: quickBooks.status !== "healthy" && quickBooks.status !== "loading" ? { label: "Connect QuickBooks", href: QUICKBOOKS_AUTHORIZE_URL } : null },
    { name: "Motive", status: "Not connected", detail: "Production adapter planned in Issue #62." },
    { name: "Outlook", status: "Future", detail: "Connector policy is not yet certified." },
  ];
  return <section className="executive-view"><ViewHeader kicker="MISSION 003 · CONNECTORS" title="Connector center" description="One governed inventory of enterprise data connections." /><div className="executive-card-grid two-column">{connectors.map(({name,status,detail,action})=><article className="connector-card" key={name}><div className="connector-heading"><Link2 size={19}/><h3>{name}</h3></div><span className={`connector-status ${status.toLowerCase().replace(" ", "-")}`}>{status}</span><p>{detail}</p>{action&&<a className="connector-action" href={action.href}>{action.label}<ArrowRight size={15}/></a>}</article>)}</div></section>;
}

export function SystemHealthView() {
  const checks = [["Frontend workspace","Healthy","Executive routing and dashboard verified."],["Backend runtime","Healthy","Runtime health verification is enforced in CI."],["Financial snapshot engine","Healthy","QuickBooks snapshots and sync history are registered."],["Motive connector","Degraded","Expected until Issue #62 is completed."]];
  return <section className="executive-view"><ViewHeader kicker="MISSION 003 · SYSTEM" title="System health" description="Operational readiness and governed boundaries." /><div className="health-summary"><Gauge size={25}/><div><strong>Core platform healthy</strong><span>Financial command center enabled</span></div></div><div className="health-list">{checks.map(([name,status,detail])=><article key={name}>{status==="Healthy"?<CheckCircle2 size={19}/>:<AlertTriangle size={19}/>}<div><h3>{name}</h3><p>{detail}</p></div><span className={`health-status ${status.toLowerCase()}`}>{status}</span></article>)}</div></section>;
}

export function ExecutiveRouteView({ page }) {
  const views = { "daily-brief": DailyBriefView, evidence: EvidenceView, decisions: DecisionCenterView, connectors: ConnectorsView, "system-health": SystemHealthView };
  const View = views[page];
  return View ? <View /> : null;
}
