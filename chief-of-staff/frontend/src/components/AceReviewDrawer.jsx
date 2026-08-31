import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RotateCcw, Save, XCircle } from "lucide-react";
import { apiClient, apiRequest } from "../apiClient";
import "./AceReviewDrawer.css";

const AUTHORIZATION_OPTIONS = [
  ["AUTHORIZED", "Authorized by MOR"],
  ["AUTHORIZED - THIRD PARTY", "Authorized — Third Party"],
  ["UNAUTHORIZED - NO MOR PERMISSION", "Unauthorized — No MOR Permission"],
];

function text(value, fallback = "—") {
  return value == null || value === "" ? fallback : String(value);
}

function dateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

function SourceField({ label, children, wide = false }) {
  return (
    <div className={wide ? "ace-review-source-field ace-review-source-wide" : "ace-review-source-field"}>
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  );
}

function reviewLabel(status) {
  if (status === "critical") return "Critical";
  if (status === "review") return "Under Review";
  if (status === "resolved") return "Resolved";
  return "Clear";
}

export default function AceReviewDrawer({ movement, onClose, onChanged }) {
  const [authorizationStatus, setAuthorizationStatus] = useState("");
  const [authorizationNotes, setAuthorizationNotes] = useState("");
  const [evidenceReference, setEvidenceReference] = useState("");
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  useEffect(() => {
    setAuthorizationStatus(movement?.authorization_status || "");
    setAuthorizationNotes(movement?.authorization_notes || "");
    setEvidenceReference(movement?.evidence_reference || "");
    setResolutionNotes(movement?.resolution_notes || "");
    setActionError("");
    setActionMessage("");
  }, [movement?.id, movement?.authorization_status, movement?.authorization_notes, movement?.evidence_reference, movement?.resolution_notes]);

  if (!movement) return null;

  const resolved = Boolean(movement.resolved_at);
  const timeline = movement.events || [];

  async function refreshAfterAction(message) {
    setActionMessage(message);
    if (onChanged) await onChanged(movement.id);
  }

  async function saveReview() {
    if (!authorizationStatus) {
      setActionError("Choose an authorization decision before saving the review.");
      return;
    }
    try {
      setSaving(true);
      setActionError("");
      setActionMessage("");
      await apiRequest(`/ace/movements/${movement.id}/authorization`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          authorization_status: authorizationStatus,
          authorization_notes: authorizationNotes.trim() || null,
          evidence_reference: evidenceReference.trim() || null,
        }),
      });
      await refreshAfterAction("Review saved. ACE source status was not changed.");
    } catch (error) {
      setActionError(error.message || "Unable to save the ACE review.");
    } finally {
      setSaving(false);
    }
  }

  async function resolveReview() {
    const notes = resolutionNotes.trim();
    if (!notes) {
      setActionError("Resolution notes are required before resolving an exception.");
      return;
    }
    const confirmed = typeof globalThis.confirm !== "function" || globalThis.confirm(
      "Resolve this MOR review? The ACE source status will remain unchanged."
    );
    if (!confirmed) return;
    try {
      setSaving(true);
      setActionError("");
      setActionMessage("");
      await apiClient.post(`/ace/movements/${movement.id}/resolve`, { resolution_notes: notes });
      await refreshAfterAction("MOR review resolved. ACE source status remains provider-controlled.");
    } catch (error) {
      setActionError(error.message || "Unable to resolve the ACE review.");
    } finally {
      setSaving(false);
    }
  }

  async function reopenReview() {
    const confirmed = typeof globalThis.confirm !== "function" || globalThis.confirm(
      "Reopen this MOR review for further investigation?"
    );
    if (!confirmed) return;
    try {
      setSaving(true);
      setActionError("");
      setActionMessage("");
      await apiClient.post(`/ace/movements/${movement.id}/reopen`, {});
      await refreshAfterAction("Review reopened and recalculated from the current ACE evidence.");
    } catch (error) {
      setActionError(error.message || "Unable to reopen the ACE review.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside className="ace-review-drawer" aria-label="ACE movement review and resolution">
      <div className="ace-review-header">
        <div>
          <small>IN-BOND</small>
          <h2>{movement.inbond_number}</h2>
          <p>{movement.bill_of_lading_number || "No BOL / PAPS"}</p>
        </div>
        <button type="button" className="ace-review-close" onClick={onClose} aria-label="Close details">
          <XCircle size={22} />
        </button>
      </div>

      <div className="ace-review-status-row">
        <span className="ace-review-chip ace-review-chip-source">ACE: {movement.record_status || "Unknown"}</span>
        <span className={`ace-review-chip ace-review-chip-${movement.review_status || "clear"}`}>
          MOR Review: {reviewLabel(movement.review_status)}
        </span>
      </div>

      <div className="ace-review-source-notice">
        <strong>ACE source — read only</strong>
        <span>Status, dates, carrier and filer data below come from the imported ACE report and cannot be manually overwritten here.</span>
      </div>

      <section className="ace-review-section">
        <h3>ACE movement evidence</h3>
        <div className="ace-review-source-grid">
          <SourceField label="ACE Status">{text(movement.record_status)}</SourceField>
          <SourceField label="Type">{text(movement.inbond_type_code)} {text(movement.inbond_type_description, "")}</SourceField>
          <SourceField label="QP Filer">{text(movement.qp_filer?.code)} · {text(movement.qp_filer?.name)}</SourceField>
          <SourceField label="Penalty">{movement.penalty_indicator == null ? "Unreported" : movement.penalty_indicator ? "Yes" : "No"}</SourceField>
          <SourceField label="In-Bond Carrier">{text(movement.inbond_carrier?.code)} · {text(movement.inbond_carrier?.name)}</SourceField>
          <SourceField label="Bonded Carrier">{text(movement.bonded_carrier?.code)} · {text(movement.bonded_carrier?.name)}</SourceField>
          <SourceField label="Manifest Carrier">{text(movement.manifest_carrier?.code)} · {text(movement.manifest_carrier?.name)}</SourceField>
          <SourceField label="Late / Overdue">{movement.days_late || 0} / {movement.days_overdue_for_export || 0} days</SourceField>
          <SourceField label="Shipper" wide>{text(movement.shipper_name)}</SourceField>
          <SourceField label="Consignee" wide>{text(movement.consignee_name)}</SourceField>
          <SourceField label="Route" wide>{text(movement.origination_port_name)} → {text(movement.destination_port_name)}</SourceField>
          <SourceField label="Create / Arrival / Export" wide>
            {text(movement.create_date)} · {text(movement.arrival_date)} · {text(movement.export_date)}
          </SourceField>
          <SourceField label="Transfer of Liability" wide>{dateTime(movement.transfer_of_liability_at)}</SourceField>
          <SourceField label="First / Last Seen" wide>{dateTime(movement.first_seen_at)} · {dateTime(movement.last_seen_at)}</SourceField>
        </div>
      </section>

      <section className="ace-review-section ace-review-management">
        <div className="ace-review-section-heading">
          <div>
            <small>MOR INTERNAL CONTROL</small>
            <h3>Review & Resolution</h3>
          </div>
          {resolved && <span className="ace-review-resolved-badge"><CheckCircle2 size={15} /> Resolved</span>}
        </div>

        <div className={`ace-review-reason ace-review-reason-${movement.review_status || "clear"}`}>
          <span>Why Polaris flagged this movement</span>
          <strong>{movement.review_reason || "No current review reason."}</strong>
        </div>

        {resolved && (
          <div className="ace-review-current-resolution">
            <span>Current resolution</span>
            <strong>{dateTime(movement.resolved_at)}</strong>
            <p>{movement.resolution_notes || "Resolved without additional notes."}</p>
            <small>Reopen this review before changing the authorization decision or investigation evidence.</small>
          </div>
        )}

        <div className="ace-review-form-grid">
          <label className="ace-review-field">
            <span>Authorization decision</span>
            <select value={authorizationStatus} onChange={(event) => setAuthorizationStatus(event.target.value)} disabled={resolved || saving}>
              <option value="">Not classified yet</option>
              {AUTHORIZATION_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>

          <label className="ace-review-field ace-review-field-wide">
            <span>Authorization / investigation notes</span>
            <textarea
              rows="4"
              value={authorizationNotes}
              onChange={(event) => setAuthorizationNotes(event.target.value)}
              disabled={resolved || saving}
              placeholder="Example: Dispatch email reviewed; shipment was approved by management on Aug 29."
            />
          </label>

          <label className="ace-review-field ace-review-field-wide">
            <span>Evidence reference</span>
            <textarea
              rows="3"
              value={evidenceReference}
              onChange={(event) => setEvidenceReference(event.target.value)}
              disabled={resolved || saving}
              placeholder="Email subject/date, broker confirmation, CBP reference, document name, or other evidence."
            />
          </label>

          {!resolved && (
            <label className="ace-review-field ace-review-field-wide">
              <span>Resolution notes</span>
              <textarea
                rows="4"
                value={resolutionNotes}
                onChange={(event) => setResolutionNotes(event.target.value)}
                disabled={saving}
                placeholder="Required only when you are ready to resolve the MOR review. Explain what was checked and why the issue is considered handled."
              />
            </label>
          )}
        </div>

        {actionError && <div className="ace-review-action-error"><AlertTriangle size={16} /> {actionError}</div>}
        {actionMessage && <div className="ace-review-action-success"><CheckCircle2 size={16} /> {actionMessage}</div>}

        <div className="ace-review-actions">
          {!resolved ? (
            <>
              <button type="button" className="ace-review-button ace-review-save" onClick={saveReview} disabled={saving}>
                <Save size={16} /> {saving ? "Saving…" : "Save Review"}
              </button>
              <button type="button" className="ace-review-button ace-review-resolve" onClick={resolveReview} disabled={saving}>
                <CheckCircle2 size={16} /> Resolve Exception
              </button>
            </>
          ) : (
            <button type="button" className="ace-review-button ace-review-reopen" onClick={reopenReview} disabled={saving}>
              <RotateCcw size={16} /> {saving ? "Reopening…" : "Reopen Review"}
            </button>
          )}
        </div>
      </section>

      <section className="ace-review-section ace-review-history">
        <h3>Movement history</h3>
        {timeline.length === 0 && <p className="ace-review-muted">No recorded changes yet.</p>}
        {timeline.map((event) => (
          <div className="ace-review-history-item" key={event.id}>
            <span>{dateTime(event.occurred_at)}</span>
            <strong>{String(event.event_type || "event").replaceAll("_", " ")}</strong>
            <p>{event.detail || (event.field_name ? `${event.field_name}: ${event.old_value ?? "—"} → ${event.new_value ?? "—"}` : "")}</p>
          </div>
        ))}
      </section>
    </aside>
  );
}
