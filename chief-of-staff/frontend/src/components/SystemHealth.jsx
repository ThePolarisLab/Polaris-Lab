import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, Gauge, RefreshCw, ShieldCheck } from "lucide-react";

import { apiClient } from "../apiClient";
import { motiveSystemHealth } from "../motiveFrontend";
import "./ExecutiveViews.css";

const dateText = (value) => {
  if (!value) return "Never";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Unavailable" : parsed.toLocaleString("en-CA");
};

function connectorState(status, loading = false) {
  if (loading || !status) return "Checking";
  if (["healthy", "connected", "success"].includes(status)) return "Healthy";
  if (["not_configured", "configured_unverified", "connected_unverified", "not_started", "checking", "running"].includes(status)) return "Checking";
  return "Degraded";
}

function HealthRow({ name, status, detail }) {
  const Icon = status === "Healthy" ? CheckCircle2 : status === "Checking" ? Database : AlertTriangle;
  return (
    <article>
      <Icon size={19} />
      <div><h3>{name}</h3><p>{detail}</p></div>
      <span className={`health-status ${status.toLowerCase().replace(" ", "-")}`}>{status}</span>
    </article>
  );
}

export default function SystemHealth() {
  const [runtime, setRuntime] = useState(null);
  const [quickBooks, setQuickBooks] = useState(null);
  const [outlook, setOutlook] = useState(null);
  const [motive, setMotive] = useState(null);
  const [torqueAI, setTorqueAI] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const results = await Promise.allSettled([
      apiClient.get("/api/v1/system/health"),
      apiClient.get("/api/v1/connectors/quickbooks"),
      apiClient.get("/api/v1/outlook/status"),
      apiClient.get("/api/v1/motive/status"),
      apiClient.get("/api/v1/torqueai/status"),
    ]);

    const [runtimeResult, quickBooksResult, outlookResult, motiveResult, torqueResult] = results;
    setRuntime(runtimeResult.status === "fulfilled" ? runtimeResult.value : { status: "degraded", checks: {} });
    setQuickBooks(quickBooksResult.status === "fulfilled" ? quickBooksResult.value : { status: "degraded", message: "QuickBooks status unavailable.", details: {} });
    setOutlook(outlookResult.status === "fulfilled" ? outlookResult.value : { health: { status: "degraded", message: "Outlook status unavailable." }, status: {} });
    setMotive(motiveResult.status === "fulfilled" ? motiveResult.value : { health: { status: "degraded", message: "Motive status unavailable." }, status: { connection_status: "failed" } });
    setTorqueAI(torqueResult.status === "fulfilled" ? torqueResult.value : { health: { status: "degraded", message: "TorqueAI durable status unavailable." }, status: {} });

    if (results.some((result) => result.status === "rejected")) {
      setError("One or more passive health reads are unavailable. No provider verification was triggered.");
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const runtimeStatus = loading ? "Checking" : runtime?.status === "ok" ? "Healthy" : "Degraded";
  const qboStatus = connectorState(quickBooks?.status, loading);
  const outlookStatus = connectorState(outlook?.health?.status, loading);
  const motiveHealth = motiveSystemHealth(motive, loading);
  const motiveStatus = loading ? "Checking" : motiveHealth.status;
  const torqueStatus = connectorState(torqueAI?.health?.status, loading);

  const qboDetails = quickBooks?.details || {};
  const outlookDetails = outlook?.status || {};
  const motiveDetails = motive?.status || {};
  const torqueDetails = torqueAI?.status || {};

  const checks = [
    ["Frontend workspace", "Healthy", "This Executive Workspace is loaded and authenticated."],
    ["Backend API & database", runtimeStatus, runtimeStatus === "Healthy" ? `API ready · database ${runtime?.checks?.database || "connected"} · checked ${dateText(runtime?.checked_at)}` : "Backend or database readiness is degraded."],
    ["QuickBooks connector", qboStatus, `${quickBooks?.message || "QuickBooks passive status."} Last successful sync: ${dateText(qboDetails.last_successful_sync_time)}.`],
    ["Outlook connector", outlookStatus, `${outlook?.health?.message || "Outlook passive status."} Last successful sync: ${dateText(outlookDetails.last_successful_sync_time)}.`],
    ["Motive connector", motiveStatus, `${motiveHealth.detail} Last vehicle sync: ${dateText(motiveDetails.last_vehicle_sync_at)} · last user sync: ${dateText(motiveDetails.last_user_sync_at)}.`],
    ["TorqueAI dispatch ingestion", torqueStatus, `${torqueAI?.health?.message || "TorqueAI durable status."} Last successful ingestion: ${dateText(torqueDetails.last_successful_completed_at)} · records stored: ${torqueDetails.records_stored ?? 0}.`],
  ];

  return (
    <section className="executive-view" aria-labelledby="system-health-title">
      <header className="executive-view-header">
        <div><p>MISSION 003 · SYSTEM</p><h1 id="system-health-title">System health</h1><span>Passive operational readiness from Polaris-owned state.</span></div>
        <button className="view-action" type="button" onClick={load} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} />{loading ? "Checking..." : "Refresh"}</button>
      </header>

      <div className="governance-banner"><ShieldCheck size={19} aria-hidden="true" /><span>Status reads do not verify or synchronize providers. Live provider access occurs only through explicit governed Verify or Sync actions.</span></div>
      {error && <div className="dashboard-error"><AlertTriangle size={18} />{error}</div>}

      <div className="health-summary"><Gauge size={25}/><div><strong>{runtimeStatus === "Healthy" ? "Runtime ready" : runtimeStatus === "Checking" ? "Checking runtime" : "Runtime degraded"}</strong><span>Connector readiness and durable ingestion evidence are shown below.</span></div></div>
      <div className="health-list">{checks.map(([name, status, detail]) => <HealthRow key={name} name={name} status={status} detail={detail} />)}</div>
    </section>
  );
}
