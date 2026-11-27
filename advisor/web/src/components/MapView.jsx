import { useEffect, useRef, useState } from 'react';
import * as L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { CrosshairIcon, MapPickIcon } from './icons.jsx';

const OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const MAP_STYLES = { osm: 'OpenStreetMap', dark: 'Network' };
const ML = '#F5C518';
const DELHI = [28.6139, 77.209];
const allowMotion = () => !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
const durationLabel = (minutes) => {
  const value = Math.round(minutes);
  return value >= 60 ? `${Math.floor(value / 60)} h ${value % 60} min` : `${value} min`;
};

function fitMap(m, points, maxZoom = 15) {
  if (!m || !points.length) return;
  m.fitBounds(L.latLngBounds(points), {
    animate: allowMotion(), duration: 0.6, maxZoom,
    paddingTopLeft: [32, 36], paddingBottomRight: [48, 52],
  });
}

function FitIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5" /><path d="m8 15 3-6 5 4" /><circle cx="8" cy="15" r="1" /><circle cx="16" cy="13" r="1" /></svg>;
}

const pinIcon = (role) => L.divIcon({
  className: 'pin-wrap',
  html: `<div class="pin ${role}"><span>${role === 'origin' ? 'A' : 'B'}</span></div>`,
  iconSize: [34, 44],
  iconAnchor: [17, 42],
});

function popupContent(onPick) {
  const box = L.DomUtil.create('div', 'pick-popup');
  const title = L.DomUtil.create('div', 'pick-title', box);
  title.textContent = 'Plan from or to here';
  const row = L.DomUtil.create('div', 'pick-row', box);
  const a = L.DomUtil.create('button', 'pick-btn origin', row);
  a.innerHTML = '<i></i>Start';
  const b = L.DomUtil.create('button', 'pick-btn destination', row);
  b.innerHTML = '<i></i>Destination';
  a.type = 'button'; b.type = 'button';
  L.DomEvent.on(a, 'click', (e) => { L.DomEvent.stop(e); onPick('origin'); });
  L.DomEvent.on(b, 'click', (e) => { L.DomEvent.stop(e); onPick('destination'); });
  return box;
}

