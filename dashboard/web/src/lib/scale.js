// Minimal scale and tick helpers for the hand-built SVG charts (pure functions).

export function linear([d0, d1], [r0, r1]) {
  const span = d1 - d0 || 1;
  const fn = (value) => r0 + ((value - d0) / span) * (r1 - r0);
  fn.domain = [d0, d1];
  fn.range = [r0, r1];
  return fn;
}

export function niceStep(span, count = 5) {
  const raw = span / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw || 1));
  const fraction = raw / power;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return nice * power;
}

// Domain rounded out to clean tick values, always including zero for magnitudes.
export function niceDomain(min, max, count = 5, includeZero = true) {
  let lo = includeZero ? Math.min(0, min) : min;
  let hi = includeZero ? Math.max(0, max) : max;
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (lo === hi) hi = lo + 1;
  const step = niceStep(hi - lo, count);
  return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step];
}

export function ticks([lo, hi], count = 5) {
  const step = niceStep(hi - lo, count);
  const out = [];
  for (let value = Math.ceil(lo / step) * step; value <= hi + step * 1e-9; value += step) {
    out.push(Number(value.toFixed(10)));
  }
  return out;
}

export function tickLabel(value) {
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(value % 1000 ? 1 : 0)}K`;
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(Math.abs(value) < 1 ? 2 : 1);
}

export function band(keys, [r0, r1], padding = 0.2) {
  const step = (r1 - r0) / Math.max(1, keys.length);
  const width = step * (1 - padding);
  const position = (key) => r0 + keys.indexOf(key) * step + (step - width) / 2;
  position.bandwidth = width;
  position.step = step;
  return position;
}

export function nearestIndex(values, target) {
  let best = 0;
  for (let i = 1; i < values.length; i += 1) {
    if (Math.abs(values[i] - target) < Math.abs(values[best] - target)) best = i;
  }
  return best;
}
