import { ChangeIcon, ChevronDownIcon, ClockIcon, InfoIcon, LeafIcon, ModeIcon, RupeeIcon, SparkIcon } from './icons.jsx';

export const inr = (v) => `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })}`;
export const mins = (m) => {
  const v = Math.round(m);
  return v >= 60 ? `${Math.floor(v / 60)} h ${v % 60} min` : `${v} min`;
};
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const SOURCE_TEXT = { registry_champion: 'registry champion', deployed_service: 'deployed API', approved_bundle: 'approved bundle' };
const MODE_LABELS = { bus: 'Bus', metro: 'Metro', rail: 'Train', cab: 'Cab' };

function routeType(journey) {
  const rides = journey.legs.filter((leg) => leg.type === 'ride');
  const cab = rides.find((leg) => leg.mode === 'cab');
  if (journey.profile === 'cab only') return `Direct ${cab?.mode_label?.toLowerCase() || 'cab'}`;
  if (cab) return 'Cab + transit';
  const modes = [...new Set(rides.map((leg) => leg.mode))];
  return modes.length === 1 ? `${MODE_LABELS[modes[0]] || 'Transit'} route` : 'Transit connection';
}

/* A journey drawn like the route strip above metro doors: coloured runs, rings where you change. */
export function RouteStrip({ journey, animate = false, height = 22 }) {
  const W = 320;
  const legs = journey.legs;
  const weights = legs.map((l) => Math.max(l.type === 'walk' ? 3 : 8, l.minutes + (l.wait_minutes || 0)));
  const total = weights.reduce((a, b) => a + b, 0);
  const pad = 7;
  let x = pad;
  const y = height / 2;
  const parts = legs.map((l, i) => {
    const w = ((W - pad * 2) * weights[i]) / total;
    const seg = { leg: l, x0: x, x1: x + w };
    x += w;
    return seg;
  });
  const joints = parts.slice(0, -1).map((p) => p.x1);
  return (
    <svg className={`strip ${animate ? 'draw' : ''}`} viewBox={`0 0 ${W} ${height}`} aria-hidden="true">
      {parts.map(({ leg, x0, x1 }, i) => (leg.type === 'walk' ? (
        <line key={i} x1={x0 + 2} x2={x1 - 2} y1={y} y2={y} className="strip-walk" />
      ) : (
        <line key={i} x1={x0} x2={x1} y1={y} y2={y} stroke={leg.color} className="strip-ride" style={{ '--d': `${i * 90}ms` }} />
      )))}
      <circle cx={pad} cy={y} r="4.2" className="strip-end start" />
      {joints.map((jx, i) => {
        const a = parts[i].leg, b = parts[i + 1].leg;
        if (a.type === 'walk' && b.type === 'walk') return null;
        return <circle key={i} cx={jx} cy={y} r="4.6" className="strip-ring" />;
      })}
      <circle cx={W - pad} cy={y} r="4.2" className="strip-end finish" />
    </svg>
  );
}

function Flags({ journey, budget }) {
  const out = [];
  const words = journey.tags.filter((t) => !['recommended', 'over budget'].includes(t));
  if (words.length) out.push(<span key="w" className="flag-text">{words.map((w) => w[0].toUpperCase() + w.slice(1)).join(', ')}</span>);
  if (!journey.within_budget && budget != null) out.push(<span key="o" className="flag over">{inr(journey.fare_inr - budget)} over budget</span>);
  if (journey.uses_bus_model) out.push(<span key="m" className="flag ml">ML bus estimate</span>);
  return out.length ? <div className="flags">{out}</div> : null;
}

