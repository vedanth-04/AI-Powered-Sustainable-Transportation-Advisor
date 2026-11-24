async function call(path, options) {
  const response = await fetch(path, options);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error = new Error(body?.error?.message || `Request failed (${response.status})`);
    error.hint = body?.error?.hint || body?.fix || null;
    error.code = body?.error?.code || 'http_error';
    throw error;
  }
  return body;
}

export const getHealth = () => call('/api/health');
export const getNetwork = () => call('/api/network');
export const searchPlaces = (q, signal, online = true) => call(`/api/places?q=${encodeURIComponent(q)}${online ? '' : '&online=0'}`, { signal });
export const planJourney = (payload) =>
  call('/api/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
export const reverseGeocode = (lat, lon, online = true) => call(`/api/reverse?lat=${lat}&lon=${lon}${online ? '' : '&online=0'}`);
export const getModel = (date) => call(`/api/model?date=${encodeURIComponent(date)}`);
