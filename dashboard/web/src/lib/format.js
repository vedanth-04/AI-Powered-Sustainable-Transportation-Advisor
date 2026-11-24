// Formatting helpers and shared visual vocabulary (pure functions, no React).

export const STATUS = {
  OK: { label: 'OK', tone: 'good' },
  PASS: { label: 'Pass', tone: 'good' },
  WARN: { label: 'Warn', tone: 'warn' },
  PARTIAL: { label: 'Partial', tone: 'warn' },
  ALERT: { label: 'Alert', tone: 'bad' },
  FAIL: { label: 'Fail', tone: 'bad' },
  MISSING: { label: 'Not run', tone: 'idle' },
  INSUFFICIENT_DATA: { label: 'Too few', tone: 'idle' },
};

export const statusMeta = (status) => STATUS[status] || { label: String(status ?? '—'), tone: 'idle' };

// Fixed categorical order: colour follows the entity, never its rank.
export const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)'];

export const SEGMENT_ORDER = [
  'ORR_CHIRAG_TO_NEHRU_PLACE_EB',
  'ORR_NEHRU_PLACE_TO_CHIRAG_WB',
  'MB_SAKET_TO_KHANPUR_EB',
  'MB_KHANPUR_TO_SAKET_WB',
];

export const SEGMENT_SHORT = {
  ORR_CHIRAG_TO_NEHRU_PLACE_EB: 'ORR EB · 90',
  ORR_NEHRU_PLACE_TO_CHIRAG_WB: 'ORR WB · 83',
  MB_SAKET_TO_KHANPUR_EB: 'MB EB · 398',
  MB_KHANPUR_TO_SAKET_WB: 'MB WB · 399',
};

export const segmentColor = (segment) => {
  const index = SEGMENT_ORDER.indexOf(segment);
  return SERIES[index >= 0 ? index : 4];
};

export const versionColor = (version) => SERIES[(Number(String(version).replace('v', '')) - 1) % SERIES.length];

export function num(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Number(value).toFixed(digits);
}

export function pct(value, digits = 0) {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function signed(value, digits = 2) {
  if (value === null || value === undefined) return '—';
  const text = Math.abs(value).toFixed(digits);
  return `${value > 0 ? '+' : value < 0 ? '−' : '±'}${text}`;
}

export function shortHash(hash, length = 10) {
  return hash ? `${hash.slice(0, length)}…` : '—';
}

export function humanize(text) {
  return String(text ?? '').replace(/_/g, ' ');
}

export function titleCase(text) {
  return humanize(text).replace(/\b\w/g, (c) => c.toUpperCase());
}

export function when(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export const CHECK_LABEL = {
  input_drift: 'Input drift',
  prediction_drift: 'Prediction drift',
  data_quality: 'Data quality',
  performance: 'Performance',
};
