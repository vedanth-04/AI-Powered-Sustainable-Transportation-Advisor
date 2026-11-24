import { useCallback, useEffect, useRef, useState } from 'react';
import { getHealth, getNetwork, planJourney, reverseGeocode, searchPlaces } from './api.js';
import PlaceInput from './components/PlaceInput.jsx';
import MapView from './components/MapView.jsx';
import InfoPanel from './components/InfoPanel.jsx';
import { Estimates, FareTable, Itinerary, LegBar, OptionRow, RoutePicker, Summary, Why } from './components/Journey.jsx';
import { ChevronDownIcon, ClockIcon, InfoIcon, LeafIcon, MapPickIcon, ModeIcon, PinIcon, SwapIcon } from './components/icons.jsx';

const PRIORITIES = [
  { key: 'balanced', label: 'Balanced', hint: 'Affordable first, then time and changes' },
  { key: 'cheapest', label: 'Cheapest', hint: 'Lowest fare wins' },
  { key: 'fastest', label: 'Fastest', hint: 'Shortest door-to-door time' },
  { key: 'greenest', label: 'Greenest', hint: 'Lowest CO₂' },
];
const SOURCE_TEXT = { registry_champion: 'registry champion', deployed_service: 'deployed API', approved_bundle: 'approved bundle' };
const EXAMPLES = [['Lajpat Nagar', 'Karol Bagh'], ['Rohini', 'Hauz Khas'], ['Chirag Delhi', 'Kalkaji']];
const MODES = [['bus', 'Bus'], ['metro', 'Metro'], ['rail', 'Train'], ['cab', 'Cab']];

