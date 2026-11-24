// Hand-built SVG charts: thin marks, recessive grid, hover tooltips on every chart.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { band, linear, nearestIndex, niceDomain, tickLabel, ticks } from '../lib/scale.js';
import { statusMeta } from '../lib/format.js';

const useIsoLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect;

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useIsoLayoutEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const measure = () => setWidth(Math.max(0, Math.floor(element.getBoundingClientRect().width)));
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function Tooltip({ tip }) {
  if (!tip) return null;
  return (
    <div className="tooltip" style={{ left: tip.x, top: tip.y, transform: tip.flip ? 'translate(calc(-100% - 14px), -50%)' : 'translate(14px, -50%)' }}>
      {tip.title && <div className="tooltip-title">{tip.title}</div>}
      {tip.rows.map((row) => (
        <div className="tooltip-row" key={row.label}>
          {row.color && <span className="swatch" style={{ background: row.color }} />}
          <span className="tooltip-label">{row.label}</span>
          <span className="tooltip-value">{row.value}</span>
        </div>
      ))}
    </div>
  );
}

function YAxis({ scale, tickValues, width, label, left }) {
  return (
    <g className="axis">
      {tickValues.map((value) => (
        <g key={value} transform={`translate(0,${scale(value)})`}>
          <line className="grid" x1={left} x2={width} />
          <text x={left - 8} dy="0.32em" textAnchor="end">{tickLabel(value)}</text>
        </g>
      ))}
      {label && <text className="axis-title" transform={`translate(12,${(scale.range[0] + scale.range[1]) / 2}) rotate(-90)`} textAnchor="middle">{label}</text>}
    </g>
  );
}

const roundedTop = (x, y, w, h, r = 4) => {
  if (h <= 0) return '';
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
};

const roundedRight = (x, y, w, h, r = 4) => {
  if (w <= 0) return '';
  const rr = Math.min(r, h / 2, w);
  return `M${x},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x}Z`;
};

function tipPosition(event, container) {
  const box = container.getBoundingClientRect();
  const x = event.clientX - box.left;
  return { x, y: event.clientY - box.top, flip: x > box.width * 0.62 };
}

