import { useState } from 'react';
import { Badge, Card, CodeLine, Empty, Icon, Legend, Status, Table } from '../components/ui.jsx';
import { GroupedBars, LineChart } from '../components/charts.jsx';
import { humanize, num, SEGMENT_ORDER, SEGMENT_SHORT, shortHash, signed, versionColor, when } from '../lib/format.js';

const STATUS_TONE = { approved: 'good', rejected: 'bad', candidate: 'warn' };
const clip = (value, length = 44) => {
  const text = String(value ?? '—');
  return text.length > length ? `${text.slice(0, length)}…` : text;
};
const WHY = [
  ['branch', 'Traceability', 'Every prediction maps to one version, and every version to its exact data rows, code commit, hyperparameters and artifact hash.'],
  ['shield', 'Safe change', 'Retraining creates a candidate. Only versions that pass the promotion gate can take the champion alias.'],
  ['refresh', 'Instant rollback', 'The previous alias always points at the last good version; the rollback drill proves it can serve.'],
  ['activity', 'Fair comparison', 'All versions are scored on the same holdout day, so "better" is reproducible.'],
  ['hash', 'Accountability', 'Promotions, rejections and rollbacks are in a hash-chained audit log with the actor.'],
];

export default function Registry({ state }) {
  const registry = state.registry;
  const [selected, setSelected] = useState(registry?.aliases?.champion || 1);
  const [from, setFrom] = useState(1);
  const [to, setTo] = useState(registry?.aliases?.champion || 2);
  if (!registry) return <div className="page"><Empty title="No version ledger yet" command="python -m scripts.run_phase3" /></div>;

  const versions = registry.versions;
  const record = versions.find((v) => v.version === selected) || versions[0];
  const aliasesOf = (version) => Object.entries(registry.aliases).filter(([, v]) => v === version).map(([alias]) => alias);
  const v1 = versions.find((v) => v.version === 1);
  const keys = versions.map((v) => `v${v.version}`);
  const colors = Object.fromEntries(keys.map((k) => [k, versionColor(k)]));
  const bars = versions.flatMap((v) => SEGMENT_ORDER.filter((s) => v.holdout_mae_by_segment?.[s] != null)
    .map((s) => ({ category: s, group: `v${v.version}`, value: v.holdout_mae_by_segment[s], status: v.status })));
  const diff = registry.diffs[`${from}-${to}`] || [];
  const drill = registry.rollback_drill;
  const mlflow = registry.mlflow || {};

  return (
    <div className="page">
      <div className="version-cards">
        {versions.map((v) => {
          const aliases = aliasesOf(v.version);
          const delta = v1 && v.version !== 1 ? v.holdout_metrics.mae_minutes - v1.holdout_metrics.mae_minutes : null;
          return (
            <button key={v.version} type="button" className={`version-card status-${v.status} ${selected === v.version ? 'active' : ''}`} onClick={() => setSelected(v.version)}>
              <div className="version-top">
                <span className="version-tag" style={{ background: versionColor(v.version) }}>v{v.version}</span>
                <span className="chips">{aliases.map((a) => <Badge key={a} tone={a === 'champion' ? 'accent' : 'neutral'}>{a}</Badge>)}</span>
                <Badge tone={STATUS_TONE[v.status]}>{v.status}</Badge>
              </div>
              <strong>{humanize(v.change_type)}</strong>
              <div className="version-mae">
                <span className="big">{num(v.holdout_metrics.mae_minutes)}</span><span className="muted"> min MAE</span>
                {delta != null && <span className={`delta ${delta < 0 ? 'good' : 'bad'}`}>{signed(delta)} vs v1</span>}
              </div>
              <span className="muted small">Trained on {v.training_window.dates_ist.map((d) => d.slice(8)).join(', ')} Jul · {v.training_window.rows} rows</span>
            </button>
          );
        })}
      </div>

      <div className="grid-2 wide-left">
        <Card title={`v${record.version} · ${humanize(record.change_type)}`} subtitle={`Created ${when(record.created_at)} · ${record.algorithm}`}
          action={<Badge tone={STATUS_TONE[record.status]}>{record.status}</Badge>}>
          <p className="lead">{record.reason}</p>
          {record.release && (
            <>
              <div className="callout"><Icon name="info" size={16} /> System release: the bus model weights are v{record.release.components.bus_model.ledger_version}'s, byte for byte, so its holdout scores are the same. The champion alias stays on v{registry.aliases.champion}; this version carries the advisor alias.</div>
              <h4 className="section-title">What this release packages</h4>
              <div className="facts">
                <div><span className="label">Bus model</span><span>v{record.release.components.bus_model.ledger_version} weights, applied to {SEGMENT_SHORT[record.release.components.bus_model.applied_to_segment] || record.release.components.bus_model.applied_to_segment}</span></div>
                <div><span className="label">Release fingerprint</span><code>{shortHash(record.release.fingerprint, 16)}</code></div>
                <div><span className="label">Planner code</span><code>{shortHash(record.release.components.planner.sha256, 16)}</code></div>
                <div><span className="label">Web client</span><code>{shortHash(record.release.components.web.sha256, 16)}</code></div>
                <div><span className="label">Delhi network snapshot</span><code>{shortHash(record.release.data.snapshot['network.npz'].sha256, 16)}</code></div>
                <div><span className="label">Pinned datasets</span><span>{Object.values(record.release.data.pinned_sources).map((d) => d.title).join('; ')}</span></div>
              </div>
            </>
          )}
          <div className="facts">
            <div><span className="label">Training window</span><span>{record.training_window.dates_ist.join(', ')}</span></div>
            <div><span className="label">Holdout</span><span>{record.holdout.dates_ist.join(', ')} · {record.holdout.rows} trips</span></div>
            <div><span className="label">Artifact sha256</span><code>{shortHash(record.artifact?.sha256, 16)}</code></div>
            <div><span className="label">Code commit</span><code>{shortHash(record.code?.git_head, 10)}</code></div>
            <div><span className="label">Runtime</span><span>scikit-learn {record.runtime?.['scikit-learn']}</span></div>
            <div><span className="label">Parent</span><span>{record.parent_version ? `v${record.parent_version}` : '—'}</span></div>
          </div>
          {record.gate && (
            <>
              <h4 className="section-title">{record.gate.kind === 'release' ? 'Release gate' : 'Promotion gate'} · {record.gate.passed ? 'passed' : 'failed'}</h4>
              <ul className="gate-list">
                {record.gate.checks.map((check) => (
                  <li key={check.name} className={check.passed ? 'ok' : 'fail'}>
                    <Status status={check.passed ? 'PASS' : 'FAIL'} compact />
                    <div><strong>{humanize(check.name)}</strong><span className="muted small">{check.detail}</span></div>
                  </li>
                ))}
              </ul>
            </>
          )}
          {!record.gate && <div className="callout"><Icon name="info" size={16} /> Imported Phase 2 release: approved by the Phase 2 quality gate (12 checks).</div>}
        </Card>

        <Card title="Why we version models">
          <div className="why-list">
            {WHY.map(([icon, title, text]) => (
              <div key={title} className="why-item">
                <span className="why-icon"><Icon name={icon} size={16} /></span>
                <div><strong>{title}</strong><p className="muted small">{text}</p></div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Holdout error by segment" subtitle="8 July · rejected version faded">
          <Legend items={keys.map((k) => ({ label: k, color: colors[k] }))} />
          <GroupedBars data={bars} categories={SEGMENT_ORDER} groups={keys} colors={colors} yLabel="MAE (min)"
            categoryLabel={(c) => SEGMENT_SHORT[c]} isFaded={(d) => d.status === 'rejected'} />
        </Card>
        <Card title="Rolling error through the holdout day" subtitle="15-trip rolling MAE, 8 July in time order">
          <Legend items={keys.map((k) => ({ label: k, color: colors[k] }))} />
          <LineChart series={registry.holdout_rolling.map((s) => ({ name: s.version, color: colors[s.version], points: s.points }))}
            xLabel="Holdout trips in time order" yLabel="Rolling MAE (min)" />
        </Card>
      </div>

      <Card title="What changed between two versions" action={
        <div className="inline-form">
          <select value={from} onChange={(e) => setFrom(Number(e.target.value))}>{versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select>
          <Icon name="arrow" size={14} />
          <select value={to} onChange={(e) => setTo(Number(e.target.value))}>{versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select>
        </div>
      }>
        {from === to ? <p className="muted">Pick two different versions.</p> : (
          <Table dense rows={diff} columns={[
            { key: 'field', label: 'Field' },
            { key: 'old', label: `v${from}`, render: (r) => <span className="mono" title={String(r.old ?? '')}>{clip(r.old)}</span> },
            { key: 'new', label: `v${to}`, render: (r) => <span className="mono" title={String(r.new ?? '')}>{clip(r.new)}</span> },
            { key: 'changed', label: 'Change', render: (r) => (r.changed ? <Badge tone="warn">changed</Badge> : <span className="muted">same</span>) },
          ]} />
        )}
      </Card>

      <div className="grid-2 wide-left">
        <Card title="Audit log" subtitle="Append-only; each entry hashes the previous one"
          action={registry.chain && <Status status={registry.chain.valid ? 'PASS' : 'FAIL'} label={registry.chain.valid ? `Chain intact · ${registry.chain.entries}` : `Broken at #${registry.chain.broken_at_sequence}`} />}>
          <ol className="timeline">
            {registry.audit.map((entry) => (
              <li key={entry.sequence} className={`tl-${entry.action}`}>
                <span className="tl-dot" />
                <div className="tl-body">
                  <div className="tl-head">
                    <strong>{humanize(entry.action)}</strong>
                    {entry.version != null && <Badge>v{entry.version}</Badge>}
                    {entry.alias && <Badge tone="neutral">{entry.alias} alias</Badge>}
                    {'after' in entry && entry.before != null && <span className="muted small">{entry.before} → {entry.after}</span>}
                    <span className="muted small tl-when">{when(entry.at)} · {entry.actor}</span>
                  </div>
                  {entry.reason && <p className="small">{entry.reason}</p>}
                  <code className="tiny">{shortHash(entry.entry_sha256, 12)}</code>
                </div>
              </li>
            ))}
          </ol>
        </Card>
        <div className="stack">
          <Card title="Rollback drill" action={drill && <Status status={drill.passed ? 'PASS' : 'FAIL'} />}>
            {drill ? (
              <ul className="steps">
                <li><Icon name="refresh" size={14} /> Rolled back v{drill.rolled_back_from} → v{drill.rolled_back_to}</li>
                <li><Icon name="hash" size={14} /> Artifact hash {drill.artifact_hash_verified ? 'verified' : 'mismatch'}</li>
                <li><Icon name="play" size={14} /> Demo prediction {num(drill.demo_prediction_minutes)} min</li>
                <li><Icon name="check" size={14} /> Champion restored to v{drill.restored_champion}</li>
              </ul>
            ) : <p className="muted">No previous version to roll back to yet.</p>}
          </Card>
          <Card title="MLflow registry mirror" action={<Badge tone={mlflow.status === 'ok' ? 'good' : mlflow.status === 'failed' ? 'bad' : 'neutral'}>{mlflow.status || 'n/a'}</Badge>}>
            {mlflow.status === 'ok' && <p className="small">Versions {(mlflow.versions || []).map((v) => `v${v.version}`).join(', ')} and the aliases {Object.entries(mlflow.aliases || {}).map(([a, v]) => `${a} → v${v}`).join(', ')} are registered in a separate Phase 3 store.</p>}
            {mlflow.error && <p className="small bad-text">{mlflow.error}</p>}
            {mlflow.reason && <p className="small muted">{mlflow.reason}</p>}
            {mlflow.ui_command && <CodeLine text={mlflow.ui_command} />}
          </Card>
        </div>
      </div>
    </div>
  );
}
