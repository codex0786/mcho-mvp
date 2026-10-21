"use client";

import { useEffect, useRef, useState } from "react";

import { apiUrl, getJsonWithWake } from "../lib/api";
import { TRACK_COLOUR, TRACK_DAYS, type FlyToDetail } from "./RegionalMap";

type Track = {
  properties: {
    country: string; first_day: string; last_day: string; days_active: number; detections: number;
    displacement_km: number; direction: string | null; km_per_day: number; active: boolean;
    latest: { longitude: number; latitude: number };
  };
};
type Tracks = { features: Track[]; total_tracks: number; caveats: string; method: { cluster_eps_km: number; link_km: number; max_gap_days: number } };

function shortDay(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

export default function MovingFronts({ country, refreshKey }: { country: string | null; refreshKey: number }) {
  const [data, setData] = useState<Tracks | null>(null);
  const [message, setMessage] = useState("Linking heat across days…");
  const generation = useRef(0);

  useEffect(() => {
    const current = ++generation.current;
    setMessage("Linking heat across days…");
    getJsonWithWake<Tracks>(apiUrl("/thermal/tracks", { days: TRACK_DAYS, country: country ?? undefined }), {
      isCurrent: () => current === generation.current,
      onWaking: () => setMessage("The server is waking up (free hosting can take about a minute). Retrying…"),
    }).then((body) => { if (body) setData(body); })
      .catch((err) => { if (current === generation.current) setMessage(`Moving fronts unavailable: ${err instanceof Error ? err.message : "unknown error"}.`); });
    return () => { generation.current += 1; };
  }, [country, refreshKey]);

  const fly = (detail: FlyToDetail) => {
    window.dispatchEvent(new CustomEvent<FlyToDetail>("mcho:fly-to", { detail }));
    document.querySelector(".map-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const tracks = data ? [...data.features].sort((a, b) => Number(b.properties.active) - Number(a.properties.active)).slice(0, 6) : [];
  return (
    <section className="fronts" aria-label="Moving fronts">
      <div className="insights-head"><h3>Moving fronts</h3><span className="muted">Last {TRACK_DAYS} days</span></div>
      {!data ? <div className="empty" role="status">{message}</div> : tracks.length === 0 ? (
        <p className="muted">No heat linked across two or more days{country ? " in this country" : ""}.</p>
      ) : (
        <ul className="insights-list">
          {tracks.map((t, i) => {
            const p = t.properties;
            const moved = p.direction && p.displacement_km >= 2 ? `moved ${Math.round(p.displacement_km)} km ${p.direction} (~${Math.round(p.km_per_day)} km/day)` : "stayed in about the same area";
            return (
              <li key={`${p.first_day}-${p.latest.longitude}-${i}`}>
                <button type="button" className="cluster-button front-button" style={{ borderLeftColor: TRACK_COLOUR }}
                  onClick={() => fly({ longitude: p.latest.longitude, latitude: p.latest.latitude, zoom: 9 })}>
                  <strong>{p.country}</strong> · {p.days_active} days · {p.detections} detections{p.active ? " · active" : ""}
                  <span>{shortDay(p.first_day)} → {shortDay(p.last_day)}: {moved}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {data && data.total_tracks > tracks.length && <p className="muted">Showing {tracks.length} of {data.total_tracks}; the map shows the largest {Math.min(40, data.total_tracks)}.</p>}
      {data && <p className="imagery-note">{data.caveats}</p>}
    </section>
  );
}
