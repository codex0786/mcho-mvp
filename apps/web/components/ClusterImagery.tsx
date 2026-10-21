"use client";

import { useEffect, useRef, useState } from "react";

import { apiUrl, getJsonWithWake, timeAgo, utcTime } from "../lib/api";

type Scene = {
  id: string; acquired_at: string; cloud_cover_percent: number | null; tile: string | null;
  preview_url: string; marker: { x: number; y: number } | null; browser_url: string;
};
type SceneSearch = { scenes: Scene[]; clearest_recent_id: string | null; caveats: string; source: { name: string } };

export default function ClusterImagery({ latitude, longitude, label }: { latitude: number; longitude: number; label: string }) {
  const [result, setResult] = useState<SceneSearch | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState("Searching recent Sentinel-2 imagery…");
  const generation = useRef(0);

  useEffect(() => {
    const current = ++generation.current;
    getJsonWithWake<SceneSearch>(apiUrl("/sentinel2/scenes", { lat: latitude, lon: longitude, days: 30 }), {
      isCurrent: () => current === generation.current,
      onWaking: () => setMessage("The server is waking up (free hosting can take about a minute). Retrying…"),
    }).then((body) => {
      if (!body) return;
      setResult(body);
      setSelectedId(body.clearest_recent_id ?? body.scenes[0]?.id ?? null);
    }).catch((err) => {
      if (current === generation.current) setMessage(`Imagery unavailable: ${err instanceof Error ? err.message : "unknown error"}.`);
    });
    return () => { generation.current += 1; };
  }, [latitude, longitude]);

  if (!result) return <div className="imagery" role="status">{message}</div>;
  if (!result.scenes.length) {
    return <div className="imagery" role="status">No Sentinel-2 scenes over this spot in the last 30 days.</div>;
  }
  const scene = result.scenes.find((s) => s.id === selectedId) ?? result.scenes[0];
  const cloud = scene.cloud_cover_percent === null ? "cloud cover unknown" : `${scene.cloud_cover_percent}% cloud`;

  return (
    <div className="imagery" aria-label={`Sentinel-2 imagery near ${label}`}>
      <figure className="imagery-figure">
        <div className="imagery-frame">
          {/* eslint-disable-next-line @next/next/no-img-element -- external, pre-sized public preview */}
          <img src={scene.preview_url} alt={`Sentinel-2 preview of tile ${scene.tile ?? "unknown"} on ${utcTime(scene.acquired_at)}, ${cloud}`}
            loading="lazy" referrerPolicy="no-referrer" />
          {scene.marker && (
            <span className="imagery-marker" style={{ left: `${scene.marker.x * 100}%`, top: `${scene.marker.y * 100}%` }}
              title="Approximate cluster location" aria-hidden="true" />
          )}
        </div>
        <figcaption>
          {utcTime(scene.acquired_at)} ({timeAgo(scene.acquired_at)}) · {cloud} · whole ~110 km tile; ring = cluster (approx.)
        </figcaption>
      </figure>
      <a className="text-link" href={scene.browser_url} target="_blank" rel="noreferrer">Open this date at full 10 m resolution (Copernicus Browser) ↗</a>
      {result.scenes.length > 1 && (
        <div className="imagery-dates" role="group" aria-label="Other recent images">
          {result.scenes.map((s) => (
            <button key={s.id} type="button" aria-pressed={s.id === scene.id} onClick={() => setSelectedId(s.id)}>
              {new Date(s.acquired_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" })}
              {s.cloud_cover_percent !== null ? ` · ${Math.round(s.cloud_cover_percent)}%☁` : ""}
            </button>
          ))}
        </div>
      )}
      <p className="imagery-note">{result.caveats} Source: {result.source.name}.</p>
    </div>
  );
}