function nowIST() {
  const d = new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);
  const pad = (n) => String(n).padStart(2, '0');
  return { date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, time: `${pad(d.getHours())}:${pad(d.getMinutes())}` };
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  const [network, setNetwork] = useState(null);
  const [origin, setOrigin] = useState(null);
  const [destination, setDestination] = useState(null);
  const start = nowIST();
  const [date, setDate] = useState(start.date);
  const [time, setTime] = useState(start.time);
  const [budget, setBudget] = useState('');
  const [priority, setPriority] = useState('balanced');
  const [women, setWomen] = useState(false);
  const [card, setCard] = useState(false);
  const [walk, setWalk] = useState(1000);
  const [modes, setModes] = useState({ bus: true, metro: true, rail: true, cab: true });
  const [cabType, setCabType] = useState('taxi_ac');
  const toggleMode = (m) => setModes((cur) => {
    const next = { ...cur, [m]: !cur[m] };
    return Object.values(next).some(Boolean) ? next : cur; // keep at least one mode
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(0);
  const [pickRole, setPickRole] = useState(null);
  const [showInfo, setShowInfo] = useState(false);
  const [toast, setToast] = useState(null);
  const [exampleLoading, setExampleLoading] = useState(null);
  const tripRef = useRef(null);
  const topRef = useRef(null);
  const mapRef = useRef(null);
  const resultsRef = useRef(null);
  const reduceMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const scrollToTrip = () => tripRef.current?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  const scrollToTop = () => topRef.current?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  const toggleMapPick = (role) => {
    const next = pickRole === role ? null : role;
    setPickRole(next);
    if (next && window.matchMedia('(max-width: 900px)').matches) {
      mapRef.current?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    }
  };

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setHealthError(e));
    getNetwork().then(setNetwork).catch(() => {});
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 4200);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    if (!result) return;
    resultsRef.current?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }, [result, reduceMotion]);

  // a changed start or destination makes the old results stale
  const setPlace = useCallback((role, place) => {
    (role === 'origin' ? setOrigin : setDestination)(place);
    setResult(null);
    setError(null);
  }, []);

  const pickPoint = useCallback(async (role, lat, lon) => {
    setPickRole(null);
    setPlace(role, { name: 'Finding the address…', detail: `${lat.toFixed(5)}, ${lon.toFixed(5)}`, lat, lon, kind: 'Map point' });
    try {
      const r = await reverseGeocode(lat, lon);
      setPlace(role, {
        name: r.name, lat, lon, kind: 'Map point', inside_delhi: r.inside_delhi,
        detail: r.detail || (r.nearest_stop ? `${r.nearest_stop.distance_m} m from ${r.nearest_stop.name}` : 'Point on the map'),
      });
      if (!r.inside_delhi) setToast('That point is outside Delhi. Routes are planned inside the NCT of Delhi only.');
    } catch {
      setPlace(role, { name: `${lat.toFixed(5)}, ${lon.toFixed(5)}`, detail: 'Point on the map', lat, lon, kind: 'Map point' });
    }
  }, [setPlace]);

  const locate = useCallback(() => {
    if (!navigator.geolocation) { setToast('This browser cannot share your location.'); return; }
    setToast('Finding your location…');
    navigator.geolocation.getCurrentPosition(
      (pos) => { setToast(null); pickPoint('origin', pos.coords.latitude, pos.coords.longitude); },
      (err) => setToast(`Location unavailable (${err.message}). Choose the start on the map instead.`),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, [pickPoint]);

  const swap = () => { const o = origin; setPlace('origin', destination); setPlace('destination', o); };

  const loadExample = async (a, b) => {
    setExampleLoading(a);
    try {
      const [ra, rb] = await Promise.all([searchPlaces(a), searchPlaces(b)]);
      if (!ra.results[0] || !rb.results[0]) throw new Error('Example stops unavailable');
      setPlace('origin', ra.results[0]);
      setPlace('destination', rb.results[0]);
    } catch {
      setToast('Could not load those example stops. Search for them or choose them on the map.');
    } finally {
      setExampleLoading(null);
    }
  };

  const submit = async (e) => {
    e?.preventDefault();
    setError(null);
    if (!origin || !destination) {
      setError({ message: 'Add a start and a destination: type a place name or click the map.' });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const body = await planJourney({
        origin: { lat: origin.lat, lon: origin.lon, label: origin.name },
        destination: { lat: destination.lat, lon: destination.lon, label: destination.name },
        depart: `${date}T${time}`, budget_inr: budget === '' ? null : Number(budget), priority,
        women_free_bus: women, smart_card: card, max_walk_m: walk,
        modes: Object.keys(modes).filter((m) => modes[m]), cab_type: cabType,
      });
      setResult(body);
      setSelected(0);
    } catch (err) {
      setResult(null);
      setError({ message: err.message, hint: err.hint });
    } finally {
      setLoading(false);
    }
  };

  const journey = result?.journeys?.[selected];
  const bm = health?.bus_model;

  return (
    <div className="app" id="advisor-top">
      <header className="top">
        <a href="#advisor-top" className="brand" aria-label="Delhi Commute Advisor home">
          <span className="brand-icon"><ModeIcon mode="metro" width={23} height={23} /></span>
          <span className="wordmark" lang="hi">सफ़र</span>
          <span className="brand-text">
            <span className="brand-name">Delhi Commute Advisor</span>
          </span>
        </a>
        <nav className="advisor-nav" aria-label="Advisor">
          <a href="#planner" className="nav-link on">Journey planner</a>
          <a href="#examples" className="nav-link">Sample trips</a>
        </nav>
        <div className="top-right">
          {bm && (
            <button type="button" className={`status ${bm.available ? 'on' : 'off'}`} onClick={() => setShowInfo(true)} title={bm.detail}>
              <span className="dot" />
              {bm.available ? `Bus model v${bm.version} · ${SOURCE_TEXT[bm.active_source] || 'available'}` : 'Bus timetables only'}
            </button>
          )}
          {health && health.geocoder.state !== 'ready' && <span className="status warn"><span className="dot" />Offline place search</span>}
          <button type="button" className="outline" disabled={!health} onClick={() => setShowInfo(true)}><InfoIcon width={17} height={17} /> How it works</button>
        </div>
      </header>

      {healthError && (
        <div className="notice bad banner">
          <strong>The advisor backend is not ready.</strong> {healthError.message}
          {healthError.hint && <code>{healthError.hint}</code>}
        </div>
      )}

      <main className="content">
        <section className="hero" aria-labelledby="page-title">
          <div className="hero-copy">
            <p className="hero-location"><PinIcon width={16} height={16} /> Delhi, India</p>
            <h1 id="page-title">Plan your trip <em>across Delhi.</em></h1>
            <p className="hero-description">Compare bus, metro, train, and cab routes by travel time, fare, and estimated emissions.</p>
          </div>
          <div className="hero-photo" aria-hidden="true" />
        </section>

        <div id="planner" className="shell" ref={topRef}>
        <aside className="sidebar">
            <form className="planner" onSubmit={submit} aria-busy={loading}>
              <div className="planner-heading">
                <span className="planner-icon"><MapPickIcon width={22} height={22} /></span>
                <div><h2>Plan a journey</h2><p>Enter a start and destination.</p></div>
              </div>
              <div className="signboard">
                <PlaceInput role="origin" label="Start" value={origin} onChange={(p) => setPlace('origin', p)}
                            placeholder="Choose your starting point" picking={pickRole === 'origin'}
                            onPickOnMap={() => toggleMapPick('origin')} onLocate={locate} />
                <div className="sign-link">
                  <span className="sign-dots" />
                  <button type="button" className="swap" onClick={swap} aria-label="Swap start and destination" title="Swap"><SwapIcon width={16} height={16} /></button>
                </div>
                <PlaceInput role="destination" label="Destination" value={destination} onChange={(p) => setPlace('destination', p)}
                            placeholder="Where are you going?" picking={pickRole === 'destination'}
                            onPickOnMap={() => toggleMapPick('destination')} onLocate={locate} />
              </div>

              <div className="settings">
                <div className="set-row">
                  <span className="set-label"><ClockIcon width={15} height={15} /> Departure <span className="tz-label">IST</span></span>
                  <div className="set-ctrl when">
                    <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required aria-label="Date" />
                    <input type="time" value={time} onChange={(e) => setTime(e.target.value)} required aria-label="Departure time (IST)" />
                    <button type="button" className="text-btn" onClick={() => { const n = nowIST(); setDate(n.date); setTime(n.time); }}>Now</button>
                  </div>
                </div>
                <div className="set-row">
                  <span className="set-label">Maximum fare</span>
                  <div className="set-ctrl budget">
                    <label className="rupee-field">
                      <span aria-hidden="true">₹</span>
                      <input type="number" min="0" step="1" inputMode="numeric" placeholder="Any" value={budget}
                             onChange={(e) => setBudget(e.target.value)} aria-label="Maximum fare in rupees" />
                    </label>
                    {[20, 40, 60].map((v) => (
                      <button type="button" key={v} aria-pressed={budget !== '' && Number(budget) === v} className={`pill ${budget !== '' && Number(budget) === v ? 'on' : ''}`} onClick={() => setBudget(String(v))}>₹{v}</button>
                    ))}
                    <button type="button" aria-pressed={budget === ''} className={`pill ${budget === '' ? 'on' : ''}`} onClick={() => setBudget('')}>Any</button>
                  </div>
                </div>
                <div className="set-row">
                  <span className="set-label">Transport modes</span>
                  <div className="set-ctrl modes" role="group" aria-label="Allowed modes">
                    {MODES.map(([m, label]) => (
                      <button key={m} type="button" aria-pressed={modes[m]} className={`mode-toggle ${modes[m] ? 'on' : ''}`} onClick={() => toggleMode(m)}>
                        <ModeIcon mode={m} width={15} height={15} />{label}
                      </button>
                    ))}
                  </div>
                </div>
                <details className="more">
                  <summary>Trip preferences <ChevronDownIcon width={16} height={16} /></summary>
                  <div className="preference-fields">
                    <div className="set-row">
                      <span className="set-label">Rank routes by</span>
                      <div className="set-ctrl seg" role="group" aria-label="Route preference">
                        {PRIORITIES.map((p) => (
                          <button type="button" key={p.key} aria-pressed={priority === p.key} title={p.hint}
                                  className={priority === p.key ? 'on' : ''} onClick={() => setPriority(p.key)}>{p.label}</button>
                        ))}
                      </div>
                    </div>
                    {modes.cab && (
                      <div className="set-row">
                        <span className="set-label">Cab type</span>
                        <div className="set-ctrl seg cabtype" role="group" aria-label="Cab type">
                          {[['taxi_ac', 'AC taxi'], ['taxi_non_ac', 'Non-AC taxi'], ['auto', 'Auto']].map(([k, label]) => (
                            <button key={k} type="button" aria-pressed={cabType === k} className={cabType === k ? 'on' : ''} onClick={() => setCabType(k)}>{label}</button>
                          ))}
                        </div>
                      </div>
                    )}
                    <label className="check"><input type="checkbox" checked={women} onChange={(e) => setWomen(e.target.checked)} /> Women travel free on DTC and cluster buses</label>
                    <label className="check"><input type="checkbox" checked={card} onChange={(e) => setCard(e.target.checked)} /> I pay the metro with a smart card (10% off)</label>
                    <label className="range"><span>Longest walk to a stop: <b>{walk} m</b></span>
                      <input type="range" min="300" max="2000" step="100" value={walk} onChange={(e) => setWalk(Number(e.target.value))} />
                    </label>
                  </div>
                </details>
              </div>

              <button type="submit" className="go" disabled={loading || exampleLoading !== null}>
                {loading ? <><span className="spinner" /> Finding routes…</> : <><MapPickIcon width={19} height={19} /> Find routes</>}
              </button>
            </form>

          {error && (
            <div className="notice bad" role="alert">
              <strong>{error.message}</strong>
              {error.hint && <span>{error.hint}</span>}
            </div>
          )}
        </aside>

        <section className="mapcol" ref={mapRef} aria-label="Delhi route map">
          <MapView network={network} journey={journey} origin={origin} destination={destination}
                   pickRole={pickRole} onPick={pickPoint} onCancelPick={() => setPickRole(null)} onLocate={locate} />
          {loading && <div className="map-loading" role="status"><span className="spinner small" /> Comparing routes</div>}
        </section>
        </div>

        <div className="after-planner">
          {result && (
            <section className="results" ref={resultsRef} aria-label="Route options">
              <div className="results-head">
                <div><h2>Compare routes</h2><span>{result.journeys.length} {result.journeys.length === 1 ? 'option' : 'options'} · {result.query.weekday}</span></div>
                {journey && <button type="button" className="outline" onClick={scrollToTrip}>View itinerary <ChevronDownIcon width={16} height={16} /></button>}
              </div>
              {result.budget_status && (
                <div className={`notice ${result.budget_status.ok ? 'good' : 'warn'}`}>{result.budget_status.message}</div>
              )}
              {result.notes.map((n, i) => <div key={i} className="notice info"><InfoIcon width={15} height={15} /><span>{n}</span></div>)}
              <ol className="options">
                {result.journeys.map((j, i) => (
                  <OptionRow key={j.id} index={i} journey={j} selected={i === selected} budget={result.query.budget_inr}
                             onSelect={() => setSelected(i)} />
                ))}
              </ol>
            </section>
          )}

          <section className="intro" id="examples" aria-labelledby="examples-title">
            <h2 id="examples-title">Try a sample trip</h2>
            <div className="examples">
              {EXAMPLES.map(([a, b]) => (
                <button key={a} type="button" disabled={loading || exampleLoading !== null} onClick={() => { loadExample(a, b); scrollToTop(); }}>
                  <span className="example-icon">{exampleLoading === a ? <span className="spinner small" /> : <PinIcon width={19} height={19} />}</span>
                  <span>{a} to <strong>{b}</strong></span>
                </button>
              ))}
            </div>
          </section>
        </div>
      </main>

      {result && journey && (
        <section className="trip" ref={tripRef} aria-label="Trip details">
          <div className="trip-inner">
            <div className="trip-top">
              <div className="trip-heading">
                <p className="trip-count">Route {selected + 1} of {result.journeys.length}{journey.tags.includes('recommended') ? ', recommended' : ''}</p>
                <h2>{result.query.origin.label}<span> to </span>{result.query.destination.label}</h2>
                <p className="trip-when">{result.query.weekday}: leave {journey.leave}, arrive {journey.arrive}</p>
              </div>
              <button type="button" className="outline back-map" onClick={scrollToTop}><MapPickIcon width={18} height={18} /> Back to the map</button>
            </div>
            {result.journeys.length > 1 && <RoutePicker journeys={result.journeys} selected={selected} onSelect={setSelected} />}
            <LegBar journey={journey} />
            <Summary journey={journey} carKg={result.car_baseline_kg_co2} />
            <div className="trip-grid">
              <div className="trip-main">
                <Itinerary journey={journey} destination={result.query.destination.label} />
              </div>
              <aside className="trip-side">
                <Why journey={journey} />
                <FareTable journey={journey} budget={result.query.budget_inr} />
                <Estimates journey={journey} />
              </aside>
            </div>
            <p className="fineprint">
              All times are estimates. Bus times come from the Delhi bus timetable, which assumes a constant speed, except on the Outer Ring Road segment where the ML bus model is used. Metro times come from the DMRC timetable and train times from a 2016 timetable. Cab times come from OpenStreetMap road routing times a Delhi traffic factor, plus an assumed pickup wait. Walking, waiting and interchange times follow fixed rules.
              Fares use DMRC slabs (Aug 2025), official bus stage fares, an assumed ordinary rail fare and indicative Delhi meter fares for cabs.
            </p>
          </div>
        </section>
      )}

      <footer className="advisor-footer">
        <span><LeafIcon width={17} height={17} /> Delhi Commute Advisor</span>
        <span>Travel times, fares and emissions are estimates.</span>
      </footer>

      {toast && <div className="toast" role="status">{toast}</div>}
      {showInfo && health && <InfoPanel health={health} date={date} onClose={() => setShowInfo(false)} />}
    </div>
  );
}
