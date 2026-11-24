import { useEffect, useState } from 'react';
import { getJSON } from '../api.js';
import { Badge, Card, Empty, Icon, Segmented, Status, Table } from '../components/ui.jsx';
import { CusumChart, ErrorTimeline, PsiBars, StatusGrid } from '../components/charts.jsx';
import { CHECK_LABEL, humanize, num, pct, SEGMENT_SHORT } from '../lib/format.js';

const friendlyScope = (scope) => Object.entries(SEGMENT_SHORT)
  .reduce((text, [id, short]) => text.replace(id, short), scope)
  .replace('all_segments', 'all segments').replace(/2019-/g, '').replace(/_/g, ' ');

const SCENARIO_ICON = { natural: 'activity', covariate_shift: 'data', concept_drift: 'alert', data_quality: 'clock' };
const LAYER_TEXT = {
  data_quality: 'Every request is validated; >5% failing over 20 requests alerts.',
  input_drift: 'PSI per feature vs the same time of day on training days.',
  prediction_drift: 'PSI on predicted minutes.',
  performance: 'Delayed labels: error vs the approved level, CUSUM per segment.',
};

export default function Drift({ state }) {
  const monitoring = state.monitoring;
  const [name, setName] = useState('concept_drift');
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [detector, setDetector] = useState('all_segments');
  const [focus, setFocus] = useState(null);

  useEffect(() => {
    if (!monitoring) return undefined;
    let cancelled = false;
    setDetail(null);
    getJSON(`/api/scenario/${name}`)
      .then((payload) => {
        if (cancelled) return;
        setDetail(payload);
        setError(null);
        // Open the segment detector that alarmed first (labels like '08 Jul 10:58' sort by time).
        const alarmed = payload.detectors.filter((d) => d.alarm && d.name !== 'all_segments')
          .sort((a, b) => a.alarm[2].localeCompare(b.alarm[2]));
        setDetector(alarmed.length ? alarmed[0].name : 'all_segments');
        const scored = Object.entries(payload.features).map(([key, rows]) => [key, Math.max(...rows.map((r) => r.psi - r.alert_threshold))]);
        scored.sort((a, b) => b[1] - a[1]);
        setFocus(scored.length ? scored[0][0] : null);
      })
      .catch((exc) => !cancelled && setError(exc.message));
    return () => { cancelled = true; };
  }, [name, monitoring]);

  if (!monitoring) return <div className="page"><Empty title="The drift replay has not been run yet" command="python -m scripts.run_phase3" /></div>;
  const summary = detail?.summary;
  const activeDetector = detail?.detectors.find((d) => d.name === detector) || detail?.detectors[0];

  return (
    <div className="page">
      <div className="scenario-cards">
        {monitoring.scenarios.map((s) => {
          const alerts = Object.values(s.alerts_by_type).reduce((sum, c) => sum + (c.ALERT || 0), 0);
          return (
            <button key={s.name} type="button" className={`scenario-card ${s.name === name ? 'active' : ''}`} onClick={() => setName(s.name)}>
              <div className="scenario-card-top">
                <span className="scenario-icon"><Icon name={SCENARIO_ICON[s.name] || 'activity'} size={18} /></span>
                {s.onset_ist ? <Badge tone="warn">injected</Badge> : <Badge tone="good">real data</Badge>}
              </div>
              <strong>{s.title}</strong>
              <span className="muted small">{s.description}</span>
              <span className="scenario-foot">
                <span><b>{alerts}</b> alerts</span>
                {s.onset_ist && <span>from {s.onset_ist.slice(5, 16).replace('T', ' ')}</span>}
              </span>
            </button>
          );
        })}
      </div>

      {error && <div className="banner banner-bad"><Icon name="alert" /> {error}</div>}
      {!detail && !error && <div className="loading"><span className="spinner" /> Loading scenario…</div>}

      {detail && (
        <>
          <div className="layer-grid">
            {Object.keys(CHECK_LABEL).map((kind) => {
              const counts = summary.alerts_by_type[kind] || { ALERT: 0, WARN: 0 };
              const delay = summary.detection_delay_minutes[kind];
              const first = summary.first_alert[kind];
              return (
                <div key={kind} className={`layer-card ${counts.ALERT ? 'fired' : ''}`}>
                  <div className="layer-top">
                    <span>{CHECK_LABEL[kind]}</span>
                    <Status status={counts.ALERT ? 'ALERT' : counts.WARN ? 'WARN' : 'OK'} compact />
                  </div>
                  <div className="layer-value">{counts.ALERT}<small> alerts</small> · {counts.WARN}<small> warnings</small></div>
                  <div className="layer-foot">
                    {first ? <>first {first.slice(5)}{delay != null && <> · <b>{Math.round(delay)} min</b> after the first affected request</>}</> : 'stayed quiet'}
                  </div>
                  <p className="muted small">{LAYER_TEXT[kind]}</p>
                </div>
              );
            })}
          </div>

          <Card title="Check status per monitoring window" subtitle="Each window is compared with the same time of day in the reference · click a column to inspect its features">
            <StatusGrid windows={detail.windows} selected={focus} onSelect={(w) => detail.features[w] && setFocus(w)} />
          </Card>

          <Card title="Prediction error as labels arrive" subtitle="Dots: each completed trip (orange = injected) · line: rolling MAE over 20 trips · dashed: approved error level">
            <ErrorTimeline points={detail.timeline} approved={monitoring.reference.approved_validation_mae} markers={detail.markers} />
          </Card>

          <div className="grid-2 wide-left">
            <Card title="Sequential performance detector (CUSUM)" subtitle="Adds up errors above the approved level; alarms past a threshold calibrated for ≤5% false alarms"
              action={null}>
              <Segmented size="sm" value={activeDetector.name} onChange={setDetector}
                options={detail.detectors.map((d) => ({ value: d.name, label: d.name === 'all_segments' ? 'All' : SEGMENT_SHORT[d.name] || d.label, dot: d.alarm ? 'var(--bad)' : undefined }))} />
              <CusumChart key={activeDetector.name} detector={activeDetector} />
              <p className="muted small">{activeDetector.alarm ? `${activeDetector.label}: alarm at ${activeDetector.alarm[2]} after ${activeDetector.alarm[0]} labels.` : `${activeDetector.label}: no alarm.`}</p>
            </Card>
            <Card title="Input drift by feature" subtitle={focus ? `Window ${focus.replace('2019-', '').replace('_', ' ')} · red tick = alert threshold` : 'No window with enough requests'}>
              {focus && detail.features[focus] ? <PsiBars rows={detail.features[focus]} /> : <p className="muted">Not enough requests in any window.</p>}
              <p className="muted small">Thresholds come from resampling the reference at this window's size, so a small window is not flagged by chance.</p>
            </Card>
          </div>

          <div className="grid-2">
            <Card title="Alerts raised" subtitle={`${detail.alerts.length} alerts and warnings in time order`}>
              <div className="alert-feed">
                {detail.alerts.length === 0 && <p className="muted">No alerts.</p>}
                {detail.alerts.map((a, i) => (
                  <div key={i} className={`alert-row sev-${a.severity}`}>
                    <span className="alert-time">{a.detected_at_ist.slice(5)}</span>
                    <Status status={a.severity} compact />
                    <div>
                      <strong>{CHECK_LABEL[a.type] || humanize(a.type)}</strong> <span className="muted">· {friendlyScope(a.scope)}</span>
                      <div className="small">{a.detail}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
            <Card title="Runbook" subtitle="Agreed response for each alert type that fired">
              {summary.recommended_actions.length ? (
                <ol className="runbook">{summary.recommended_actions.map((action) => <li key={action}>{action}</li>)}</ol>
              ) : <p className="muted">Nothing to do: no alert reached ALERT level.</p>}
              <div className="callout">
                <Icon name="info" size={16} />
                <span>Only a <strong>performance</strong> alarm opens a retraining candidate. Input drift alone triggers investigation: in the demand-shift scenario the inputs drifted while error fell.</span>
              </div>
            </Card>
          </div>

          <Card title="Data-quality checks per window" subtitle="Share of requests failing each rule">
            <Table dense rows={detail.windows} columns={[
              { key: 'short', label: 'Window' },
              { key: 'requests', label: 'Requests', align: 'right' },
              { key: 'status', label: 'Status', render: (r) => <Status status={r.statuses['Data quality']} compact /> },
              ...Object.keys(detail.windows[0]?.dq || {}).map((rule) => ({ key: rule, label: humanize(rule), align: 'right', render: (r) => pct(r.dq[rule]) })),
              { key: 'mae', label: 'MAE (min)', align: 'right', render: (r) => num(r.mae) },
            ]} />
          </Card>

          <Card title="All scenarios side by side" subtitle="First alert after onset (IST)">
            <Table rows={monitoring.scenarios} columns={[
              { key: 'title', label: 'Scenario', render: (s) => <strong>{s.title}</strong> },
              ...Object.keys(CHECK_LABEL).map((kind) => ({ key: kind, label: CHECK_LABEL[kind], render: (s) => (s.first_alert[kind] ? s.first_alert[kind].slice(5) : <span className="muted">—</span>) })),
              { key: 'delay', label: 'Fastest (min)', align: 'right', render: (s) => {
                const values = Object.values(s.detection_delay_minutes || {});
                return values.length ? Math.round(Math.min(...values)) : '—';
              } },
            ]} />
          </Card>

          <Card title="How detection works">
            <div className="method-grid">
              <div><h4>Reference</h4><p>Inputs from v1's training days (1–3 July). Errors from v1's approved validation day (5 July), so the reference day itself stays quiet.</p></div>
              <div><h4>Calibrated thresholds</h4><p>Warn/alert at the 95th/99th percentile of the statistic on same-sized resamples of in-control data, not textbook cut-offs.</p></div>
              <div><h4>Delayed labels</h4><p>A trip's true duration exists only when the bus leaves the segment, so performance is judged as labels arrive.</p></div>
              <div><h4>Signal, not verdict</h4><p>Only a performance alarm opens retraining, and the candidate must still pass the promotion gate.</p></div>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
