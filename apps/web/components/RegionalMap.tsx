"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { apiUrl, getJsonWithWake, utcTime } from "../lib/api";
import { changeColour, type MaritimeArea } from "./ShippingPanel";

type EventFeature = { type: "Feature"; id: string; geometry: GeoJSON.Geometry; properties: Record<string, unknown> };
type EventCollection = {
  type: "FeatureCollection"; features: EventFeature[]; response_generated_at?: string;
  truncated?: boolean; feature_limit?: number;
};
type ThermalCollection = EventCollection & { freshness?: { configured: boolean } };
export type FlyToDetail = { longitude: number; latitude: number; zoom?: number };
export type Bbox = [number, number, number, number];
export type PublishedEvent = { id: string; eventType: string; verificationStatus: string; eventStart: string | null };
type Props = {
  hours: number;
  country: string | null;
  // Bounding box to show; null shows the whole region. Changes move the map.
  focus: Bbox | null;
  // Incremented by the Refresh button.
  refreshKey: number;
  onEvents?: (events: PublishedEvent[]) => void;
  // Chokepoints and ports with aggregate traffic (IMF PortWatch).
  maritime?: { chokepoints: MaritimeArea[]; ports: MaritimeArea[] } | null;
};
const REGION_VIEW = { center: [39, 27] as [number, number], zoom: 3.2 };

const STYLE = process.env.NEXT_PUBLIC_MAP_STYLE_URL || "";
// Colours shared with the legend and the insights panel.
export const THERMAL_COLOURS = { new: "#ff5a36", recurring: "#ffb020", persistent: "#8f9bb0" } as const;
export const TRACK_COLOUR = "#7fd3ff";
export const TRACK_DAYS = 7;
const CONFIDENCE = { l: "low", n: "nominal", h: "high" } as Record<string, string>;

