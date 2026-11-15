import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { MapPin } from "../lib/types";

/** Approximate places of found items (rounded to ~100 m on the server). OpenStreetMap tiles. */
export function MapView({ pins, onSelect }: { pins: MapPin[]; onSelect?: (p: MapPin) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!el.current || map.current) return;
    map.current = L.map(el.current, { scrollWheelZoom: false, attributionControl: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    return () => { map.current?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    if (!map.current || !layer.current) return;
    layer.current.clearLayers();
    const latlngs: L.LatLngExpression[] = [];
    for (const p of pins) {
      const marker = L.circleMarker([p.lat, p.lng], {
        radius: 9, weight: 2, color: "#ffffff", fillColor: p.status === "Pending" ? "#eda100" : "#2a78d6", fillOpacity: 1,
      });
      const box = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = p.name;
      const sub = document.createElement("div");
      sub.textContent = `${p.location ?? ""}${p.status === "Pending" ? " · claim under review" : ""}`;
      box.append(title, sub);
      marker.bindPopup(box);
      if (onSelect) marker.on("click", () => onSelect(p));
      marker.addTo(layer.current);
      latlngs.push([p.lat, p.lng]);
    }
    if (latlngs.length) map.current.fitBounds(L.latLngBounds(latlngs).pad(0.3), { maxZoom: 17 });
    else map.current.setView([20.59, 78.96], 4);
  }, [pins, onSelect]);

  return <div ref={el} className="h-[420px] w-full overflow-hidden rounded-3xl border border-stone-200 dark:border-stone-800" role="region" aria-label="Map of found items" />;
}
