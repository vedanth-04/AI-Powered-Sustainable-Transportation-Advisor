// Thin fetch helpers for the Python backend (dashboard/server.py).
async function handle(response) {
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && body.error) message = body.error;
    } catch {
      /* not JSON */
    }
    throw new Error(message);
  }
  return response;
}

export const getJSON = async (url) => (await handle(await fetch(url))).json();
export const getText = async (url) => (await handle(await fetch(url))).text();
export const postJSON = async (url, body) =>
  (await handle(await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }))).json();
