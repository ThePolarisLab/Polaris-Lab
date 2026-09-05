import { useMemo, useState } from "react";
import { AlertTriangle, Database, FileSearch, ShieldCheck } from "lucide-react";

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

function ReviewTable({ title, description, rows, currency, tone }) {
  return (
    <section className={`fuel-review-panel ${tone || ""}`}>
      <header><div><h2>{title}</h2><p>{description}</p></div><strong>{rows.length}</strong></header>
      {rows.length === 0 ? <div className="fuel-empty">No lines in this queue.</div> : (
        <div className="fuel-review-table-wrap">
          <table className="fuel-review-table">
            <thead><tr><th>Line</th><th>Date / product</th><th>Billed vs quote</th><th>Qty</th><th>Rate delta</th><th>Analytical impact</th><th>Evidence</th></tr></thead>
            <tbody>{rows.map((line) => (
              <tr key={line.invoice_line_id || line.line_number}>
                <td><strong>#{line.line_number}</strong><span>{line.status}</span></td>
                <td><strong>{line.transaction_date || "No date"}</strong><span>{line.product_code} · {line.category}</span></td>
                <td><strong>{line.invoice_billed_price} → {line.quote_price}</strong><span>{line.price_basis || currency}</span></td>
                <td>{line.invoice_quantity}</td>
                <td><strong>{line.rate_difference}</strong><span>{line.fallback_days ? `${line.fallback_days}d prior quote` : "same-date quote"}</span></td>
                <td><strong>{signedAmount(line.analytical_impact, currency)}</strong><span>analytical only</span></td>
                <td><strong>{evidenceText(line)}</strong><span>{line.selected_effective_date ? `effective ${line.selected_effective_date}` : ""}</span></td>
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
      <header><div><h2>DEF quantity verification</h2><p>Supplier price comparison does not apply. Quantity stays pending until both required evidence classes are verified.</p></div><strong>{rows.length}</strong></header>
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
  const [error, setError] = useState("");
  const review = useMemo(() => preview ? buildFuelReview(preview) : null, [preview]);

  async function loadInvoice(event) {
    event.preventDefault();
    if (!/^\d+$/.test(invoiceRunId)) {
      setError("Enter a valid Polaris invoice run ID.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = await apiClient.get(`/api/v1/fuel/invoices/${invoiceRunId}/price-reconciliation`);
      if (!payload?.read_only) throw new Error("Fuel review requires a read-only reconciliation preview.");
      setPreview(payload);
      window.location.hash = `#executive/fuel-review?invoice=${invoiceRunId}`;
    } catch (requestError) {
      setPreview(null);
      setError(requestError.message || "Unable to load the fuel price-reconciliation preview.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="fuel-review" aria-labelledby="fuel-review-title">
      <header className="fuel-review-header">
        <div><p>FUEL · READ-ONLY REVIEW</p><h1 id="fuel-review-title">Fuel invoice review</h1><span>Prioritize supplier price exceptions, preserve exact evidence, and keep DEF quantity verification separate.</span></div>
        <form className="fuel-run-form" onSubmit={loadInvoice}><label>Invoice run ID<input value={invoiceRunId} onChange={(event) => setInvoiceRunId(event.target.value.trim())} inputMode="numeric" placeholder="e.g. 4" /></label><button type="submit" disabled={loading}>{loading ? "Loading…" : "Review invoice"}</button></form>
      </header>

      <div className="fuel-governance"><ShieldCheck size={19} aria-hidden="true" /><span>Observer mode only. This screen does not approve, adjust, pay, contact a supplier, import evidence, or reconcile Motive.</span></div>
      <div className="fuel-precision-notice"><FileSearch size={19} aria-hidden="true" /><span><strong>Display cue only:</strong> non-zero rate differences at or below {OBSERVED_PRECISION_RATE_BAND} per unit are grouped as possible precision candidates. Their exact backend status remains a price difference; no supplier rounding rule or tolerance is assumed.</span></div>

      {error && <div className="fuel-state error" role="alert"><AlertTriangle size={20} /><div><strong>Fuel review unavailable</strong><span>{error}</span></div></div>}
      {!preview && !error && <div className="fuel-state"><Database size={20} /><div><strong>Select a stored invoice run</strong><span>Polaris will read the existing tenant-scoped supplier price preview. No new supplier or Outlook call is made.</span></div></div>}

      {preview && review && (
        <>
          <div className="fuel-meta"><span><strong>{preview.invoice_number}</strong> · run {preview.invoice_run_id}</span><span>{preview.currency} · {preview.line_count} lines</span><span>{preview.policy_version}</span><span>read_only: {String(preview.read_only)}</span></div>
          <div className="fuel-kpis">
            <article><span>Investigate</span><strong>{review.investigate.length}</strong><small>Outside observed precision-sized band</small></article>
            <article><span>Possible precision</span><strong>{review.precisionCandidates.length}</strong><small>Still exact price differences</small></article>
            <article><span>Net analytical difference</span><strong>{signedAmount(review.netAnalyticalImpact, preview.currency)}</strong><small>Not a confirmed overcharge or refund</small></article>
            <article><span>DEF quantity pending</span><strong>{review.defPending.length}</strong><small>Receipt + Motive required</small></article>
            <article><span>Unresolved</span><strong>{review.unresolved.length}</strong><small>Evidence gap or contradiction</small></article>
          </div>

          <ReviewTable title="Investigate first" description="Differences larger than the observed precision-sized band, sorted by absolute analytical impact." rows={review.investigate} currency={preview.currency} tone="investigate-panel" />
          <ReviewTable title="Possible precision differences" description={`Exact non-zero differences ≤ ${OBSERVED_PRECISION_RATE_BAND} per unit. Keep visible until a supplier rounding policy is independently certified.`} rows={review.precisionCandidates} currency={preview.currency} />
          <DefTable rows={review.defPending} />
          {review.unresolved.length > 0 && <section className="fuel-review-panel unresolved-panel"><header><div><h2>Unresolved evidence</h2><p>These lines remain unresolved by the backend policy and require evidence, not assumptions.</p></div><strong>{review.unresolved.length}</strong></header><div className="fuel-unresolved-list">{review.unresolved.map((line) => <div key={line.invoice_line_id || line.line_number}><strong>Line #{line.line_number}</strong><span>{line.reason || "unresolved"}</span></div>)}</div></section>}
          <p className="fuel-disclaimer">Analytical impact = invoice quantity × (invoice billed price − supplier quote). It is not confirmed loss, refund, supplier liability, accounting adjustment, or payment approval.</p>
        </>
      )}
    </section>
  );
}
