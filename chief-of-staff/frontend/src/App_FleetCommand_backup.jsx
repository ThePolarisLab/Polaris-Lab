import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API_BASE = "http://127.0.0.1:8000";

const emptyTruck = {
  unit_number: "",
  make: "",
  model: "",
  year: new Date().getFullYear(),
  vin: "",
  plate: "",
  status: "Available",
};

function StatCard({ label, value, hint }) {
  return (
    <section className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </section>
  );
}

function App() {
  const [company, setCompany] = useState(null);
  const [trucks, setTrucks] = useState([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [form, setForm] = useState(emptyTruck);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const [companyResponse, trucksResponse] = await Promise.all([
        fetch(`${API_BASE}/company`),
        fetch(`${API_BASE}/trucks`),
      ]);
      if (!companyResponse.ok || !trucksResponse.ok) {
        throw new Error("Polaris could not load live business data.");
      }
      const [companyData, truckData] = await Promise.all([
        companyResponse.json(),
        trucksResponse.json(),
      ]);
      setCompany(companyData);
      setTrucks(truckData);
    } catch (err) {
      setError(err.message || "Unable to connect to Polaris Engine.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  const counts = useMemo(() => {
    const normalized = trucks.map((truck) => String(truck.status || "").toLowerCase());
    return {
      total: trucks.length,
      available: normalized.filter((status) => status === "available").length,
      onTrip: normalized.filter((status) => status === "on trip" || status === "loaded").length,
      maintenance: normalized.filter((status) => status === "maintenance" || status === "repair").length,
    };
  }, [trucks]);

  const filteredTrucks = useMemo(() => {
    return trucks.filter((truck) => {
      const searchText = [truck.unit_number, truck.make, truck.model, truck.year, truck.plate, truck.status]
        .join(" ")
        .toLowerCase();
      const matchesSearch = searchText.includes(query.toLowerCase());
      const matchesStatus = statusFilter === "All" || truck.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [trucks, query, statusFilter]);

  function updateForm(event) {
    const { name, value } = event.target;
    setForm((current) => ({
      ...current,
      [name]: name === "year" ? Number(value) : value,
    }));
  }

  async function addTruck(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/trucks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Unable to save truck.");
      }
      const createdTruck = await response.json();
      setTrucks((current) => [...current, createdTruck]);
      setForm(emptyTruck);
      setShowForm(false);
    } catch (err) {
      setError(err.message || "Unable to save truck.");
    } finally {
      setSaving(false);
    }
  }

  function statusClass(status) {
    return String(status || "Unknown").toLowerCase().replaceAll(" ", "-");
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Polaris OS · Fleet Command</p>
          <h1>Good Morning, {company?.owner || "Founder"}.</h1>
          <p className="hero-copy">
            {company?.company_name || "Connecting to your company"} · {company?.headquarters || company?.country || "Builder #0001"}
          </p>
        </div>
        <button className="secondary-button" onClick={loadDashboard}>Refresh live data</button>
      </header>

      {error && <div className="alert">{error}</div>}

      <section className="section-heading">
        <div>
          <p className="section-kicker">Fleet health</p>
          <h2>Fleet Command</h2>
          <p>One calm view of the assets that keep your business moving.</p>
        </div>
        <button className="primary-button" onClick={() => setShowForm(true)}>+ Add Truck</button>
      </section>

      <section className="stats-grid">
        <StatCard label="Total Trucks" value={counts.total} hint="Stored in Polaris Memory" />
        <StatCard label="Available" value={counts.available} hint="Ready for assignment" />
        <StatCard label="On Trip" value={counts.onTrip} hint="Currently earning" />
        <StatCard label="Maintenance" value={counts.maintenance} hint="Needs attention" />
      </section>

      <section className="fleet-panel">
        <div className="toolbar">
          <input type="search" placeholder="Search unit, make, model, plate..." value={query} onChange={(event) => setQuery(event.target.value)} />
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option>All</option><option>Available</option><option>On Trip</option><option>Loaded</option><option>Maintenance</option><option>Repair</option>
          </select>
        </div>

        {loading ? (
          <div className="empty-state">Loading live fleet data…</div>
        ) : filteredTrucks.length === 0 ? (
          <div className="empty-state">No trucks match this view. Add a truck to begin Fleet Command.</div>
        ) : (
          <div className="truck-grid">
            {filteredTrucks.map((truck) => (
              <article className="truck-card" key={truck.id}>
                <div className="truck-card-top">
                  <div>
                    <span className="unit-label">Unit {truck.unit_number}</span>
                    <h3>{truck.year} {truck.make} {truck.model}</h3>
                  </div>
                  <span className={`status-badge ${statusClass(truck.status)}`}>{truck.status}</span>
                </div>
                <dl>
                  <div><dt>Plate</dt><dd>{truck.plate || "Not recorded"}</dd></div>
                  <div><dt>VIN</dt><dd>{truck.vin || "Not recorded"}</dd></div>
                  <div><dt>Polaris ID</dt><dd>#{truck.id}</dd></div>
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="insight-card">
        <p className="section-kicker">Polaris insight</p>
        <h2>{counts.available > 0 ? `${counts.available} truck${counts.available === 1 ? "" : "s"} ready for work.` : "No trucks are currently marked Available."}</h2>
        <p>This is the first Fleet Command release. Future releases will connect utilization, maintenance, Motive, revenue, cost per mile, and Builder recommendations.</p>
      </section>

      {showForm && (
        <div className="modal-backdrop" role="presentation">
          <section className="modal" role="dialog" aria-modal="true">
            <div className="modal-header">
              <div><p className="section-kicker">Polaris Memory</p><h2>Add Truck</h2></div>
              <button className="icon-button" onClick={() => setShowForm(false)}>×</button>
            </div>
            <form onSubmit={addTruck}>
              <div className="form-grid">
                <label>Unit number<input required name="unit_number" value={form.unit_number} onChange={updateForm} /></label>
                <label>Status<select name="status" value={form.status} onChange={updateForm}><option>Available</option><option>On Trip</option><option>Loaded</option><option>Maintenance</option><option>Repair</option></select></label>
                <label>Make<input required name="make" value={form.make} onChange={updateForm} /></label>
                <label>Model<input required name="model" value={form.model} onChange={updateForm} /></label>
                <label>Year<input required type="number" min="1980" max="2100" name="year" value={form.year} onChange={updateForm} /></label>
                <label>Plate<input name="plate" value={form.plate} onChange={updateForm} /></label>
                <label className="full-width">VIN<input name="vin" value={form.vin} onChange={updateForm} /></label>
              </div>
              <div className="modal-actions">
                <button type="button" className="secondary-button" onClick={() => setShowForm(false)}>Cancel</button>
                <button className="primary-button" disabled={saving}>{saving ? "Saving…" : "Save Truck"}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
