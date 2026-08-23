import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../apiClient";
import { motiveUtilizationHistoryPresentation } from "../motiveUtilizationHistoryFrontend";

const HISTORY_PATH = "/api/v1/motive/fleet/vehicle-utilization-kpi/history?days=30";

function HistoryChart({ presentation }) {
  const { chart } = presentation;
  const titleId = "utilization-history-chart-title";
  const descriptionId = "utilization-history-chart-description";

  return (
    <div className="utilization-history-chart-wrap">
      <svg
        className="utilization-history-chart"
        viewBox={`0 0 ${chart.width} ${chart.height}`}
        role="img"
        aria-labelledby={`${titleId} ${descriptionId}`}
      >
        <title id={titleId}>30-day observed vehicle utilization history</title>
        <desc id={descriptionId}>{presentation.summary}. Missing snapshot dates are shown as gaps.</desc>

        <g className="utilization-history-grid" aria-hidden="true">
          {presentation.yTicks.map((tick) => (
            <g key={tick.value}>
              <line x1={chart.plotLeft} x2={chart.plotRight} y1={tick.y} y2={tick.y} />
              <text x={chart.plotLeft - 10} y={tick.y + 4} textAnchor="end">{tick.value}%</text>
            </g>
          ))}
          {presentation.xAnchors.map((anchor) => (
            <text key={anchor.date} x={anchor.x} y={chart.xLabelY} textAnchor="middle">{anchor.date.slice(5)}</text>
          ))}
        </g>

        <g className="utilization-history-segments" aria-hidden="true">
          {presentation.segments.map((segment, index) => (
            <line
              key={`${segment.x1}-${segment.x2}-${index}`}
              x1={segment.x1}
              y1={segment.y1}
              x2={segment.x2}
              y2={segment.y2}
            />
          ))}
        </g>

        <g className="utilization-history-points">
          {presentation.points.map((point) => point.kind === "available" ? (
            <circle
              key={point.windowEnd}
              cx={point.x}
              cy={point.y}
              r="5"
              tabIndex="0"
              role="img"
              aria-label={point.label}
            >
              <title>{point.label}</title>
            </circle>
          ) : (
            <g
              key={point.windowEnd}
              tabIndex="0"
              role="img"
              aria-label={point.label}
              className="utilization-history-unavailable"
            >
              <line
                x1={point.x}
                x2={point.x}
                y1={chart.unavailableY - 6}
                y2={chart.unavailableY + 6}
              />
              <title>{point.label}</title>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}

export default function MotiveUtilizationHistory({ refreshSequence }) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [requestFailed, setRequestFailed] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadHistory() {
      try {
        setLoading(true);
        setRequestFailed(false);
        const response = await apiClient.get(HISTORY_PATH);
        if (active) setPayload(response);
      } catch (_) {
        if (active) {
          setPayload(null);
          setRequestFailed(true);
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadHistory();
    return () => {
      active = false;
    };
  }, [refreshSequence]);

  const presentation = useMemo(
    () => motiveUtilizationHistoryPresentation(payload, { loading, requestFailed }),
    [payload, loading, requestFailed]
  );

  return (
    <section className="utilization-history-region" aria-labelledby="utilization-history-title">
      <div className="utilization-history-heading">
        <h3 id="utilization-history-title">{presentation.title}</h3>
        {presentation.summary && <p>{presentation.summary}</p>}
      </div>

      {presentation.status === "ready" ? (
        <>
          <HistoryChart presentation={presentation} />
          <p className="utilization-history-latest">{presentation.latestDetail}</p>
          <p className="utilization-history-footer">
            {presentation.range} · Gaps indicate dates with no snapshot.
          </p>
        </>
      ) : (
        <div className="utilization-history-state">
          <p>{presentation.message}</p>
          {presentation.range && <small>{presentation.range}</small>}
        </div>
      )}
    </section>
  );
}

export const motiveUtilizationHistoryPath = HISTORY_PATH;
