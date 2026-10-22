"use client";

import { timeAgo } from "../lib/api";

type Heat = { status: string; detections: number | null; nearest_km: number | null; radius_km: number | null; max_frp_mw: number | null; persistent_excluded: number | null };
export type UcdpEvent = {
  id: number; date_start: string; date_end: string; country_code: string; country: string; place: string; adm_1: string | null;
  type: string; type_code: number; dyad: string; conflict: string; side_a: string; side_b: string;
  deaths_best: number; deaths_low: number; deaths_high: number; deaths_civilians: number; code_status: string | null;
  where_prec: number; date_prec: number; longitude: number; latitude: number; heat: Heat;
};
type CountryRow = { country_code: string; country: string; events: number; deaths_best: number; deaths_low: number; deaths_high: number; deaths_civilians: number; by_type: Record<string, number> };
type Front = { country: string; first_day: string; last_day: string; detections: number; latest: { longitude: number; latitude: number };
  ucdp_events: number; ucdp_deaths_best: number; ucdp_latest: string; ucdp_dyad: string; nearest_event_km: number };
export type ConflictOverview = {
  releases: { release: string; month: string; fetched_at: string; events_mena: number }[];
  period: { start: string; end: string; months: string[]; missing_months: string[] } | null;
  totals: { events: number; deaths_best: number; deaths_low: number; deaths_high: number; deaths_civilians: number } | null;
  by_country: CountryRow[]; by_month: { month: string; fetched: boolean; events: number | null; deaths_best: number | null }[];
  top_events: UcdpEvent[]; events_with_heat: UcdpEvent[]; fronts_near_violence: Front[];
  events: GeoJSON.FeatureCollection;
  heat_check: { configured: boolean; checked?: number; with_heat?: number; no_heat?: number; persistent_only?: number; pending?: number; not_checkable?: number; share_with_heat?: number | null };
  attribution: string; citation: string; caveats: string; heat_note: string; transformation: string;
  freshness: { refresh_scheduled: boolean; last_successful_refresh_at: string | null; last_attempt: { status: string; error_summary: string | null } | null };
};

// Shared with the map: UCDP type of violence.
export const VIOLENCE_COLOURS: Record<number, string> = { 1: "#e8496b", 2: "#c77dff", 3: "#ffd166" };
const SHORT_TYPE: Record<number, string> = { 1: "State-based", 2: "Non-state", 3: "Against civilians" };

const n = (value: number) => value.toLocaleString("en-GB");
const monthName = (month: string) => new Date(`${month}-01T00:00:00Z`).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });

function deaths(e: { deaths_best: number; deaths_low: number; deaths_high: number }): string {
  return e.deaths_low === e.deaths_high ? n(e.deaths_best) : `${n(e.deaths_best)} (${n(e.deaths_low)}–${n(e.deaths_high)})`;
}

