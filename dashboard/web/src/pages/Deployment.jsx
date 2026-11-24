import { useState } from 'react';
import { postJSON } from '../api.js';
import { Badge, Card, CodeLine, Icon, Status, Table } from '../components/ui.jsx';
import { LineChart } from '../components/charts.jsx';
import { num, SEGMENT_ORDER, SEGMENT_SHORT, shortHash, versionColor } from '../lib/format.js';

export default function Deployment({ state, reload }) {
  const { release, state: deployState, workflows, export: bundle, checks } = state.deployment;
  const [baseUrl, setBaseUrl] = useState('http://127.0.0.1:8001');
  const [probe, setProbe] = useState(null);
  const [probing, setProbing] = useState(false);
  const [form, setForm] = useState({ segment_id: SEGMENT_ORDER[0], date: '2019-07-08', time: '17:10' });
  const [prediction, setPrediction] = useState(null);
  const [predicting, setPredicting] = useState(false);

  const runProbe = async () => {
    setProbing(true);
    try {
      setProbe(await postJSON('/api/service-check', { base_url: baseUrl }));
      reload();
    } catch (exc) {
      setProbe({ error: exc.message });
    } finally {
      setProbing(false);
    }
  };
  const runPredict = async () => {
    setPredicting(true);
    try {
      setPrediction(await postJSON('/api/predict', form));
    } catch (exc) {
      setPrediction({ error: exc.message, predictions: [] });
    } finally {
      setPredicting(false);
    }
  };

  const history = (checks || []).map((c, i) => ({ ...c, n: i + 1 }));
  const latency = [
    { name: '/health', color: 'var(--s1)', points: history.map((c) => [c.n, c.health_latency_ms || 0, `${c.base_url} · ${c.checked_at.slice(11, 19)} UTC`]) },
    { name: '/predict/bus', color: 'var(--s2)', points: history.map((c) => [c.n, c.predict_latency_ms || 0, `${c.base_url} · ${c.checked_at.slice(11, 19)} UTC`]) },
  ];
  const ok = history.filter((c) => c.health_status === 200 && c.predict_status === 200).length;
  const maxMinutes = Math.max(1, ...(prediction?.predictions || []).map((p) => p.minutes || 0));

  return (
    <div className="page">
      <div className="grid-2">
        <Card title="Live Phase 2 release (v1)" subtitle="GHCR image pinned by digest" action={<Badge tone="good">released</Badge>}>
          {release ? (
            <div className="facts">
              <div><span className="label">Image digest</span><code>{shortHash(release.image.split('@')[1], 24)}</code></div>
              <div><span className="label">Expected demo prediction</span><span>{num(release.expected_minutes, 4)} min</span></div>
              <div><span className="label">Release run</span><a href={release.release_run} target="_blank" rel="noreferrer">GitHub Actions <Icon name="arrow" size={12} /></a></div>
              {deployState && <div><span className="label">Local Compose</span><span>v{deployState.active.model_version} on port {deployState.active.port}</span></div>}
              <div><span className="label">CI workflows</span><span className="chips">{workflows.map((w) => <span key={w} className="chip">{w}</span>)}</span></div>
            </div>
          ) : <p className="muted">No Phase 2 deployment record found.</p>}
        </Card>
        <Card title="Phase 3 champion bundle" subtitle="Same FastAPI code, new model version" action={bundle && <Badge tone="accent">v{bundle.version}</Badge>}>
          {bundle ? (
            <>
              <div className="facts">
                <div><span className="label">Bundle</span><code>outputs/phase3/{bundle.path}</code></div>
                <div><span className="label">Manifest sha256</span><code>{shortHash(bundle.manifest_sha256, 16)}</code></div>
                <div><span className="label">Demo prediction</span><span>{num(bundle.demo_prediction_minutes, 3)} min</span></div>
              </div>
              <p className="label">Serve it next to v1</p>
              <CodeLine text={bundle.serve_command} />
              <p className="muted small">Publishing a v2 image still goes through the release approval workflow.</p>
            </>
          ) : <p className="muted">Run the lifecycle to export the champion.</p>}
        </Card>
      </div>

      <Card title="Service health probe" subtitle="Black-box check of a running API: GET /health and POST /predict/bus with the documented example">
        <div className="inline-form">
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} spellCheck={false} aria-label="API base URL" />
          <button type="button" className="btn btn-primary" onClick={runProbe} disabled={probing}>
            <Icon name="play" size={14} /> {probing ? 'Checking…' : 'Run check'}
          </button>
          <span className="muted small">v1 container: 8001 · v2 bundle: 8002</span>
        </div>
        {probe && (probe.error ? <div className="banner banner-bad"><Icon name="alert" /> {probe.error}</div> : (
          <div className="probe-result">
            <div className={`probe ${probe.health_status === 200 ? 'ok' : 'fail'}`}>
              <span className="label">GET /health</span>
              <strong>{probe.health_status ?? 'no response'}</strong>
              <span>{probe.health_latency_ms} ms</span>
              {probe.health_response?.model_version && <Badge tone="accent">model v{probe.health_response.model_version}</Badge>}
            </div>
            <div className={`probe ${probe.predict_status === 200 ? 'ok' : 'fail'}`}>
              <span className="label">POST /predict/bus</span>
              <strong>{probe.predict_status ?? 'no response'}</strong>
              <span>{probe.predict_latency_ms} ms</span>
              {probe.predict_response?.duration_minutes && <Badge tone="good">{num(probe.predict_response.duration_minutes, 3)} min</Badge>}
            </div>
          </div>
        ))}
        {history.length > 0 && (
          <>
            <p className="muted small">{history.length} checks recorded · success rate {Math.round((ok / history.length) * 100)}%</p>
            {history.length > 1 && <LineChart series={latency} xLabel="Check number" yLabel="Latency (ms)" format={(v) => `${v.toFixed(0)} ms`} height={200} />}
          </>
        )}
      </Card>

      <Card title="Every registered version, side by side" subtitle="In-process predictions from the registry artifacts">
        <div className="inline-form">
          <select value={form.segment_id} onChange={(e) => setForm({ ...form, segment_id: e.target.value })}>
            {SEGMENT_ORDER.map((s) => <option key={s} value={s}>{SEGMENT_SHORT[s]}</option>)}
          </select>
          <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          <input type="time" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
          <button type="button" className="btn btn-primary" onClick={runPredict} disabled={predicting}>
            <Icon name="play" size={14} /> {predicting ? 'Predicting…' : 'Predict'}
          </button>
        </div>
        {prediction?.error && <div className="banner banner-bad"><Icon name="alert" /> {prediction.error}</div>}
        {prediction?.predictions?.length > 0 && (
          <>
            {!prediction.in_api_scope && <div className="banner banner-warn"><Icon name="info" /> The deployed API serves only Route 90 on ORR eastbound; this is for model inspection.</div>}
            <div className="predictions">
              {prediction.predictions.map((p) => (
                <div key={p.version} className={`prediction status-${p.status}`}>
                  <span className="version-tag" style={{ background: versionColor(p.version) }}>v{p.version}</span>
                  <span className="prediction-bar"><span style={{ width: `${((p.minutes || 0) / maxMinutes) * 100}%`, background: versionColor(p.version) }} /></span>
                  <strong>{p.minutes != null ? `${num(p.minutes)} min` : '—'}</strong>
                  <span className="muted small">{p.aliases.join(', ') || p.status}{p.note ? ` · ${p.note}` : ''}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </Card>

      {history.length > 0 && (
        <Card title="Probe history">
          <Table dense rows={[...history].reverse().slice(0, 10)} columns={[
            { key: 'checked_at', label: 'When (UTC)', render: (c) => c.checked_at.replace('T', ' ').slice(0, 19) },
            { key: 'base_url', label: 'Target' },
            { key: 'h', label: '/health', render: (c) => <Status status={c.health_status === 200 ? 'PASS' : 'FAIL'} label={String(c.health_status ?? '—')} compact /> },
            { key: 'p', label: '/predict/bus', render: (c) => <Status status={c.predict_status === 200 ? 'PASS' : 'FAIL'} label={String(c.predict_status ?? '—')} compact /> },
            { key: 'l', label: 'Latency', align: 'right', render: (c) => `${c.health_latency_ms} / ${c.predict_latency_ms} ms` },
          ]} />
        </Card>
      )}
    </div>
  );
}
