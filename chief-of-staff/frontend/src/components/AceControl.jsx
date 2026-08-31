import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, FileDown, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { apiClient } from "../apiClient";
import AceReviewDrawer from "./AceReviewDrawer";
import "./AceControl.css";

const FILTERS = {
  status: "",
  inbond_number: "",
  bol: "",
  shipper: "",
  consignee: "",
  qp_filer: "",
  inbond_carrier: "",
  bonded_carrier: "",
  manifest_carrier: "",
  origin_port: "",
  destination_port: "",
  inbond_type: "",
  authorization_status: "",
  exception_type: "",
  open_closed: "",
  late: "",
  overdue: "",
  penalty: "",
  transfer_of_liability: "",
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

function filtersFromHash() {
  const [, queryString = ""] = window.location.hash.split("?");
  if (!queryString) return { filters: FILTERS, activeOnly: false, counterFilter: "" };
  const params = new URLSearchParams(queryString);
  const filters = { ...FILTERS };
  Object.keys(filters).forEach((key) => {
    if (params.has(key)) filters[key] = params.get(key) || "";
  });
  return { filters, activeOnly: params.get("active_only") === "true", counterFilter: params.get("counter_filter") || "" };
}

function StatusPill({ movement }) {
  const tone = movement.review_status === "critical"
    ? "critical"
    : movement.review_status === "review"
      ? "review"
      : movement.record_status === "Open"
        ? "open"
        : "clear";
  const label = movement.authorization_status === "UNAUTHORIZED - NO MOR PERMISSION"
    ? "Unauthorized"
    : movement.review_status === "critical"
      ? "Critical"
      : movement.review_status === "review"
        ? "Review"
        : movement.review_status === "resolved"
          ? "Resolved"
          : movement.record_status || "Clear";
  return <span className={`ace-status ace-status-${tone}`}>{label}</span>;
}

export default function AceControl() {
  const initialView = filtersFromHash();
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState(initialView.filters);
  const [activeOnly, setActiveOnly] = useState(initialView.activeOnly);
  const [counterFilter, setCounterFilter] = useState(initialView.counterFilter);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [feedHealth, setFeedHealth] = useState(null);
  const [error, setError] = useState("");

  const query = useMemo(
    () => qs({ search, ...filters, active_only: activeOnly, counter_filter: counterFilter, limit: 250 }),
    [search, filters, activeOnly, counterFilter],
  );

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
      apiClient.get("/ace/feed-health").then(setFeedHealth).catch(() => setFeedHealth(null));
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

  async function refreshMovement(id) {
    await load();
    await openMovement(id);
  }

  function applyCounterFilter(label) {
    setSearch("");
    setFilters(FILTERS);
    setActiveOnly(false);
    setCounterFilter("");
    if (label === "Active") {
      setActiveOnly(true);
      setCounterFilter("active");
      return;
    }
    const next = { ...FILTERS };
    if (label === "Open") next.status = "Open";
    if (label === "Exceptions") setCounterFilter("exceptions");
    if (label === "Overdue") next.overdue = "true";
    if (label === "Late") next.late = "true";
    if (label === "Unauthorized") setCounterFilter("unauthorized");
    setFilters(next);
  }

  function exportCsv() {
    const header = ["In-Bond", "BOL", "Status", "Shipper", "Consignee", "QP Filer", "In-Bond Carrier", "Bonded Carrier", "Manifest Carrier", "Origin", "Destination", "Review"];
    const rows = items.map((item) => [
      item.inbond_number,
      item.bill_of_lading_number,
      item.record_status,
      item.shipper_name,
      item.consignee_name,
      item.qp_filer?.code,
      item.inbond_carrier?.code,
      item.bonded_carrier?.code,
      item.manifest_carrier?.code,
      item.origination_port_name,
      item.destination_port_name,
      item.review_reason,
    ]);
    const csv = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `polaris-ace-report-${new Date().toISOString().slice(0, 10)}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function importLatestReport() {
    try {
      setImporting(true);
      setError("");
      const result = await apiClient.post("/ace/import/outlook-latest");
      setImportResult(result);
      await load();
    } catch (requestError) {
      setError(requestError.message || "Unable to import latest ACE report.");
    } finally {
      setImporting(false);
    }
  }

  function importMessage(result) {
    if (!result) return "";
    const counts = `${result.records_read || 0} read · ${result.records_inserted || 0} inserted · ${result.records_updated || 0} updated · ${result.exceptions_created || 0} exceptions`;
    if (result.status === "import_success") return `Success: ${counts}`;
    if (result.status === "already_processed") return `Already processed: ${counts}`;
    if (result.status === "no_source_found") return "No report found.";
    if (result.status === "source_contract_error") return "Source contract error.";
    return "Import failed.";
  }

  function feedStatusLabel(status) {
    if (status === "healthy") return "Healthy";
    if (status === "no_new_report_yet") return "No new report yet";
    if (status === "warning") return "Watch";
    if (status === "error") return "Import failed";
    return "Unknown";
  }

  function dateText(value) {
    return value ? new Date(value).toLocaleString() : "Not yet recorded";
  }

  function movementDate(value) {
    if (!value) return "—";
    const normalized = /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value;
    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime())
      ? value
      : parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  return (
    <section className="ace-control-page">
      <div className="ace-page-heading">
        <div>
          <span className="ace-eyebrow"><ShieldCheck size={16} /> ACE CONTROL</span>
          <h1>In-Bond / Bond Control</h1>
          <p>Search, monitor, resolve, and report on scheduled ACE In-Bond Bills of Lading activity. Manifest is a separate source not connected yet.</p>
        </div>
        <div className="ace-action-stack">
          <button type="button" className="ace-export-button" onClick={importLatestReport} disabled={importing}>
            <RefreshCw size={17} className={importing ? "spin" : ""} /> {importing ? "Importing..." : "Import Latest ACE Report"}
          </button>
          <button type="button" className="ace-export-button" onClick={exportCsv}>
            <FileDown size={17} /> Export filtered report
          </button>
        </div>
      </div>

      {importResult && <div className="ace-import-result">{importMessage(importResult)}</div>}
      {feedHealth && (
        <section className={`ace-feed-health ace-feed-${feedHealth.status || "unknown"}`} aria-label="ACE daily feed health">
          <div>
            <span className="ace-eyebrow"><RefreshCw size={15} /> ACE DAILY FEED</span>
            <strong>{feedStatusLabel(feedHealth.status)}</strong>
          </div>
          <div><span>Last successful import</span><strong>{dateText(feedHealth.latest_successful_import_at)}</strong></div>
          <div><span>Source</span><strong>{feedHealth.source || "Outlook scheduled report"}</strong></div>
          <div><span>Mode</span><strong>{feedHealth.latest_successful_mode || "—"}</strong></div>
          <div><span>Rows processed</span><strong>{feedHealth.records_read || 0}</strong></div>
        </section>
      )}

      {summary && (
        <div className="ace-kpis">
          {[
            ["Active", summary.active],
            ["Open", summary.open],
            ["Exceptions", summary.exceptions],
            ["Overdue", summary.overdue],
            ["Late", summary.late],
            ["Unauthorized", summary.unauthorized],
          ].map(([label, value]) => (
            <button type="button" key={label} onClick={() => applyCounterFilter(label)}>
              <span>{label}</span><strong>{value}</strong>
            </button>
          ))}
        </div>
      )}

      <div className="ace-search-row">
        <label className="ace-global-search">
          <Search size={18} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search In-Bond, BOL/PAPS, shipper, consignee, carrier, QP filer, port…" />
        </label>
        <label className="ace-toggle">
          <input type="checkbox" checked={activeOnly} onChange={(event) => setActiveOnly(event.target.checked)} /> Active only
        </label>
      </div>

      <div className="ace-filter-grid">
        <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">All statuses</option><option>Open</option><option>Fully Closed</option></select>
        <input placeholder="In-Bond Number" value={filters.inbond_number} onChange={(event) => setFilters({ ...filters, inbond_number: event.target.value })} />
        <input placeholder="BOL / PAPS" value={filters.bol} onChange={(event) => setFilters({ ...filters, bol: event.target.value })} />
        <input placeholder="Shipper" value={filters.shipper} onChange={(event) => setFilters({ ...filters, shipper: event.target.value })} />
        <input placeholder="Consignee" value={filters.consignee} onChange={(event) => setFilters({ ...filters, consignee: event.target.value })} />
        <input placeholder="QP Filer" value={filters.qp_filer} onChange={(event) => setFilters({ ...filters, qp_filer: event.target.value })} />
        <input placeholder="In-Bond Carrier" value={filters.inbond_carrier} onChange={(event) => setFilters({ ...filters, inbond_carrier: event.target.value })} />
        <input placeholder="Bonded Carrier" value={filters.bonded_carrier} onChange={(event) => setFilters({ ...filters, bonded_carrier: event.target.value })} />
        <input placeholder="Manifest Carrier" value={filters.manifest_carrier} onChange={(event) => setFilters({ ...filters, manifest_carrier: event.target.value })} />
        <input placeholder="Origin Port" value={filters.origin_port} onChange={(event) => setFilters({ ...filters, origin_port: event.target.value })} />
        <input placeholder="Destination Port" value={filters.destination_port} onChange={(event) => setFilters({ ...filters, destination_port: event.target.value })} />
        <input placeholder="In-Bond Type" value={filters.inbond_type} onChange={(event) => setFilters({ ...filters, inbond_type: event.target.value })} />
        <input placeholder="Authorization Status" value={filters.authorization_status} onChange={(event) => setFilters({ ...filters, authorization_status: event.target.value })} />
        <input placeholder="Exception Type" value={filters.exception_type} onChange={(event) => setFilters({ ...filters, exception_type: event.target.value })} />
        <select value={filters.open_closed} onChange={(event) => setFilters({ ...filters, open_closed: event.target.value })}><option value="">Open + closed</option><option value="open">Open management view</option><option value="closed">Resolved historical</option></select>
        <select value={filters.late} onChange={(event) => setFilters({ ...filters, late: event.target.value })}><option value="">Late: Any</option><option value="true">Late only</option><option value="false">Not late</option></select>
        <select value={filters.overdue} onChange={(event) => setFilters({ ...filters, overdue: event.target.value })}><option value="">Overdue: Any</option><option value="true">Overdue only</option><option value="false">Not overdue</option></select>
        <select value={filters.penalty} onChange={(event) => setFilters({ ...filters, penalty: event.target.value })}><option value="">Penalty: Any</option><option value="true">Penalty only</option><option value="false">No penalty</option></select>
        <select value={filters.transfer_of_liability} onChange={(event) => setFilters({ ...filters, transfer_of_liability: event.target.value })}><option value="">Liability: Any</option><option value="true">Transfer present</option><option value="false">No transfer</option></select>
        <label>From<input type="date" value={filters.start_date} onChange={(event) => setFilters({ ...filters, start_date: event.target.value })} /></label>
        <label>To<input type="date" value={filters.end_date} onChange={(event) => setFilters({ ...filters, end_date: event.target.value })} /></label>
        <button type="button" onClick={() => { setFilters(FILTERS); setSearch(""); setActiveOnly(false); setCounterFilter(""); }}>Clear filters</button>
      </div>

      {error && <div className="ace-error"><AlertTriangle size={17} /> {error}</div>}
      <div className="ace-table-meta"><strong>{total}</strong> matching movements</div>
      <div className="ace-table-wrap">
        <table className="ace-table">
          <thead>
            <tr>
              <th className="ace-col-identity">In-Bond / BOL</th>
              <th className="ace-col-status">Status</th>
              <th className="ace-col-dates">Create / Arrive Date</th>
              <th className="ace-col-filer">QP Filer</th>
              <th className="ace-col-carrier">In-Bond / Manifest Carrier</th>
              <th className="ace-col-route">Route</th>
              <th className="ace-col-exception">Exception</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan="7">Loading ACE movements…</td></tr>}
            {!loading && items.length === 0 && <tr><td colSpan="7">No movements match these filters.</td></tr>}
            {!loading && items.map((item) => (
              <tr key={item.id} onClick={() => openMovement(item.id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") openMovement(item.id); }}>
                <td className="ace-col-identity"><strong>{item.inbond_number}</strong><span>{item.bill_of_lading_number || "—"}</span></td>
                <td className="ace-col-status"><StatusPill movement={item} /></td>
                <td className="ace-col-dates ace-date-pair"><strong>{movementDate(item.create_date)}</strong><span>{movementDate(item.arrival_date)}</span></td>
                <td className="ace-col-filer"><strong>{item.qp_filer?.code || "—"}</strong><span>{item.qp_filer?.name || "—"}</span></td>
                <td className="ace-col-carrier"><strong>{item.inbond_carrier?.code || "—"}</strong><span>{item.manifest_carrier?.code || "—"}</span></td>
                <td className="ace-col-route"><strong>{item.origination_port_name || "—"}</strong><span>{item.destination_port_name || "—"}</span></td>
                <td className="ace-col-exception">{item.review_reason || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <AceReviewDrawer movement={selected} onClose={() => setSelected(null)} onChanged={refreshMovement} />
    </section>
  );
}
