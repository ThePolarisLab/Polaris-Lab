import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../apiClient";
import { runtimeConfig } from "../runtimeConfig";
import "./ExecutiveDashboard.css";

function BriefSection({ title, children, isEmpty = false, emptyText = "Nothing requires attention." }) {
  return (
    <section className="polaris-card daily-brief-section">
      <h2>{title}</h2>
      {isEmpty ? <p className="muted">{emptyText}</p> : children}
    </section>
  );
}

function BriefItems({ items = [], linkLabel = "Open item" }) {
  return (
    <div className="item-list">
      {items.map((item, index) => (
        <article className="dashboard-item" key={`${item.title}-${item.entity_id ?? "none"}-${index}`}>
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
            <small>{item.source}</small>
            {typeof item.entity_id === "string" && item.entity_id.startsWith("#") && (
              <a className="dashboard-item-link" href={item.entity_id}>{linkLabel}</a>
            )}
          </div>
          <span className={`severity severity-${item.severity.toLowerCase()}`}>{item.severity}</span>
        </article>
      ))}
    </div>
  );
}

function BriefPriority({ items = [] }) {
  return (
    <ol className="priority-list daily-priority-list">
      {items.map((item) => (
        <li key={`${item.rank}-${item.title}`}>
          <strong>{item.title}</strong>
          <p>{item.reason}</p>
          <small>{item.source}</small>
        </li>
      ))}
    </ol>
  );
}

export default function DailyBrief() {
  const workspace = runtimeConfig.workspace;
  const dashboardPath = useMemo(
    () => `/dashboard/executive?user_name=${encodeURIComponent(workspace.userName)}`,
    [workspace.userName]
  );
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadBrief() {
    try {
      setLoading(true);
      setError("");
      setDashboard(await apiClient.get(dashboardPath));
    } catch (requestError) {
      console.error("Unable to load Polaris daily brief:", requestError);
      setError(requestError.message || "Polaris could not load the Daily Brief.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBrief();
  }, [dashboardPath]);

  if (loading && !dashboard) {
    return (
      <main className="dashboard-shell daily-brief-shell">
        <section className="polaris-card">
          <p className="eyebrow">POLARIS DAILY BRIEF</p>
          <h2>Preparing the executive morning brief...</h2>
          <p className="muted">Prioritizing changes, attention items, carry-forward work, waiting-on items, and feed health.</p>
        </section>
      </main>
    );
  }

  if (error && !dashboard) {
    return (
      <main className="dashboard-shell daily-brief-shell">
        <section className="polaris-card">
          <p className="eyebrow">POLARIS DAILY BRIEF</p>
          <h2>Daily Brief unavailable</h2>
          <p>{error}</p>
          <button type="button" className="primary-button" onClick={loadBrief}>Try Again</button>
        </section>
      </main>
    );
  }

  const brief = dashboard?.daily_brief ?? {};
  const priorities = brief.todays_priority ?? [];
  const needsAttention = brief.needs_attention ?? [];
  const aceSummary = brief.ace_summary ?? [];
  const carryForward = brief.carry_forward ?? [];
  const waitingOn = brief.waiting_on ?? [];
  const systemHealth = brief.system_health ?? [];

  return (
    <main className="dashboard-shell daily-brief-shell">
      <header className="dashboard-hero daily-brief-hero">
        <div>
          <p className="eyebrow">POLARIS DAILY BRIEF - {workspace.organizationName}</p>
          <h1>{dashboard.greeting}</h1>
          <p>Morning scan: what changed, what needs attention, what is urgent, what is waiting, and what is carrying forward.</p>
          <p>Estimated review time: <strong>{dashboard.review_minutes} minutes</strong></p>
        </div>
        <div className="dashboard-hero-actions">
          <button type="button" className="secondary-button" onClick={loadBrief} disabled={loading}>{loading ? "Refreshing..." : "Refresh"}</button>
          <div className="status-panel"><span>Business Status</span><strong>{dashboard.business_status}</strong></div>
        </div>
      </header>

      {error && <div className="form-error">Daily Brief refresh warning: {error}</div>}

      <div className="daily-brief-grid">
        <BriefSection title="Today's Priority" isEmpty={priorities.length === 0} emptyText="No urgent executive priorities are queued.">
          <BriefPriority items={priorities} />
        </BriefSection>
        <BriefSection title="Needs Attention" isEmpty={needsAttention.length === 0} emptyText="Nothing urgent requires attention.">
          <BriefItems items={needsAttention} linkLabel="Open in ACE" />
        </BriefSection>
        <BriefSection title="ACE / Bond Control" isEmpty={aceSummary.length === 0} emptyText="No ACE management summary is available yet.">
          <BriefItems items={aceSummary} linkLabel="Open in ACE" />
        </BriefSection>
        <BriefSection title="Carry Forward" isEmpty={carryForward.length === 0} emptyText="No unresolved work is carrying forward.">
          <BriefItems items={carryForward} />
        </BriefSection>
        <BriefSection title="Waiting On" isEmpty={waitingOn.length === 0} emptyText="No assigned waiting-on items are currently open.">
          <BriefItems items={waitingOn} />
        </BriefSection>
        <BriefSection title="System / Data Health" isEmpty={systemHealth.length === 0} emptyText="No actionable feed or connector issues.">
          <BriefItems items={systemHealth} linkLabel="Open in ACE" />
        </BriefSection>
      </div>
    </main>
  );
}
