import { useCallback, useEffect, useMemo, useState } from "react";
import { Database, Filter, RefreshCw, Truck } from "lucide-react";
import { apiClient } from "../apiClient";
import "./DispatchDashboard.css";

const EMPTY_FILTERS = Object.freeze({ from: "", to: "", status: "", customer: "", dispatcher: "" });
const PAGE_LIMIT = 25;

function formatDate(value) {
  if (!value) return "—";
  const dateValue = String(value).slice(0, 10);
  const parsed = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "short", day: "numeric" }).format(parsed);
}

function formatMiles(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-CA", { maximumFractionDigits: 1 }).format(value);
}

function buildPath(filters, page) {
  const params = new URLSearchParams({ page: String(page), limit: String(PAGE_LIMIT) });
  if (filters.from && filters.to) {
    params.set("from", filters.from);
    params.set("to", filters.to);
  }
  if (filters.status) params.set("status", filters.status);
  if (filters.customer) params.set("customer", filters.customer);
  if (filters.dispatcher) params.set("dispatcher", filters.dispatcher);
  return `/api/v1/torqueai/dispatches?${params.toString()}`;
}

function statusClass(status) {
  const normalized = String(status || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return `dispatch-status dispatch-status-${normalized}`;
}

export default function DispatchDashboard() {
  const [draftFilters, setDraftFilters] = useState({ ...EMPTY_FILTERS });
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS });
  const [page, setPage] = useState(1);
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const dateWindowIncomplete = Boolean(draftFilters.from) !== Boolean(draftFilters.to);

  const loadDispatches = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const response = await apiClient.get(buildPath(filters, page));
      setPayload(response);
    } catch (requestError) {
      setError(requestError.message || "Unable to load stored TorqueAI dispatch records.");
      setPayload(null);
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    loadDispatches();
  }, [loadDispatches]);

  const rows = payload?.data || [];
  const summary = useMemo(() => ({
    total: payload?.total_count ?? 0,
    visible: payload?.rows_returned ?? 0,
    page: payload?.page ?? page,
    providerCalls: payload?.provider_called === false ? 0 : "—",
  }), [payload, page]);

  function updateDraft(name, value) {
    setDraftFilters((current) => ({ ...current, [name]: value }));
  }

  function applyFilters(event) {
    event.preventDefault();
    if (dateWindowIncomplete) return;
    setPage(1);
    setFilters({
      from: draftFilters.from,
      to: draftFilters.to,
      status: draftFilters.status.trim(),
      customer: draftFilters.customer.trim(),
      dispatcher: draftFilters.dispatcher.trim(),
    });
  }

  function clearFilters() {
    setDraftFilters({ ...EMPTY_FILTERS });
    setFilters({ ...EMPTY_FILTERS });
    setPage(1);
  }

  return (
    <section className="dispatch-dashboard" aria-labelledby="dispatch-title">
      <div className="dispatch-hero">
        <div>
          <div className="dispatch-eyebrow"><Truck size={16} aria-hidden="true" /> OPERATIONS · DISPATCH</div>
          <h1 id="dispatch-title">Dispatch Control</h1>
          <p>Tenant-scoped TorqueAI dispatch records read from Polaris durable storage.</p>
        </div>
        <div className="dispatch-source-badge"><Database size={16} aria-hidden="true" /><span><strong>Durable database</strong><small>Neon read only · no provider call</small></span></div>
      </div>

      <div className="dispatch-summary-grid" aria-label="Dispatch read summary">
        <article><span>Total stored dispatches</span><strong>{loading ? "…" : summary.total}</strong><small>Matching current filters</small></article>
        <article><span>Rows on this page</span><strong>{loading ? "…" : summary.visible}</strong><small>Page size {PAGE_LIMIT}</small></article>
        <article><span>Current page</span><strong>{summary.page}</strong><small>{payload?.has_more ? "More records available" : "End of result set"}</small></article>
        <article><span>TorqueAI provider calls</span><strong>{summary.providerCalls}</strong><small>This screen reads Neon only</small></article>
      </div>

      <form className="dispatch-filters" onSubmit={applyFilters}>
        <div className="dispatch-filter-heading"><Filter size={17} aria-hidden="true" /><span>Stored-record filters</span></div>
        <label>Ship date from<input type="date" value={draftFilters.from} onChange={(event) => updateDraft("from", event.target.value)} /></label>
        <label>Ship date to<input type="date" value={draftFilters.to} onChange={(event) => updateDraft("to", event.target.value)} /></label>
        <label>Status<input type="text" value={draftFilters.status} onChange={(event) => updateDraft("status", event.target.value)} placeholder="Exact status" /></label>
        <label>Customer<input type="text" value={draftFilters.customer} onChange={(event) => updateDraft("customer", event.target.value)} placeholder="Exact customer" /></label>
        <label>Dispatcher<input type="text" value={draftFilters.dispatcher} onChange={(event) => updateDraft("dispatcher", event.target.value)} placeholder="Exact dispatcher" /></label>
        <div className="dispatch-filter-actions">
          <button type="submit" className="primary-button" disabled={dateWindowIncomplete || loading}>Apply</button>
          <button type="button" className="dispatch-secondary-button" onClick={clearFilters} disabled={loading}>Clear</button>
        </div>
        {dateWindowIncomplete && <p className="dispatch-filter-error" role="alert">Select both ship-date fields or leave both blank.</p>}
      </form>

      <div className="dispatch-table-card">
        <div className="dispatch-table-toolbar">
          <div><strong>Durable dispatch records</strong><span>{payload?.source === "durable_database" ? "Source verified: durable database" : "Awaiting source verification"}</span></div>
          <button type="button" className="dispatch-reload-button" onClick={loadDispatches} disabled={loading}><RefreshCw size={16} aria-hidden="true" />{loading ? "Loading…" : "Reload stored records"}</button>
        </div>

        {error && <div className="dispatch-state dispatch-error" role="alert">{error}</div>}
        {!error && loading && <div className="dispatch-state">Loading stored dispatch records…</div>}
        {!error && !loading && rows.length === 0 && <div className="dispatch-state">No stored dispatches match these filters.</div>}

        {!error && !loading && rows.length > 0 && (
          <div className="dispatch-table-scroll">
            <table className="dispatch-table">
              <thead><tr><th>Load</th><th>Order</th><th>Status</th><th>Ship / Delivery</th><th>Customer</th><th>Dispatcher / Driver</th><th>Truck / Trailer</th><th>Loaded miles</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.load_number}-${row.order_number}`}>
                    <td><strong>{row.load_number || "—"}</strong></td>
                    <td>{row.order_number || "—"}</td>
                    <td><span className={statusClass(row.status)}>{row.status || "Unreported"}</span></td>
                    <td><span>{formatDate(row.ship_date)}</span><small>{formatDate(row.delivery_date)}</small></td>
                    <td>{row.customer_name || "—"}</td>
                    <td><span>{row.dispatcher_name || "—"}</span><small>{row.driver_name || "—"}</small></td>
                    <td><span>{row.truck_number || "—"}</span><small>{row.trailer_number || "—"}</small></td>
                    <td>{formatMiles(row.loaded_miles)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="dispatch-pagination">
          <button type="button" className="dispatch-secondary-button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={loading || page <= 1}>Previous</button>
          <span>Page {page}</span>
          <button type="button" className="dispatch-secondary-button" onClick={() => setPage((current) => current + 1)} disabled={loading || !payload?.has_more}>Next</button>
        </div>
      </div>

      <p className="dispatch-footnote">Financial fields, billing details, stops, addresses, raw provider payloads, and automatic synchronization are intentionally not part of this dashboard.</p>
    </section>
  );
}
