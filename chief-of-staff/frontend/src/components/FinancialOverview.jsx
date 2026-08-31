import { useEffect, useState } from "react";
import { AlertTriangle, Database, ShieldCheck } from "lucide-react";

import { apiClient } from "../apiClient";
import { moneyExact } from "../formatters";
import "./FinancialOverview.css";

const FINANCIAL_METRICS = [
  { key: "revenue", label: "Revenue" },
  { key: "expenses", label: "Total expenses" },
  { key: "gross_profit", label: "Gross profit" },
  { key: "net_income", label: "Net income" },
  { key: "cash", label: "Cash position" },
  { key: "accounts_receivable", label: "Accounts receivable" },
  { key: "accounts_payable", label: "Accounts payable" },
];

function dateText(value) {
  if (!value) return "Never";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Unavailable" : parsed.toLocaleString("en-CA");
}

function metricSource(metadata) {
  if (!metadata) return "QuickBooks snapshot";
  const report = metadata.report_name === "ProfitAndLoss" ? "Profit & Loss" : metadata.report_name === "BalanceSheet" ? "Balance Sheet" : metadata.report_name;
  const label = metadata.report_label;
  return [report, label].filter(Boolean).join(" · ") || "QuickBooks snapshot";
}

function metricIsUnavailable(value) {
  return value === null || value === undefined || value === "";
}

function metricValue(key, value, currency) {
  if (key === "gross_profit" && metricIsUnavailable(value)) return "Unavailable";
  return moneyExact(value, currency);
}

function metricProvenance(key, value, metadata) {
  if (key === "gross_profit" && metricIsUnavailable(value)) return "Not provided by QuickBooks API";
  return metricSource(metadata);
}

export default function FinancialOverview() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError("");

    apiClient.get("/api/v1/qbo/executive-summary")
      .then((payload) => { if (mounted) setSummary(payload); })
      .catch((requestError) => {
        if (!mounted) return;
        setSummary(null);
        setError(requestError.message || "Unable to load the stored QuickBooks financial snapshot.");
      })
      .finally(() => { if (mounted) setLoading(false); });

    return () => { mounted = false; };
  }, []);

  const metrics = summary?.metrics;
  const metadata = summary?.metrics_metadata ?? {};

  return (
    <section className="financial-overview" aria-labelledby="financial-overview-title">
      <header className="financial-overview-header">
        <div>
          <p>QUICKBOOKS · FINANCIAL SYSTEM OF RECORD</p>
          <h1 id="financial-overview-title">Financial overview</h1>
          <span>Read-only executive totals from the latest QuickBooks snapshots stored by Polaris.</span>
        </div>
        <a className="financial-manage-link" href="#executive/connectors">Connector status</a>
      </header>

      <div className="financial-governance-banner">
        <ShieldCheck size={18} aria-hidden="true" />
        <span>This page reads Polaris-owned snapshots only. It does not call QuickBooks or trigger synchronization.</span>
      </div>

      {error && (
        <div className="financial-state financial-state-error" role="alert">
          <AlertTriangle size={20} aria-hidden="true" />
          <div><strong>Financial overview unavailable</strong><span>{error}</span></div>
        </div>
      )}

      {loading && !error && (
        <div className="financial-state">
          <Database size={20} aria-hidden="true" />
          <div><strong>Loading financial snapshot</strong><span>Reading the latest durable QuickBooks evidence from Polaris.</span></div>
        </div>
      )}

      {!loading && !error && !metrics && (
        <div className="financial-state">
          <Database size={20} aria-hidden="true" />
          <div><strong>No financial snapshot available</strong><span>Use the governed QuickBooks Sync control in Connectors, then return here.</span></div>
        </div>
      )}

      {!loading && !error && metrics && (
        <>
          <div className="financial-meta-grid" aria-label="Financial snapshot metadata">
            <div><span>Period</span><strong>{summary.period?.start || "Start"} → {summary.period?.end || "Current"}</strong></div>
            <div><span>Accounting basis</span><strong>{summary.period?.basis || "Unavailable"}</strong></div>
            <div><span>Currency</span><strong>{summary.currency || "CAD"}</strong></div>
            <div><span>Last synchronized</span><strong>{dateText(summary.last_sync)}</strong></div>
          </div>

          <div className="financial-kpi-grid">
            {FINANCIAL_METRICS.map(({ key, label }) => (
              <article className="financial-kpi-card" key={key}>
                <span>{label}</span>
                <strong>{metricValue(key, metrics[key], summary.currency)}</strong>
                <small>{metricProvenance(key, metrics[key], metadata[key])}</small>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
