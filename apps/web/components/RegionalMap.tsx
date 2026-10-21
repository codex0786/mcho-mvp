"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { apiUrl, getJsonWithWake, utcTime } from "../lib/api";

type EventFeature = { type: "Feature"; id: string; geometry: GeoJSON.Geometry; properties: Record<string, unknown> };
type EventCollection = {
  type: "FeatureCollection"; features: EventFeature[]; response_generated_at?: string;
  truncated?: boolean; feature_limit?: number;
};
type ThermalCollection = EventCollection & { freshness?: { configured: boolean } };
export type FlyToDetail = { longitude: number; latitude: number; zoom?: number };

const STYLE = process.env.NEXT_PUBLIC_MAP_STYLE_URL || "";
const THERMAL_HOURS = 24;
// Colours shared with the legend and the insights panel.
export const THERMAL_COLOURS = { new: "#ff5a36", recurring: "#ffb020", persistent: "#8f9bb0" } as const;
const CONFIDENCE = { l: "low", n: "nominal", h: "high" } as Record<string, string>;

export default function RegionalMap() {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [status, setStatus] = useState("Loading map configuration…");
  // Tracked separately so a data status is not overwritten while tiles are still arriving.
  const [basemapLoading, setBasemapLoading] = useState(false);
  const [thermalStatus, setThermalStatus] = useState("");
  // Incremented by every refresh and on unmount, so superseded requests stop quietly.
  const eventGeneration = useRef(0);
  const thermalGeneration = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let instance: MapLibreMap | null = null;
    let refreshButton: HTMLElement | null = null;
    let handler: (() => void) | null = null;
    let moveTimer: ReturnType<typeof setTimeout> | undefined;
    const flyTo = (event: Event) => {
      const detail = (event as CustomEvent<FlyToDetail>).detail;
      instance?.flyTo({ center: [detail.longitude, detail.latitude], zoom: detail.zoom ?? 9, essential: true });
    };
    window.addEventListener("mcho:fly-to", flyTo);

    async function initialize() {
      let styleUrl = STYLE;
      if (!styleUrl) {
        try {
          const configResponse = await fetch("/api/public-config", { cache: "no-store" });
          if (configResponse.ok) {
            const runtime = await configResponse.json() as { mapStyleUrl?: unknown };
            if (typeof runtime.mapStyleUrl === "string") styleUrl = runtime.mapStyleUrl.trim();
          }
        } catch {
          // Continue to an explicit no-style state rather than guessing a basemap.
        }
      }
      if (cancelled || !container.current) return;
      if (!styleUrl) {
        setStatus("No basemap style configured. Set MCHO_MAP_STYLE_URL on the web service to a permitted MapLibre style URL.");
        return;
      }

      setStatus("Loading basemap…");
      setBasemapLoading(true);
      instance = new maplibregl.Map({
        container: container.current,
        style: styleUrl,
        center: [39, 27],
        zoom: 3.2,
      });
      instance.addControl(new maplibregl.NavigationControl(), "top-right");
      let styleReady = false;
      // "load" waits for every initial tile; it only marks the basemap as complete.
      instance.once("load", () => { if (!cancelled) setBasemapLoading(false); });
      instance.on("error", () => {
        if (cancelled || styleReady) return;
        setBasemapLoading(false);
        setStatus("The basemap style could not be loaded. Check MCHO_MAP_STYLE_URL; no event data is inferred.");
      });
      // Data layers only need the style, so records are requested as soon as it is
      // parsed rather than after all basemap tiles have arrived.
      instance.once("style.load", () => {
        if (!instance || cancelled) return;
        styleReady = true;
        instance.addSource("thermal", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        instance.addLayer({
          id: "thermal-points", type: "circle", source: "thermal",
          paint: {
            "circle-color": ["match", ["get", "classification"],
              "new", THERMAL_COLOURS.new, "recurring", THERMAL_COLOURS.recurring, THERMAL_COLOURS.persistent],
            "circle-radius": ["interpolate", ["linear"], ["coalesce", ["get", "frp_mw"], 1], 1, 3, 20, 5, 100, 8, 500, 11],
            "circle-opacity": ["match", ["get", "classification"], "persistent", 0.45, 0.85],
            "circle-stroke-color": "#1b0d06", "circle-stroke-width": 0.6,
          },
        });
        instance.addSource("events", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
          cluster: true,
          clusterRadius: 45,
        });
        instance.addLayer({
          id: "event-clusters", type: "circle", source: "events",
          filter: ["has", "point_count"],
          paint: { "circle-radius": ["step", ["get", "point_count"], 16, 10, 21, 30, 27], "circle-opacity": 0.75 },
        });
        instance.addLayer({
          id: "event-points", type: "circle", source: "events",
          filter: ["!", ["has", "point_count"]],
          paint: { "circle-radius": 7, "circle-stroke-width": 1.5 },
        });
        setStatus("Loading published event records…");
        void refresh(instance);
        void refreshThermal(instance);
      });
      instance.on("moveend", () => {
        clearTimeout(moveTimer);
        moveTimer = setTimeout(() => { if (instance && !cancelled) void refreshThermal(instance); }, 600);
      });
      instance.on("click", "event-points", (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const props = feature.properties || {};
        new maplibregl.Popup().setLngLat(e.lngLat).setHTML(
          `<strong>${escapeHtml(String(props.event_type || "Event"))}</strong><br/>Status: ${escapeHtml(String(props.verification_status || "unknown"))}<br/>${escapeHtml(String(props.event_start || "Time not provided"))}`,
        ).addTo(instance!);
      });
      instance.on("click", "thermal-points", (e) => {
        const feature = e.features?.[0];
        if (!feature || feature.geometry.type !== "Point") return;
        const p = feature.properties || {};
        const label = { new: "New activity", recurring: "Recurring activity", persistent: "Persistent site (likely flare/industry)" }[String(p.classification)] ?? "Heat detection";
        const frp = p.frp_mw === null || p.frp_mw === undefined || p.frp_mw === "null" ? "not reported" : `${Number(p.frp_mw).toFixed(1)} MW`;
        new maplibregl.Popup({ maxWidth: "280px" }).setLngLat(feature.geometry.coordinates as [number, number]).setHTML(
          `<strong>${escapeHtml(label)}</strong><br/>`
          + `${escapeHtml(String(p.country || ""))} · ${escapeHtml(utcTime(String(p.acquired_at)))}<br/>`
          + `Fire radiative power: ${escapeHtml(frp)}<br/>`
          + `Confidence: ${escapeHtml(CONFIDENCE[String(p.confidence)] ?? String(p.confidence))} · ${escapeHtml(String(p.satellite))} ${p.daynight === "N" ? "night" : "day"} pass<br/>`
          + `<em>Satellite heat signature — not a verified event.</em>`,
        ).addTo(instance!);
      });
      for (const layer of ["thermal-points", "event-points"]) {
        instance.on("mouseenter", layer, () => { if (instance) instance.getCanvas().style.cursor = "pointer"; });
        instance.on("mouseleave", layer, () => { if (instance) instance.getCanvas().style.cursor = ""; });
      }
      map.current = instance;
      refreshButton = document.getElementById("refresh");
      handler = () => { if (instance) { void refresh(instance); void refreshThermal(instance); } };
      refreshButton?.addEventListener("click", handler);
    }

    void initialize();
    return () => {
      cancelled = true;
      eventGeneration.current += 1;
      thermalGeneration.current += 1;
      clearTimeout(moveTimer);
      window.removeEventListener("mcho:fly-to", flyTo);
      if (refreshButton && handler) refreshButton.removeEventListener("click", handler);
      instance?.remove();
      map.current = null;
    };
    // Map initialization intentionally runs once; the style is resolved at runtime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function bounds(instance: MapLibreMap) {
    const b = instance.getBounds();
    const clamp = (value: number, limit: number) => Math.max(-limit, Math.min(limit, value));
    return { west: clamp(b.getWest(), 180), south: clamp(b.getSouth(), 90), east: clamp(b.getEast(), 180), north: clamp(b.getNorth(), 90) };
  }

  async function refresh(instance: MapLibreMap) {
    const generation = ++eventGeneration.current;
    try {
      const from = (document.getElementById("from-date") as HTMLInputElement | null)?.value;
      const to = (document.getElementById("to-date") as HTMLInputElement | null)?.value;
      const verification = (document.getElementById("verification") as HTMLSelectElement | null)?.value;
      const url = apiUrl("/map/events", {
        ...bounds(instance),
        from: from ? `${from}T00:00:00Z` : undefined, to: to ? `${to}T23:59:59Z` : undefined,
        verification_status: verification || undefined,
      });
      const data = await getJsonWithWake<EventCollection>(url, {
        isCurrent: () => generation === eventGeneration.current,
        onWaking: () => setStatus("The API is waking up (free hosting can take about a minute). Retrying…"),
      });
      if (!data) return;
      (instance.getSource("events") as maplibregl.GeoJSONSource | undefined)?.setData(data as GeoJSON.FeatureCollection);
      const count = data.truncated
        ? `Showing the first ${data.features.length} published map features (limit ${data.feature_limit ?? data.features.length}); zoom in or narrow the dates to see all`
        : `${data.features.length} published map features`;
      setStatus(`${count} · API data timestamp ${data.response_generated_at || "not supplied"}`);
      renderEventList(data.features);
    } catch (err) {
      if (generation !== eventGeneration.current) return;
      setStatus(`Map data unavailable: ${err instanceof Error ? err.message : "unknown error"}. No live data is inferred.`);
    }
  }

  async function refreshThermal(instance: MapLibreMap) {
    const generation = ++thermalGeneration.current;
    setThermalStatus("Satellite heat detections: retrieving…");
    try {
      const data = await getJsonWithWake<ThermalCollection>(apiUrl("/thermal/detections", { ...bounds(instance), hours: THERMAL_HOURS }), {
        isCurrent: () => generation === thermalGeneration.current,
        onWaking: () => setThermalStatus("Satellite heat detections: server waking up, retrying…"),
      });
      if (!data) return;
      (instance.getSource("thermal") as maplibregl.GeoJSONSource | undefined)?.setData(data as GeoJSON.FeatureCollection);
      if (data.freshness && !data.freshness.configured) {
        setThermalStatus("Satellite heat detections: the NASA FIRMS feed is not configured on the server.");
        return;
      }
      const newest = data.features.reduce<string | null>((latest, f) => {
        const t = String(f.properties.acquired_at);
        return !latest || t > latest ? t : latest;
      }, null);
      const shown = data.truncated ? `first ${data.features.length} (zoom in for all)` : `${data.features.length}`;
      setThermalStatus(`Satellite heat detections in view, last ${THERMAL_HOURS} h: ${shown}${newest ? ` · newest ${utcTime(newest)}` : ""}`);
    } catch (err) {
      if (generation !== thermalGeneration.current) return;
      setThermalStatus(`Satellite heat detections unavailable: ${err instanceof Error ? err.message.replace("API returned", "server returned") : "unknown error"}.`);
    }
  }

  function renderEventList(features: EventFeature[]) {
    const target = document.getElementById("event-list");
    if (!target) return;
    target.replaceChildren();
    if (!features.length) { const p = document.createElement("div"); p.className = "empty"; p.textContent = "No published events in this map view and time range."; target.append(p); return; }
    for (const f of features.slice(0, 30)) {
      const card = document.createElement("article"); card.className = "event-item";
      const title = document.createElement("strong"); title.textContent = String(f.properties.event_type || "Event");
      const meta = document.createElement("p"); meta.textContent = `${String(f.properties.verification_status || "unknown")} · ${String(f.properties.event_start || "Time not provided")}`;
      card.append(title, meta); target.append(card);
    }
  }

  return (
    <div className="map-wrap">
      <div ref={container} className="map-canvas" aria-label="Interactive regional map"/>
      <div className="map-legend" aria-label="Map legend">
        <strong>Satellite heat, last {THERMAL_HOURS} h</strong>
        <span><i style={{ background: THERMAL_COLOURS.new }}/>New activity</span>
        <span><i style={{ background: THERMAL_COLOURS.recurring }}/>Recurring</span>
        <span><i style={{ background: THERMAL_COLOURS.persistent }}/>Persistent site</span>
        <small>Size = fire intensity. Unverified.</small>
      </div>
      <div className="map-status">
        <div role="status">{status}{basemapLoading && status !== "Loading basemap…" ? " · Basemap tiles still loading…" : ""}</div>
        {thermalStatus && <div className="map-status-thermal" role="status">{thermalStatus}</div>}
      </div>
    </div>
  );
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char);
}
