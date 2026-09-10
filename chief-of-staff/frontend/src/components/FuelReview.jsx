import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, FileSearch, RotateCcw, ShieldCheck } from "lucide-react";

import { apiClient } from "../apiClient";
import { OBSERVED_PRECISION_RATE_BAND, buildFuelReview } from "../fuelReviewModel";
import "./FuelReview.css";

function initialInvoiceRunId() {
  const query = window.location.hash.split("?")[1] || "";
  const value = new URLSearchParams(query).get("invoice") || "";
  return /^\d+$/.test(value) ? value : "";
}

function signedAmount(value, currency) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  const text = String(value);
  return `${text.startsWith("-") ? "-" : "+"}${currency} ${text.replace(/^[+-]/, "")}`;
}

function evidenceText(line) {
  const parts = [];
  if (line.quote_evidence_id) parts.push(`quote row ${line.quote_evidence_id}`);
  if (line.quote_source_filename) parts.push(line.quote_source_filename);
  if (line.quote_source_sha256) parts.push(`SHA ${line.quote_source_sha256.slice(0, 12)}…`);
  return parts.join(" · ") || "No supplier quote evidence applies to this line.";
}

function reviewText(line) {
  const review = line.review || {};
  if (review.disposition !== "approved_no_action") return "Not reviewed";
  const pieces = ["Approved — no action"];
  if (review.reviewer_role) pieces.push(review.reviewer_role);
  if (review.reviewed_at) pieces.push(new Date(review.reviewed_at).toLocaleString());
  return pieces.join(" · ");
}