function flyTo(longitude: number, latitude: number) {
  window.dispatchEvent(new CustomEvent("mcho:fly-to", { detail: { longitude, latitude, zoom: 9 } }));
  document.querySelector(".map-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function heatText(h: Heat): string {
  if (h.status === "heat") return `Satellite heat ${h.nearest_km?.toFixed(1)} km away (${h.detections} detection${h.detections === 1 ? "" : "s"} within ${h.radius_km} km, ±1 day)`;
  if (h.status === "no_heat") return `No satellite heat within ${h.radius_km} km, ±1 day`;
  if (h.status === "persistent_only") return "Only heat from a persistent site (likely flare/industry) nearby";
  if (h.status === "pending") return "Heat cross-check pending";
  return "Place or date too imprecise for a heat cross-check";
}

function EventRow({ e }: { e: UcdpEvent }) {
  return (
    <article className="ucdp-event" aria-label={`${e.place}, ${e.date_start}`}>
      <div className="ucdp-event-head">
        <span className="ucdp-type" style={{ borderColor: VIOLENCE_COLOURS[e.type_code] }}>{SHORT_TYPE[e.type_code] ?? e.type}</span>
        <strong>{e.place}</strong>
        <button type="button" className="text-button" onClick={() => flyTo(e.longitude, e.latitude)}>Map</button>
      </div>
      <div className="muted">
        {e.date_start}{e.date_end !== e.date_start ? ` → ${e.date_end}` : ""} · {e.country} · {e.dyad}
      </div>
      <div>Deaths: <strong>{deaths(e)}</strong>{e.deaths_civilians ? ` · civilians ${n(e.deaths_civilians)}` : ""}
        {e.code_status && e.code_status !== "Clear" ? <span className="muted"> · UCDP flag: {e.code_status}</span> : null}</div>
      <div className={e.heat.status === "heat" ? "ucdp-heat-yes" : "muted"}>{heatText(e.heat)}</div>
    </article>
  );
}

export default function ConflictPanel({ data, message, countryName }: { data: ConflictOverview | null; message: string; countryName: string | null }) {
  if (!data) return <section className="conflict side-card" aria-label="Verified conflict events"><h2>Verified conflict events and deaths</h2><div className="empty" role="status">{message}</div></section>;
  const failed = data.freshness.last_attempt?.status === "failed" ? data.freshness.last_attempt.error_summary : null;
  const hc = data.heat_check;
  return (
    <section className="conflict side-card" aria-label="Verified conflict events">
      <div className="insights-head">
        <h2>Verified conflict events and deaths{countryName ? ` · ${countryName}` : ""}</h2>
        <span className="muted">UCDP Candidate (preliminary, monthly){data.period ? ` · ${data.period.months.map(monthName).join(", ")}` : ""}</span>
      </div>
      {!data.period && (
        <div className="empty" role="status">
          {data.freshness.refresh_scheduled || data.freshness.last_attempt?.status === "running"
            ? "Downloading UCDP's monthly event releases for the first time; refresh the page in a minute."
            : "No UCDP releases downloaded yet."}
        </div>
      )}
      {failed && <p className="insights-warning" role="status">Latest UCDP update failed: {failed}</p>}
      {data.period && data.totals && (
        <>
          {data.period.missing_months.length > 0 && (
            <p className="insights-warning" role="status">Not downloaded: {data.period.missing_months.map(monthName).join(", ")}. Those months are missing, not zero.</p>
          )}
          <div className="conflict-totals">
            <div><span className="chokepoint-value">{n(data.totals.events)}</span><small> events</small></div>
            <div><span className="chokepoint-value">{n(data.totals.deaths_best)}</span><small> deaths (best estimate; range {n(data.totals.deaths_low)}–{n(data.totals.deaths_high)})</small></div>
            <div><span className="chokepoint-value">{n(data.totals.deaths_civilians)}</span><small> civilian deaths</small></div>
          </div>
          <div className="conflict-months" aria-label="By month">
            {data.by_month.map((m) => (
              <span key={m.month}>{monthName(m.month)}: {m.events === null ? "not downloaded" : `${n(m.events)} events, ${n(m.deaths_best ?? 0)} deaths`}</span>
            ))}
          </div>
          {!countryName && data.by_country.length > 0 && (
            <table className="insights-table">
              <thead><tr><th>Country</th><th>Events</th><th>Deaths</th><th>Civilians</th><th>Main type</th></tr></thead>
              <tbody>
                {data.by_country.slice(0, 10).map((c) => {
                  const main = Object.entries(c.by_type).sort((a, b) => b[1] - a[1])[0];
                  return (
                    <tr key={c.country_code}>
                      <td>{c.country}</td><td>{n(c.events)}</td><td>{deaths(c)}</td><td>{n(c.deaths_civilians)}</td>
                      <td className="muted">{main && main[1] > 0 ? main[0] : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          <h3>Heat cross-check</h3>
          {!hc.configured ? <p className="muted">Needs the NASA FIRMS key on the server.</p> : (
            <p>
              {hc.checked ? <><strong>{n(hc.with_heat ?? 0)}</strong> of {n(hc.checked)} precisely located events had satellite heat nearby within a day
                {hc.share_with_heat != null ? ` (${Math.round(hc.share_with_heat * 100)}%)` : ""}.</> : "No events checked yet."}
              {hc.pending ? ` ${n(hc.pending)} still being checked.` : ""}
              {hc.not_checkable ? <span className="muted"> {n(hc.not_checkable)} events have a place or date too imprecise to check.</span> : null}
            </p>
          )}
          {data.events_with_heat.length > 0 && (
            <div className="ucdp-list" aria-label="Events with satellite heat">
              {data.events_with_heat.slice(0, 6).map((e) => <EventRow key={e.id} e={e} />)}
            </div>
          )}

          {data.fronts_near_violence.length > 0 && (
            <>
              <h3>Today&apos;s heat fronts in places with recent verified violence</h3>
              <ul className="fronts-near">
                {data.fronts_near_violence.map((f) => (
                  <li key={`${f.latest.longitude},${f.latest.latitude}`}>
                    <button type="button" className="text-button" onClick={() => flyTo(f.latest.longitude, f.latest.latitude)}>{f.country}, active {f.first_day} → {f.last_day}</button>
                    {" "}<span className="muted">{n(f.detections)} detections · {n(f.ucdp_events)} UCDP event{f.ucdp_events === 1 ? "" : "s"} within 25 km in the last 180 days ({n(f.ucdp_deaths_best)} deaths, latest {f.ucdp_latest}, mostly {f.ucdp_dyad})</span>
                  </li>
                ))}
              </ul>
              <p className="muted">Context, not cause: UCDP data runs about 3–7 weeks behind the satellites.</p>
            </>
          )}

          {data.top_events.length > 0 && (
            <>
              <h3>Deadliest events</h3>
              <div className="ucdp-list" aria-label="Deadliest events">
                {data.top_events.slice(0, 6).map((e) => <EventRow key={e.id} e={e} />)}
              </div>
            </>
          )}
        </>
      )}
      <p className="imagery-note">
        {data.caveats} {data.heat_note} {data.transformation} {data.attribution}. Cite: {data.citation}.
        {data.freshness.last_successful_refresh_at ? ` Checked ${timeAgo(data.freshness.last_successful_refresh_at)}.` : ""}
      </p>
    </section>
  );
}