export function OptionRow({ journey, selected, onSelect, budget, index }) {
  const rides = journey.legs.filter((l) => l.type === 'ride');
  const cabLegs = rides.filter((l) => l.mode === 'cab');
  const hasCab = cabLegs.length > 0;
  const routeLabel = routeType(journey);
  const recommended = journey.tags.includes('recommended');
  const sourceNote = journey.uses_bus_model
    ? 'Includes an ML estimate on the supported bus segment'
    : hasCab
      ? (rides.every((l) => l.mode === 'cab') ? 'Indicative cab fare · pickup time assumed' : 'Timetables + cab estimates · fares indicative')
      : 'Timetable estimates · walking and waiting included';
  return (
    <li className={`option ${selected ? 'selected' : ''} ${recommended ? 'recommended' : ''} ${hasCab ? 'is-cab' : ''} ${journey.profile === 'cab only' ? 'direct-cab' : ''} ${journey.within_budget ? '' : 'over'}`} style={{ '--option-index': index }}>
      <button type="button" onClick={onSelect} aria-pressed={selected} aria-label={`Route ${index + 1}, ${routeLabel}${recommended ? ', recommended' : ''}, ${journey.leave} to ${journey.arrive}, ${mins(journey.duration_min)}, ${inr(journey.fare_inr)}, ${plural(journey.vehicle_changes, 'change', 'changes')}, ${journey.co2_kg.toFixed(2)} kilograms of CO₂${!journey.within_budget && budget != null ? `, ${inr(journey.fare_inr - budget)} over budget` : ''}`}>
        <div className="option-heading">
          <div className="option-heading-main">
            <span className="option-mode-mark"><ModeIcon mode={hasCab ? 'cab' : rides[0]?.mode || 'walk'} width={20} height={20} /></span>
            <div><span className="option-id">Route {String(index + 1).padStart(2, '0')}</span><strong className="option-number option-title">{routeLabel}</strong></div>
          </div>
          <div className="option-badges">
            {recommended && <span className="flag rec"><SparkIcon width={12} height={12} />Recommended</span>}
            {selected && <span className="option-state"><span className="option-check" aria-hidden="true">✓</span>Selected</span>}
          </div>
        </div>
        <div className="opt-primary">
          <div className="opt-route-modes">
            <div className="opt-lines">
              {rides.map((l, i) => (
                <span key={i} className="line-tag" style={{ '--c': l.color }}>
                  <ModeIcon mode={l.mode} width={14} height={14} />
                  {l.mode === 'metro' ? l.route.replace(' Line', '') : l.mode === 'rail' ? `Train ${l.route.split(' ')[0]}` : l.mode === 'cab' ? l.cab?.type_label || l.mode_label : `Bus ${l.route.split(' ')[0]}`}
                </span>
              ))}
            </div>
            <Flags journey={journey} budget={budget} />
          </div>
          <div className="opt-price">
            <strong className={`opt-fare opt-price-value ${journey.within_budget ? '' : 'bad'}`}>{inr(journey.fare_inr)}</strong>
            <span className="opt-price-label">{hasCab ? 'estimated fare' : 'total fare'}</span>
          </div>
        </div>
        <div className="opt-timing">
          <div className="opt-times" aria-label={`Depart ${journey.leave}, arrive ${journey.arrive}`}><time>{journey.leave}</time><span className="dash" aria-hidden="true">→</span><time>{journey.arrive}</time></div>
          <div className="opt-dur"><ClockIcon width={14} height={14} />{mins(journey.duration_min)}</div>
        </div>
        <RouteStrip journey={journey} animate />
        <div className="opt-facts">
          <span className="opt-fact"><ChangeIcon width={13} height={13} /><span className="opt-fact-value">{journey.vehicle_changes === 0 ? 'Direct' : plural(journey.vehicle_changes, 'change', 'changes')}</span></span>
          <span className="opt-fact"><ModeIcon mode="walk" width={13} height={13} /><span className="opt-fact-value">{journey.walk_m} m walk</span></span>
          <span className="opt-fact opt-co2"><LeafIcon width={13} height={13} /><span className="opt-fact-value">{journey.co2_kg.toFixed(2)} kg CO₂</span></span>
        </div>
        {cabLegs.map((leg, i) => (
          <div key={i} className="cab-option-facts">
            <span className="cab-option-icon"><ModeIcon mode="cab" width={16} height={16} /></span>
            <div className="cab-option-metrics">
              <span><span className="cab-metric-label">Pickup</span><strong>~{mins(leg.wait_minutes)}</strong></span>
              <span><span className="cab-metric-label">Drive</span><strong>~{mins(leg.minutes)}</strong></span>
              <span><span className="cab-metric-label">Distance</span><strong>{leg.distance_km} km</strong></span>
              {rides.length > 1 && <span><span className="cab-metric-label">Cab fare</span><strong>{inr(leg.fare_inr)}</strong></span>}
            </div>
          </div>
        ))}
        <div className="opt-source"><InfoIcon width={12} height={12} /><span>{sourceNote}</span></div>
      </button>
    </li>
  );
}

