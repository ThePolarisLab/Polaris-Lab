import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, FileDown, Search, ShieldCheck, XCircle } from "lucide-react";
import { apiClient } from "../apiClient";

const FILTERS = {
  status: "",
  shipper: "",
  qp_filer: "",
  inbond_carrier: "",
  bonded_carrier: "",
  manifest_carrier: "",
  start_date: "",
  end_date: "",
};

function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== false && value != null) search.set(key, String(value));
  });
  return search.toString();
}

function StatusPill({ movement }) {
  const tone = movement.review_status === "critical" ? "critical" : movement.review_status === "review" ? "review" : movement.record_status === "Open" ? "open" : "clear";
  const label = movement.authorization_status === "UNAUTHORIZED - NO MOR PERMISSION"
    ? "Unauthorized"
    : movement.review_status === "critical"
      ? "Critical"
      : movement.review_status === "review"
        ? "Review"
        : movement.record_status || "Clear";
  return <span className={`ace-status ace-status-${tone}`}>{label}</span>;
}

function DetailDrawer({ movement, onClose }) {
  if (!movement) return null;
  const timeline = movement.events || [];
  return (
    <aside className="ace-detail-drawer" aria-label="ACE movement details">
      <div className="ace-detail-header">
        <div><small>In-Bond</small><h2>{movement.inbond_number}</h2><p>{movement.bill_of_lading_number || "No BOL"}</p></div>
        <button type="button" onClick={onClose} aria-label="Close details"><XCircle size={20} /></button>
      </div>
      <StatusPill movement={movement} />
      <div className="ace-detail-grid">
        <div><span>Type</span><strong>{movement.inbond_type_code || "—"} {movement.inbond_type_description || ""}</strong></div>
        <div><span>Status</span><strong>{movement.record_status || "—"}</strong></div>
        <div><span>Shipper</span><strong>{movement.shipper_name || "—"}</strong></div>
        <div><span>Consignee</span><strong>{movement.consignee_name || "—"}</strong></div>
        <div><span>QP Filer</span><strong>{movement.qp_filer?.code || "—"} · {movement.qp_filer?.name || "—"}</strong></div>
        <div><span>In-Bond Carrier</span><strong>{movement.inbond_carrier?.code || "—"} · {movement.inbond_carrier?.name || "—"}</strong></div>
        <div><span>Bonded Carrier</span><strong>{movement.bonded_carrier?.code || "—"} · {movement.bonded_carrier?.name || "—"}</strong></div>
        <div><span>Manifest Carrier</span><strong>{movement.manifest_carrier?.code || "—"} · {movement.manifest_carrier?.name || "—"}</strong></div>
        <div><span>Route</span><strong>{movement.origination_port_name || "—"} → {movement.destination_port_name || "—"}</strong></div>
        <div><span>Create / Arrival / Export</span><strong>{movement.create_date || "—"} · {movement.arrival_date || "—"} · {movement.export_date || "—"}</strong></div>
        <div><span>Late / Overdue</span><strong>{movement.days_late || 0} / {movement.days_overdue_for_export || 0} days</strong></div>
        <div><span>Review reason</span><strong>{movement.review_reason || "None"}</strong></div>
      </div>
      <section className="ace-timeline">
        <h3>Movement history</h3>
        {timeline.length === 0 && <p className="ace-muted">No recorded changes yet.</p>}
        {timeline.map((event) => (
          <div className="ace-timeline-item" key={event.id}>
            <span>{new Date(event.occurred_at).toLocaleString()}</span>
            <strong>{event.event_type.replaceAll("_", " ")}</strong>
            <p>{event.detail || (event.field_name ? `${event.field_name}: ${event.old_value ?? "—"} → ${event.new_value ?? "—"}` : "")}</p>
          </div>
        ))}
      </section>
    </aside>
  );
}

