import { useEffect, useState } from "react";
import "./ExecutiveDashboard.css";

const API_BASE = "http://127.0.0.1:8000";

const EMPTY_ACTION = {
  author: "Surinder",
  note_type: "ACTION",
  title: "",
  details: "",
  target_entity: "",
  assigned_to: "",
  due_at: "",
};

function Section({
  title,
  children,
  isEmpty = false,
  emptyText = "Nothing requires attention.",
}) {
  return (
    <section className="polaris-card">
      <h2>{title}</h2>

      {isEmpty ? (
        <p className="muted">{emptyText}</p>
      ) : (
        children
      )}
    </section>
  );
}

function ItemList({ items = [] }) {
  return (
    <div className="item-list">
      {items.map((item, index) => (
        <article
          className="dashboard-item"
          key={`${item.title}-${item.entity_id ?? "none"}-${index}`}
        >
          <div>
            <strong>{item.title}</strong>

            <p>{item.detail}</p>

            <small>{item.source}</small>
          </div>

          <span
            className={`severity severity-${item.severity.toLowerCase()}`}
          >
            {item.severity}
          </span>
        </article>
      ))}
    </div>
  );
}

function AddActionForm({
  action,
  saving,
  error,
  onChange,
  onSubmit,
  onCancel,
}) {
  return (
    <div className="modal-backdrop">
      <section
        className="action-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-action-title"
      >
        <div className="action-modal-header">
          <div>
            <p className="eyebrow">POLARIS TEAM NOTES</p>

            <h2 id="add-action-title">
              Add New Action
            </h2>
          </div>

          <button
            type="button"
            className="close-button"
            onClick={onCancel}
            disabled={saving}
            aria-label="Close action form"
          >
            ×
          </button>
        </div>

        <form
          className="action-form"
          onSubmit={onSubmit}
        >
          <label>
            Title
            <input
              name="title"
              type="text"
              value={action.title}
              onChange={onChange}
              placeholder="Example: Call Canada Packers"
              required
              maxLength={200}
              autoFocus
            />
          </label>

          <label>
            Details
            <textarea
              name="details"
              value={action.details}
              onChange={onChange}
              placeholder="Describe what needs to be completed."
              required
              rows={4}
            />
          </label>

          <div className="action-form-grid">
            <label>
              Type
              <select
                name="note_type"
                value={action.note_type}
                onChange={onChange}
              >
                <option value="ACTION">
                  Action
                </option>

                <option value="BLOCKER">
                  Blocker
                </option>

                <option value="INFORMATION">
                  Information
                </option>

                <option value="DECISION">
                  Decision
                </option>
              </select>
            </label>

            <label>
              Author
              <input
                name="author"
                type="text"
                value={action.author}
                onChange={onChange}
                required
                maxLength={120}
              />
            </label>

            <label>
              Assign To
              <input
                name="assigned_to"
                type="text"
                value={action.assigned_to}
                onChange={onChange}
                placeholder="Operations, Accounting, Surinder..."
                maxLength={120}
              />
            </label>

            <label>
              Due Date and Time
              <input
                name="due_at"
                type="datetime-local"
                value={action.due_at}
                onChange={onChange}
              />
            </label>
          </div>

          <label>
            Related Entity
            <input
              name="target_entity"
              type="text"
              value={action.target_entity}
              onChange={onChange}
              placeholder="Example: customer.canada_packers or truck.214"
              maxLength={255}
            />
          </label>

          {error && (
            <div className="form-error">
              {error}
            </div>
          )}

          <div className="action-form-buttons">
            <button
              type="button"
              className="secondary-button"
              onClick={onCancel}
              disabled={saving}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="primary-button"
              disabled={saving}
            >
              {saving ? "Saving..." : "Save Action"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default function ExecutiveDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [dashboardError, setDashboardError] = useState("");
  const [loading, setLoading] = useState(true);

  const [showActionForm, setShowActionForm] = useState(false);
  const [savingAction, setSavingAction] = useState(false);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");
  const [action, setAction] = useState(EMPTY_ACTION);

  async function loadDashboard() {
    try {
      setLoading(true);
      setDashboardError("");

      const response = await fetch(
        `${API_BASE}/dashboard/executive?user_name=Surinder`
      );

      if (!response.ok) {
        const responseText = await response.text();

        throw new Error(
          responseText ||
          `Dashboard request failed with status ${response.status}.`
        );
      }

      const data = await response.json();

      setDashboard(data);
    } catch (requestError) {
      console.error(
        "Unable to load Polaris dashboard:",
        requestError
      );

      setDashboardError(
        requestError.message ||
        "Polaris could not load the dashboard."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  function openActionForm() {
    setAction({
      ...EMPTY_ACTION,
      author: "Surinder",
    });

    setActionError("");
    setActionSuccess("");
    setShowActionForm(true);
  }

  function closeActionForm() {
    if (savingAction) {
      return;
    }

    setShowActionForm(false);
    setActionError("");
  }

  function handleActionChange(event) {
    const { name, value } = event.target;

    setAction((currentAction) => ({
      ...currentAction,
      [name]: value,
    }));
  }

  async function handleActionSubmit(event) {
    event.preventDefault();

    const cleanTitle = action.title.trim();
    const cleanDetails = action.details.trim();
    const cleanAuthor = action.author.trim();

    if (!cleanTitle) {
      setActionError("Please enter an action title.");
      return;
    }

    if (!cleanDetails) {
      setActionError("Please enter action details.");
      return;
    }

    if (!cleanAuthor) {
      setActionError("Please enter the author's name.");
      return;
    }

    const payload = {
      author: cleanAuthor,
      note_type: action.note_type,
      title: cleanTitle,
      details: cleanDetails,
      target_entity:
        action.target_entity.trim() || null,
      assigned_to:
        action.assigned_to.trim() || null,
      due_at: action.due_at
        ? new Date(action.due_at).toISOString()
        : null,
    };

    try {
      setSavingAction(true);
      setActionError("");
      setActionSuccess("");

      const response = await fetch(
        `${API_BASE}/team-notes`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        }
      );

      if (!response.ok) {
        let errorMessage =
          `Action could not be saved. Status: ${response.status}`;

        try {
          const errorData = await response.json();

          if (errorData.detail) {
            errorMessage =
              typeof errorData.detail === "string"
                ? errorData.detail
                : JSON.stringify(errorData.detail);
          }
        } catch {
          // Keep the default error message.
        }

        throw new Error(errorMessage);
      }

      await response.json();

      setShowActionForm(false);
      setAction(EMPTY_ACTION);
      setActionSuccess(
        `"${cleanTitle}" was added successfully.`
      );

      await loadDashboard();
    } catch (requestError) {
      console.error(
        "Unable to save action:",
        requestError
      );

      setActionError(
        requestError.message ||
        "Polaris could not save the action."
      );
    } finally {
      setSavingAction(false);
    }
  }

  if (loading && !dashboard) {
    return (
      <main className="dashboard-shell">
        <section className="polaris-card">
          <p className="eyebrow">POLARIS</p>
          <h2>Preparing your executive brief...</h2>
          <p className="muted">
            Reviewing missions, team notes, reasoning,
            and business activity.
          </p>
        </section>
      </main>
    );
  }

  if (dashboardError && !dashboard) {
    return (
      <main className="dashboard-shell">
        <section className="polaris-card">
          <p className="eyebrow">POLARIS</p>
          <h2>Dashboard unavailable</h2>

          <p>{dashboardError}</p>

          <button
            type="button"
            className="primary-button"
            onClick={loadDashboard}
          >
            Try Again
          </button>
        </section>
      </main>
    );
  }

  const needsAttention =
    dashboard?.needs_attention ?? [];

  const carryForward =
    dashboard?.carry_forward ?? [];

  const todaysPlan =
    dashboard?.todays_plan ?? [];

  const comingUp =
    dashboard?.coming_up ?? [];

  const watchItems =
    dashboard?.watch_items ?? [];

  return (
    <main className="dashboard-shell">
      <header className="dashboard-hero">
        <div>
          <p className="eyebrow">
            POLARIS
          </p>

          <h1>{dashboard.greeting}</h1>

          <p>
            Here is where your business stands right now.
          </p>

          <p>
            Estimated review time:{" "}
            <strong>
              {dashboard.review_minutes} minutes
            </strong>
          </p>
        </div>

        <div className="dashboard-hero-actions">
          <button
            type="button"
            className="primary-button add-action-button"
            onClick={openActionForm}
          >
            + Add Action
          </button>

          <button
            type="button"
            className="secondary-button"
            onClick={loadDashboard}
            disabled={loading}
          >
            {loading ? "Refreshing..." : "Refresh"}
          </button>

          <div className="status-panel">
            <span>Business Status</span>

            <strong>
              {dashboard.business_status}
            </strong>
          </div>
        </div>
      </header>

      {actionSuccess && (
        <div className="success-banner">
          {actionSuccess}
        </div>
      )}

      {dashboardError && (
        <div className="form-error">
          Dashboard refresh warning: {dashboardError}
        </div>
      )}

      <div className="summary-strip">
        <div>
          <strong>
            {dashboard.open_team_notes}
          </strong>

          <span>Open Notes</span>
        </div>

        <div>
          <strong>
            {dashboard.active_missions}
          </strong>

          <span>Active Missions</span>
        </div>

        <div>
          <strong>
            {dashboard.total_trucks}
          </strong>

          <span>Trucks</span>
        </div>
      </div>

      <div className="dashboard-grid">
        <Section
          title="Needs Attention"
          isEmpty={needsAttention.length === 0}
          emptyText="Nothing urgent requires your attention."
        >
          <ItemList items={needsAttention} />
        </Section>

        <Section
          title="Carry Forward"
          isEmpty={carryForward.length === 0}
          emptyText="No unfinished work has been carried forward."
        >
          <ItemList items={carryForward} />
        </Section>

        <Section
          title="Today's Plan"
          isEmpty={todaysPlan.length === 0}
          emptyText="No priorities have been created for today."
        >
          <ol className="priority-list">
            {todaysPlan.map((item) => (
              <li
                key={`${item.rank}-${item.title}`}
              >
                <strong>
                  {item.title}
                </strong>

                <p>
                  {item.reason}
                </p>

                <small>
                  {item.source}
                </small>
              </li>
            ))}
          </ol>
        </Section>

        <Section
          title="Coming Up"
          isEmpty={comingUp.length === 0}
          emptyText="Nothing is due within the next seven days."
        >
          <ItemList items={comingUp} />
        </Section>

        <Section
          title="Watch Items"
          isEmpty={watchItems.length === 0}
          emptyText="There are no additional watch items."
        >
          <ItemList items={watchItems} />
        </Section>

        <section className="polaris-card recommendation-card">
          <h2>
            Polaris Recommendation
          </h2>

          <p>
            {dashboard.recommendation}
          </p>
        </section>
      </div>

      <section className="ask-polaris">
        <input
          aria-label="Ask Polaris"
          placeholder="Ask Polaris..."
          disabled
        />

        <span>
          The conversational dashboard connection will
          be added in a future milestone.
        </span>
      </section>

      {showActionForm && (
        <AddActionForm
          action={action}
          saving={savingAction}
          error={actionError}
          onChange={handleActionChange}
          onSubmit={handleActionSubmit}
          onCancel={closeActionForm}
        />
      )}
    </main>
  );
}