export default function RegionalMap({ hours, country, focus, refreshKey, onEvents, maritime }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [status, setStatus] = useState("Loading map configuration…");
  // Tracked separately so a data status is not overwritten while tiles are still arriving.
  const [basemapLoading, setBasemapLoading] = useState(false);
  const [thermalStatus, setThermalStatus] = useState("");
  // Incremented by every refresh and on unmount, so superseded requests stop quietly.
  const eventGeneration = useRef(0);
  const thermalGeneration = useRef(0);
  const trackGeneration = useRef(0);
  // Latest props for map callbacks that are registered once.
  const filters = useRef({ hours, country, onEvents, maritime });
  filters.current = { hours, country, onEvents, maritime };
  const styleReady = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let instance: MapLibreMap | null = null;
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
        ...REGION_VIEW,
      });
      instance.addControl(new maplibregl.NavigationControl(), "top-right");
      // "load" waits for every initial tile; it only marks the basemap as complete.
      instance.once("load", () => { if (!cancelled) setBasemapLoading(false); });
      instance.on("error", () => {
        if (cancelled || styleReady.current) return;
        setBasemapLoading(false);
        setStatus("The basemap style could not be loaded. Check MCHO_MAP_STYLE_URL; no event data is inferred.");
      });
      // Data layers only need the style, so records are requested as soon as it is
      // parsed rather than after all basemap tiles have arrived.
      instance.once("style.load", () => {
        if (!instance || cancelled) return;
        styleReady.current = true;
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
          // Higher keys draw on top, so new activity is never hidden under flare sites.
          layout: { "circle-sort-key": ["match", ["get", "classification"], "new", 2, "recurring", 1, 0] },
        });
        instance.addSource("tracks", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        instance.addLayer({
          id: "track-lines", type: "line", source: "tracks",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": TRACK_COLOUR, "line-width": ["case", ["get", "active"], 3, 2], "line-opacity": ["case", ["get", "active"], 0.95, 0.55] },
        });
        instance.addSource("track-heads", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        instance.addLayer({
          id: "track-heads", type: "circle", source: "track-heads",
          paint: { "circle-radius": 5, "circle-color": TRACK_COLOUR, "circle-stroke-color": "#06121c", "circle-stroke-width": 2 },
        });
        instance.addSource("maritime", { type: "geojson", data: maritimeGeoJson(filters.current.maritime) });
        instance.addLayer({
          id: "maritime-points", type: "circle", source: "maritime",
          paint: {
            "circle-radius": ["case", ["==", ["get", "kind"], "chokepoint"], 9, 4],
            "circle-color": ["get", "colour"], "circle-opacity": ["case", ["==", ["get", "kind"], "chokepoint"], 0.25, 0.9],
            "circle-stroke-color": ["get", "colour"], "circle-stroke-width": ["case", ["==", ["get", "kind"], "chokepoint"], 2.5, 1],
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
        void refreshTracks(instance);
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
      const trackPopup = (e: maplibregl.MapLayerMouseEvent) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        const moved = Number(p.displacement_km) >= 2 && p.direction && p.direction !== "null"
          ? `moved ${Number(p.displacement_km).toFixed(0)} km ${p.direction} (${Number(p.km_per_day).toFixed(0)} km/day)` : "stayed in about the same place";
        new maplibregl.Popup({ maxWidth: "280px" }).setLngLat(e.lngLat).setHTML(
          `<strong>Moving front${p.active === true || p.active === "true" ? " (active)" : ""}</strong><br/>`
          + `${escapeHtml(String(p.country))} · ${escapeHtml(String(p.first_day))} → ${escapeHtml(String(p.last_day))}<br/>`
          + `${escapeHtml(String(p.days_active))} days with heat · ${escapeHtml(moved)}<br/>`
          + `${escapeHtml(String(p.detections))} detections<br/><em>Shows how heat moved, not what caused it.</em>`,
        ).addTo(instance!);
      };
      instance.on("click", "maritime-points", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        const change = p.change === null || p.change === undefined || p.change === "null" ? "no comparison with last year" : `${Number(p.change) > 0 ? "+" : ""}${p.change}% vs the same days last year`;
        new maplibregl.Popup({ maxWidth: "260px" }).setLngLat(e.lngLat).setHTML(
          `<strong>${escapeHtml(String(p.name))}</strong> (${p.kind === "chokepoint" ? "chokepoint" : "port"})<br/>`
          + `${p.avg === null || p.avg === "null" ? "No recent figure" : `${escapeHtml(String(p.avg))} ${p.kind === "chokepoint" ? "transits" : "port calls"}/day`} (last 7 days)<br/>`
          + `${escapeHtml(change)}<br/><em>Source: IMF PortWatch (AIS-based aggregate).</em>`,
        ).addTo(instance!);
      });
      instance.on("click", "track-lines", trackPopup);
      instance.on("click", "track-heads", trackPopup);
      for (const layer of ["thermal-points", "event-points", "track-lines", "track-heads", "maritime-points"]) {
        instance.on("mouseenter", layer, () => { if (instance) instance.getCanvas().style.cursor = "pointer"; });
        instance.on("mouseleave", layer, () => { if (instance) instance.getCanvas().style.cursor = ""; });
      }
      map.current = instance;
    }

    void initialize();
    return () => {
      cancelled = true;
      eventGeneration.current += 1;
      thermalGeneration.current += 1;
      trackGeneration.current += 1;
      clearTimeout(moveTimer);
      window.removeEventListener("mcho:fly-to", flyTo);
      instance?.remove();
      map.current = null;
    };
    // Map initialization intentionally runs once; the style is resolved at runtime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (map.current && styleReady.current) void refreshThermal(map.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hours, country, refreshKey]);

  useEffect(() => {
    if (map.current && styleReady.current) void refreshTracks(map.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [country, refreshKey]);

  useEffect(() => {
    if (map.current && styleReady.current && refreshKey > 0) void refresh(map.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    if (focus) instance.fitBounds([[focus[0], focus[1]], [focus[2], focus[3]]], { padding: 40, maxZoom: 8 });
    else instance.easeTo(REGION_VIEW);
  }, [focus]);

  useEffect(() => {
    const source = map.current && styleReady.current ? map.current.getSource("maritime") as maplibregl.GeoJSONSource | undefined : undefined;
    source?.setData(maritimeGeoJson(maritime));
  }, [maritime]);

  function bounds(instance: MapLibreMap) {
    const b = instance.getBounds();
    const clamp = (value: number, limit: number) => Math.max(-limit, Math.min(limit, value));
    return { west: clamp(b.getWest(), 180), south: clamp(b.getSouth(), 90), east: clamp(b.getEast(), 180), north: clamp(b.getNorth(), 90) };
  }

  async function refresh(instance: MapLibreMap) {
    const generation = ++eventGeneration.current;
    try {
      const url = apiUrl("/map/events", bounds(instance));
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
      filters.current.onEvents?.(data.features.map((f) => ({
        id: String(f.id), eventType: String(f.properties.event_type || "Event"),
        verificationStatus: String(f.properties.verification_status || "unknown"),
        eventStart: f.properties.event_start ? String(f.properties.event_start) : null,
      })));
    } catch (err) {
      if (generation !== eventGeneration.current) return;
      setStatus(`Map data unavailable: ${err instanceof Error ? err.message : "unknown error"}. No live data is inferred.`);
    }
  }

  async function refreshTracks(instance: MapLibreMap) {
    const generation = ++trackGeneration.current;
    try {
      const data = await getJsonWithWake<{ type: "FeatureCollection"; features: Array<{ properties: Record<string, unknown> & { latest: { longitude: number; latitude: number } } }> }>(
        apiUrl("/thermal/tracks", { days: TRACK_DAYS, country: filters.current.country ?? undefined }),
        { isCurrent: () => generation === trackGeneration.current },
      );
      if (!data) return;
      (instance.getSource("tracks") as maplibregl.GeoJSONSource | undefined)?.setData(data as unknown as GeoJSON.FeatureCollection);
      (instance.getSource("track-heads") as maplibregl.GeoJSONSource | undefined)?.setData({
        type: "FeatureCollection",
        features: data.features.map((f) => ({
          type: "Feature", properties: f.properties,
          geometry: { type: "Point", coordinates: [f.properties.latest.longitude, f.properties.latest.latitude] },
        })),
      } as GeoJSON.FeatureCollection);
    } catch {
      // Tracks are supplementary; the detection layer already reports API problems.
    }
  }

  async function refreshThermal(instance: MapLibreMap) {
    const generation = ++thermalGeneration.current;
    setThermalStatus("Satellite heat detections: retrieving…");
    try {
      const { hours: windowHours, country: selected } = filters.current;
      const data = await getJsonWithWake<ThermalCollection>(apiUrl("/thermal/detections", {
        ...bounds(instance), hours: windowHours, country: selected ?? undefined,
      }), {
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
      const shown = data.truncated
        ? `${data.features.length} shown, new and recurring first (zoom in to see every persistent site)`
        : `${data.features.length}`;
      setThermalStatus(`Satellite heat detections in view, last ${windowHours} h: ${shown}${newest ? ` · newest ${utcTime(newest)}` : ""}`);
    } catch (err) {
      if (generation !== thermalGeneration.current) return;
      setThermalStatus(`Satellite heat detections unavailable: ${err instanceof Error ? err.message.replace("API returned", "server returned") : "unknown error"}.`);
    }
  }

  return (
    <div className="map-wrap">
      <div ref={container} className="map-canvas" aria-label="Interactive regional map"/>
      <div className="map-legend" aria-label="Map legend">
        <strong>Satellite heat, last {hours} h</strong>
        <span><i style={{ background: THERMAL_COLOURS.new }}/>New activity</span>
        <span><i style={{ background: THERMAL_COLOURS.recurring }}/>Recurring</span>
        <span><i style={{ background: THERMAL_COLOURS.persistent }}/>Persistent site</span>
        <span><i className="legend-line" style={{ background: TRACK_COLOUR }}/>Moving front, {TRACK_DAYS} days</span>
        <span><i className="legend-ring"/>Shipping chokepoint / port</span>
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

function maritimeGeoJson(maritime: Props["maritime"]): GeoJSON.FeatureCollection {
  const areas = [
    ...(maritime?.chokepoints ?? []).map((a) => ({ ...a, kind: "chokepoint" })),
    ...(maritime?.ports ?? []).map((a) => ({ ...a, kind: "port" })),
  ];
  return {
    type: "FeatureCollection",
    features: areas.map((a) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [a.longitude, a.latitude] },
      properties: { name: a.name, kind: a.kind, avg: a.avg_7d, change: a.change_vs_last_year_pct, colour: changeColour(a.change_vs_last_year_pct) },
    })),
  };
}
