import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Database,
  FileCheck2,
  Gauge,
  Link2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import "./ExecutiveViews.css";

const briefItems = [
  { title: "Review exceptions", detail: "No live operational exceptions are connected yet.", tone: "attention" },
  { title: "Confirm priorities", detail: "Executive priorities will be ranked from governed evidence.", tone: "neutral" },
  { title: "Prepare decisions", detail: "Recommendations remain advisory until explicitly approved.", tone: "positive" },
];

const evidenceItems = [
  { source: "Polaris Runtime", status: "Available", detail: "Runtime and workspace configuration are verifiable." },
  { source: "QuickBooks Online", status: "Planned", detail: "Production adapter tracked in Issue #61." },
  { source: "Motive", status: "Planned", detail: "Production adapter tracked in Issue #62." },
];

const decisions = [
  { title: "Executive Workspace sequencing", status: "Approved", rationale: "Complete the governed workspace before production connectors." },
  { title: "Production data mutations", status: "Restricted", rationale: "Observer/advisory mode remains the operating boundary." },
  { title: "Connector rollout", status: "Pending", rationale: "Begin after Mission 003 certification." },
];

function ViewHeader({ kicker, title, description, action }) {
  return (
    <header className="executive-view-header">
      <div>
        <p>{kicker}</p>
        <h1>{title}</h1>
        <span>{description}</span>
      </div>
      {action}
    </header>
  );
}

function StateBanner({ children }) {
  return (
    <div className="governance-banner">
      <ShieldCheck size={19} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

export function DailyBriefView() {
  return (
    <section className="executive-view" aria-labelledby="daily-brief-title">
      <ViewHeader
        kicker="MISSION 003 · DAILY BRIEF"
        title="Today’s executive brief"
        description="A governed summary of what changed, what matters, and what requires attention."
        action={<button className="view-action" type="button" disabled><RefreshCw size={16} /> Refresh brief</button>}
      />
      <StateBanner>Preview mode: live business sources will populate this brief after connector certification.</StateBanner>
      <div className="brief-hero-card">
        <div><Sparkles size={22} /><span>Executive posture</span></div>
        <h2>Platform ready. Business evidence pending.</h2>
        <p>The workspace is operational and remains safely advisory while production connectors are prepared.</p>
      </div>
      <div className="executive-card-grid three-column">
        {briefItems.map((item) => (
          <article className={`executive-card ${item.tone}`} key={item.title}>
            <span className="card-eyebrow"><Clock3 size={15} /> Next action</span>
            <h3>{item.title}</h3>
            <p>{item.detail}</p>
            <button type="button" disabled>Open item <ArrowRight size={15} /></button>
          </article>
        ))}
      </div>
    </section>
  );
}

export function EvidenceView() {
  return (
    <section className="executive-view" aria-labelledby="evidence-title">
      <ViewHeader kicker="MISSION 003 · EVIDENCE" title="Evidence explorer" description="Trace every future recommendation back to its source and operating context." />
      <StateBanner>Evidence is read-only and source-labelled. No unsupported inference is presented as fact.</StateBanner>
      <div className="evidence-table" role="table" aria-label="Evidence sources">
        <div className="evidence-row evidence-heading" role="row"><span>Source</span><span>Status</span><span>Coverage</span></div>
        {evidenceItems.map((item) => (
          <div className="evidence-row" role="row" key={item.source}>
            <strong><Database size={17} /> {item.source}</strong>
            <span className={`status-pill ${item.status.toLowerCase()}`}>{item.status}</span>
            <p>{item.detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export function DecisionCenterView() {
  return (
    <section className="executive-view" aria-labelledby="decisions-title">
      <ViewHeader kicker="MISSION 003 · DECISIONS" title="Decision center" description="Separate recommendations, approvals, restrictions, and rationale." />
      <StateBanner>Polaris may advise and explain. External-system action requires explicit authority.</StateBanner>
      <div className="decision-list">
        {decisions.map((decision) => (
          <article className="decision-card" key={decision.title}>
            <div className="decision-icon"><FileCheck2 size={20} /></div>
            <div><span className="card-eyebrow">Governance decision</span><h3>{decision.title}</h3><p>{decision.rationale}</p></div>
            <span className={`decision-status ${decision.status.toLowerCase()}`}>{decision.status}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

export function ConnectorsView() {
  const connectors = [
    ["Polaris Runtime", "Connected", "Core runtime contract is available."],
    ["QuickBooks Online", "Not connected", "Production adapter planned in Issue #61."],
    ["Motive", "Not connected", "Production adapter planned in Issue #62."],
    ["Outlook", "Future", "Connector policy and evidence contract not yet certified."],
  ];
  return (
    <section className="executive-view" aria-labelledby="connectors-title">
      <ViewHeader kicker="MISSION 003 · CONNECTORS" title="Connector center" description="One governed inventory of enterprise data connections." />
      <div className="executive-card-grid two-column">
        {connectors.map(([name, status, detail]) => (
          <article className="connector-card" key={name}>
            <div className="connector-heading"><Link2 size={19} /><h3>{name}</h3></div>
            <span className={`connector-status ${status.toLowerCase().replace(" ", "-")}`}>{status}</span>
            <p>{detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function SystemHealthView() {
  const checks = [
    ["Frontend workspace", "Healthy", "Executive routing and build contract verified."],
    ["Backend runtime", "Healthy", "Runtime health verification is enforced in CI."],
    ["TypeScript core", "Healthy", "Executive Memory and Atlas tests remain protected."],
    ["Production connectors", "Degraded", "Expected until Issues #61 and #62 are completed."],
  ];
  return (
    <section className="executive-view" aria-labelledby="system-health-title">
      <ViewHeader kicker="MISSION 003 · SYSTEM" title="System health" description="Operational readiness, degraded capabilities, and governed boundaries." />
      <div className="health-summary">
        <Gauge size={25} /><div><strong>Core platform healthy</strong><span>3 healthy · 1 expected degraded capability</span></div>
      </div>
      <div className="health-list">
        {checks.map(([name, status, detail]) => (
          <article key={name}>
            {status === "Healthy" ? <CheckCircle2 size={19} /> : <AlertTriangle size={19} />}
            <div><h3>{name}</h3><p>{detail}</p></div>
            <span className={`health-status ${status.toLowerCase()}`}>{status}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

export function ExecutiveRouteView({ page }) {
  const views = {
    "daily-brief": DailyBriefView,
    evidence: EvidenceView,
    decisions: DecisionCenterView,
    connectors: ConnectorsView,
    "system-health": SystemHealthView,
  };
  const View = views[page];
  return View ? <View /> : null;
}
