import { useEffect, useMemo, useState } from 'react';
import { getModel } from '../api.js';
import { XIcon } from './icons.jsx';

const SOURCE_LABEL = {
  registry_champion: 'Phase 3 registry champion',
  deployed_service: 'Deployed Docker API',
  approved_bundle: 'Phase 2 approved bundle',
  all: 'Bus model',
};

function ProfileChart({ profile, timetable }) {
  const [hover, setHover] = useState(null);
  const pts = profile.filter((p) => p.minutes != null);
  if (pts.length < 2) return null;
  const W = 640, H = 220, L = 40, R = 16, T = 16, B = 30;
  const toMin = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
  const x0 = toMin(pts[0].time), x1 = toMin(pts[pts.length - 1].time);
  const vals = pts.map((p) => p.minutes).concat(timetable ? [timetable] : []);
  const yMax = Math.ceil(Math.max(...vals) * 1.15), yMin = 0;
  const sx = (t) => L + ((toMin(t) - x0) / (x1 - x0)) * (W - L - R);
  const sy = (v) => T + (1 - (v - yMin) / (yMax - yMin)) * (H - T - B);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p.time).toFixed(1)},${sy(p.minutes).toFixed(1)}`).join('');
  const area = `${line}L${sx(pts.at(-1).time)},${sy(0)}L${sx(pts[0].time)},${sy(0)}Z`;
  const ticks = [];
  for (let v = 0; v <= yMax; v += yMax > 20 ? 5 : 2) ticks.push(v);
  const hours = [6, 9, 12, 15, 18, 21].filter((h) => h * 60 >= x0 && h * 60 <= x1);
  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * W;
    let best = 0;
    pts.forEach((p, i) => { if (Math.abs(sx(p.time) - x) < Math.abs(sx(pts[best].time) - x)) best = i; });
    setHover(best);
  };
  const h = hover != null ? pts[hover] : null;
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img"
           aria-label="Predicted travel time on the Outer Ring Road segment by time of day">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} className="grid" />
            <text x={L - 8} y={sy(v) + 4} className="tick" textAnchor="end">{v}</text>
          </g>
        ))}
        {hours.map((hh) => (
          <text key={hh} x={sx(`${String(hh).padStart(2, '0')}:00`)} y={H - 8} className="tick" textAnchor="middle">{`${String(hh).padStart(2, '0')}:00`}</text>
        ))}
        <path d={area} className="area" />
        <path d={line} className="series" />
        {timetable && (
          <g>
            <line x1={L} x2={W - R} y1={sy(timetable)} y2={sy(timetable)} className="ref" />
            <text x={W - R} y={sy(timetable) - 6} textAnchor="end" className="ref-label">Timetable {timetable} min</text>
          </g>
        )}
        {h && (
          <g>
            <line x1={sx(h.time)} x2={sx(h.time)} y1={T} y2={H - B} className="cross" />
            <circle cx={sx(h.time)} cy={sy(h.minutes)} r="4.5" className="dot" />
          </g>
        )}
      </svg>
      {h && (
        <div className="chart-tip" style={{ left: `${(sx(h.time) / W) * 100}%` }}>
          <b>{h.time}</b> · model {h.minutes.toFixed(1)} min{timetable ? ` · timetable ${timetable} min` : ''}
        </div>
      )}
    </div>
  );
}

export default function InfoPanel({ health, date, onClose }) {
  const [tab, setTab] = useState('method');
  const [model, setModel] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    getModel(date).then(setModel).catch((e) => setErr(e.message));
  }, [date]);
  const a = health.assumptions;
  const f = a.fares;
  const bm = model || health.bus_model;
  const range = useMemo(() => {
    const p = (model?.profile || []).filter((x) => x.minutes != null);
    if (!p.length) return null;
    const lo = p.reduce((m, x) => (x.minutes < m.minutes ? x : m)), hi = p.reduce((m, x) => (x.minutes > m.minutes ? x : m));
    return { lo, hi };
  }, [model]);

  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="How the advisor works">
        <div className="modal-head">
          <div className="tabs" role="tablist">
            {[['method', 'Prediction method'], ['data', 'Data sources'], ['assume', 'Assumptions']].map(([k, l]) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
            ))}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><XIcon /></button>
        </div>

        {tab === 'method' && (
          <div className="modal-body">
            <div className="method-flow">
              <div className="mf-card"><div className="mf-k">Metro & trains</div><div className="mf-v">Timetables</div><p>DMRC GTFS and the Indian Railways timetable. Fixed schedules on segregated track barely vary, so a timetable is the right estimator; no observed trip-time data exists to train on.</p></div>
              <div className="mf-card ml"><div className="mf-k">Buses on Outer Ring Road (eastbound)</div><div className="mf-v">ML model</div><p>Gradient-boosted travel-time model, used only on its approved segment Chirag Delhi → Nehru Place, with the entry time the bus reaches the segment.</p></div>
              <div className="mf-card"><div className="mf-k">All other buses</div><div className="mf-v">Timetable</div><p>OTD bus GTFS. OTD generated these times assuming constant speed, so they are labelled as schedule estimates.</p></div>
              <div className="mf-card"><div className="mf-k">Cabs and autos</div><div className="mf-v">Road routing + rules</div><p>OpenStreetMap road routing (OSRM), stretched by a Delhi traffic factor for the hour, plus an assumed pickup wait. Indicative meter fares; availability is not checked.</p></div>
              <div className="mf-card"><div className="mf-k">Walking, waiting, interchanges</div><div className="mf-v">Rules</div><p>Straight-line distance × {a.walking.detour_factor} at {a.walking.speed_kmh} km/h; waits come from the timetable; fixed entry and interchange buffers.</p></div>
            </div>

            <h4>Which model is used, and why it is trusted</h4>
            <ol className="chain">
              {(bm.sources || []).map((s, i) => (
                <li key={s.source} className={s.ok ? (bm.active_source === s.source ? 'active' : 'ok') : 'off'}>
                  <span className="chain-n">{i + 1}</span>
                  <div>
                    <div className="chain-title">{SOURCE_LABEL[s.source] || s.source}
                      {bm.active_source === s.source && <span className="badge-on">in use</span>}
                      {!s.ok && <span className="badge-off">unavailable</span>}
                      {s.ok && bm.active_source !== s.source && <span className="badge-off">standby</span>}
                    </div>
                    <div className="chain-detail">{s.detail}</div>
                  </div>
                </li>
              ))}
            </ol>
            <p className="small muted">The first source that passes its checks is used: the registry champion needs a valid hash-chained audit log, an approved status, a passed promotion gate and an artifact hash equal to the registry record; bundles are loaded read-only with the project's own loader (scikit-learn version, feature schema, checksum). Features are built exactly as in the serving API (cold_start_v1).</p>
            {bm.parity && (
              <div className={`parity ${bm.parity.ok === true ? 'good' : bm.parity.ok === false ? 'bad' : 'warn'}`}>
                <b>Parity check:</b> {bm.parity.detail}{bm.parity.ok === true ? ' - identical to the deployed model.' : ''}
              </div>
            )}

            <h4>Predicted time on the segment through the day ({date})</h4>
            {err && <div className="callout bad">{err}</div>}
            {model && model.available && model.profile?.length > 0 ? (
              <>
                <ProfileChart profile={model.profile} timetable={model.timetable_minutes} />
                <p className="small muted">
                  Full gate-to-gate segment ({model.segment_km} km). {range && <>Fastest {range.lo.minutes.toFixed(1)} min at {range.lo.time}, slowest {range.hi.minutes.toFixed(1)} min at {range.hi.time}. </>}
                  {model.typical_error_min ? <>Typical error on this segment in the holdout: ±{model.typical_error_min} min (MAE). </> : null}
                  The timetable line is the OTD schedule for the same stretch.
                </p>
              </>
            ) : (
              <div className="callout warn">{bm.detail}</div>
            )}
          </div>
        )}

        {tab === 'data' && (
          <div className="modal-body">
            <div className="source-grid">
              {health.sources.map((s) => (
                <div key={s.key} className="source">
                  <div className="source-title">{s.title}</div>
                  <div className="muted small">{s.publisher} · {s.vintage}</div>
                  <p className="small">{s.notes}</p>
                  <a href={s.url} target="_blank" rel="noreferrer">{s.url}</a>
                </div>
              ))}
              <div className="source">
                <div className="source-title">Place search</div>
                <div className="muted small">Online: OpenStreetMap via Photon / Nominatim · {health.geocoder.state}</div>
                <p className="small">Addresses and landmarks come from OpenStreetMap when the server has internet. Offline, Delhi ward localities and transit stops are searched. Points outside the NCT of Delhi boundary are rejected.</p>
              </div>
            </div>
          </div>
        )}

        {tab === 'assume' && (
          <div className="modal-body">
            <div className="assume-grid small">
              <div><strong>Walking</strong><br />{a.walking.speed_kmh} km/h, straight line × {a.walking.detour_factor}; up to {a.walking.max_transfer_m} m between stops; widened up to 2.5 km when no stop is near.</div>
              <div><strong>Buffers</strong><br />Metro entry {a.transfer_buffers_min.board_metro_from_street} min, metro interchange {a.transfer_buffers_min.metro_interchange} min, bus {a.transfer_buffers_min.board_bus} min, rail {a.transfer_buffers_min.board_rail_from_street} min.</div>
              <div><strong>Metro fares</strong><br />{f.metro.source} Weekdays ₹{f.metro.weekday_inr.join(' / ')}; Sundays ₹{f.metro.sunday_holiday_inr.join(' / ')} (slabs up to {f.metro.slabs_km.join(' / ')} km and beyond).</div>
              <div><strong>Bus fares</strong><br />{f.bus.source} {f.bus.fallback_source}</div>
              <div><strong>Rail fares</strong><br />{f.rail.source}</div>
              {a.cab && (
                <div><strong>Cab and auto fares</strong><br />{Object.values(a.cab.types).map((t) => `${t.label}: ₹${t.base_inr} for the first ${t.base_km} km, then ₹${t.per_km_inr}/km`).join('; ')}; 25% extra from 11 pm to 5 am. {a.cab.fare_source}</div>
              )}
              {a.cab && (
                <div><strong>Cab time</strong><br />Road route time × traffic factor by hour ({a.cab.traffic_factor.map((p) => `${p.from_h}–${p.to_h} h ×${p.factor}`).join(', ')}) plus an assumed pickup wait. Without road routing: straight line × {a.cab.fallback.road_detour_factor} at {a.cab.fallback.free_flow_speed_kmh} km/h. Cab legs under {a.cab.min_cab_km} km are not offered.</div>
              )}
              <div><strong>CO₂ (kg per passenger-km)</strong><br />bus {a.emissions_kg_per_pkm.bus}, metro {a.emissions_kg_per_pkm.metro}, rail {a.emissions_kg_per_pkm.rail}; driving alone {a.emissions_kg_per_pkm.car_baseline} for comparison.</div>
              <div><strong>Ranking</strong><br />Options worse on every criterion are dropped; the rest are scored by your priority. Options within budget always come first.</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