export default function AceControl() {
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState(FILTERS);
  const [activeOnly, setActiveOnly] = useState(false);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const query = useMemo(() => qs({ search, ...filters, active_only: activeOnly, limit: 250 }), [search, filters, activeOnly]);

  async function load() {
    try {
      setLoading(true);
      setError("");
      const [summaryPayload, movementPayload] = await Promise.all([
        apiClient.get("/ace/summary"),
        apiClient.get(`/ace/movements?${query}`),
      ]);
      setSummary(summaryPayload);
      setItems(movementPayload.items || []);
      setTotal(movementPayload.total || 0);
    } catch (requestError) {
      setError(requestError.message || "Unable to load ACE data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [query]);

  async function openMovement(id) {
    try {
      setSelected(await apiClient.get(`/ace/movements/${id}`));
    } catch (requestError) {
      setError(requestError.message || "Unable to load movement details.");
    }
  }

  function exportCsv() {
    const header = ["In-Bond", "BOL", "Status", "Shipper", "Consignee", "QP Filer", "In-Bond Carrier", "Bonded Carrier", "Manifest Carrier", "Origin", "Destination", "Review"];
    const rows = items.map((item) => [
      item.inbond_number, item.bill_of_lading_number, item.record_status, item.shipper_name, item.consignee_name,
      item.qp_filer?.code, item.inbond_carrier?.code, item.bonded_carrier?.code, item.manifest_carrier?.code,
      item.origination_port_name, item.destination_port_name, item.review_reason,
    ]);
    const csv = [header, ...rows].map((row) => row.map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `polaris-ace-report-${new Date().toISOString().slice(0, 10)}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="ace-control-page">
      <div className="ace-page-heading">
        <div><span className="ace-eyebrow"><ShieldCheck size={16} /> ACE CONTROL</span><h1>Manifest & Bond Shipments</h1><p>Search, monitor, resolve, and report on ACE movement activity.</p></div>
        <button type="button" className="ace-export-button" onClick={exportCsv}><FileDown size={17} /> Export filtered report</button>
      </div>

      {summary && (
        <div className="ace-kpis">
          {[['Active', summary.active], ['Open', summary.open], ['Exceptions', summary.exceptions], ['Overdue', summary.overdue], ['Late', summary.late], ['Unauthorized', summary.unauthorized]].map(([label, value]) => (
            <div key={label}><span>{label}</span><strong>{value}</strong></div>
          ))}
        </div>
      )}

      <div className="ace-search-row">
        <label className="ace-global-search"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search In-Bond, BOL/PAPS, shipper, consignee, carrier, QP filer, port…" /></label>
        <label className="ace-toggle"><input type="checkbox" checked={activeOnly} onChange={(event) => setActiveOnly(event.target.checked)} /> Active only</label>
      </div>

      <div className="ace-filter-grid">
        <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">All statuses</option><option>Open</option><option>Fully Closed</option></select>
        <input placeholder="Shipper" value={filters.shipper} onChange={(event) => setFilters({ ...filters, shipper: event.target.value })} />
        <input placeholder="QP Filer" value={filters.qp_filer} onChange={(event) => setFilters({ ...filters, qp_filer: event.target.value })} />
        <input placeholder="In-Bond Carrier" value={filters.inbond_carrier} onChange={(event) => setFilters({ ...filters, inbond_carrier: event.target.value })} />
        <input placeholder="Bonded Carrier" value={filters.bonded_carrier} onChange={(event) => setFilters({ ...filters, bonded_carrier: event.target.value })} />
        <input placeholder="Manifest Carrier" value={filters.manifest_carrier} onChange={(event) => setFilters({ ...filters, manifest_carrier: event.target.value })} />
        <label>From<input type="date" value={filters.start_date} onChange={(event) => setFilters({ ...filters, start_date: event.target.value })} /></label>
        <label>To<input type="date" value={filters.end_date} onChange={(event) => setFilters({ ...filters, end_date: event.target.value })} /></label>
        <button type="button" onClick={() => { setFilters(FILTERS); setSearch(""); setActiveOnly(false); }}>Clear filters</button>
      </div>

      {error && <div className="ace-error"><AlertTriangle size={17} /> {error}</div>}
      <div className="ace-table-meta"><strong>{total}</strong> matching movements</div>
      <div className="ace-table-wrap">
        <table className="ace-table">
          <thead><tr><th>In-Bond / BOL</th><th>Status</th><th>Shipper → Consignee</th><th>QP Filer</th><th>In-Bond / Manifest Carrier</th><th>Route</th><th>Exception</th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan="7">Loading ACE movements…</td></tr>}
            {!loading && items.length === 0 && <tr><td colSpan="7">No movements match these filters.</td></tr>}
            {!loading && items.map((item) => (
              <tr key={item.id} onClick={() => openMovement(item.id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") openMovement(item.id); }}>
                <td><strong>{item.inbond_number}</strong><span>{item.bill_of_lading_number || "—"}</span></td>
                <td><StatusPill movement={item} /></td>
                <td><strong>{item.shipper_name || "—"}</strong><span>{item.consignee_name || "—"}</span></td>
                <td><strong>{item.qp_filer?.code || "—"}</strong><span>{item.qp_filer?.name || "—"}</span></td>
                <td><strong>{item.inbond_carrier?.code || "—"}</strong><span>{item.manifest_carrier?.code || "—"}</span></td>
                <td><strong>{item.origination_port_name || "—"}</strong><span>{item.destination_port_name || "—"}</span></td>
                <td>{item.review_reason || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <DetailDrawer movement={selected} onClose={() => setSelected(null)} />
    </section>
  );
}
