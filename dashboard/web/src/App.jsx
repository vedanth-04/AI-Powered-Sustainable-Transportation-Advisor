import { useCallback, useEffect, useState } from 'react';
import { getJSON } from './api.js';
import { Icon } from './components/ui.jsx';
import Overview from './pages/Overview.jsx';
import Pipeline from './pages/Pipeline.jsx';
import DataPage from './pages/Data.jsx';
import Experiments from './pages/Experiments.jsx';
import Drift from './pages/Drift.jsx';
import Registry from './pages/Registry.jsx';
import Deployment from './pages/Deployment.jsx';
import Governance from './pages/Governance.jsx';

const PAGES = [
  { id: 'overview', label: 'Overview', icon: 'overview', title: 'MLOps control room', subtitle: 'The whole lifecycle of the bus riding-time model at a glance', component: Overview },
  { id: 'pipeline', label: 'Pipeline', icon: 'pipeline', title: 'End-to-end pipeline', subtitle: 'Eleven stages from raw GPS to rollback, each backed by an artifact', component: Pipeline },
  { id: 'data', label: 'Data', icon: 'data', title: 'Data & labels', subtitle: 'Delhi bus GPS (July 2019) turned into labelled segment traversals', component: DataPage },
  { id: 'experiments', label: 'Experiments', icon: 'flask', title: 'Experiments & quality gate', subtitle: 'How v1 was selected and approved in Phase 2', component: Experiments },
  { id: 'drift', label: 'Drift monitor', icon: 'activity', title: 'Drift detection & monitoring', subtitle: 'Historical replay of 5 and 8 July with induced data and model drift', component: Drift },
  { id: 'registry', label: 'Model registry', icon: 'layers', title: 'Model versions', subtitle: 'Why each version exists, how it was gated, and the audit trail', component: Registry },
  { id: 'deployment', label: 'Deployment', icon: 'rocket', title: 'Release & serving', subtitle: 'Pinned releases, the exported champion, live health and predictions', component: Deployment },
  { id: 'governance', label: 'Governance', icon: 'shield', title: 'Governance', subtitle: 'Controls, their evidence and why they fit this project', component: Governance },
];

function readTheme() {
  try {
    return localStorage.getItem('mlops-theme') || 'dark';
  } catch {
    return 'dark';
  }
}

function currentPage() {
  const id = (typeof window !== 'undefined' ? window.location.hash : '').replace('#', '');
  return PAGES.some((page) => page.id === id) ? id : 'overview';
}

export default function App() {
  const [page, setPage] = useState(currentPage);
  const [theme, setTheme] = useState(readTheme);
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setState(await getJSON('/api/state'));
      setError(null);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const onHash = () => setPage(currentPage());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem('mlops-theme', theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);

  const go = (id) => {
    window.location.hash = id;
    setPage(id);
    window.scrollTo({ top: 0 });
  };
  const meta = PAGES.find((p) => p.id === page);
  const Page = meta.component;
  const kpis = state?.kpis;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Icon name="bus" size={22} /></div>
          <div>
            <strong>Transit MLOps</strong>
            <span>Sustainable Transportation Advisor</span>
          </div>
        </div>
        <nav>
          {PAGES.map((item) => (
            <button key={item.id} type="button" className={`nav-item ${item.id === page ? 'active' : ''}`} onClick={() => go(item.id)}>
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="replay-note">
            <Icon name="clock" size={14} />
            <span>Historical replay · 5 & 8 Jul 2019. Not a live public service.</span>
          </div>
          <button type="button" className="btn btn-ghost theme-toggle" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={16} />
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{meta.title}</h1>
            <p className="muted">{meta.subtitle}</p>
          </div>
          <div className="topbar-actions">
            {kpis?.champion && (
              <span className="champion-chip">
                <span className="pulse" /> Serving <strong>v{kpis.champion}</strong>
                {kpis.previous && <span className="muted"> · rollback v{kpis.previous}</span>}
              </span>
            )}
            <button type="button" className="btn" onClick={load} disabled={loading}>
              <Icon name="refresh" size={16} className={loading ? 'spin' : ''} /> Refresh
            </button>
          </div>
        </header>

        {error && (
          <div className="banner banner-bad">
            <Icon name="alert" />
            <div>
              <strong>Cannot reach the dashboard API.</strong> {error}. Start it with <code>python -m dashboard.server</code> from the repository root.
            </div>
          </div>
        )}
        {!state && !error && <div className="loading"><span className="spinner" /> Loading pipeline artifacts…</div>}
        {state && <Page state={state} go={go} reload={load} />}
        <footer className="footer muted small">
          Artifacts read from <code>{state?.phase3_dir || 'outputs/phase3'}</code>
          {state?.generated_at && <> · refreshed {new Date(state.generated_at).toLocaleTimeString()}</>}
        </footer>
      </main>
    </div>
  );
}
