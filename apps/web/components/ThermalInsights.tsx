"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiUrl, getJsonWithWake, timeAgo, utcTime } from "../lib/api";
import type { FlyToDetail } from "./RegionalMap";

type Country = {
  iso_a3: string; name: string; active_detections: number; new_detections: number; persistent_detections: number;
  baseline_daily_average: number; ratio_to_baseline: number | null; max_frp_mw: number | null; elevated: boolean;
};
type Cluster = {
  country: string; detections: number; longitude: number; latitude: number; max_frp_mw: number | null;
  first_seen: string; last_seen: string; satellites: number;
};
type Insights = {
  window_hours: number; latest_detection_at: string | null; baseline_days_available: number;
  totals: { active_detections: number; new_detections: number; persistent_detections: number; elevated_countries: number };
  countries: Country[]; new_activity_clusters: Cluster[];
  method: { cell_degrees: number; cluster_degrees: number; baseline_days: number; persistent_min_days: number; elevated_rule: string };
  caveats: string; source: { name: string; url: string; attribution: string };
  freshness: {
    configured: boolean; refresh_scheduled: boolean; refresh_running: boolean; last_successful_refresh_at: string | null;
    last_attempt: { status: string; started_at: string; error_summary: string | null } | null;
  };
};

const RELOAD_MS = 10 * 60_000;
const WARMING_RELOAD_MS = 30_000;