export default function MapView({ network, journey, origin, destination, pickRole, onPick, onCancelPick, onLocate }) {
  const el = useRef(null);
  const map = useRef(null);
  const layers = useRef({});
  const lastJourney = useRef(null);
  const handlers = useRef({ onPick, pickRole });
  handlers.current = { onPick, pickRole };
  const [style, setStyle] = useState('osm');
  const [wheelHint, setWheelHint] = useState(false);
  const [tilesFailed, setTilesFailed] = useState(false);

  // create the map once
  useEffect(() => {
    // The page scrolls past the map to the trip details, so a plain scroll wheel scrolls the page and
    // Ctrl (or Cmd) + scroll zooms the map.
    const m = L.map(el.current, {
      zoomControl: false, attributionControl: true, preferCanvas: true, scrollWheelZoom: false,
      zoomAnimation: allowMotion(), fadeAnimation: allowMotion(), markerZoomAnimation: allowMotion(),
    })
      .setView(DELHI, 11);
    let hintTimer = null;
    const onWheel = (e) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const zoom = m.getZoom() + (e.deltaY < 0 ? 1 : -1);
        m.setZoomAround(m.mouseEventToContainerPoint(e), Math.max(m.getMinZoom(), Math.min(m.getMaxZoom(), zoom)), { animate: allowMotion() });
        setWheelHint(false);
      } else {
        setWheelHint(true);
        clearTimeout(hintTimer);
        hintTimer = setTimeout(() => setWheelHint(false), 1400);
      }
    };
    el.current.addEventListener('wheel', onWheel, { passive: false });
    L.control.zoom({ position: 'bottomright' }).addTo(m);
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(m);
    layers.current.network = L.layerGroup().addTo(m);
    layers.current.journey = L.layerGroup().addTo(m);
    layers.current.pins = new Map();
    m.on('click', (e) => {
      const { onPick: pick, pickRole: role } = handlers.current;
      if (role) {
        pick(role, e.latlng.lat, e.latlng.lng);
        return;
      }
      L.popup({ closeButton: false, className: 'pick-popup-wrap', offset: [0, -4] })
        .setLatLng(e.latlng)
        .setContent(popupContent((r) => { m.closePopup(); handlers.current.onPick(r, e.latlng.lat, e.latlng.lng); }))
        .openOn(m);
    });
    map.current = m;
    const host = el.current;
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => m.invalidateSize({ pan: false })) : null;
    observer?.observe(host);
    return () => { observer?.disconnect(); host.removeEventListener('wheel', onWheel); clearTimeout(hintTimer); m.remove(); map.current = null; };
  }, []);

  // base tiles
  useEffect(() => {
    const m = map.current;
    setTilesFailed(false);
    el.current.dataset.mapStyle = style;
    if (style !== 'osm') return undefined;
    let errors = 0;
    const t = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: OSM_ATTR, maxZoom: 19 });
    t.on('tileerror', () => { errors += 1; if (errors > 6) setTilesFailed(true); });
    t.on('tileload', () => setTilesFailed(false));
    t.addTo(m).bringToBack();
    return () => {
      // Leaflet's remove listener detaches the tile layer's map events.
      t.remove();
      t.off();
    };
  }, [style]);

  // cursor while picking
  useEffect(() => {
    el.current.classList.toggle('picking', Boolean(pickRole));
    map.current.closePopup();
  }, [pickRole]);

  useEffect(() => {
    if (!pickRole) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancelPick();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [pickRole, onCancelPick]);

  // network overlay: boundary, metro lines, stations, model corridor
  useEffect(() => {
    const g = layers.current.network;
    g.clearLayers();
    if (!network) return;
    const dark = style === 'dark';
    L.polygon(network.boundary, { color: dark ? '#758BA6' : '#15213F', weight: 1.5, opacity: dark ? 0.6 : 0.45, dashArray: '2 6', fill: false, interactive: false }).addTo(g);
    const dim = Boolean(journey);
    network.metro_lines.forEach((line) => {
      L.polyline(line.points, { color: line.color, weight: dim ? 2 : 3, opacity: dim ? 0.22 : 0.7, interactive: false }).addTo(g);
    });
    network.stations.forEach((s) => {
      const mk = L.circleMarker([s.lat, s.lon], {
        radius: s.mode === 'rail' ? 3.4 : 2.8, color: s.mode === 'rail' ? (dark ? '#C59B72' : '#8A5A3B') : (dark ? '#A2B4CB' : '#15213F'), weight: 1.2,
        fillColor: s.mode === 'rail' ? (dark ? '#C59B72' : '#8A5A3B') : (dark ? '#15263B' : '#FFFFFF'), fillOpacity: dim ? 0.5 : 1, opacity: dim ? 0.35 : 0.9,
      });
      mk.bindTooltip(`${s.name} · ${s.mode === 'rail' ? 'Railway station' : 'Metro station'}`, { direction: 'top', className: 'map-tip' });
      mk.addTo(g);
    });
    if (network.corridor) {
      L.polyline(network.corridor.path, { color: dark ? '#0B1627' : '#15213F', weight: 8, opacity: dim ? 0.15 : 0.7, interactive: false }).addTo(g);
      L.polyline(network.corridor.path, { color: ML, weight: 3.5, opacity: dim ? 0.4 : 1, dashArray: '6 6' })
        .bindTooltip(`Bus-model stretch: Outer Ring Road eastbound, Chirag Delhi to Nehru Place (buses ${network.corridor.routes.join(', ')})`,
          { sticky: true, className: 'map-tip' })
        .addTo(g);
    }
  }, [network, journey, style]);

  // journey
  useEffect(() => {
    const g = layers.current.journey;
    g.clearLayers();
    const changedSelection = lastJourney.current !== journey;
    lastJourney.current = journey;
    if (!journey) return;
    const dark = style === 'dark';
    const highlights = [];
    journey.legs.forEach((leg) => {
      if (leg.type === 'walk') {
        L.polyline(leg.path, { color: dark ? '#C4D0E1' : '#4A5470', weight: 4, opacity: 0.95, dashArray: '1 8', lineCap: 'round' })
          .bindTooltip(`Walk ${leg.distance_m} m · ${Math.round(leg.minutes)} min`, { sticky: true, className: 'map-tip' }).addTo(g);
        return;
      }
      if (changedSelection && allowMotion()) {
        highlights.push(L.polyline(leg.path, {
          color: leg.color, weight: 24, opacity: 0.3, lineCap: 'round', lineJoin: 'round', interactive: false,
        }).addTo(g));
      }
      L.polyline(leg.path, { color: dark ? '#091321' : '#FFFFFF', weight: 12, opacity: 0.95, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(g);
      L.polyline(leg.path, { color: leg.color, weight: 6.5, opacity: 1, lineCap: 'round', lineJoin: 'round' })
        .bindTooltip(`${leg.mode_label} ${leg.route} · ${leg.from.name} → ${leg.to.name} · ${leg.depart}–${leg.arrive}`, { sticky: true, className: 'map-tip' })
        .addTo(g);
      if (leg.bus_model?.applied && leg.bus_model.path_range) {
        const [i0, i1] = leg.bus_model.path_range;
        L.polyline(leg.path.slice(i0, i1 + 1), { color: ML, weight: 3, opacity: 1, dashArray: '6 6', lineCap: 'butt' })
          .bindTooltip(`ML estimate: ${leg.bus_model.model_minutes} min on this stretch (timetable ${leg.bus_model.timetable_minutes} min)`, { sticky: true, className: 'map-tip' })
          .addTo(g);
      }
      leg.path.slice(1, -1).forEach((p, i) => {
        L.circleMarker(p, { radius: 2.4, color: leg.color, weight: 1.2, fillColor: dark ? '#0D1B2E' : '#FFFFFF', fillOpacity: 1 })
          .bindTooltip(leg.stop_names[i + 1], { className: 'map-tip' }).addTo(g);
      });
      [[leg.from, leg.depart, 'Board'], [leg.to, leg.arrive, 'Get off']].forEach(([p, t, what]) => {
        L.circleMarker([p.lat, p.lon], { radius: 6.5, color: dark ? '#0A1424' : '#15213F', weight: 2.5, fillColor: '#FFFFFF', fillOpacity: 1 })
          .bindTooltip(`<b>${what}</b> ${leg.mode_label} ${leg.route}<br>${p.name} · ${t}`, { direction: 'top', className: 'map-tip' })
          .addTo(g);
      });
    });
    // A short Canvas halo makes a newly selected route easy to identify without
    // implying live vehicle movement. It runs once and respects reduced motion.
    if (!highlights.length) return undefined;
    let animation;
    const started = performance.now();
    const emphasize = (now) => {
      const progress = Math.min((now - started) / 650, 1);
      if (progress === 1 || !allowMotion()) {
        highlights.forEach((line) => g.removeLayer(line));
        return;
      }
      highlights.forEach((line) => line.setStyle({ opacity: 0.3 * (1 - progress), weight: 24 - progress * 10 }));
      animation = requestAnimationFrame(emphasize);
    };
    animation = requestAnimationFrame(emphasize);
    return () => cancelAnimationFrame(animation);
  }, [journey, style]);

  // Changing the base map keeps the user's zoom and position; only selecting a
  // different journey automatically fits its full route.
  useEffect(() => {
    if (journey) fitMap(map.current, journey.legs.flatMap((leg) => leg.path));
  }, [journey]);

  // origin / destination pins (draggable)
  useEffect(() => {
    const pins = layers.current.pins;
    for (const [role, place] of [['origin', origin], ['destination', destination]]) {
      const pin = pins.get(role);
      if (!place) {
        pin?.marker.remove();
        pins.delete(role);
        continue;
      }

      const { lat, lon, name } = place;
      const title = `${role === 'origin' ? 'Start' : 'Destination'}: ${name}`;
      if (pin) {
        // Replacing an icon during animated zoom skips its position transition.
        if (lat !== pin.lat || lon !== pin.lon) {
          pin.marker.setLatLng([lat, lon]);
          pin.lat = lat;
          pin.lon = lon;
        }
        if (pin.marker.options.title !== title) {
          pin.marker.options.title = title;
          pin.marker.getElement()?.setAttribute('title', title);
          pin.marker.setTooltipContent(title);
        }
        continue;
      }

      const marker = L.marker([lat, lon], { icon: pinIcon(role), draggable: true, zIndexOffset: 1000, title });
      marker.bindTooltip(title, { direction: 'top', offset: [0, -38], className: 'map-tip' });
      marker.on('dragend', () => {
        const point = marker.getLatLng();
        handlers.current.onPick(role, point.lat, point.lng);
      });
      marker.addTo(map.current);
      pins.set(role, { marker, lat, lon });
    }
  }, [origin, destination]);

  const originLat = origin?.lat;
  const originLon = origin?.lon;
  const destinationLat = destination?.lat;
  const destinationLon = destination?.lon;

  // An address lookup can change a pin's label without changing its coordinates.
  useEffect(() => {
    if (journey) return;
    const points = [[originLat, originLon], [destinationLat, destinationLon]]
      .filter(([lat, lon]) => lat != null && lon != null);
    const m = map.current;
    if (points.length === 2) fitMap(m, points);
    else if (points.length === 1) m.setView(points[0], Math.max(m.getZoom(), 13), { animate: allowMotion() });
  }, [originLat, originLon, destinationLat, destinationLon, journey]);

  const fitSelection = () => {
    const points = journey?.legs.flatMap((leg) => leg.path) || [origin, destination].filter(Boolean).map((p) => [p.lat, p.lon]);
    fitMap(map.current, points);
  };

  const viewDelhi = () => {
    if (network?.boundary?.length) fitMap(map.current, network.boundary, 11);
    else map.current.setView(DELHI, 11, { animate: allowMotion() });
  };

  const changeStyleWithKeyboard = (event) => {
    const keys = Object.keys(MAP_STYLES);
    const index = keys.indexOf(style);
    let next;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = keys[(index + 1) % keys.length];
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = keys[(index - 1 + keys.length) % keys.length];
    else if (event.key === 'Home') next = keys[0];
    else if (event.key === 'End') next = keys[keys.length - 1];
    else return;
    event.preventDefault();
    setStyle(next);
    event.currentTarget.querySelector(`[data-style="${next}"]`)?.focus();
  };

  const selectedPlaces = [['origin', origin], ['destination', destination]].filter(([, place]) => place);
  const contextHint = journey
    ? `${durationLabel(journey.duration_min)} · ${journey.vehicle_changes === 0 ? 'Direct' : `${journey.vehicle_changes} ${journey.vehicle_changes === 1 ? 'change' : 'changes'}`} · ₹${Number(journey.fare_inr).toLocaleString('en-IN', { maximumFractionDigits: 1 })}`
    : origin && destination ? 'Your places are set. Find routes to compare.'
      : origin ? 'Choose your destination to complete the journey.'
        : destination ? 'Choose your starting point to complete the journey.'
          : 'Click anywhere to set a start or destination.';

  return (
    <div className={`mapview ${journey ? 'has-journey' : ''}`}>
      <header className="map-panel-header">
        <div className="map-panel-heading">
          <span className="map-panel-icon" aria-hidden="true"><MapPickIcon width={19} height={19} /></span>
          <strong>Delhi route map</strong>
        </div>
        <div className="map-tools" role="group" aria-label="Map controls">
          <div className="style-switch" role="radiogroup" aria-label="Map style" onKeyDown={changeStyleWithKeyboard}>
            {Object.entries(MAP_STYLES).map(([key, label]) => (
              <button key={key} type="button" role="radio" aria-checked={style === key} tabIndex={style === key ? 0 : -1} data-style={key}
                title={key === 'osm' ? 'OpenStreetMap streets and places' : 'Transit network without background map tiles'}
                className={style === key ? 'on' : ''} onClick={() => setStyle(key)}>
                {label}
              </button>
            ))}
          </div>
          <span className="map-tool-divider" aria-hidden="true" />
          <button type="button" className="tool-btn map-locate" onClick={onLocate} aria-label="Use my current location as the start" title="Use my current location as the start"><CrosshairIcon width={16} height={16} /><span>Locate me</span></button>
          {(journey || origin || destination) && <button type="button" className="tool-btn fit-route" onClick={fitSelection} aria-label={journey ? 'Fit the selected route in view' : 'Show selected places on the map'} title="Fit the selected journey or places in view"><FitIcon /><span>{journey ? 'Fit route' : 'View points'}</span></button>}
          <button type="button" className="tool-btn map-reset" onClick={viewDelhi} aria-label="Show the whole Delhi service area" title="Show the Delhi service area"><MapPickIcon width={16} height={16} /><span>All Delhi</span></button>
        </div>
      </header>

      <div className="map-canvas">
        <div ref={el} className="leaflet-host" aria-label="Interactive Delhi transport map. Click to choose a start or destination; use arrow keys to pan and plus or minus to zoom." />
        {pickRole && (
          <div className="pick-banner" role="status">
            <span className={`pick-dot ${pickRole}`} />
            Click the map to set the {pickRole === 'origin' ? 'start' : 'destination'}
            <button type="button" onClick={onCancelPick} title="Cancel map selection (Escape)">Cancel</button>
          </div>
        )}
        {wheelHint && <div className="wheel-hint" role="status">Use Ctrl or ⌘ + scroll to zoom</div>}
        {tilesFailed && (
          <div className="tiles-off" role="status"><span>The street map is unavailable. Your routes and stations are still shown.</span><button type="button" className="map-fallback-action" onClick={() => setStyle('dark')}>Use network map</button></div>
        )}
      </div>

      <footer className="map-panel-footer">
        <div className={`map-context ${selectedPlaces.length ? 'has-places' : ''}`} role="status" aria-live="polite" aria-atomic="true">
          {journey && (
            <div className="map-context-heading">
              <span className="map-context-kicker">Selected journey</span>
              <span className="map-context-provider">{journey.leave}–{journey.arrive}</span>
            </div>
          )}
          {selectedPlaces.length > 0 && (
            <div className="map-context-places">
              {selectedPlaces.map(([role, place]) => (
                <div key={role} className="map-context-place">
                  <span className={`map-place-marker ${role}`} aria-label={role === 'origin' ? 'Start' : 'Destination'}>{role === 'origin' ? 'A' : 'B'}</span>
                  <strong title={place.name}>{place.name}</strong>
                </div>
              ))}
            </div>
          )}
          <span className={`map-context-subtitle ${journey ? 'map-route-facts' : ''}`}>{contextHint}</span>
        </div>
        <div className="map-key" role="group" aria-label="Map legend">
          <span><i className="k-pin a" aria-hidden="true">A</i>Start</span>
          <span><i className="k-pin b" aria-hidden="true">B</i>Destination</span>
          <span><i className="k-walk" aria-hidden="true" />Walk</span>
          <span title="Metro station"><i className="k-station" aria-hidden="true" />Metro</span>
          <span title="Railway station"><i className="k-rail" aria-hidden="true" />Rail</span>
          {journey?.legs.some((l) => l.mode === 'cab') && <span><i className="k-cab" aria-hidden="true" />Cab</span>}
          {network?.corridor && <span title="Bus travel-time model on the supported Outer Ring Road stretch"><i className="k-model" aria-hidden="true" />ML bus segment</span>}
        </div>
      </footer>
    </div>
  );
}
