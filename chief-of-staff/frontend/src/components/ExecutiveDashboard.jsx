import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../apiClient";
import {
  motiveIdleTimeShareKpiPresentation,
  motiveUtilizationKpiPresentation,
} from "../motiveFrontend";
import { runtimeConfig } from "../runtimeConfig";
import "./ExecutiveDashboard.css";
import MotiveUtilizationHistory from "./MotiveUtilizationHistory";
import "./MotiveUtilizationKpi.css";

function createEmptyAction(author) {
  return {
    author,
    note_type: "ACTION",
    title: "",
    details: "",
    target_entity: "",
    assigned_to: "",
    due_at: "",
  };
}

function Section({ title, children, isEmpty = false, emptyText = "Nothing requires attention." }) {
  return (
    <section className="polaris-card">
      <h2>{title}</h2>
      {isEmpty ? <p className="muted">{emptyText}</p> : children}
    </section>
  );
}

function ItemList({ items = [] }) {
  return (
    <div className="item-list">
      {items.map((item, index) => (
        <article className="dashboard-item" key={`${item.title}-${item.entity_id ?? "none"}-${index}`}>
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
            <small>{item.source}</small>
            {typeof item.entity_id === "string" && item.entity_id.startsWith("#") && (
              <a className="dashboard-item-link" href={item.entity_id}>Open in ACE</a>
            )}
          </div>
          <span className={`severity severity-${item.severity.toLowerCase()}`}>{item.severity}</span>
        </article>
      ))}
    </div>
  );
}

function FleetKpiObservation({ presentation }) {
  return (
    <article className="fleet-kpi-observation" aria-label={presentation.title}>
      <div className="fleet-kpi-heading">
        <h3>{presentation.title}</h3>
        {presentation.description && <p>{presentation.description}</p>}
      </div>
      <div className="fleet-kpi-content">
        <strong className="fleet-kpi-value">{presentation.value}</strong>
        <div className="fleet-kpi-meta">
          {presentation.coverage && <p><span>Coverage</span><strong>{presentation.coverage}</strong></p>}
          <p className="fleet-kpi-completeness">{presentation.completeness}</p>
          {presentation.window && <small>{presentation.window}</small>}
        </div>
      </div>
    </article>
  );
}

function FleetOperationsCard({ utilizationPresentation, idleTimeSharePresentation, historyRefreshSequence }) {
  return (
    <section className="polaris-card fleet-operations-card" aria-labelledby="fleet-operations-title">
      <div className="fleet-operations-heading">
        <p className="eyebrow">FLEET / OPERATIONS</p>
        <h2 id="fleet-operations-title">Current Observations</h2>
      </div>
      <div className="fleet-current-observations">
        <FleetKpiObservation presentation={utilizationPresentation} />
        <FleetKpiObservation presentation={idleTimeSharePresentation} />
      </div>
      <MotiveUtilizationHistory refreshSequence={historyRefreshSequence} />
    </section>
  );
}

