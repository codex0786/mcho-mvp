"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { apiUrl, getJsonWithWake } from "../lib/api";
import ConflictPanel, { type ConflictOverview } from "./ConflictPanel";
import CountryTrend from "./CountryTrend";
import DamagePanel, { type DamageOverview } from "./DamagePanel";
import MovingFronts from "./MovingFronts";
import ShippingPanel, { type MaritimeOverview } from "./ShippingPanel";
import RegionalMap, { type Bbox, type PublishedEvent } from "./RegionalMap";
import ThermalInsights from "./ThermalInsights";

type Country = { iso_a3: string; name: string; bbox: Bbox };

const WINDOWS = [
  { hours: 6, label: "Last 6 hours" },
  { hours: 24, label: "Last 24 hours" },
  { hours: 72, label: "Last 3 days" },
];

function readUrlState(): { hours: number; country: string | null } {
  const params = new URLSearchParams(window.location.search);
  const hours = Number(params.get("hours"));
  const country = (params.get("country") || "").toUpperCase();
  return {
    hours: WINDOWS.some((w) => w.hours === hours) ? hours : 24,
    country: /^[A-Z]{3}$/.test(country) ? country : null,
  };
}

export default function ObservatoryDashboard() {
  const [hours, setHours] = useState(24);
  const [country, setCountry] = useState<string | null>(null);
  const [countries, setCountries] = useState<Country[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [events, setEvents] = useState<PublishedEvent[]>([]);
  const [maritime, setMaritime] = useState<MaritimeOverview | null>(null);
  const [maritimeMessage, setMaritimeMessage] = useState("Loading shipping data…");
  const [damage, setDamage] = useState<DamageOverview | null>(null);
  const [conflict, setConflict] = useState<ConflictOverview | null>(null);
  const [conflictMessage, setConflictMessage] = useState("Loading verified conflict events…");
  const [damageMessage, setDamageMessage] = useState("Loading damage assessments…");

  // Read shareable state after mount so server and client render the same markup.
  useEffect(() => {
    const initial = readUrlState();
    setHours(initial.hours);
    setCountry(initial.country);
    getJsonWithWake<{ items: Country[] }>(apiUrl("/thermal/countries"))
      .then((body) => { if (body) setCountries(body.items); })
      .catch(() => setCountries([]));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (hours === 24) params.delete("hours"); else params.set("hours", String(hours));
    if (country) params.set("country", country); else params.delete("country");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
  }, [hours, country]);

  useEffect(() => {
    let current = true;
    setMaritimeMessage("Loading shipping data…");
    getJsonWithWake<MaritimeOverview>(apiUrl("/maritime/overview", { country: country ?? undefined }), {
      isCurrent: () => current,
      onWaking: () => setMaritimeMessage("The server is waking up (free hosting can take about a minute). Retrying…"),
    }).then((body) => { if (body) setMaritime(body); })
      .catch((err) => { if (current) setMaritimeMessage(`Shipping data unavailable: ${err instanceof Error ? err.message : "unknown error"}.`); });
    return () => { current = false; };
  }, [country, refreshKey]);

  useEffect(() => {
    let current = true;
    setConflictMessage("Loading verified conflict events…");
    getJsonWithWake<ConflictOverview>(apiUrl("/conflict/overview", { country: country ?? undefined }), {
      isCurrent: () => current,
      onWaking: () => setConflictMessage("The server is waking up (free hosting can take about a minute). Retrying…"),
    }).then((body) => { if (body) setConflict(body); })
      .catch((err) => { if (current) setConflictMessage(`Verified conflict events unavailable: ${err instanceof Error ? err.message : "unknown error"}.`); });
    return () => { current = false; };
  }, [country, refreshKey]);

  useEffect(() => {
    let current = true;
    setDamageMessage("Loading damage assessments…");
    getJsonWithWake<DamageOverview>(apiUrl("/damage/overview", { country: country ?? undefined }), {
      isCurrent: () => current,
      onWaking: () => setDamageMessage("The server is waking up (free hosting can take about a minute). Retrying…"),
    }).then((body) => { if (body) setDamage(body); })
      .catch((err) => { if (current) setDamageMessage(`Damage assessments unavailable: ${err instanceof Error ? err.message : "unknown error"}.`); });
    return () => { current = false; };
  }, [country, refreshKey]);

  const selected = useMemo(() => countries.find((c) => c.iso_a3 === country) ?? null, [countries, country]);
  // An unknown code in the URL falls back to the whole region once the list has loaded.
  useEffect(() => { if (country && countries.length && !selected) setCountry(null); }, [country, countries, selected]);

  const selectCountry = useCallback((iso3: string | null) => {
    setCountry(iso3);
    if (iso3) document.querySelector(".map-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  return (
    <>
      <section className="toolbar" aria-label="Map filters">
        <label>Time window
          <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            {WINDOWS.map((w) => <option key={w.hours} value={w.hours}>{w.label}</option>)}
          </select>
        </label>
        <label>Country
          <select value={country ?? ""} onChange={(e) => selectCountry(e.target.value || null)}>
            <option value="">All MENA countries</option>
            {countries.map((c) => <option key={c.iso_a3} value={c.iso_a3}>{c.name}</option>)}
          </select>
        </label>
        <button type="button" onClick={() => setRefreshKey((k) => k + 1)}>Refresh</button>
        <span className="toolbar-note">Satellite data updates about hourly. Share this view with its link.</span>
      </section>
      <div className="content-grid">
        <section className="map-card">
          <div className="section-heading">
            <h2>{selected ? selected.name : "Regional map"}</h2>
            <span>Satellite heat detections · unverified</span>
          </div>
          <RegionalMap hours={hours} country={country} focus={selected?.bbox ?? null} refreshKey={refreshKey} onEvents={setEvents} maritime={maritime} damage={damage?.cells ?? null} conflict={conflict?.events ?? null} />
        </section>
        <aside className="side-card">
          {country && <><CountryTrend key={country} iso3={country} onClose={() => selectCountry(null)} /><div className="section-divider" /></>}
          <ThermalInsights key={refreshKey} hours={hours} country={country} onSelectCountry={selectCountry} />
          <div className="section-divider" />
          <MovingFronts country={country} refreshKey={refreshKey} />
          {events.length > 0 && (
            <>
              <div className="section-divider" />
              <h2>Published events</h2>
              <p className="muted">Human-reviewed records with sources.</p>
              <div className="event-list">
                {events.slice(0, 30).map((e) => (
                  <article key={e.id} className="event-item">
                    <strong>{e.eventType}</strong>
                    <p>{e.verificationStatus} · {e.eventStart ?? "Time not provided"}</p>
                  </article>
                ))}
              </div>
            </>
          )}
        </aside>
      </div>
      <ConflictPanel data={conflict} message={conflictMessage} countryName={selected?.name ?? null} />
      <ShippingPanel data={maritime} message={maritimeMessage} countryName={selected?.name ?? null} />
      <DamagePanel data={damage} message={damageMessage} countryName={selected?.name ?? null} />
    </>
  );
}