export function Summary({ journey, carKg }) {
  const saved = Math.max(0, carKg - journey.co2_kg);
  const tickets = journey.legs.filter((l) => l.type === 'ride' && l.fare_inr > 0).length;
  return (
    <div className="summary" role="group" aria-label="Journey at a glance">
      <div><span className="summary-label"><ClockIcon className="summary-icon" width={16} height={16} />Travel time</span><b>{mins(journey.duration_min)}</b><span className="summary-note">Door to door, including waits</span></div>
      <div><span className="summary-label"><RupeeIcon className="summary-icon" width={16} height={16} />Total fare</span><b>{inr(journey.fare_inr)}</b><span className="summary-note">{plural(tickets, 'ticket', 'tickets')}</span></div>
      <div><span className="summary-label"><ChangeIcon className="summary-icon" width={16} height={16} />Changes</span><b>{journey.vehicle_changes === 0 ? 'Direct' : journey.vehicle_changes}</b><span className="summary-note">{journey.vehicle_changes === 0 ? 'No vehicle changes' : plural(journey.vehicle_changes, 'vehicle change', 'vehicle changes')}</span></div>
      <div className="green"><span className="summary-label"><LeafIcon className="summary-icon" width={16} height={16} />CO₂ estimate</span><b>{journey.co2_kg.toFixed(2)} kg</b><span className="summary-note">{saved > 0 ? `${saved.toFixed(2)} kg less than a car` : 'Estimated per passenger'}</span></div>
    </div>
  );
}

export function Why({ journey }) {
  return (
    <div className="why">
      <div className="detail-card-head"><LeafIcon width={17} height={17} /><h4>Why this route</h4></div>
      <ul>{journey.why.map((w, i) => <li key={i}>{w}</li>)}</ul>
    </div>
  );
}

function SourceTag({ leg }) {
  if (leg.type === 'walk') return <span className="src rule">Walking rule</span>;
  if (leg.bus_model?.applied) return <span className="src ml">ML estimate + timetable</span>;
  if (leg.mode === 'cab') return <span className="src cab">{leg.cab?.method === 'osrm' ? 'Road route + traffic rule' : 'Distance rule + traffic rule'}</span>;
  return <span className="src sched">{leg.mode === 'rail' ? 'Rail timetable' : leg.mode === 'metro' ? 'Metro timetable' : 'Bus timetable'}</span>;
}

