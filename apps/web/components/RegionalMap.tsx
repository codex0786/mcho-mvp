"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type EventFeature = { type: "Feature"; id: string; geometry: GeoJSON.Geometry; properties: Record<string, unknown> };
type EventCollection = { type: "FeatureCollection"; features: EventFeature[]; response_generated_at?: string };
const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN;
const API = API_ORIGIN
  ? `${API_ORIGIN.replace(/\/$/, "")}/api/v1`
  : (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1");
const STYLE = process.env.NEXT_PUBLIC_MAP_STYLE_URL || "";

export default function RegionalMap() {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [status, setStatus] = useState("Waiting for map style configuration.");
  const [events, setEvents] = useState<EventFeature[]>([]);

  useEffect(() => {
    if (!container.current) return;
    if (!STYLE) {
      setStatus("No basemap style configured. Set NEXT_PUBLIC_MAP_STYLE_URL to a permitted MapLibre style URL.");
      return;
    }
    const instance = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [39, 27],
      zoom: 3.2,
    });
    instance.addControl(new maplibregl.NavigationControl(), "top-right");
    instance.on("load", () => {
      instance.addSource("events", { type: "geojson", data: { type: "FeatureCollection", features: [] }, cluster: true, clusterRadius: 45 });
      instance.addLayer({ id: "event-clusters", type: "circle", source: "events", filter: ["has", "point_count"], paint: { "circle-radius": ["step", ["get", "point_count"], 16, 10, 21, 30, 27], "circle-opacity": 0.75 } });
      instance.addLayer({ id: "event-points", type: "circle", source: "events", filter: ["!", ["has", "point_count"]], paint: { "circle-radius": 7, "circle-stroke-width": 1.5 } });
      setStatus("Map loaded. Loading published event records…");
      void refresh(instance);
    });
    instance.on("click", "event-points", (e) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const props = feature.properties || {};
      new maplibregl.Popup().setLngLat(e.lngLat).setHTML(`<strong>${escapeHtml(String(props.event_type || "Event"))}</strong><br/>Status: ${escapeHtml(String(props.verification_status || "unknown"))}<br/>${escapeHtml(String(props.event_start || "Time not provided"))}`).addTo(instance);
    });
    map.current = instance;
    const refreshButton = document.getElementById("refresh");
    const handler = () => void refresh(instance);
    refreshButton?.addEventListener("click", handler);
    return () => { refreshButton?.removeEventListener("click", handler); instance.remove(); map.current = null; };
    // Map initialization intentionally runs once per configured style.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh(instance: MapLibreMap) {
    try {
      const b = instance.getBounds();
      const url = new URL(`${API}/map/events`);
      url.searchParams.set("west", String(b.getWest())); url.searchParams.set("south", String(b.getSouth()));
      url.searchParams.set("east", String(b.getEast())); url.searchParams.set("north", String(b.getNorth()));
      const from = (document.getElementById("from-date") as HTMLInputElement | null)?.value;
      const to = (document.getElementById("to-date") as HTMLInputElement | null)?.value;
      if (from) url.searchParams.set("from", `${from}T00:00:00Z`);
      if (to) url.searchParams.set("to", `${to}T23:59:59Z`);
      const verification = (document.getElementById("verification") as HTMLSelectElement | null)?.value;
      if (verification) url.searchParams.set("verification_status", verification);
      const response = await fetch(url.toString(), { cache: "no-store" });
      if (!response.ok) throw new Error(`API returned HTTP ${response.status}`);
      const data = await response.json() as EventCollection;
      const source = instance.getSource("events") as maplibregl.GeoJSONSource | undefined;
      source?.setData(data as GeoJSON.FeatureCollection);
      setEvents(data.features || []);
      setStatus(`${data.features.length} published map features · API data timestamp ${data.response_generated_at || "not supplied"}`);
      renderEventList(data.features);
    } catch (err) {
      setStatus(`Map data unavailable: ${err instanceof Error ? err.message : "unknown error"}. No live data is inferred.`);
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

  return <div className="map-wrap"><div ref={container} className="map-canvas" aria-label="Interactive regional map"/><div className="map-status" role="status">{status}</div></div>;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char);
}