// ----- grouped vertical bars ------------------------------------------------------------------------
export function GroupedBars({ data, categories, groups, colors, height = 260, yLabel, format = (v) => v.toFixed(2),
  categoryLabel = (c) => c, isFaded = () => false }) {
  const [ref, width] = useWidth();
  const [tip, setTip] = useState(null);
  const margin = { top: 12, right: 12, bottom: 44, left: 52 };
  const max = Math.max(...data.map((d) => d.value), 0);
  const yDomain = niceDomain(0, max * 1.08);
  const y = linear(yDomain, [height - margin.bottom, margin.top]);
  const outer = band(categories, [margin.left, Math.max(margin.left + 1, width - margin.right)], 0.28);
  const inner = band(groups, [0, outer.bandwidth], 0.08);
  return (
    <div className="chart" ref={ref} onMouseLeave={() => setTip(null)}>
      {width > 0 && (
        <svg width={width} height={height}>
          <YAxis scale={y} tickValues={ticks(yDomain)} width={width - margin.right} left={margin.left} label={yLabel} />
          {categories.map((category) => (
            <text key={category} className="axis tick-x" x={outer(category) + outer.bandwidth / 2} y={height - margin.bottom + 18} textAnchor="middle">
              {categoryLabel(category)}
            </text>
          ))}
          {data.map((d) => {
            const x = outer(d.category) + inner(d.group);
            const top = y(d.value);
            const faded = isFaded(d);
            return (
              <path key={`${d.category}-${d.group}`} d={roundedTop(x, top, Math.max(1, inner.bandwidth), y(0) - top)}
                className="mark" style={{ fill: colors[d.group], opacity: faded ? 0.35 : 1 }}
                onMouseMove={(event) => setTip({ ...tipPosition(event, ref.current), title: categoryLabel(d.category),
                  rows: [{ label: d.group, value: format(d.value), color: colors[d.group] }, ...(d.extra || [])] })} />
            );
          })}
          <line className="baseline" x1={margin.left} x2={width - margin.right} y1={y(0)} y2={y(0)} />
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}

// ----- multi-series line chart with crosshair -------------------------------------------------------
export function LineChart({ series, height = 260, xLabel, yLabel, format = (v) => v.toFixed(2), reference }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const margin = { top: 14, right: 16, bottom: 40, left: 52 };
  const xs = series.flatMap((s) => s.points.map((p) => p[0]));
  const ys = series.flatMap((s) => s.points.map((p) => p[1])).concat(reference ? [reference.value] : []);
  const xMin = xs.length ? Math.min(...xs) : 0;
  const xDomain = [xMin, Math.max(xMin + 1, ...xs)];
  const yDomain = niceDomain(0, Math.max(...ys, 1) * 1.05);
  const x = linear(xDomain, [margin.left, Math.max(margin.left + 1, width - margin.right)]);
  const y = linear(yDomain, [height - margin.bottom, margin.top]);
  const path = (points) => points.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
  const onMove = (event) => {
    const box = ref.current.getBoundingClientRect();
    const target = x.domain[0] + ((event.clientX - box.left - margin.left) / (width - margin.left - margin.right)) * (x.domain[1] - x.domain[0]);
    setHover({ target, pos: tipPosition(event, ref.current) });
  };
  let tip = null;
  if (hover) {
    const rows = series.map((s) => {
      if (!s.points.length) return null;
      const point = s.points[nearestIndex(s.points.map((p) => p[0]), hover.target)];
      return { label: s.name, value: format(point[1]), color: s.color, point };
    }).filter(Boolean);
    tip = { ...hover.pos, title: rows[0]?.point[2] || `x = ${Math.round(hover.target)}`, rows };
  }
  return (
    <div className="chart" ref={ref} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={height}>
          <YAxis scale={y} tickValues={ticks(yDomain)} width={width - margin.right} left={margin.left} label={yLabel} />
          {ticks(xDomain, 6).map((value) => (
            <text key={value} className="axis tick-x" x={x(value)} y={height - margin.bottom + 18} textAnchor="middle">{tickLabel(value)}</text>
          ))}
          {xLabel && <text className="axis axis-title" x={(margin.left + width - margin.right) / 2} y={height - 4} textAnchor="middle">{xLabel}</text>}
          {reference && (
            <g>
              <line className="ref-line" x1={margin.left} x2={width - margin.right} y1={y(reference.value)} y2={y(reference.value)} />
              <text className="ref-label" x={width - margin.right - 4} y={y(reference.value) - 6} textAnchor="end">{reference.label}</text>
            </g>
          )}
          {series.map((s) => <path key={s.name} d={path(s.points)} className="line" style={{ stroke: s.color }} />)}
          {tip && <line className="crosshair" x1={x(tip.rows[0].point[0])} x2={x(tip.rows[0].point[0])} y1={margin.top} y2={height - margin.bottom} />}
          {tip && tip.rows.map((row) => (
            <circle key={row.label} cx={x(row.point[0])} cy={y(row.point[1])} r={4.5} className="hover-dot" style={{ fill: row.color }} />
          ))}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}

// ----- error timeline: each label, rolling MAE, approved level, injection marker --------------------
export function ErrorTimeline({ points, approved, markers = {}, height = 300 }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const margin = { top: 34, right: 16, bottom: 40, left: 52 };
  const sorted = useMemo(() => [...points.map((p) => p[1])].sort((a, b) => a - b), [points]);
  const clip = Math.max(10, (sorted[Math.floor(sorted.length * 0.97)] || 10) * 1.1);
  const yDomain = niceDomain(0, clip);
  const x = linear([1, Math.max(2, points.length)], [margin.left, Math.max(margin.left + 1, width - margin.right)]);
  const y = linear(yDomain, [height - margin.bottom, margin.top]);
  const yc = (value) => y(Math.min(value, yDomain[1]));
  const rolling = points.filter((p) => p[2] !== null);
  const line = rolling.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${yc(p[2]).toFixed(1)}`).join('');
  const onMove = (event) => {
    const box = ref.current.getBoundingClientRect();
    const target = 1 + ((event.clientX - box.left - margin.left) / (width - margin.left - margin.right)) * (points.length - 1);
    const index = Math.max(0, Math.min(points.length - 1, Math.round(target) - 1));
    setHover({ index, pos: tipPosition(event, ref.current) });
  };
  const active = hover ? points[hover.index] : null;
  const tip = active && {
    ...hover.pos, title: `Label #${active[0]} · ${active[5]}`,
    rows: [{ label: 'Segment', value: active[4] },
      { label: 'Absolute error', value: `${active[1].toFixed(2)} min`, color: active[3] ? 'var(--s2)' : 'var(--muted)' },
      { label: 'Rolling MAE (20)', value: active[2] === null ? '—' : `${active[2].toFixed(2)} min`, color: 'var(--s1)' },
      { label: 'Event', value: active[3] ? 'Injected change' : 'Real traffic' }],
  };
  const marker = (value, text, cls, row) => value && (
    <g className={cls}>
      <line x1={x(value)} x2={x(value)} y1={margin.top - 4} y2={height - margin.bottom} />
      <text x={x(value) + 5} y={margin.top - 18 + row * 13}>{text}</text>
    </g>
  );
  return (
    <div className="chart" ref={ref} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={height}>
          <YAxis scale={y} tickValues={ticks(yDomain)} width={width - margin.right} left={margin.left} label="Absolute error (min)" />
          {ticks([1, points.length], 8).map((value) => (
            <text key={value} className="axis tick-x" x={x(value)} y={height - margin.bottom + 18} textAnchor="middle">{tickLabel(value)}</text>
          ))}
          <text className="axis axis-title" x={(margin.left + width - margin.right) / 2} y={height - 4} textAnchor="middle">Completed trips in label-arrival order (5 Jul → 8 Jul)</text>
          {marker(markers.day_break, '8 Jul starts', 'marker-muted', 0)}
          {marker(markers.onset, 'injection starts', 'marker-alert', 1)}
          {points.map((p) => (
            <circle key={p[0]} cx={x(p[0])} cy={yc(p[1])} r={p[1] > yDomain[1] ? 4 : 3}
              className={`dot ${p[3] ? 'dot-injected' : 'dot-real'} ${p[1] > yDomain[1] ? 'dot-clipped' : ''}`} />
          ))}
          <line className="ref-line" x1={margin.left} x2={width - margin.right} y1={y(approved)} y2={y(approved)} />
          <text className="ref-label" x={margin.left + 6} y={y(approved) - 6}>approved MAE {approved.toFixed(2)} min</text>
          <path d={line} className="line line-strong" style={{ stroke: 'var(--s1)' }} />
          {active && <line className="crosshair" x1={x(active[0])} x2={x(active[0])} y1={margin.top} y2={height - margin.bottom} />}
          {active && <circle cx={x(active[0])} cy={yc(active[1])} r={6} className="hover-ring" />}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}

// ----- CUSUM ----------------------------------------------------------------------------------------
export function CusumChart({ detector, height = 240 }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const margin = { top: 18, right: 16, bottom: 40, left: 52 };
  const points = detector.points;
  const max = Math.max(detector.threshold * 1.25, ...points.map((p) => p[1]));
  const yDomain = niceDomain(0, max);
  const x = linear([1, Math.max(2, points.length)], [margin.left, Math.max(margin.left + 1, width - margin.right)]);
  const y = linear(yDomain, [height - margin.bottom, margin.top]);
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
  const area = `${line}L${x(points.length).toFixed(1)},${y(0)}L${x(1).toFixed(1)},${y(0)}Z`;
  const onMove = (event) => {
    const box = ref.current.getBoundingClientRect();
    const target = 1 + ((event.clientX - box.left - margin.left) / (width - margin.left - margin.right)) * (points.length - 1);
    setHover({ index: Math.max(0, Math.min(points.length - 1, Math.round(target) - 1)), pos: tipPosition(event, ref.current) });
  };
  const active = hover ? points[hover.index] : null;
  const tip = active && { ...hover.pos, title: `Label #${active[0]} · ${active[2]}`,
    rows: [{ label: 'CUSUM', value: active[1].toFixed(2), color: 'var(--s1)' },
      { label: 'Alarm threshold', value: detector.threshold.toFixed(2), color: 'var(--bad)' }] };
  return (
    <div className="chart" ref={ref} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      {width > 0 && points.length > 0 && (
        <svg width={width} height={height}>
          <YAxis scale={y} tickValues={ticks(yDomain)} width={width - margin.right} left={margin.left} label="CUSUM statistic" />
          {ticks([1, points.length], 8).map((value) => (
            <text key={value} className="axis tick-x" x={x(value)} y={height - margin.bottom + 18} textAnchor="middle">{tickLabel(value)}</text>
          ))}
          <text className="axis axis-title" x={(margin.left + width - margin.right) / 2} y={height - 4} textAnchor="middle">Labels received by this detector</text>
          <path d={area} className="area" style={{ fill: 'var(--s1)' }} />
          <path d={line} className="line line-strong" style={{ stroke: 'var(--s1)' }} />
          <line className="threshold-line" x1={margin.left} x2={width - margin.right} y1={y(detector.threshold)} y2={y(detector.threshold)} />
          <text className="threshold-label" x={margin.left + 6} y={y(detector.threshold) - 6}>alarm threshold {detector.threshold.toFixed(1)}</text>
          {detector.alarm && (() => {
            const ax = x(detector.alarm[0]);
            const right = ax < margin.left + 220; // keep the label clear of the threshold label
            return (
              <g className="alarm">
                <circle cx={ax} cy={y(detector.alarm[1])} r={7} />
                <text x={right ? ax + 12 : ax - 12} y={y(detector.alarm[1]) - 12} textAnchor={right ? 'start' : 'end'}>ALARM · {detector.alarm[2]}</text>
              </g>
            );
          })()}
          {active && <line className="crosshair" x1={x(active[0])} x2={x(active[0])} y1={margin.top} y2={height - margin.bottom} />}
          {active && <circle cx={x(active[0])} cy={y(active[1])} r={5} className="hover-dot" style={{ fill: 'var(--s1)' }} />}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}

// ----- status grid (HTML, so every cell carries its word) ------------------------------------------
const CHECKS = ['Input drift', 'Prediction drift', 'Data quality', 'Performance'];

export function StatusGrid({ windows, onSelect, selected }) {
  return (
    <div className="status-grid" style={{ gridTemplateColumns: `130px repeat(${windows.length}, minmax(64px, 1fr))` }}>
      <div />
      {windows.map((w) => (
        <button key={w.window} type="button" className={`sg-head ${selected === w.window ? 'selected' : ''}`} onClick={() => onSelect && onSelect(w.window)}
          title={`${w.requests} requests${w.injected ? `, ${w.injected} injected` : ''}`}>
          <span>{w.short.split(' · ')[0]}</span>
          <strong>{w.short.split(' · ')[1]}</strong>
        </button>
      ))}
      {CHECKS.map((check) => [
        <div key={check} className="sg-row-label">{check}</div>,
        ...windows.map((w) => {
          const meta = statusMeta(w.statuses[check]);
          return (
            <div key={`${check}-${w.window}`} className={`sg-cell tone-${meta.tone}`} title={`${w.window} · ${check}: ${meta.label}`}>
              {meta.label}
            </div>
          );
        }),
      ])}
    </div>
  );
}

// ----- PSI bars with calibrated thresholds -------------------------------------------------------
export function PsiBars({ rows }) {
  const [ref, width] = useWidth();
  const [tip, setTip] = useState(null);
  const ordered = [...rows].sort((a, b) => b.psi - a.psi);
  const rowHeight = 34;
  const margin = { top: 6, right: 70, bottom: 30, left: 118 };
  const height = margin.top + margin.bottom + rowHeight * ordered.length;
  const max = Math.max(...ordered.map((r) => Math.max(r.psi, r.alert_threshold || 0)), 0.1);
  const xDomain = niceDomain(0, max * 1.1);
  const x = linear(xDomain, [margin.left, Math.max(margin.left + 1, width - margin.right)]);
  return (
    <div className="chart" ref={ref} onMouseLeave={() => setTip(null)}>
      {width > 0 && (
        <svg width={width} height={height}>
          {ticks(xDomain, 5).map((value) => (
            <g key={value} className="axis">
              <line className="grid" x1={x(value)} x2={x(value)} y1={margin.top} y2={height - margin.bottom} />
              <text x={x(value)} y={height - margin.bottom + 16} textAnchor="middle">{tickLabel(value)}</text>
            </g>
          ))}
          {ordered.map((row, index) => {
            const top = margin.top + index * rowHeight + 7;
            const meta = statusMeta(row.status);
            return (
              <g key={row.feature}
                onMouseMove={(event) => setTip({ ...tipPosition(event, ref.current), title: row.feature, rows: [
                  { label: 'PSI', value: row.psi.toFixed(3) }, { label: 'Warn above', value: (row.warn_threshold ?? 0).toFixed(3) },
                  { label: 'Alert above', value: (row.alert_threshold ?? 0).toFixed(3) },
                  { label: 'Chance by luck', value: `${((row.null_exceedance ?? 0) * 100).toFixed(1)}%` },
                  ...(row.ks_pvalue != null ? [{ label: 'KS p-value', value: row.ks_pvalue.toExponential(1) }] : [])] })}>
                <text className="axis bar-label" x={margin.left - 10} y={top + 10} dy="0.32em" textAnchor="end">{row.feature.replace(/_/g, ' ')}</text>
                <rect x={margin.left} y={top} width={Math.max(0, x.range[1] - margin.left)} height={20} className="track" rx={4} />
                <path d={roundedRight(margin.left, top, Math.max(0, x(row.psi) - margin.left), 20)} className={`mark fill-${meta.tone}`} />
                <line x1={x(row.alert_threshold || 0)} x2={x(row.alert_threshold || 0)} y1={top - 4} y2={top + 24} className="threshold-tick" />
                <text className={`status-text tone-text-${meta.tone}`} x={Math.max(x(row.psi), x(row.alert_threshold || 0)) + 8} y={top + 10} dy="0.32em">{meta.label}</text>
              </g>
            );
          })}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}

// ----- box plot ---------------------------------------------------------------------------------
export function BoxPlot({ boxes, colorOf, labelOf = (b) => b.label, height = 280, yLabel = 'Minutes' }) {
  const [ref, width] = useWidth();
  const [tip, setTip] = useState(null);
  const margin = { top: 12, right: 12, bottom: 46, left: 52 };
  const max = Math.max(...boxes.map((b) => Math.max(b.high, ...(b.outliers || []))), 1);
  const yDomain = niceDomain(0, max * 1.05);
  const y = linear(yDomain, [height - margin.bottom, margin.top]);
  const xb = band(boxes.map((b) => b.segment), [margin.left, Math.max(margin.left + 1, width - margin.right)], 0.55);
  return (
    <div className="chart" ref={ref} onMouseLeave={() => setTip(null)}>
      {width > 0 && (
        <svg width={width} height={height}>
          <YAxis scale={y} tickValues={ticks(yDomain)} width={width - margin.right} left={margin.left} label={yLabel} />
          {boxes.map((b) => {
            const left = xb(b.segment);
            const mid = left + xb.bandwidth / 2;
            const color = colorOf(b.segment);
            return (
              <g key={b.segment} onMouseMove={(event) => setTip({ ...tipPosition(event, ref.current), title: labelOf(b), rows: [
                { label: 'Trips', value: b.n }, { label: 'Median', value: `${b.median.toFixed(1)} min`, color },
                { label: 'Middle 50%', value: `${b.q1.toFixed(1)}–${b.q3.toFixed(1)} min` },
                { label: 'Slowest', value: `${Math.max(b.high, ...(b.outliers || [])).toFixed(1)} min` }] })}>
                <line x1={mid} x2={mid} y1={y(b.low)} y2={y(b.high)} className="whisker" />
                <line x1={mid - 8} x2={mid + 8} y1={y(b.low)} y2={y(b.low)} className="whisker" />
                <line x1={mid - 8} x2={mid + 8} y1={y(b.high)} y2={y(b.high)} className="whisker" />
                <rect x={left} y={y(b.q3)} width={xb.bandwidth} height={Math.max(1, y(b.q1) - y(b.q3))} rx={5} style={{ fill: color }} className="box" />
                <line x1={left} x2={left + xb.bandwidth} y1={y(b.median)} y2={y(b.median)} className="median" />
                {(b.outliers || []).map((value, i) => <circle key={i} cx={mid} cy={y(value)} r={3} className="outlier" style={{ stroke: color }} />)}
                <text className="axis tick-x" x={mid} y={height - margin.bottom + 18} textAnchor="middle">{labelOf(b)}</text>
              </g>
            );
          })}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}

// ----- horizontal bars (e.g. detection delay) ----------------------------------------------------
export function HBars({ rows, format = (v) => v, color = 'var(--s1)', unit = '' }) {
  const max = Math.max(...rows.map((r) => r.value || 0), 1);
  return (
    <div className="hbars">
      {rows.map((row) => (
        <div className="hbar" key={row.label}>
          <span className="hbar-label">{row.label}</span>
          <span className="hbar-track">
            <span className="hbar-fill" style={{ width: `${row.value == null ? 0 : Math.max(2, (row.value / max) * 100)}%`, background: row.color || color }} />
          </span>
          <span className="hbar-value">{row.value == null ? (row.empty || '—') : `${format(row.value)}${unit}`}</span>
        </div>
      ))}
    </div>
  );
}