/* Timetable-style itinerary: times on the left, the line diagram in the middle, instructions on the right. */
export function Itinerary({ journey, destination }) {
  const legs = journey.legs;
  const last = legs[legs.length - 1];
  return (
    <details className="journey-details" key={journey.id} open={journey.modes.includes('cab')}>
      <summary className="journey-disclosure">
        <span className="journey-disclosure-icon"><ModeIcon mode={journey.modes?.[0] || 'walk'} width={21} height={21} /></span>
        <span className="journey-disclosure-copy"><strong>{journey.modes.includes('cab') ? `${routeType(journey)} itinerary` : 'Journey details'}</strong><span className="journey-disclosure-meta">{plural(legs.length, 'step', 'steps')} · {journey.leave}–{journey.arrive} · {mins(journey.duration_min)}</span></span>
        <ChevronDownIcon className="journey-disclosure-chevron" width={20} height={20} />
      </summary>
      <ol className="itin" aria-label="Detailed journey instructions">
      {legs.map((l, i) => (
        <li key={i} className={`itin-leg ${l.type}`} style={{ '--c': l.type === 'walk' ? 'var(--walk)' : l.color, '--step-index': i }}>
          <div className="itin-time"><time>{l.depart}</time><span className="itin-duration">{Math.round(l.minutes)} min</span></div>
          <div className="itin-rail" aria-hidden="true"><span className={`node ${i === 0 ? 'start' : ''}`} /></div>
          <div className="itin-body">
            <span className="itin-step-label">Step {String(i + 1).padStart(2, '0')} · {l.type === 'walk' ? 'Walk' : l.mode === 'cab' ? 'Cab ride' : l.mode_label}</span>
            {l.type === 'walk' ? (
              <>
                <div className="itin-place itin-leg-title">{l.from.name}</div>
                <div className="itin-act"><ModeIcon mode="walk" width={15} height={15} /> Walk {l.distance_m} m, about {Math.round(l.minutes)} min{l.to.kind !== 'place' ? <> to {l.to.name}</> : null}</div>
                <div className="itin-foot"><SourceTag leg={l} /></div>
              </>
            ) : l.mode === 'cab' ? (
              <>
                <div className="itin-place itin-leg-title">{l.from.name}</div>
                <div className="itin-act">
                  <span className="line-badge" style={{ '--c': l.color }}><ModeIcon mode="cab" width={14} height={14} />{l.cab.type_label}</span>
                  <span className="toward">to {l.to.name}</span>
                </div>
                <div className="itin-meta">
                  <span>Pickup about {Math.round(l.wait_minutes)} min (assumed)</span>
                  <span>Drive about {Math.round(l.minutes)} min</span>
                  <span>{l.distance_km} km</span>
                  <span className="fare">{inr(l.fare_inr)}</span>
                </div>
                <div className="cab-note">
                  <InfoIcon width={15} height={15} />
                  <span>
                    {l.cab.method === 'osrm' ? `Road route from OpenStreetMap: ${Math.round(l.cab.free_flow_min)} min on free-flowing roads` : `No road routing available: ${l.distance_km} km estimated from the straight line`},
                    {' '}stretched ×{l.cab.traffic_factor} for Delhi traffic at this hour. The fare is an indicative meter fare; app cabs price dynamically and availability is not checked.
                  </span>
                </div>
                <div className="itin-off"><time className="off-time">{l.arrive}</time> Arrive at <b>{l.to.name}</b></div>
                <div className="itin-foot"><SourceTag leg={l} /><span className="basis">Fare: {l.fare_basis}</span></div>
              </>
            ) : (
              <>
                <div className="itin-place itin-leg-title">{l.from.name}</div>
                <div className="itin-act">
                  <span className="line-badge" style={{ '--c': l.color }}><ModeIcon mode={l.mode} width={14} height={14} />{l.mode_label} {l.route}</span>
                  <span className="toward">towards {l.towards}</span>
                </div>
                <div className="itin-meta">
                  {l.wait_minutes > 0.4 && <span>Wait about {Math.round(l.wait_minutes)} min</span>}
                  <span>{plural(l.stops, 'stop', 'stops')}, {Math.round(l.minutes)} min</span>
                  <span>{l.distance_km} km</span>
                  <span className="fare">{l.fare_inr > 0 ? inr(l.fare_inr) : l.fare_basis.startsWith('same metro') ? 'Same ticket' : inr(0)}</span>
                </div>
                {l.stop_names.length > 2 && (
                  <details className="via">
                    <summary>{plural(l.stop_names.length - 2, 'stop', 'stops')} on the way</summary>
                    <p>{l.stop_names.slice(1, -1).join(', ')}</p>
                  </details>
                )}
                {l.bus_model?.applied && (
                  <div className="ml-note">
                    <InfoIcon width={15} height={15} />
                    <span>
                      On the Outer Ring Road stretch {l.bus_model.from} to {l.bus_model.to} (entering at {l.bus_model.entry_time}) the ML bus model v{l.bus_model.model_version}
                      {' '}({SOURCE_TEXT[l.bus_model.model_source] || l.bus_model.model_source}) predicts {l.bus_model.model_minutes} min
                      {l.bus_model.typical_error_min ? ` ± ${l.bus_model.typical_error_min}` : ''}; the timetable says {l.bus_model.timetable_minutes} min.
                    </span>
                  </div>
                )}
                <div className="itin-off"><time className="off-time">{l.arrive}</time> Get off at <b>{l.to.name}</b></div>
                <div className="itin-foot"><SourceTag leg={l} /><span className="basis">Fare: {l.fare_basis}</span></div>
              </>
            )}
          </div>
        </li>
      ))}
      <li className="itin-leg end itin-arrival">
        <div className="itin-time"><time>{last.arrive}</time></div>
        <div className="itin-rail" aria-hidden="true"><span className="node finish" /></div>
        <div className="itin-body"><span className="itin-step-label">Destination</span><div className="itin-place">{destination}</div><div className="itin-act muted">You have arrived</div></div>
      </li>
      </ol>
    </details>
  );
}