function ReviewTable({ title, description, rows, currency, tone, onApprove, onReopen, busyLineId, headerAction }) {
  return (
    <section className={`fuel-review-panel ${tone || ""}`}>
      <header>
        <div><h2>{title}</h2><p>{description}</p></div>
        <div className="fuel-panel-actions">{headerAction}<strong>{rows.length}</strong></div>
      </header>
      {rows.length === 0 ? <div className="fuel-empty">No lines in this queue.</div> : (
        <div className="fuel-review-table-wrap">
          <table className="fuel-review-table">
            <thead><tr><th>Line</th><th>Date / product</th><th>Billed vs quote</th><th>Qty</th><th>Rate delta</th><th>Analytical impact</th><th>Evidence</th><th>Review</th></tr></thead>
            <tbody>{rows.map((line) => (
              <tr key={line.invoice_line_id || line.line_number}>
                <td><strong>#{line.line_number}</strong><span>{line.status}</span></td>
                <td><strong>{line.transaction_date || "No date"}</strong><span>{line.product_code} · {line.category}</span></td>
                <td><strong>{line.invoice_billed_price} → {line.quote_price}</strong><span>{line.price_basis || currency}</span></td>
                <td>{line.invoice_quantity}</td>
                <td><strong>{line.rate_difference}</strong><span>{line.fallback_days ? `${line.fallback_days}d prior quote` : "same-date quote"}</span></td>
                <td><strong>{signedAmount(line.analytical_impact, currency)}</strong><span>analytical only</span></td>
                <td><strong>{evidenceText(line)}</strong><span>{line.selected_effective_date ? `effective ${line.selected_effective_date}` : ""}</span></td>
                <td className="fuel-review-action-cell">
                  <strong>{reviewText(line)}</strong>
                  {line.review?.reason && <span>Reason: {line.review.reason}</span>}
                  {onApprove && <button type="button" disabled={busyLineId === line.invoice_line_id} onClick={() => onApprove(line)}>{busyLineId === line.invoice_line_id ? "Saving…" : "Approve discrepancy"}</button>}
                  {onReopen && <button type="button" className="secondary" disabled={busyLineId === line.invoice_line_id} onClick={() => onReopen(line)}><RotateCcw size={14} />{busyLineId === line.invoice_line_id ? "Saving…" : "Reopen"}</button>}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DefTable({ rows }) {
  return (
    <section className="fuel-review-panel def-panel">
      <header><div><h2>DEF quantity verification</h2><p>Supplier price comparison does not apply. Quantity stays pending until both required evidence classes are verified.</p></div><div className="fuel-panel-actions"><strong>{rows.length}</strong></div></header>
      {rows.length === 0 ? <div className="fuel-empty">No pending DEF quantity lines.</div> : (
        <div className="fuel-review-table-wrap">
          <table className="fuel-review-table">
            <thead><tr><th>Line</th><th>Date</th><th>Product</th><th>Invoice price</th><th>Quantity</th><th>Status</th><th>Required evidence</th></tr></thead>
            <tbody>{rows.map((line) => (
              <tr key={line.invoice_line_id || line.line_number}>
                <td><strong>#{line.line_number}</strong></td><td>{line.transaction_date || "No date"}</td><td>{line.product_code}</td>
                <td>{line.invoice_billed_price}</td><td>{line.invoice_quantity}</td>
                <td><strong>{line.quantity_verification_status}</strong></td>
                <td>{(line.quantity_required_evidence || []).join(" + ")}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function FuelReview() {
  const [invoiceRunId, setInvoiceRunId] = useState(initialInvoiceRunId);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busyLineId, setBusyLineId] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const review = useMemo(() => preview ? buildFuelReview(preview) : null, [preview]);

  async function fetchInvoice(runId) {
    const payload = await apiClient.get(`/api/v1/fuel/invoices/${runId}/price-reconciliation`);
    if (!payload?.read_only || !payload?.evidence_read_only) throw new Error("Fuel review requires immutable reconciliation evidence.");
    setPreview(payload);
    window.location.hash = `#executive/fuel-review?invoice=${runId}`;
    return payload;
  }

  async function loadInvoice(event) {
    event.preventDefault();
    if (!/^\d+$/.test(invoiceRunId)) {
      setError("Enter a valid Polaris invoice run ID.");
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      await fetchInvoice(invoiceRunId);
    } catch (requestError) {
      setPreview(null);
      setError(requestError.message || "Unable to load the fuel price-reconciliation preview.");
    } finally {
      setLoading(false);
    }
  }

  async function approveLine(line) {
    let reason = null;
    if (line.review_priority === "investigate") {
      reason = window.prompt("Reason required for a material discrepancy. Approval means reviewed and accepted with no further action; it does not change the price difference or accounting records.", line.review?.reason || "");
      if (reason === null) return;
      if (!reason.trim()) {
        setError("A reason is required to approve a material discrepancy.");
        return;
      }
    }
    setBusyLineId(line.invoice_line_id);
    setError("");
    setNotice("");
    try {
      await apiClient.post(`/api/v1/fuel/invoices/${invoiceRunId}/price-reconciliation/${line.invoice_line_id}/approve`, { reason });
      await fetchInvoice(invoiceRunId);
      setNotice(`Line #${line.line_number} approved — no action. The technical price difference is unchanged.`);
    } catch (requestError) {
      setError(requestError.message || "Unable to record discrepancy approval.");
    } finally {
      setBusyLineId(null);
    }
  }

  async function approveAllPrecision() {
    if (!review?.precisionCandidates.length) return;
    const confirmed = window.confirm(`Approve ${review.precisionCandidates.length} currently open precision-sized discrepancies as reviewed — no action? This does not create a rounding tolerance or change their price_difference status.`);
    if (!confirmed) return;
    setBulkBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await apiClient.post(`/api/v1/fuel/invoices/${invoiceRunId}/price-reconciliation/approve-precision`, {});
      await fetchInvoice(invoiceRunId);
      setNotice(`${result.approved_count} precision-sized discrepancies approved — no action. No supplier rounding rule was inferred.`);
    } catch (requestError) {
      setError(requestError.message || "Unable to approve precision-sized discrepancies.");
    } finally {
      setBulkBusy(false);
    }
  }

  async function reopenLine(line) {
    const reason = window.prompt("Optional reason for reopening this discrepancy:", "");
    if (reason === null) return;
    setBusyLineId(line.invoice_line_id);
    setError("");
    setNotice("");
    try {
      await apiClient.post(`/api/v1/fuel/invoices/${invoiceRunId}/price-reconciliation/${line.invoice_line_id}/reopen`, { reason });
      await fetchInvoice(invoiceRunId);
      setNotice(`Line #${line.line_number} reopened. The previous approval remains in audit history.`);
    } catch (requestError) {
      setError(requestError.message || "Unable to reopen discrepancy.");
    } finally {
      setBusyLineId(null);
    }
  }

  return (
    <section className="fuel-review" aria-labelledby="fuel-review-title">
      <header className="fuel-review-header">
        <div><p>FUEL · EVIDENCE READ-ONLY · REVIEW DISPOSITIONS</p><h1 id="fuel-review-title">Fuel invoice review</h1><span>Prioritize supplier price exceptions, preserve exact evidence, and record a separate human review decision.</span></div>
        <form className="fuel-run-form" onSubmit={loadInvoice}><label>Invoice run ID<input value={invoiceRunId} onChange={(event) => setInvoiceRunId(event.target.value.trim())} inputMode="numeric" placeholder="e.g. 4" /></label><button type="submit" disabled={loading}>{loading ? "Loading…" : "Review invoice"}</button></form>
      </header>

      <div className="fuel-governance"><ShieldCheck size={19} aria-hidden="true" /><span>Supplier evidence and technical reconciliation remain immutable. Approval records only an append-only review disposition; it does not adjust, pay, contact a supplier, post to accounting, import evidence, or reconcile Motive.</span></div>
      <div className="fuel-precision-notice"><FileSearch size={19} aria-hidden="true" /><span><strong>Display cue only:</strong> non-zero rate differences at or below {OBSERVED_PRECISION_RATE_BAND} per unit are grouped as possible precision candidates. Approval does not convert them to matches and no supplier rounding rule or tolerance is assumed.</span></div>

      {error && <div className="fuel-state error" role="alert"><AlertTriangle size={20} /><div><strong>Fuel review action unavailable</strong><span>{error}</span></div></div>}
      {notice && <div className="fuel-state success" role="status"><CheckCircle2 size={20} /><div><strong>Review recorded</strong><span>{notice}</span></div></div>}
      {!preview && !error && <div className="fuel-state"><Database size={20} /><div><strong>Select a stored invoice run</strong><span>Polaris will read the existing tenant-scoped supplier price preview. No new supplier or Outlook call is made.</span></div></div>}

      {preview && review && (
        <>
          <div className="fuel-meta"><span><strong>{preview.invoice_number}</strong> · run {preview.invoice_run_id}</span><span>{preview.currency} · {preview.line_count} lines</span><span>{preview.policy_version}</span><span>evidence_read_only: {String(preview.evidence_read_only)}</span></div>
          <div className="fuel-kpis">
            <article><span>Open discrepancies</span><strong>{review.openPriceDifferences.length}</strong><small>Need review or investigation</small></article>
            <article><span>Approved — no action</span><strong>{review.approvedDifferences.length}</strong><small>Technical differences preserved</small></article>
            <article><span>Open analytical impact</span><strong>{signedAmount(review.openAnalyticalImpact, preview.currency)}</strong><small>Not confirmed supplier liability</small></article>
            <article><span>Total analytical difference</span><strong>{signedAmount(review.netAnalyticalImpact, preview.currency)}</strong><small>Includes approved and open items</small></article>
            <article><span>DEF quantity pending</span><strong>{review.defPending.length}</strong><small>Receipt + Motive required</small></article>
            <article><span>Unresolved</span><strong>{review.unresolved.length}</strong><small>Evidence gap or contradiction</small></article>
          </div>

          <ReviewTable title="Investigate first" description="Open differences larger than the observed precision-sized band, sorted by absolute analytical impact. A reason is required to approve one with no further action." rows={review.investigate} currency={preview.currency} tone="investigate-panel" onApprove={approveLine} busyLineId={busyLineId} />
          <ReviewTable title="Possible precision differences" description={`Open exact non-zero differences ≤ ${OBSERVED_PRECISION_RATE_BAND} per unit. One-click approval records reviewed — no action; it is not a tolerance rule.`} rows={review.precisionCandidates} currency={preview.currency} onApprove={approveLine} busyLineId={busyLineId} headerAction={<button type="button" className="fuel-bulk-button" disabled={bulkBusy || review.precisionCandidates.length === 0} onClick={approveAllPrecision}>{bulkBusy ? "Saving…" : "Approve all precision"}</button>} />
          <ReviewTable title="Approved — no action" description={`Accepted review decisions. The original price_difference status and exact analytical impact remain visible. Approved analytical impact: ${signedAmount(review.approvedAnalyticalImpact, preview.currency)}.`} rows={review.approvedDifferences} currency={preview.currency} tone="approved-panel" onReopen={reopenLine} busyLineId={busyLineId} />
          <DefTable rows={review.defPending} />
          {review.unresolved.length > 0 && <section className="fuel-review-panel unresolved-panel"><header><div><h2>Unresolved evidence</h2><p>These lines remain unresolved by the backend policy and require evidence, not assumptions.</p></div><div className="fuel-panel-actions"><strong>{review.unresolved.length}</strong></div></header><div className="fuel-unresolved-list">{review.unresolved.map((line) => <div key={line.invoice_line_id || line.line_number}><strong>Line #{line.line_number}</strong><span>{line.reason || "unresolved"}</span></div>)}</div></section>}
          <p className="fuel-disclaimer">Analytical impact = invoice quantity × (invoice billed price − supplier quote). It is not confirmed loss, refund, supplier liability, accounting adjustment, or payment approval. “Approved — no action” is a human review disposition only.</p>
        </>
      )}
    </section>
  );
}
