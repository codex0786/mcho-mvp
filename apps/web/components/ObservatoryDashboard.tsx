"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { apiUrl, getJsonWithWake } from "../lib/api";
import CountryTrend from "./CountryTrend";
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
          <RegionalMap hours={hours} country={country} focus={selected?.bbox ?? null} refreshKey={refreshKey} onEvents={setEvents} />
        </section>
        <aside className="side-card">
          {country && <><CountryTrend key={country} iso3={country} onClose={() => selectCountry(null)} /><div className="section-divider" /></>}
          <ThermalInsights key={refreshKey} hours={hours} country={country} onSelectCountry={selectCountry} />
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
    </>
  );
}
