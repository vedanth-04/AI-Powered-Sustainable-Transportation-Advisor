import { Badge, Card, Empty, Icon, Kpi, Legend, Status } from '../components/ui.jsx';
import { GroupedBars, HBars } from '../components/charts.jsx';
import { CHECK_LABEL, num, SEGMENT_ORDER, SEGMENT_SHORT, signed, versionColor } from '../lib/format.js';

export default function Overview({ state, go }) {
  const { kpis, pipeline, monitoring, registry } = state;
  const done = pipeline.filter((s) => s.status === 'PASS').length;
  const maeDelta = kpis.champion_mae != null && kpis.v1_mae != null ? kpis.champion_mae - kpis.v1_mae : null;
  const natural = monitoring?.scenarios.find((s) => s.name === 'natural');
  const injected = monitoring?.scenarios.filter((s) => s.name !== 'natural') || [];

  const delays = injected.map((s) => {
    const values = Object.values(s.detection_delay_minutes || {});
    return { label: s.title.replace('Induced ', ''), value: values.length ? Math.min(...values) : null, empty: 'not detected' };
  });

  const versionBars = [];
  if (registry) {
    for (const v of registry.versions) {
      for (const segment of SEGMENT_ORDER) {
        const value = v.holdout_mae_by_segment?.[segment];
        if (value != null) versionBars.push({ category: segment, group: `v${v.version}`, value, status: v.status,
          extra: [{ label: 'Status', value: v.status }] });
      }
    }
  }
  const versionKeys = registry ? registry.versions.map((v) => `v${v.version}`) : [];
  const colors = Object.fromEntries(versionKeys.map((k) => [k, versionColor(k)]));

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-text">
          <Badge tone="accent">Phase 3 · Productionization & deployment</Badge>
          <h2>Predict Delhi bus riding time, watch it in production, and change it safely.</h2>
          <p>
            A gradient-boosting model estimates minutes per road segment from 2019 GPS traces. We replay unseen days, detect
            drift, retrain behind a promotion gate, and keep every version traceable and reversible.
          </p>
          <div className="hero-actions">
            <button type="button" className="btn btn-primary" onClick={() => go('drift')}><Icon name="activity" size={16} /> See drift detection</button>
            <button type="button" className="btn" onClick={() => go('registry')}><Icon name="layers" size={16} /> Model versions</button>
          </div>
        </div>
        <div className="hero-ring">
          <svg viewBox="0 0 120 120" width="150" height="150" aria-label={`${done} of ${pipeline.length} stages complete`}>
            <circle cx="60" cy="60" r="50" className="ring-track" />
            <circle cx="60" cy="60" r="50" className="ring-fill" strokeDasharray={`${(done / pipeline.length) * 314} 314`} transform="rotate(-90 60 60)" />
            <text x="60" y="58" textAnchor="middle" className="ring-value">{done}/{pipeline.length}</text>
            <text x="60" y="76" textAnchor="middle" className="ring-label">stages live</text>
          </svg>
        </div>
      </section>

      <div className="kpi-grid">
        <Kpi icon="layers" label="Serving champion" value={kpis.champion ? `v${kpis.champion}` : '—'}
          hint={kpis.previous ? `rollback target v${kpis.previous}` : 'run the lifecycle'} />
        <Kpi icon="activity" label="Champion holdout MAE" value={kpis.champion_mae != null ? `${num(kpis.champion_mae)} min` : '—'}
          hint={maeDelta != null ? `${signed(maeDelta)} min vs v1` : null} trend={maeDelta != null && maeDelta < 0 ? 'good' : null} tone="good" />
        <Kpi icon="alert" label="Injected drifts detected" value={kpis.injected_total ? `${kpis.injected_detected}/${kpis.injected_total}` : '—'}
          hint="road works · timezone bug · demand shift" tone="warn" />
        <Kpi icon="clock" label="Real drift alarms" value={kpis.real_alarms ?? '—'}
          hint={natural?.cusum_alarms?.[0] ? `first ${natural.cusum_alarms[0].detected_at_ist.slice(5)}` : 'no injection'} tone="bad" />
        <Kpi icon="hash" label="Audit chain" value={kpis.chain_valid == null ? '—' : kpis.chain_valid ? 'Intact' : 'Broken'}
          hint={`${kpis.audit_entries} hash-linked entries`} tone={kpis.chain_valid === false ? 'bad' : 'accent'} />
        <Kpi icon="refresh" label="Rollback drill" value={kpis.drill_passed == null ? '—' : kpis.drill_passed ? 'Passed' : 'Failed'}
          hint="v2 → v1 → v2 verified" tone="good" />
      </div>

      <Card title="Pipeline health" subtitle="Click any stage for its evidence" action={<button type="button" className="btn btn-ghost btn-small" onClick={() => go('pipeline')}>Open pipeline <Icon name="arrow" size={14} /></button>}>
        <div className="mini-pipeline">
          {pipeline.map((stage, index) => (
            <button key={stage.key} type="button" className={`mini-stage status-${stage.status}`} onClick={() => go('pipeline')} title={stage.detail}>
              <span className="mini-dot">{index + 1}</span>
              <span className="mini-name">{stage.stage.replace(/^\d+\.\s*/, '')}</span>
            </button>
          ))}
        </div>
      </Card>

      <div className="grid-2">
        <Card title="Time to first alert" subtitle="Minutes from the first affected request to the first ALERT">
          {monitoring ? <HBars rows={delays} format={(v) => Math.round(v)} unit=" min" color="var(--s2)" /> : <Empty command="python -m scripts.run_phase3" />}
          {monitoring && <p className="muted small spaced">Data quality is checked on every request; input drift is judged when a time-of-day window closes; performance waits for buses to finish the segment.</p>}
          {natural && (
            <div className="callout">
              <Icon name="info" size={16} />
              <span>
                With <strong>no injection</strong>, the monitor still flagged {natural.cusum_alarms.length} real performance alarm(s) on 8 July:
                {' '}{natural.cusum_alarms.map((a) => `${SEGMENT_SHORT[a.detector] || a.detector} at ${a.detected_at_ist.slice(11)}`).join(', ')}.
              </span>
            </div>
          )}
        </Card>
        <Card title="Holdout error by segment and version" subtitle="8 July 2019 · lower is better · rejected version faded">
          {registry ? (
            <>
            <Legend items={versionKeys.map((k) => ({ label: k, color: colors[k] }))} />
            <GroupedBars data={versionBars} categories={SEGMENT_ORDER} groups={versionKeys} colors={colors} yLabel="MAE (min)"
              categoryLabel={(c) => SEGMENT_SHORT[c]} isFaded={(d) => d.status === 'rejected'} />
            </>
          ) : <Empty command="python -m scripts.run_phase3" />}
        </Card>
      </div>

      {monitoring && (
        <Card title="What each scenario triggered" subtitle="First alert per monitoring layer after the change began">
          <div className="scenario-strip">
            {monitoring.scenarios.map((s) => (
              <button key={s.name} type="button" className="scenario-mini" onClick={() => go('drift')}>
                <div className="scenario-mini-head">
                  <strong>{s.title}</strong>
                  {s.onset_ist ? <Badge tone="warn">injected</Badge> : <Badge tone="good">real data</Badge>}
                </div>
                <ul>
                  {Object.keys(CHECK_LABEL).map((kind) => (
                    <li key={kind}>
                      <span>{CHECK_LABEL[kind]}</span>
                      {s.first_alert[kind] ? <Status status="ALERT" label={s.first_alert[kind].slice(11)} compact /> : <Status status="OK" label="quiet" compact />}
                    </li>
                  ))}
                </ul>
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
