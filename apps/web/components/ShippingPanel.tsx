"use client";

import { timeAgo } from "../lib/api";

export type MaritimeArea = {
  id: string; name: string; country_code: string | null; longitude: number; latitude: number;
  avg_7d: number | null; avg_7d_last_year: number | null; change_vs_last_year_pct: number | null;
  series: { day: string; value: number | null }[];
  tankers_avg_7d?: number | null; capacity_dwt_avg_7d?: number | null;
  import_tonnes_7d?: number | null; export_tonnes_7d?: number | null;
};
export type MaritimeOverview = {
  latest_day: string | null; chokepoints: MaritimeArea[]; ports: MaritimeArea[];
  attribution: string; caveats: string; transformation: string; country: string | null;
  freshness: { refresh_scheduled: boolean; last_successful_refresh_at: string | null; last_attempt: { status: string; error_summary: string | null } | null };
};

export function changeColour(change: number | null): string {
  if (change === null) return "#c9d4e2";
  if (change <= -25) return "#ff6b6b";
  if (change >= 25) return "#5dd39e";
  return "#c9d4e2";
}

function changeText(change: number | null): string {
  if (change === null) return "no comparison";
  return `${change > 0 ? "+" : ""}${change}% vs last year`;
}

function Sparkline({ series, label }: { series: MaritimeArea["series"]; label: string }) {
  const width = 160;
  const height = 36;
  const values = series.map((p) => p.value).filter((v): v is number => v !== null);
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const step = width / (series.length - 1);
  // Break the line at missing days instead of drawing through them.
  const segments: string[] = [];
  let current = "";
  series.forEach((p, i) => {
    if (p.value === null) { if (current) segments.push(current); current = ""; return; }
    const point = `${(i * step).toFixed(1)},${(height - (p.value / max) * (height - 2) - 1).toFixed(1)}`;
    current = current ? `${current} L${point}` : `M${point}`;
  });
  if (current) segments.push(current);
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      {segments.map((d) => <path key={d} d={d} fill="none" stroke="#7fd3ff" strokeWidth="1.5" />)}
    </svg>
  );
}

function kilotonnes(value: number | null | undefined): string {
  return value == null ? "—" : `${Math.round(value / 1000).toLocaleString("en-GB")} kt`;
}

export default function ShippingPanel({ data, message, countryName }: { data: MaritimeOverview | null; message: string; countryName: string | null }) {
  if (!data) return <section className="shipping side-card" aria-label="Shipping"><h2>Shipping through the region</h2><div className="empty" role="status">{message}</div></section>;
  const failed = data.freshness.last_attempt?.status === "failed" ? data.freshness.last_attempt.error_summary : null;
  return (
    <section className="shipping side-card" aria-label="Shipping">
      <div className="insights-head">
        <h2>Shipping through the region</h2>
        <span className="muted">IMF PortWatch · daily, AIS-based{data.latest_day ? ` · latest day ${data.latest_day}` : ""}</span>
      </div>
      {!data.latest_day && (
        <div className="empty" role="status">
          {data.freshness.refresh_scheduled || data.freshness.last_attempt?.status === "running"
            ? "Downloading shipping data from IMF PortWatch for the first time. This takes about a minute; refresh the page shortly."
            : "No shipping data stored yet."}
        </div>
      )}
      {failed && <p className="insights-warning" role="status">Latest shipping download failed: {failed}</p>}
      {data.latest_day && (
        <>
          <h3>Chokepoints · ships per day, last 7 days</h3>
          <div className="chokepoints">
            {data.chokepoints.map((c) => (
              <article key={c.id} className="chokepoint" aria-label={c.name}>
                <div className="chokepoint-head"><strong>{c.name}</strong>
                  <span className="change" style={{ color: changeColour(c.change_vs_last_year_pct) }}>{changeText(c.change_vs_last_year_pct)}</span>
                </div>
                <div className="chokepoint-value">{c.avg_7d ?? "—"}<small> /day</small></div>
                <div className="muted">
                  {c.avg_7d_last_year != null ? `Same days last year: ${c.avg_7d_last_year}/day` : "Last year: not available"}
                  {c.tankers_avg_7d != null ? ` · tankers ${c.tankers_avg_7d}/day` : ""}
                </div>
                <Sparkline series={c.series} label={`${c.name}: daily transits over 90 days`} />
              </article>
            ))}
          </div>
          <h3>Ports{countryName ? ` in ${countryName}` : " (busiest in the region)"} · calls per day, last 7 days</h3>
          {data.ports.length === 0 ? <p className="muted">PortWatch covers no ports{countryName ? ` in ${countryName}` : ""}.</p> : (
            <table className="insights-table ports-table">
              <thead><tr><th>Port</th><th>Calls/day</th><th>vs last yr</th><th>Imports 7d</th><th>Exports 7d</th></tr></thead>
              <tbody>
                {data.ports.map((p) => (
                  <tr key={p.id}>
                    <td>{p.name}{!countryName && p.country_code ? <span className="muted"> · {p.country_code}</span> : null}</td>
                    <td>{p.avg_7d ?? "—"}</td>
                    <td style={{ color: changeColour(p.change_vs_last_year_pct) }}>{p.change_vs_last_year_pct == null ? "—" : `${p.change_vs_last_year_pct > 0 ? "+" : ""}${p.change_vs_last_year_pct}%`}</td>
                    <td>{kilotonnes(p.import_tonnes_7d)}</td>
                    <td>{kilotonnes(p.export_tonnes_7d)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      <p className="imagery-note">
        {data.caveats} {data.transformation} {data.attribution}.
        {data.freshness.last_successful_refresh_at ? ` Checked ${timeAgo(data.freshness.last_successful_refresh_at)}.` : ""}
      </p>
    </section>
  );
}
