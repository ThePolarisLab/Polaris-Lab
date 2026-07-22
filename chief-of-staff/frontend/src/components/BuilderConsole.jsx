import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Clock3,
  Code2,
  Database,
  GitCommitHorizontal,
  RefreshCw,
  Server,
  ShieldCheck,
} from "lucide-react";
import "./BuilderConsole.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const REFRESH_INTERVAL_MS = 30_000;

function formatUptime(totalSeconds = 0) {
  const seconds = Math.max(0, Number(totalSeconds) || 0);
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);

  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m ${seconds % 60}s`;
}

function formatTimestamp(value) {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

async function readJson(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message = payload.detail || payload.message || `Request failed (${response.status})`;
    throw new Error(message);
  }

  return payload;
}

function StatusCard({ icon: Icon, label, value, detail, tone = "neutral" }) {
  return (
    <article className={`builder-status-card builder-status-${tone}`}>
      <div className="builder-status-icon" aria-hidden="true">
        <Icon size={21} strokeWidth={1.8} />
      </div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        {detail && <small>{detail}</small>}
      </div>
    </article>
  );
}

export default function BuilderConsole() {
  const [health, setHealth] = useState(null);
  const [info, setInfo] = useState(null);
  const [version, setVersion] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  const loadRuntime = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setError("");

    try {
      const [healthData, infoData, versionData] = await Promise.all([
        readJson("/api/v1/system/health"),
        readJson("/api/v1/system/info"),
        readJson("/api/v1/system/version"),
      ]);
      setHealth(healthData);
      setInfo(infoData);
      setVersion(versionData);
      setLastUpdated(new Date());
    } catch (requestError) {
      setError(requestError.message || "Runtime information is unavailable.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRuntime();
    const timer = window.setInterval(
      () => loadRuntime({ silent: true }),
      REFRESH_INTERVAL_MS,
    );
    return () => window.clearInterval(timer);
  }, [loadRuntime]);

  const systemTone = health?.status === "ok" ? "healthy" : "warning";
  const databaseConnected = health?.checks?.database === "connected";
  const commit = version?.git_commit || info?.git_commit || "unknown";
  const shortCommit = commit === "unknown" ? commit : commit.slice(0, 12);

  const cards = useMemo(
    () => [
      {
        icon: Activity,
        label: "System health",
        value: health?.status ?? (loading ? "Checking" : "Unknown"),
        detail: health?.checked_at ? `Checked ${formatTimestamp(health.checked_at)}` : null,
        tone: systemTone,
      },
      {
        icon: Database,
        label: "Database",
        value: health?.checks?.database ?? "Unknown",
        detail: databaseConnected ? "Readiness query passed" : "Requires attention",
        tone: databaseConnected ? "healthy" : "warning",
      },
      {
        icon: Server,
        label: "Environment",
        value: info?.environment ?? "Unknown",
        detail: info?.service ?? "Polaris runtime",
      },
      {
        icon: Code2,
        label: "Version",
        value: version?.version ?? "Unknown",
        detail: "Deployed application version",
      },
      {
        icon: GitCommitHorizontal,
        label: "Git commit",
        value: shortCommit,
        detail: commit === "unknown" ? "Build metadata not supplied" : commit,
      },
      {
        icon: Clock3,
        label: "Uptime",
        value: formatUptime(info?.uptime_seconds),
        detail: info?.started_at ? `Started ${formatTimestamp(info.started_at)}` : null,
      },
    ],
    [commit, databaseConnected, health, info, loading, shortCommit, systemTone, version],
  );

  return (
    <main className="builder-shell">
      <header className="builder-hero">
        <div>
          <p className="builder-eyebrow">POLARIS ENGINEERING</p>
          <h1>Builder Console</h1>
          <p className="builder-lead">
            Live operational visibility for the Polaris application runtime.
          </p>
        </div>
        <button
          className="builder-refresh-button"
          type="button"
          onClick={() => loadRuntime()}
          disabled={loading}
        >
          <RefreshCw size={17} className={loading ? "builder-spin" : ""} />
          {loading ? "Refreshing" : "Refresh status"}
        </button>
      </header>

      <section className={`builder-summary builder-summary-${systemTone}`}>
        <ShieldCheck size={24} />
        <div>
          <strong>
            {health?.status === "ok" ? "All monitored systems operational" : "Runtime requires attention"}
          </strong>
          <p>
            Organization: {info?.organization ?? "unknown"} · API: {health?.checks?.api ?? "unknown"}
          </p>
        </div>
      </section>

      {error && (
        <section className="builder-error" role="alert">
          <strong>Unable to refresh runtime status</strong>
          <p>{error}</p>
        </section>
      )}

      <section className="builder-grid" aria-live="polite" aria-busy={loading}>
        {cards.map((card) => (
          <StatusCard key={card.label} {...card} />
        ))}
      </section>

      <footer className="builder-footer">
        <span>Automatic refresh every 30 seconds</span>
        <span>Last updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : "Not yet"}</span>
      </footer>
    </main>
  );
}
