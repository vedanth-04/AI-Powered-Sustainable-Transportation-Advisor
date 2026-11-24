import { useEffect, useId, useRef, useState } from 'react';
import { searchPlaces } from '../api.js';
import { CrosshairIcon, MapPickIcon, ModeIcon, PinIcon, XIcon } from './icons.jsx';

const ICON_MODE = { metro: 'metro', rail: 'rail', bus: 'bus' };

function KindIcon({ place }) {
  if (ICON_MODE[place.mode]) return <ModeIcon mode={place.mode} width={15} height={15} />;
  return <PinIcon width={15} height={15} />;
}

export default function PlaceInput({ role, label, value, onChange, onPickOnMap, picking, onLocate, placeholder }) {
  const [text, setText] = useState(value?.name || '');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(null);
  const listId = useId();
  const box = useRef(null);
  const input = useRef(null);
  const editingSelection = useRef(false);

  useEffect(() => {
    if (editingSelection.current && !value) {
      editingSelection.current = false;
      return;
    }
    setText(value?.name || '');
  }, [value]);

  useEffect(() => {
    const q = text.trim();
    if (!open || q.length < 2 || (value && text === value.name)) {
      setResults([]);
      return undefined;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setBusy(true);
      try {
        const body = await searchPlaces(q, controller.signal);
        setResults(body.results);
        setOnline(body.online);
        setActive(0);
      } catch (err) {
        if (err.name !== 'AbortError') setResults([]);
      } finally {
        setBusy(false);
      }
    }, 220);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [text, open, value]);

  useEffect(() => {
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false);
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const choose = (place) => {
    onChange(place);
    setText(place.name);
    setOpen(false);
    setResults([]);
  };

  const onKey = (e) => {
    if (e.key === 'Escape') { setOpen(false); return; }
    if (!open || !results.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(results.length - 1, a + 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    if (e.key === 'Enter') { e.preventDefault(); choose(results[active]); }
  };

  const q = text.trim();
  const showEmpty = open && !busy && q.length >= 2 && !(value && text === value.name) && results.length === 0;
  const showHelp = open && q.length < 2 && !value;

  return (
    <div className={`place ${picking ? 'picking' : ''}`} ref={box}>
      <div className="place-row">
        <span className={`place-pin ${role}`}>{role === 'origin' ? 'A' : 'B'}</span>
        <div className="place-field">
          <span className="place-label" aria-hidden="true">{label}</span>
          <input
            ref={input}
            value={text}
            placeholder={placeholder}
            aria-label={label}
            onChange={(e) => {
              setText(e.target.value);
              setOpen(true);
              if (value) {
                editingSelection.current = true;
                onChange(null);
              }
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKey}
            role="combobox"
            aria-expanded={open && results.length > 0}
            aria-controls={open && results.length > 0 ? listId : undefined}
            aria-activedescendant={open && results[active] ? `${listId}-${active}` : undefined}
            aria-autocomplete="list"
          />
          {value?.detail && text === value.name && <div className="place-detail">{value.detail}</div>}
          {value && value.inside_delhi === false && <div className="place-warn">Outside Delhi - not covered</div>}
        </div>
        {busy && <span className="spinner small" aria-label="Searching" />}
        {value && (
          <button type="button" className="icon-btn" aria-label={`Clear ${label}`} onClick={() => { onChange(null); setText(''); input.current?.focus(); }}>
            <XIcon width={15} height={15} />
          </button>
        )}
        <button type="button" className={`icon-btn ${picking ? 'on' : ''}`} title="Choose on the map" aria-label={`Choose ${label} on the map`}
                onClick={onPickOnMap}>
          <MapPickIcon width={17} height={17} />
        </button>
      </div>

      {open && (results.length > 0 || showEmpty || showHelp) && (
        <ul className="suggestions" id={listId} role="listbox">
          {showHelp && (
            <>
              {role === 'origin' && (
                <li role="option" aria-selected="false" className="special" onMouseDown={(e) => { e.preventDefault(); setOpen(false); onLocate(); }}>
                  <span className="s-icon loc"><CrosshairIcon width={15} height={15} /></span>
                  <span className="s-main"><span className="s-name">Use my current location</span><span className="s-detail">Needs location permission in the browser</span></span>
                </li>
              )}
              <li role="option" aria-selected="false" className="special" onMouseDown={(e) => { e.preventDefault(); setOpen(false); onPickOnMap(); }}>
                <span className="s-icon"><MapPickIcon width={15} height={15} /></span>
                <span className="s-main"><span className="s-name">Choose on the map</span><span className="s-detail">Click anywhere in Delhi</span></span>
              </li>
              <li className="hint">Type a locality, landmark, market, hospital, college or address - e.g. “Lajpat Nagar”, “India Gate”, “AIIMS”.</li>
            </>
          )}
          {results.map((p, i) => (
            <li key={`${p.id}-${i}`} id={`${listId}-${i}`} role="option" aria-selected={i === active} className={i === active ? 'active' : ''}
                onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); choose(p); }}>
              <span className={`s-icon ${p.mode}`}><KindIcon place={p} /></span>
              <span className="s-main">
                <span className="s-name">{p.name}</span>
                <span className="s-detail">{p.detail || p.kind}</span>
              </span>
              <span className={`s-kind ${p.source === 'OpenStreetMap' ? 'osm' : ''}`}>{p.kind}</span>
            </li>
          ))}
          {showEmpty && (
            <li className="hint">
              Nothing found for “{q}”.{online && online !== 'ready' ? ' Online place search is unavailable, so only Delhi localities and stations are searched.' : ''} You can also choose the point on the map.
            </li>
          )}
          {results.length > 0 && online && online !== 'ready' && (
            <li className="hint small">Offline search: localities and stations only (online search {online}).</li>
          )}
        </ul>
      )}
    </div>
  );
}
