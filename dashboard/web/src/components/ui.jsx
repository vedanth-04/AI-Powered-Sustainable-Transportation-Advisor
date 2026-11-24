import { useState } from 'react';
import { statusMeta } from '../lib/format.js';

const PATHS = {
  overview: 'M3 12l9-8 9 8M5 10v10h5v-6h4v6h5V10',
  pipeline: 'M4 6h5v5H4zM15 13h5v5h-5zM9 8.5h3a2 2 0 0 1 2 2v3.5a2 2 0 0 0 1 1.5',
  data: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  flask: 'M9 3h6M10 3v6L4.5 18.5A1.6 1.6 0 0 0 6 21h12a1.6 1.6 0 0 0 1.5-2.5L14 9V3M7 15h10',
  activity: 'M3 12h4l3-8 4 16 3-8h4',
  layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5',
  rocket: 'M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2M9 13l2 2M14 4c3-1 6-1 6-1s0 3-1 6l-6 6-5-5zM15 9a1 1 0 1 0 0-.01',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM8.5 12l2.5 2.5 4.5-5',
  sun: 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
  refresh: 'M20 11a8 8 0 0 0-14.9-3.5M4 4v4h4M4 13a8 8 0 0 0 14.9 3.5M20 20v-4h-4',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M6 6l12 12M18 6L6 18',
  alert: 'M12 3l10 18H2zM12 10v5M12 18v.01',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2',
  branch: 'M6 3v12M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9c0 5-12 3-12 6',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  bus: 'M5 4h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM4 11h16M8 18v2M16 18v2M7.5 14.5h.01M16.5 14.5h.01',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  hash: 'M5 9h14M5 15h14M10 4L8 20M16 4l-2 16',
  play: 'M7 4l12 8-12 8z',
  server: 'M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5v.01',
};

export function Icon({ name, size = 18, className = '' }) {
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] || PATHS.info} />
    </svg>
  );
}

export function Card({ title, subtitle, action, children, className = '', pad = true }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <p className="muted small">{subtitle}</p>}
          </div>
          {action && <div className="card-action">{action}</div>}
        </header>
      )}
      <div className={pad ? 'card-body' : ''}>{children}</div>
    </section>
  );
}

export function Kpi({ icon, label, value, hint, tone = 'accent', trend }) {
  return (
    <div className={`kpi tone-${tone}`}>
      <div className="kpi-icon"><Icon name={icon} size={20} /></div>
      <div className="kpi-text">
        <span className="kpi-label">{label}</span>
        <span className="kpi-value">{value}</span>
        {hint && <span className={`kpi-hint ${trend ? `trend-${trend}` : ''}`}>{hint}</span>}
      </div>
    </div>
  );
}

const TONE_ICON = { good: 'check', warn: 'alert', bad: 'x', idle: 'clock', accent: 'info' };

export function Status({ status, label, compact = false }) {
  const meta = statusMeta(status);
  return (
    <span className={`pill tone-${meta.tone} ${compact ? 'pill-compact' : ''}`}>
      <Icon name={TONE_ICON[meta.tone]} size={12} />
      {label || meta.label}
    </span>
  );
}

export function Badge({ children, tone = 'neutral', title }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

export function Segmented({ options, value, onChange, size = 'md' }) {
  return (
    <div className={`segmented segmented-${size}`} role="tablist">
      {options.map((option) => (
        <button key={option.value} type="button" role="tab" aria-selected={option.value === value}
          className={option.value === value ? 'active' : ''} onClick={() => onChange(option.value)}>
          {option.dot && <span className="dot" style={{ background: option.dot }} />}
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Table({ columns, rows, empty = 'Nothing to show yet.', dense = false }) {
  if (!rows || !rows.length) return <p className="muted">{empty}</p>;
  return (
    <div className="table-wrap">
      <table className={`table ${dense ? 'table-dense' : ''}`}>
        <thead>
          <tr>{columns.map((column) => <th key={column.key} className={column.align === 'right' ? 'right' : ''}>{column.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.id ?? index}>
              {columns.map((column) => (
                <td key={column.key} className={column.align === 'right' ? 'right num' : ''}>
                  {column.render ? column.render(row) : row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Empty({ title = 'Not produced yet', command }) {
  return (
    <div className="empty">
      <Icon name="info" size={22} />
      <div>
        <strong>{title}</strong>
        {command && <p className="muted">Run <code>{command}</code> from the repository root, then press Refresh.</p>}
      </div>
    </div>
  );
}

export function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button type="button" className="btn btn-ghost btn-small" onClick={copy}>
      <Icon name={copied ? 'check' : 'copy'} size={14} /> {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

export function CodeLine({ text }) {
  return (
    <div className="codeline">
      <code>{text}</code>
      <CopyButton text={text} />
    </div>
  );
}

export function Legend({ items }) {
  return (
    <div className="legend">
      {items.map((item) => (
        <span key={item.label} className="legend-item">
          <span className={`swatch ${item.shape || ''}`} style={{ background: item.color, borderColor: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

export function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}