/* Wide route bar for the trip section: one labelled run per leg, sized by time. */
export function LegBar({ journey }) {
  const legs = journey.legs;
  return (
    <div className="legbar" role="group" aria-label="Route overview">
      {legs.map((l, i) => {
        const weight = Math.max(l.type === 'walk' ? 4 : 10, l.minutes + (l.wait_minutes || 0));
        return (
          <div key={i} className={`lb-leg ${l.type}`} style={{ flexGrow: weight, '--c': l.type === 'walk' ? 'var(--walk)' : l.color }}>
            <div className="lb-bar" aria-hidden="true"><span className={`lb-node ${i === 0 ? 'start' : ''}`} />{i === legs.length - 1 && <span className="lb-node finish" />}</div>
            <div className="lb-label">
              <ModeIcon mode={l.type === 'walk' ? 'walk' : l.mode} width={15} height={15} />
              <span className="lb-name">{l.type === 'walk' ? `Walk ${l.distance_m} m` : `${l.mode_label} ${l.route}`}</span>
              <span className="lb-min">{Math.round(l.minutes)} min</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function FareTable({ journey, budget }) {
  const rides = journey.legs.filter((l) => l.type === 'ride');
  return (
    <div className="side-block fare-block">
      <div className="detail-card-head"><RupeeIcon width={17} height={17} /><h4>Fare breakdown</h4></div>
      <table className="fares" aria-label="Fare breakdown by journey leg">
        <tbody>
          {rides.map((l, i) => (
            <tr key={i}>
              <td><span className="fare-line" style={{ '--c': l.color }}>{l.mode_label} {l.route}</span><span className="fare-basis">{l.fare_basis}</span></td>
              <td className="num">{l.fare_inr > 0 ? inr(l.fare_inr) : l.fare_basis.startsWith('same metro') ? 'Included' : inr(0)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr><td>Total</td><td className="num">{inr(journey.fare_inr)}</td></tr>
          {budget != null && (
            <tr className={journey.within_budget ? 'ok' : 'bad'}>
              <td colSpan={2}>{journey.within_budget ? `${inr(budget - journey.fare_inr)} left of your ${inr(budget)} budget` : `${inr(journey.fare_inr - budget)} more than your ${inr(budget)} budget`}</td>
            </tr>
          )}
        </tfoot>
      </table>
    </div>
  );
}

export function Estimates({ journey }) {
  return (
    <div className="side-block estimates-block">
      <div className="detail-card-head"><InfoIcon width={17} height={17} /><h4>Estimate sources</h4></div>
      <ul className="est">
        {journey.legs.map((l, i) => (
          <li key={i}>
            <SourceTag leg={l} />
            <span>{l.type === 'walk' ? `Walk ${l.distance_m} m` : `${l.mode_label} ${l.route}`}: {l.type === 'walk' ? 'straight-line distance, detour factor and walking speed' : l.estimate_source}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RoutePicker({ journeys, selected, onSelect }) {
  return (
    <div className="picker" role="group" aria-label="Choose a route">
      {journeys.map((j, i) => (
        <button key={j.id} type="button" aria-pressed={i === selected} className={i === selected ? 'on' : ''} onClick={() => onSelect(i)}>
          <span className="pk-n">Route {i + 1}<span className="pk-route-type">{routeType(j)}</span></span>
          <span className="pk-t pk-times">{j.leave}<span className="pk-arrow" aria-hidden="true">→</span>{j.arrive}</span>
          <span className="pk-f">{inr(j.fare_inr)}, {mins(j.duration_min)}</span>
          {j.tags.includes('recommended') && <span className="pk-rec">Recommended</span>}
        </button>
      ))}
    </div>
  );
}
