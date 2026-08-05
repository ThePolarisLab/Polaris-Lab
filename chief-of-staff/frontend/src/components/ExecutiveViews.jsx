import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Database,
  FileCheck2,
  Gauge,
  Inbox,
  Link2,
  Mail,
  RefreshCw,
  ShieldCheck,
  Unplug,
} from "lucide-react";
import { apiClient } from "../apiClient";
import { money } from "../formatters";
import "./ExecutiveViews.css";

function ViewHeader({ kicker, title, description, action }) {
  return <header className="executive-view-header"><div><p>{kicker}</p><h1>{title}</h1><span>{description}</span></div>{action}</header>;
}

function StateBanner({ children }) {
  return <div className="governance-banner"><ShieldCheck size={19} aria-hidden="true" /><span>{children}</span></div>;
}

const dateText = (value) => value ? new Date(value).toLocaleString("en-CA") : "Never";

export function DailyBriefView() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setSummary(await apiClient.get("/api/v1/qbo/executive-summary"));
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
      await apiClient.post("/api/v1/qbo/sync?mode=incremental");
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
    ["Cash position", metrics?.cash], ["Total accounts receivable", metrics?.accounts_receivable],
    ["Total accounts payable", metrics?.accounts_payable],
  ];

  return (
    <section className="executive-view" aria-labelledby="daily-brief-title">
      <ViewHeader
        kicker="POLARIS v1.0 · FINANCIAL COMMAND CENTER"
        title="Executive financial dashboard"
        description="A live, Polaris-owned financial view synchronized from QuickBooks Online."
        action={<button className="view-action" type="button" onClick={syncNow} disabled={syncing}><RefreshCw size={16} className={syncing ? "spin" : ""} />{syncing ? "Syncing..." : "Sync now"}</button>}
      />
      {error && <div className="dashboard-error"><AlertTriangle size={18} />{error}</div>}
      {loading ? <StateBanner>Loading the latest synchronized financial snapshot...</StateBanner> : !metrics ? (
        <div className="dashboard-empty"><Database size={28} /><h2>Financial snapshot required</h2><p>QuickBooks is connected, but Polaris has not stored its first financial snapshot yet.</p><button className="connector-action" type="button" onClick={syncNow} disabled={syncing}>Create first snapshot</button></div>
      ) : (
        <>
          <div className="dashboard-meta">
            <span className={`connector-status ${summary.status === "success" ? "connected" : "not-connected"}`}>{summary.status === "success" ? "QuickBooks synchronized" : summary.status}</span>
            <span>{summary.period?.start || "Start"} to {summary.period?.end || "Current"} · {summary.period?.basis || "Accrual"}</span>
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
    ["Outlook", "Planned", "Read-only evidence ingestion is being activated in Track 4B."],
    ["Motive", "Planned", "Production adapter tracked separately in Track 4C."],
  ];
  return <section className="executive-view"><ViewHeader kicker="MISSION 003 · EVIDENCE" title="Evidence explorer" description="Trace every recommendation back to its source." /><StateBanner>Evidence is read-only and source-labelled.</StateBanner><div className="evidence-table">{items.map(([source,status,detail])=><div className="evidence-row" key={source}><strong><Database size={17}/>{source}</strong><span className={`status-pill ${status.toLowerCase()}`}>{status}</span><p>{detail}</p></div>)}</div></section>;
}

export function DecisionCenterView() {
  const decisions = [["Executive Workspace sequencing","Approved","Complete governed connector trust gates before cross-connector correlation."],["Production data mutations","Restricted","Observer/advisory mode remains the operating boundary."],["Connector rollout","Approved","QuickBooks reconciliation, Outlook activation, and Motive activation proceed as separately governed tracks."]];
  return <section className="executive-view"><ViewHeader kicker="MISSION 003 · DECISIONS" title="Decision center" description="Separate recommendations, approvals, restrictions, and rationale." /><StateBanner>Polaris may advise and explain. External-system action requires explicit authority.</StateBanner><div className="decision-list">{decisions.map(([title,status,rationale])=><article className="decision-card" key={title}><div className="decision-icon"><FileCheck2 size={20}/></div><div><span className="card-eyebrow">Governance decision</span><h3>{title}</h3><p>{rationale}</p></div><span className={`decision-status ${status.toLowerCase()}`}>{status}</span></article>)}</div></section>;
}

function connectorPresentation(connector) {
  if (connector.status === "healthy") return ["Connected", connector.message || "Connector health verified."];
  if (["degraded", "sync_error", "synchronization_failed", "rate_limited"].includes(connector.status)) return ["Degraded", connector.message || "Connector requires attention."];
  if (connector.status === "company_mismatch") return ["Company mismatch", connector.message || "Connected company does not match Mor Logistics."];
  if (connector.status === "reauthorization_required") return ["Reauthorize", connector.message || "Authorization must be refreshed."];
  if (connector.status === "not_configured") return ["Not configured", connector.message || "Connector environment variables are required."];
  return ["Not connected", connector.message || "Connector authorization is required."];
}

function ConnectorCard({ name, status, detail, children }) {
  return <article className="connector-card"><div className="connector-heading"><Link2 size={19}/><h3>{name}</h3></div><span className={`connector-status ${status.toLowerCase().replace(" ", "-")}`}>{status}</span><p>{detail}</p>{children}</article>;
}

export function ConnectorsView() {
  const [quickBooks, setQuickBooks] = useState({ status: "loading", message: "Checking the hosted QuickBooks connection...", details: {} });
  const [outlook, setOutlook] = useState({ health: { status: "loading", message: "Checking Outlook connection..." }, status: {} });
  const [attention, setAttention] = useState([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    const [quickBooksResult, outlookResult, attentionResult] = await Promise.allSettled([
      apiClient.get("/api/v1/connectors/quickbooks"),
      apiClient.get("/api/v1/outlook/status"),
      apiClient.get("/api/v1/outlook/attention?limit=5"),
    ]);
    if (quickBooksResult.status === "fulfilled") setQuickBooks(quickBooksResult.value);
    else setQuickBooks({ status: "disconnected", message: "Unable to read QuickBooks status.", details: {} });
    if (outlookResult.status === "fulfilled") setOutlook(outlookResult.value);
    else setOutlook({ health: { status: "disconnected", message: "Unable to read Outlook status." }, status: {} });
    if (attentionResult.status === "fulfilled") setAttention(attentionResult.value.items || []);
    else setAttention([]);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function connectQuickBooks() {
    setBusy("qbo-connect");
    setError("");
    try {
      const payload = await apiClient.get("/api/v1/connectors/quickbooks/oauth/authorize-url");
      window.location.assign(payload.authorization_url);
    } catch (requestError) {
      setError(requestError.message || "Unable to start QuickBooks authorization.");
      setBusy("");
    }
  }

  async function verifyQuickBooks() {
    setBusy("qbo-verify");
    setError("");
    try {
      await apiClient.post("/api/v1/qbo/verification");
      await load();
    } catch (requestError) {
      setError(requestError.message || "QuickBooks verification failed.");
    } finally {
      setBusy("");
    }
  }

  async function syncQuickBooks() {
    setBusy("qbo-sync");
    setError("");
    try {
      await apiClient.post("/api/v1/qbo/sync?mode=incremental");
      await load();
    } catch (requestError) {
      setError(requestError.message || "QuickBooks sync failed.");
    } finally {
      setBusy("");
    }
  }

  async function disconnectQuickBooks() {
    setBusy("qbo-disconnect");
    setError("");
    try {
      await apiClient.delete("/api/v1/connectors/quickbooks/oauth/connection");
      await load();
    } catch (requestError) {
      setError(requestError.message || "QuickBooks disconnect failed.");
    } finally {
      setBusy("");
    }
  }

  async function connectOutlook() {
    setBusy("outlook-connect");
    setError("");
    try {
      const payload = await apiClient.get("/api/v1/outlook/connect");
      window.location.assign(payload.authorization_url);
    } catch (requestError) {
      setError(requestError.message || "Unable to start Outlook authorization.");
      setBusy("");
    }
  }

  async function syncOutlook() {
    setBusy("outlook-sync");
    setError("");
    try {
      await apiClient.post("/api/v1/outlook/sync?mode=incremental");
      await load();
    } catch (requestError) {
      setError(requestError.message || "Outlook sync failed.");
    } finally {
      setBusy("");
    }
  }

  async function disconnectOutlook() {
    setBusy("outlook-disconnect");
    setError("");
    try {
      await apiClient.post("/api/v1/outlook/disconnect");
      await load();
    } catch (requestError) {
      setError(requestError.message || "Outlook disconnect failed.");
    } finally {
      setBusy("");
    }
  }

  const [qboStatus, qboDetail] = quickBooks.status === "loading" ? ["Checking", quickBooks.message] : connectorPresentation(quickBooks);
  const qboDetails = quickBooks.details || {};
  const outlookHealth = outlook.health || { status: "disconnected", message: "Outlook status unavailable." };
  const [outlookStatus, outlookDetail] = outlookHealth.status === "loading" ? ["Checking", outlookHealth.message] : connectorPresentation(outlookHealth);
  const outlookDetails = outlook.status || outlookHealth.details || {};

  return <section className="executive-view"><ViewHeader kicker="MISSION 003 · CONNECTORS" title="Connector center" description="One governed inventory of enterprise data connections." />{error&&<div className="dashboard-error"><AlertTriangle size={18}/>{error}</div>}<div className="executive-card-grid two-column"><ConnectorCard name="Polaris Runtime" status="Connected" detail="Core runtime contract is available."/><ConnectorCard name="QuickBooks Online" status={qboStatus} detail={qboDetail}><div className="connector-detail-list"><span>Expected: {qboDetails.expected_company_name || "MOR LOGISTICS MANITOBA LIMITED"}</span><span>Verified: {qboDetails.verified_company_name || "Not verified"}</span><span>Last sync: {dateText(qboDetails.last_successful_sync_time)}</span><span>Authorization: {qboDetails.authorization_status || "unknown"}</span></div><div className="connector-action-row"><button className="connector-action" type="button" onClick={connectQuickBooks} disabled={Boolean(busy)}>{busy==="qbo-connect"?"Opening...":"Connect"}<ArrowRight size={15}/></button><button className="connector-action" type="button" onClick={verifyQuickBooks} disabled={Boolean(busy)}>{busy==="qbo-verify"?"Verifying...":"Verify"}</button><button className="connector-action" type="button" onClick={syncQuickBooks} disabled={Boolean(busy)}>{busy==="qbo-sync"?"Syncing...":"Sync"}</button><button className="connector-action" type="button" onClick={disconnectQuickBooks} disabled={Boolean(busy)}><Unplug size={15}/>{busy==="qbo-disconnect"?"Disconnecting...":"Disconnect"}</button></div></ConnectorCard><ConnectorCard name="Outlook" status={outlookStatus} detail={outlookDetail}><div className="connector-detail-list"><span>Mailbox: {outlookDetails.mailbox_address || "Not connected"}</span><span>Microsoft tenant: {outlookDetails.microsoft_tenant_status || "unknown"}</span><span>Scopes: {(outlookDetails.granted_scopes || ["Mail.Read"]).join(", ")}</span><span>Last sync: {dateText(outlookDetails.last_successful_sync_time)}</span><span>Reauthorization: {outlookDetails.reauthorization_required ? "required" : "not required"}</span></div><div className="connector-action-row"><button className="connector-action" type="button" onClick={connectOutlook} disabled={Boolean(busy)}>{busy==="outlook-connect"?"Opening...":"Connect"}<ArrowRight size={15}/></button><button className="connector-action" type="button" onClick={syncOutlook} disabled={Boolean(busy)}>{busy==="outlook-sync"?"Syncing...":"Sync"}</button><button className="connector-action" type="button" onClick={disconnectOutlook} disabled={Boolean(busy)}><Unplug size={15}/>{busy==="outlook-disconnect"?"Disconnecting...":"Disconnect"}</button></div>{attention.length > 0 && <div className="connector-detail-list"><strong><Inbox size={15}/> Executive attention</strong>{attention.map((item)=><span key={item.message_id}>{item.category}: {item.subject || "No subject"}</span>)}</div>}</ConnectorCard><ConnectorCard name="Motive" status="Planned" detail="Track 4C remains separately governed and does not write into Outlook or QuickBooks tables."/></div></section>;
}

export function SystemHealthView() {
  const [quickBooks, setQuickBooks] = useState(null);
  const [outlook, setOutlook] = useState(null);
  useEffect(() => {
    apiClient.get("/api/v1/connectors/quickbooks").then(setQuickBooks).catch(() => setQuickBooks({ status: "degraded", message: "QuickBooks status unavailable." }));
    apiClient.get("/api/v1/outlook/status").then(setOutlook).catch(() => setOutlook({ health: { status: "degraded", message: "Outlook status unavailable." } }));
  }, []);
  const outlookHealth = outlook?.health;
  const checks = [["Frontend workspace","Healthy","Executive routing and dashboard verified."],["Backend runtime","Healthy","Runtime health verification is enforced in CI."],["Financial snapshot engine","Healthy","QuickBooks snapshots and sync history are registered."],["QuickBooks connector",quickBooks?.status === "healthy" ? "Healthy" : "Degraded",quickBooks?.message || "Connector details require authenticated access."],["Outlook connector",outlookHealth?.status === "healthy" ? "Healthy" : "Degraded",outlookHealth?.message || "Read-only Outlook activation requires authenticated access."],["Motive connector","Degraded","Track 4C production activation is separate."]];
  return <section className="executive-view"><ViewHeader kicker="MISSION 003 · SYSTEM" title="System health" description="Operational readiness and governed boundaries." /><div className="health-summary"><Gauge size={25}/><div><strong>Core platform healthy</strong><span>Financial command center enabled</span></div></div><div className="health-list">{checks.map(([name,status,detail])=><article key={name}>{status==="Healthy"?<CheckCircle2 size={19}/>:name.includes("Outlook")?<Mail size={19}/>:<AlertTriangle size={19}/>}<div><h3>{name}</h3><p>{detail}</p></div><span className={`health-status ${status.toLowerCase()}`}>{status}</span></article>)}</div></section>;
}

export function ExecutiveRouteView({ page }) {
  const views = { "daily-brief": DailyBriefView, evidence: EvidenceView, decisions: DecisionCenterView, connectors: ConnectorsView, "system-health": SystemHealthView };
  const View = views[page];
  return View ? <View /> : null;
}
