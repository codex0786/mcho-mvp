"use client";

import { useState } from "react";

import { timeAgo } from "../lib/api";

export type DamageCounts = { destroyed: number; severe: number; moderate: number; possible: number; unclassified: number };
export type DamageAssessment = {
  id: string; title: string; country_code: string | null; unosat_code: string | null;
  published_on: string | null; imagery_date: string | null; status: "pending" | "mapped" | "catalogue" | "failed";
  status_detail: string | null; on_map: boolean; superseded_by: string | null; counts: DamageCounts | null;
  bbox: [number, number, number, number] | null; hdx_url: string; licence: string; licence_url: string | null;
  summary: string; caveats: string | null;
};
export type DamageOverview = {
  assessments: DamageAssessment[]; cells: GeoJSON.FeatureCollection; totals_on_map: DamageCounts; cell_km: number;
  attribution: string; caveats: string; transformation: string;
  freshness: { refresh_scheduled: boolean; last_successful_refresh_at: string | null; last_attempt: { status: string; error_summary: string | null } | null };
};

// Shared with the map legend: share of structures in a cell that UNOSAT classed as destroyed.
export const DAMAGE_COLOURS = { low: "#f2c14e", mid: "#f08a4b", high: "#c0392b", unclassified: "#b48ead" } as const;

const n = (value: number | null | undefined) => (value ?? 0).toLocaleString("en-GB");

function countsText(c: DamageCounts): string {
  const parts = [
    c.destroyed && `${n(c.destroyed)} destroyed`, c.severe && `${n(c.severe)} severely damaged`,
    c.moderate && `${n(c.moderate)} moderately damaged`, c.possible && `${n(c.possible)} possibly damaged`,
    c.unclassified && `${n(c.unclassified)} damaged or destroyed (class not given)`,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "No damaged structures recorded";
}

function showOnMap(a: DamageAssessment) {
  if (!a.bbox) return;
  const [w, s, e, nn] = a.bbox;
  const span = Math.max(e - w, nn - s);
  const zoom = span > 1 ? 8 : span > 0.3 ? 10 : 12;
  window.dispatchEvent(new CustomEvent("mcho:fly-to", { detail: { longitude: (w + e) / 2, latitude: (s + nn) / 2, zoom } }));
  document.querySelector(".map-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function DamagePanel({ data, message, countryName }: { data: DamageOverview | null; message: string; countryName: string | null }) {
  const [showAll, setShowAll] = useState(false);
  if (!data) return <section className="damage side-card" aria-label="Damage assessments"><h2>UN satellite damage assessments</h2><div className="empty" role="status">{message}</div></section>;
  const mapped = data.assessments.filter((a) => a.on_map);
  const others = data.assessments.filter((a) => !a.on_map);
  const pending = data.assessments.filter((a) => a.status === "pending").length;
  const failed = data.freshness.last_attempt?.status === "failed" ? data.freshness.last_attempt.error_summary : null;
  return (
    <section className="damage side-card" aria-label="Damage assessments">
      <div className="insights-head">
        <h2>UN satellite damage assessments{countryName ? ` · ${countryName}` : ""}</h2>
        <span className="muted">UNOSAT · building damage seen in satellite imagery</span>
      </div>
      {!data.assessments.length && (
        <div className="empty" role="status">
          {data.freshness.refresh_scheduled || data.freshness.last_attempt?.status === "running"
            ? "Fetching the UNOSAT catalogue from HDX for the first time; refresh the page in a minute."
            : `No UNOSAT conflict damage assessments${countryName ? ` for ${countryName}` : ""} on HDX.`}
        </div>
      )}
      {failed && <p className="insights-warning" role="status">Latest update failed: {failed}</p>}
      {pending > 0 && <p className="muted" role="status">{pending} more assessment{pending === 1 ? " is" : "s are"} still being processed; they appear here as they finish.</p>}
      {mapped.length > 0 && (
        <div className="damage-list">
          {mapped.map((a) => (
            <article key={a.id} className="damage-item" aria-label={a.title}>
              <div className="damage-item-head">
                <strong>{a.title}</strong>
                {a.bbox && <button type="button" className="text-button" onClick={() => showOnMap(a)}>Show on map</button>}
              </div>
              <div className="muted">Imagery {a.imagery_date ?? "date not given"}{a.published_on ? ` · published ${a.published_on}` : ""}{a.unosat_code ? ` · ${a.unosat_code}` : ""}</div>
              {a.counts && <p className="damage-counts">{countsText(a.counts)}</p>}
              <details>
                <summary>UNOSAT&apos;s description</summary>
                <p>{a.summary}</p>
                {a.caveats && <p className="muted">{a.caveats}</p>}
              </details>
              <a className="text-link" href={a.hdx_url} target="_blank" rel="noreferrer">Dataset on HDX ({a.licence}) ↗</a>
            </article>
          ))}
        </div>
      )}
      {others.length > 0 && (
        <>
          <button type="button" className="text-button" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Hide" : "Show"} {others.length} older, overlapping or unmapped assessment{others.length === 1 ? "" : "s"}
          </button>
          {showAll && (
            <table className="insights-table damage-table">
              <thead><tr><th>Assessment</th><th>Date</th><th>On map</th></tr></thead>
              <tbody>
                {others.map((a) => (
                  <tr key={a.id}>
                    <td><a className="text-link" href={a.hdx_url} target="_blank" rel="noreferrer">{a.title}</a>{a.counts ? <div className="muted">{countsText(a.counts)}</div> : null}</td>
                    <td>{a.imagery_date ?? a.published_on ?? "—"}</td>
                    <td className="muted">{a.superseded_by ? `Covered by newer: ${a.superseded_by}` : a.status === "pending" ? "Processing" : a.status_detail ?? "Not mapped"}</td>
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
