"use client";

import { useEffect, useRef, useState } from "react";

import { apiUrl, getJsonWithWake } from "../lib/api";
import { THERMAL_COLOURS } from "./RegionalMap";

type Point = {
  date: string; covered: boolean; partial: boolean;
  total: number | null; persistent: number | null; other: number | null; max_frp_mw: number | null;
};
type Trend = { iso_a3: string; name: string; days: number; series: Point[]; persistent_rule: string; coverage_note: string };

// Dry-season burning (savanna and agricultural fires) dominates detections here from
// roughly October to March, so high counts in that period are expected.
const SEASONAL_BURNING = new Set(["SDN", "MRT"]);

const WIDTH = 320;
const HEIGHT = 120;
const BAR_GAP = 2;

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

export default function CountryTrend({ iso3, onClose }: { iso3: string; onClose: () => void }) {
  const [trend, setTrend] = useState<Trend | null>(null);
  const [message, setMessage] = useState("Loading the 3-week trend…");
  const generation = useRef(0);

  useEffect(() => {
    const current = ++generation.current;
    setTrend(null);
    setMessage("Loading the 3-week trend…");
    getJsonWithWake<Trend>(apiUrl(`/thermal/countries/${encodeURIComponent(iso3)}/trend`, { days: 21 }), {
      isCurrent: () => current === generation.current,
      onWaking: () => setMessage("The server is waking up (free hosting can take about a minute). Retrying…"),
    }).then((body) => { if (body) setTrend(body); })
      .catch((err) => { if (current === generation.current) setMessage(`Trend unavailable: ${err instanceof Error ? err.message : "unknown error"}.`); });
    return () => { generation.current += 1; };
  }, [iso3]);

  if (!trend) return <section className="trend" aria-label="Country trend"><div className="empty" role="status">{message}</div></section>;

  const max = Math.max(1, ...trend.series.map((p) => p.total ?? 0));
  const barWidth = WIDTH / trend.series.length - BAR_GAP;
  const covered = trend.series.filter((p) => p.covered && !p.partial);
  const recent = covered.slice(-7).reduce((sum, p) => sum + (p.other ?? 0), 0);
  const earlier = covered.slice(-14, -7).reduce((sum, p) => sum + (p.other ?? 0), 0);
  const comparable = covered.length >= 14;

  return (
    <section className="trend" aria-label={`${trend.name} 3-week trend`}>
      <div className="insights-head">
        <h3>{trend.name}: last 3 weeks</h3>
        <button type="button" className="link-button" onClick={onClose}>Back to all countries</button>
      </div>
      {comparable && (
        <p className="trend-summary">
          Activity (excluding persistent sites): <strong>{recent}</strong> detections in the last 7 full days vs <strong>{earlier}</strong> the week before
          {earlier > 0 ? ` (${recent >= earlier ? "+" : ""}${Math.round(((recent - earlier) / earlier) * 100)}%)` : ""}.
        </p>
      )}
      {SEASONAL_BURNING.has(trend.iso_a3) && (
        <p className="trend-season">
          Seasonal context: October to March is the main dry-season burning period in {trend.name}. Many detections are savanna
          and agricultural fires, so high counts in this period are expected and are not by themselves a sign of conflict.
        </p>
      )}
      <svg className="trend-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT + 18}`} role="img"
        aria-label={`Daily satellite heat detections in ${trend.name} over ${trend.days} days`}>
        <defs>
          <pattern id="no-data" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="4" stroke="#3a4a5e" strokeWidth="2" />
          </pattern>
        </defs>
        {trend.series.map((p, i) => {
          const x = i * (barWidth + BAR_GAP);
          if (!p.covered) {
            return <rect key={p.date} x={x} y={HEIGHT - 12} width={barWidth} height={12} fill="url(#no-data)"><title>{`${shortDate(p.date)}: no data`}</title></rect>;
          }
          const otherHeight = ((p.other ?? 0) / max) * HEIGHT;
          const persistentHeight = ((p.persistent ?? 0) / max) * HEIGHT;
          return (
            <g key={p.date} opacity={p.partial ? 0.55 : 1}>
              <title>{`${shortDate(p.date)}${p.partial ? " (so far today)" : ""}: ${p.other} activity, ${p.persistent} at persistent sites`}</title>
              <rect x={x} y={HEIGHT - persistentHeight} width={barWidth} height={persistentHeight} fill={THERMAL_COLOURS.persistent} />
              <rect x={x} y={HEIGHT - persistentHeight - otherHeight} width={barWidth} height={otherHeight} fill={THERMAL_COLOURS.new} />
            </g>
          );
        })}
        <text x={0} y={HEIGHT + 14} className="trend-axis">{shortDate(trend.series[0].date)}</text>
        <text x={WIDTH} y={HEIGHT + 14} className="trend-axis" textAnchor="end">Today</text>
        <text x={0} y={10} className="trend-axis">max {max}/day</text>
      </svg>
      <div className="trend-legend">
        <span><i style={{ background: THERMAL_COLOURS.new }} />Activity</span>
        <span><i style={{ background: THERMAL_COLOURS.persistent }} />Persistent sites</span>
        <span><i className="trend-legend-nodata" />No data</span>
      </div>
      <details className="insights-method">
        <summary>Daily numbers and notes</summary>
        <table className="insights-table">
          <thead><tr><th>Day (UTC)</th><th>Activity</th><th>Persistent</th></tr></thead>
          <tbody>
            {[...trend.series].reverse().map((p) => (
              <tr key={p.date}>
                <td>{shortDate(p.date)}{p.partial ? " (so far)" : ""}</td>
                <td>{p.covered ? p.other : "no data"}</td>
                <td>{p.covered ? p.persistent : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>{trend.persistent_rule} {trend.coverage_note}</p>
      </details>
    </section>
  );
}
