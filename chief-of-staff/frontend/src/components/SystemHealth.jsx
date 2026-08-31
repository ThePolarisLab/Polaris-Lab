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

const ageText = (value) => {
  if (!value) return "no successful data yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "age unavailable";
  const minutes = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 60000));
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
};

const labelText = (value) => String(value || "unknown").replaceAll("_", " ");

function connectorState(status, loading = false) {
  if (loading || !status) return "Checking";
  if (["healthy", "connected", "success"].includes(status)) return "Healthy";
  if (["not_configured", "configured_unverified", "connected_unverified", "not_started", "checking", "running"].includes(status)) return "Checking";
  return "Degraded";
}

function freshnessState(status, loading = false) {
  if (loading || !status) return "Checking";
  if (status === "current") return "Healthy";
  if (["failed", "stale"].includes(status)) return "Degraded";
  return "Checking";
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

function quickBooksRecovery(status, details) {
  if (details?.reauthorization_required || status === "reauthorization_required") return "Reconnect QuickBooks before the next Verify or Sync action.";
  if (status === "company_mismatch") return "Run Verify and resolve the company-identity mismatch before synchronization.";
  if (status && status !== "healthy") return "Use Verify first; run Sync only after authorization and company identity are healthy.";
  return "Manual cadence: run Sync when a newer financial snapshot is required.";
}

function outlookRecovery(status, details) {
  if (details?.reauthorization_required || status === "reauthorization_required") return "Reconnect Outlook before the next synchronization.";
  if (status && status !== "healthy") return "Confirm mailbox authorization, then use the governed Sync action.";
  return "Manual cadence: run Sync when newer mailbox evidence is required.";
}

function motiveRecovery(status, details) {
  if (details?.authorization_required || status === "authorization_required" || status === "not_configured") return "Administrator-managed Motive Company API Key configuration requires attention.";
  if (details?.last_vehicle_sync_status && details.last_vehicle_sync_status !== "success") return "Verify Motive, then rerun only the vehicle sync if the failure remains relevant.";
  if (details?.last_user_sync_status && details.last_user_sync_status !== "success") return "Verify Motive, then rerun only the user sync if the failure remains relevant.";
  return "Vehicle and user ingestion are manual/operator-managed; no stale-data SLA is imposed here.";
}

export default function SystemHealth() {
  const [runtime, setRuntime] = useState(null);
  const [quickBooks, setQuickBooks] = useState(null);
  const [outlook, setOutlook] = useState(null);
  const [motive, setMotive] = useState(null);
  const [torqueAI, setTorqueAI] = useState(null);
  const [freshness, setFreshness] = useState(null);
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
      apiClient.get("/api/v1/system/connector-freshness"),
    ]);

    const [runtimeResult, quickBooksResult, outlookResult, motiveResult, torqueResult, freshnessResult] = results;
    setRuntime(runtimeResult.status === "fulfilled" ? runtimeResult.value : { status: "degraded", checks: {} });
    setQuickBooks(quickBooksResult.status === "fulfilled" ? quickBooksResult.value : { status: "degraded", message: "QuickBooks status unavailable.", details: {} });
    setOutlook(outlookResult.status === "fulfilled" ? outlookResult.value : { health: { status: "degraded", message: "Outlook status unavailable." }, status: {} });
    setMotive(motiveResult.status === "fulfilled" ? motiveResult.value : { health: { status: "degraded", message: "Motive status unavailable." }, status: { connection_status: "failed" } });
    setTorqueAI(torqueResult.status === "fulfilled" ? torqueResult.value : { health: { status: "degraded", message: "TorqueAI durable status unavailable." }, status: {} });
    setFreshness(freshnessResult.status === "fulfilled" ? freshnessResult.value : { torqueai: {}, motive_vehicle_utilization: {} });

    if (results.some((result) => result.status === "rejected")) {
      setError("One or more passive health reads are unavailable. No provider verification or synchronization was triggered.");
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const runtimeStatus = loading ? "Checking" : runtime?.status === "ok" ? "Healthy" : "Degraded";
  const qboStatus = connectorState(quickBooks?.status, loading);
  const outlookStatus = connectorState(outlook?.health?.status, loading);
  const motiveHealth = motiveSystemHealth(motive, loading);
  const motiveStatus = loading ? "Checking" : motiveHealth.status;

  const qboDetails = quickBooks?.details || {};
  const outlookDetails = outlook?.status || {};
  const motiveDetails = motive?.status || {};
  const torqueDetails = torqueAI?.status || {};
  const torqueFreshness = freshness?.torqueai || {};
  const motiveUtilizationFreshness = freshness?.motive_vehicle_utilization || {};

  const torqueStatus = freshnessState(torqueFreshness.freshness_status, loading);
  const motiveUtilizationStatus = freshnessState(motiveUtilizationFreshness.freshness_status, loading);

  const qboIssue = qboStatus === "Degraded" ? qboDetails.last_safe_error_summary : null;
  const outlookIssue = outlookStatus === "Degraded" ? outlookDetails.last_safe_error_summary : null;
  const motiveIssue = motiveStatus === "Degraded" ? motiveDetails.last_error_message_sanitized : null;

  const checks = [
    ["Frontend workspace", "Healthy", "This Executive Workspace is loaded and authenticated."],
    ["Backend API & database", runtimeStatus, runtimeStatus === "Healthy" ? `API ready · database ${runtime?.checks?.database || "connected"} · checked ${dateText(runtime?.checked_at)}` : "Backend or database readiness is degraded."],
    ["QuickBooks connector", qboStatus, `Cadence: manual/operator · last successful sync ${dateText(qboDetails.last_successful_sync_time)} (${ageText(qboDetails.last_successful_sync_time)}).${qboIssue ? ` Current issue: ${qboIssue}.` : ""} Recovery: ${quickBooksRecovery(quickBooks?.status, qboDetails)}`],
    ["Outlook connector", outlookStatus, `Cadence: manual/operator · last successful sync ${dateText(outlookDetails.last_successful_sync_time)} (${ageText(outlookDetails.last_successful_sync_time)}).${outlookIssue ? ` Current issue: ${outlookIssue}.` : ""} Recovery: ${outlookRecovery(outlook?.health?.status, outlookDetails)}`],
    ["Motive vehicle & user ingestion", motiveStatus, `Cadence: manual/operator · vehicle ${dateText(motiveDetails.last_vehicle_sync_at)} (${ageText(motiveDetails.last_vehicle_sync_at)}) · user ${dateText(motiveDetails.last_user_sync_at)} (${ageText(motiveDetails.last_user_sync_at)}).${motiveIssue ? ` Current issue: ${motiveIssue}.` : ""} Recovery: ${motiveRecovery(motiveDetails.connection_status, motiveDetails)}`],
    ["TorqueAI dispatch ingestion", torqueStatus, `Freshness: ${labelText(torqueFreshness.freshness_status)} · cadence: hourly scheduled · last scheduled success ${dateText(torqueFreshness.last_successful_at)} (${ageText(torqueFreshness.last_successful_at)}) · latest run ${labelText(torqueFreshness.latest_run_status || torqueDetails.latest_run_status)}${torqueFreshness.latest_run_error_code ? ` · error ${torqueFreshness.latest_run_error_code}` : ""} · records stored ${torqueDetails.records_stored ?? 0}. Recovery: ${torqueFreshness.recovery || "Freshness evidence unavailable; inspect passive status before intervention."}`],
    ["Motive vehicle utilization scheduler", motiveUtilizationStatus, `Freshness: ${labelText(motiveUtilizationFreshness.freshness_status)} · daily window ${motiveUtilizationFreshness.schedule_window_local || "06:00-13:59"} ${motiveUtilizationFreshness.request_timezone || "America/Chicago"} · completed through ${motiveUtilizationFreshness.completed_through || "none"} · expected ${motiveUtilizationFreshness.expected_completed_through || "unknown"} · latest attempt ${labelText(motiveUtilizationFreshness.latest_attempt_status)}${motiveUtilizationFreshness.latest_attempt_error_code ? ` · error ${motiveUtilizationFreshness.latest_attempt_error_code}` : ""}. Recovery: ${motiveUtilizationFreshness.recovery || "Freshness evidence unavailable; inspect passive status before intervention."}`],
  ];

  return (
    <section className="executive-view" aria-labelledby="system-health-title">
      <header className="executive-view-header">
        <div><p>MISSION 003 · SYSTEM</p><h1 id="system-health-title">System health</h1><span>Passive operational readiness, freshness, failures, and recovery guidance from Polaris-owned state.</span></div>
        <button className="view-action" type="button" onClick={load} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} />{loading ? "Checking..." : "Refresh"}</button>
      </header>

      <div className="governance-banner"><ShieldCheck size={19} aria-hidden="true" /><span>Status reads do not verify or synchronize providers. Scheduled freshness uses governed Polaris scheduler contracts, not provider SLAs; manual connectors show age without inventing a stale threshold.</span></div>
      {error && <div className="dashboard-error"><AlertTriangle size={18} />{error}</div>}

      <div className="health-summary"><Gauge size={25}/><div><strong>{runtimeStatus === "Healthy" ? "Runtime ready" : runtimeStatus === "Checking" ? "Checking runtime" : "Runtime degraded"}</strong><span>Connector readiness and durable ingestion freshness are shown below.</span></div></div>
      <div className="health-list">{checks.map(([name, status, detail]) => <HealthRow key={name} name={name} status={status} detail={detail} />)}</div>
    </section>
  );
}