function AddActionForm({ action, saving, error, onChange, onSubmit, onCancel }) {
  return (
    <div className="modal-backdrop">
      <section className="action-modal" role="dialog" aria-modal="true" aria-labelledby="add-action-title">
        <div className="action-modal-header">
          <div>
            <p className="eyebrow">POLARIS TEAM NOTES</p>
            <h2 id="add-action-title">Add New Action</h2>
          </div>
          <button type="button" className="close-button" onClick={onCancel} disabled={saving} aria-label="Close action form">×</button>
        </div>

        <form className="action-form" onSubmit={onSubmit}>
          <label>
            Title
            <input name="title" type="text" value={action.title} onChange={onChange} placeholder="Example: Call Canada Packers" required maxLength={200} autoFocus />
          </label>

          <label>
            Details
            <textarea name="details" value={action.details} onChange={onChange} placeholder="Describe what needs to be completed." required rows={4} />
          </label>

          <div className="action-form-grid">
            <label>
              Type
              <select name="note_type" value={action.note_type} onChange={onChange}>
                <option value="ACTION">Action</option>
                <option value="BLOCKER">Blocker</option>
                <option value="INFORMATION">Information</option>
                <option value="DECISION">Decision</option>
              </select>
            </label>

            <label>
              Author
              <input name="author" type="text" value={action.author} onChange={onChange} required maxLength={120} />
            </label>

            <label>
              Assign To
              <input name="assigned_to" type="text" value={action.assigned_to} onChange={onChange} placeholder="Operations, Accounting, Dispatch..." maxLength={120} />
            </label>

            <label>
              Due Date and Time
              <input name="due_at" type="datetime-local" value={action.due_at} onChange={onChange} />
            </label>
          </div>

          <label>
            Related Entity
            <input name="target_entity" type="text" value={action.target_entity} onChange={onChange} placeholder="Example: customer.canada_packers or truck.214" maxLength={255} />
          </label>

          {error && <div className="form-error">{error}</div>}

          <div className="action-form-buttons">
            <button type="button" className="secondary-button" onClick={onCancel} disabled={saving}>Cancel</button>
            <button type="submit" className="primary-button" disabled={saving}>{saving ? "Saving..." : "Save Action"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default function ExecutiveDashboard() {
  const workspace = runtimeConfig.workspace;
  const dashboardPath = useMemo(
    () => `/dashboard/executive?user_name=${encodeURIComponent(workspace.userName)}`,
    [workspace.userName]
  );

  const [dashboard, setDashboard] = useState(null);
  const [dashboardError, setDashboardError] = useState("");
  const [loading, setLoading] = useState(true);
  const [utilizationKpi, setUtilizationKpi] = useState(null);
  const [utilizationKpiLoading, setUtilizationKpiLoading] = useState(true);
  const [utilizationKpiRequestFailed, setUtilizationKpiRequestFailed] = useState(false);
  const [idleTimeShareKpi, setIdleTimeShareKpi] = useState(null);
  const [idleTimeShareKpiLoading, setIdleTimeShareKpiLoading] = useState(true);
  const [idleTimeShareKpiRequestFailed, setIdleTimeShareKpiRequestFailed] = useState(false);
  const [historyRefreshSequence, setHistoryRefreshSequence] = useState(0);
  const [showActionForm, setShowActionForm] = useState(false);
  const [savingAction, setSavingAction] = useState(false);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");
  const [action, setAction] = useState(() => createEmptyAction(workspace.userName));

  async function loadDashboard() {
    try {
      setLoading(true);
      setDashboardError("");
      setDashboard(await apiClient.get(dashboardPath));
    } catch (requestError) {
      console.error("Unable to load Polaris dashboard:", requestError);
      setDashboardError(requestError.message || "Polaris could not load the dashboard.");
    } finally {
      setLoading(false);
    }
  }

  async function loadUtilizationKpi() {
    try {
      setUtilizationKpiLoading(true);
      setUtilizationKpiRequestFailed(false);
      setUtilizationKpi(await apiClient.get("/api/v1/motive/fleet/vehicle-utilization-kpi"));
    } catch (_) {
      setUtilizationKpi(null);
      setUtilizationKpiRequestFailed(true);
    } finally {
      setUtilizationKpiLoading(false);
    }
  }

  async function loadIdleTimeShareKpi() {
    try {
      setIdleTimeShareKpiLoading(true);
      setIdleTimeShareKpiRequestFailed(false);
      setIdleTimeShareKpi(await apiClient.get("/api/v1/motive/fleet/vehicle-idle-time-share-kpi"));
    } catch (_) {
      setIdleTimeShareKpi(null);
      setIdleTimeShareKpiRequestFailed(true);
    } finally {
      setIdleTimeShareKpiLoading(false);
    }
  }

  async function refreshDashboard() {
    setHistoryRefreshSequence((current) => current + 1);
    await Promise.allSettled([loadDashboard(), loadUtilizationKpi(), loadIdleTimeShareKpi()]);
  }

  useEffect(() => {
    void refreshDashboard();
  }, [dashboardPath]);

  function openActionForm() {
    setAction(createEmptyAction(workspace.userName));
    setActionError("");
    setActionSuccess("");
    setShowActionForm(true);
  }

  function closeActionForm() {
    if (savingAction) return;
    setShowActionForm(false);
    setActionError("");
  }

  function handleActionChange(event) {
    const { name, value } = event.target;
    setAction((currentAction) => ({ ...currentAction, [name]: value }));
  }

  async function handleActionSubmit(event) {
    event.preventDefault();

    const cleanTitle = action.title.trim();
    const cleanDetails = action.details.trim();
    const cleanAuthor = action.author.trim();

    if (!cleanTitle) return setActionError("Please enter an action title.");
    if (!cleanDetails) return setActionError("Please enter action details.");
    if (!cleanAuthor) return setActionError("Please enter the author's name.");

    const payload = {
      author: cleanAuthor,
      note_type: action.note_type,
      title: cleanTitle,
      details: cleanDetails,
      target_entity: action.target_entity.trim() || null,
      assigned_to: action.assigned_to.trim() || null,
      due_at: action.due_at ? new Date(action.due_at).toISOString() : null,
    };

    try {
      setSavingAction(true);
      setActionError("");
      setActionSuccess("");
      await apiClient.post("/team-notes", payload);
      setShowActionForm(false);
      setAction(createEmptyAction(workspace.userName));
      setActionSuccess(`"${cleanTitle}" was added successfully.`);
      await loadDashboard();
    } catch (requestError) {
      console.error("Unable to save action:", requestError);
      setActionError(requestError.message || "Polaris could not save the action.");
    } finally {
      setSavingAction(false);
    }
  }

  if (loading && !dashboard) {
    return (
      <main className="dashboard-shell">
        <section className="polaris-card">
          <p className="eyebrow">POLARIS · {workspace.organizationName}</p>
          <h2>Preparing {workspace.userName}&apos;s executive brief...</h2>
          <p className="muted">Reviewing missions, team notes, reasoning, and business activity.</p>
        </section>
      </main>
    );
  }

  if (dashboardError && !dashboard) {
    return (
      <main className="dashboard-shell">
        <section className="polaris-card">
          <p className="eyebrow">POLARIS · {workspace.workspaceName}</p>
          <h2>Dashboard unavailable</h2>
          <p>{dashboardError}</p>
          <button type="button" className="primary-button" onClick={refreshDashboard}>Try Again</button>
        </section>
      </main>
    );
  }

  const needsAttention = dashboard?.needs_attention ?? [];
  const carryForward = dashboard?.carry_forward ?? [];
  const todaysPlan = dashboard?.todays_plan ?? [];
  const comingUp = dashboard?.coming_up ?? [];
  const watchItems = dashboard?.watch_items ?? [];
  const utilizationPresentation = motiveUtilizationKpiPresentation(utilizationKpi, {
    loading: utilizationKpiLoading,
    requestFailed: utilizationKpiRequestFailed,
  });
  const idleTimeSharePresentation = motiveIdleTimeShareKpiPresentation(idleTimeShareKpi, {
    loading: idleTimeShareKpiLoading,
    requestFailed: idleTimeShareKpiRequestFailed,
  });

  return (
    <main className="dashboard-shell">
      <header className="dashboard-hero">
        <div>
          <p className="eyebrow">POLARIS · {workspace.organizationName} · {workspace.workspaceName}</p>
          <h1>{dashboard.greeting}</h1>
          <p>Here is where your business stands right now.</p>
          <p>Estimated review time: <strong>{dashboard.review_minutes} minutes</strong></p>
        </div>

        <div className="dashboard-hero-actions">
          <button type="button" className="primary-button add-action-button" onClick={openActionForm}>+ Add Action</button>
          <button type="button" className="secondary-button" onClick={refreshDashboard} disabled={loading}>{loading ? "Refreshing..." : "Refresh"}</button>
          <div className="status-panel"><span>Business Status</span><strong>{dashboard.business_status}</strong></div>
        </div>
      </header>

      {actionSuccess && <div className="success-banner">{actionSuccess}</div>}
      {dashboardError && <div className="form-error">Dashboard refresh warning: {dashboardError}</div>}

      <div className="summary-strip">
        <div><strong>{dashboard.open_team_notes}</strong><span>Open Notes</span></div>
        <div><strong>{dashboard.active_missions}</strong><span>Active Missions</span></div>
        <div><strong>{dashboard.total_trucks}</strong><span>Trucks</span></div>
      </div>

      <FleetOperationsCard
        utilizationPresentation={utilizationPresentation}
        idleTimeSharePresentation={idleTimeSharePresentation}
        historyRefreshSequence={historyRefreshSequence}
      />

      <div className="dashboard-grid">
        <Section title="Needs Attention" isEmpty={needsAttention.length === 0} emptyText="Nothing urgent requires your attention."><ItemList items={needsAttention} /></Section>
        <Section title="Carry Forward" isEmpty={carryForward.length === 0} emptyText="No unfinished work has been carried forward."><ItemList items={carryForward} /></Section>
        <Section title="Today's Plan" isEmpty={todaysPlan.length === 0} emptyText="No priorities have been created for today.">
          <ol className="priority-list">
            {todaysPlan.map((item) => <li key={`${item.rank}-${item.title}`}><strong>{item.title}</strong><p>{item.reason}</p><small>{item.source}</small></li>)}
          </ol>
        </Section>
        <Section title="Coming Up" isEmpty={comingUp.length === 0} emptyText="Nothing is due within the next seven days."><ItemList items={comingUp} /></Section>
        <Section title="Watch Items" isEmpty={watchItems.length === 0} emptyText="There are no additional watch items."><ItemList items={watchItems} /></Section>
        <section className="polaris-card recommendation-card"><h2>Polaris Recommendation</h2><p>{dashboard.recommendation}</p></section>
      </div>

      <section className="ask-polaris">
        <input aria-label="Ask Polaris" placeholder="Ask Polaris..." disabled />
        <span>The conversational dashboard connection will be added in a future milestone.</span>
      </section>

      {showActionForm && <AddActionForm action={action} saving={savingAction} error={actionError} onChange={handleActionChange} onSubmit={handleActionSubmit} onCancel={closeActionForm} />}
    </main>
  );
}