function flyTo(detail: FlyToDetail) {
  window.dispatchEvent(new CustomEvent<FlyToDetail>("mcho:fly-to", { detail }));
  document.querySelector(".map-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

type Props = { hours: number; country: string | null; onSelectCountry: (iso3: string) => void };

export default function ThermalInsights({ hours, country, onSelectCountry }: Props) {
  const [data, setData] = useState<Insights | null>(null);
  const [message, setMessage] = useState("Retrieving satellite insights…");
  const generation = useRef(0);

  const load = useCallback(async () => {
    const current = ++generation.current;
    try {
      const body = await getJsonWithWake<Insights>(apiUrl("/thermal/insights", { hours, country: country ?? undefined }), {
        isCurrent: () => current === generation.current,
        onWaking: () => setMessage("The server is waking up (free hosting can take about a minute). Retrying…"),
      });
      if (!body) return;
      setData(body);
      setMessage("");
    } catch (err) {
      if (current === generation.current) setMessage(`Satellite insights unavailable: ${err instanceof Error ? err.message : "unknown error"}.`);
    }
  }, [hours, country]);

  const warming = Boolean(data && data.freshness.configured && !data.latest_detection_at
    && (data.freshness.refresh_scheduled || data.freshness.refresh_running || data.freshness.last_attempt?.status === "running"));

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), warming ? WARMING_RELOAD_MS : RELOAD_MS);
    return () => { clearInterval(timer); generation.current += 1; };
  }, [load, warming]);

  if (!data) return <section className="insights" aria-label="Satellite insights"><h2>Satellite insights</h2><div className="empty" role="status">{message}</div></section>;

  const { freshness, totals } = data;
  const elevated = data.countries.filter((c) => c.elevated);
  const activeCountries = data.countries.filter((c) => c.active_detections > 0 || c.persistent_detections > 0).slice(0, 10);
  const failed = freshness.last_attempt?.status === "failed" ? freshness.last_attempt.error_summary : null;

  return (
    <section className="insights" aria-label="Satellite insights">
      <div className="insights-head">
        <h2>Satellite insights</h2>
        <span className="muted">Last {data.window_hours} h · NASA FIRMS</span>
      </div>

      {!freshness.configured && (
        <div className="empty" role="status">The NASA FIRMS satellite feed is not configured on the server yet, so there are no detections to analyse.</div>
      )}
      {freshness.configured && !data.latest_detection_at && (
        <div className="empty" role="status">
          {warming ? "Downloading the first 10 days of satellite detections. This takes about a minute; the panel updates automatically."
            : "No satellite detections stored yet."}
        </div>
      )}
      {failed && <p className="insights-warning" role="status">Latest satellite download failed: {failed}</p>}

      {data.latest_detection_at && (
        <>
          <p className="insights-fresh" role="status">
            Latest satellite pass {timeAgo(data.latest_detection_at)} ({utcTime(data.latest_detection_at)}) · data checked {timeAgo(freshness.last_successful_refresh_at)}
          </p>
          <div className="insights-totals">
            <div><strong>{totals.active_detections}</strong><span>active detections</span></div>
            <div><strong>{totals.new_detections}</strong><span>at new locations</span></div>
            <div><strong>{totals.elevated_countries}</strong><span>countries above normal</span></div>
          </div>
          {data.baseline_days_available < data.method.baseline_days && (
            <p className="muted">Baseline still building: {data.baseline_days_available} of {data.method.baseline_days} days of history, so comparisons are provisional.</p>
          )}

          <h3>Above normal</h3>
          {elevated.length === 0 ? <p className="muted">No country is above its recent baseline.</p> : (
            <ul className="insights-list">
              {elevated.map((c) => (
                <li key={c.iso_a3}>
                  <button type="button" className="link-button" onClick={() => onSelectCountry(c.iso_a3)}><strong>{c.name}</strong></button>
                  : {c.active_detections} detections
                  {c.ratio_to_baseline ? ` (${c.ratio_to_baseline}× the 7-day daily average of ${c.baseline_daily_average})` : " (none in the previous 7 days)"}
                </li>
              ))}
            </ul>
          )}

          <h3>New activity clusters{country ? ` in ${data.countries.find((c) => c.iso_a3 === country)?.name ?? country}` : ""}</h3>
          {data.new_activity_clusters.length === 0 ? <p className="muted">No clusters of heat at previously quiet locations.</p> : (
            <ul className="insights-list">
              {data.new_activity_clusters.map((c) => (
                <li key={`${c.longitude},${c.latitude}`}>
                  <button type="button" className="cluster-button" onClick={() => flyTo({ longitude: c.longitude, latitude: c.latitude, zoom: 10 })}>
                    <strong>{c.country}</strong> · {c.detections} detections
                    <span>near {c.latitude.toFixed(2)}, {c.longitude.toFixed(2)} · last {timeAgo(c.last_seen)}{c.max_frp_mw ? ` · peak ${c.max_frp_mw.toFixed(0)} MW` : ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <h3>By country</h3>
          {activeCountries.length === 0 ? <p className="muted">No detections in the last {data.window_hours} hours.</p> : (
            <table className="insights-table">
              <thead><tr><th>Country</th><th title="Non-persistent detections">Active</th><th title="At locations quiet for 7 days">New</th><th title="Daily average over the previous 7 days">7-day avg</th></tr></thead>
              <tbody>
                {activeCountries.map((c) => (
                  <tr key={c.iso_a3} className={c.elevated ? "elevated" : undefined}>
                    <td><button type="button" className="link-button" onClick={() => onSelectCountry(c.iso_a3)}>{c.name}</button></td><td>{c.active_detections}</td><td>{c.new_detections}</td><td>{c.baseline_daily_average}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <details className="insights-method">
        <summary>How this is calculated</summary>
        <p>{data.caveats}</p>
        <p>
          Detections are grouped into ~{Math.round(data.method.cell_degrees * 111)} km cells. A cell with heat on at least {data.method.persistent_min_days} of
          the previous {data.method.baseline_days} days is a <em>persistent site</em> (usually gas flares or industry) and is left out of the activity counts.
          A cell with no heat in those {data.method.baseline_days} days is <em>new activity</em>. A country is <em>above normal</em> with {data.method.elevated_rule}.
          Clusters group new activity into ~{Math.round(data.method.cluster_degrees * 111)} km areas.
        </p>
        <p>Source: <a className="text-link" href={data.source.url} target="_blank" rel="noreferrer">{data.source.attribution}</a>.</p>
      </details>
    </section>
  );
}
