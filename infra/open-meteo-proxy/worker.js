/**
 * Open-Meteo forecast proxy — a Cloudflare Worker (free plan).
 *
 * Why: Open-Meteo's free tier limits calls per IP address, and hosting platforms such as Render
 * share their outbound IPs between many apps, so that shared daily quota runs out ("Daily API
 * request limit exceeded"). Open-Meteo counts requests coming from Cloudflare Workers per
 * Cloudflare account instead, so routing the API's weather calls through this Worker gives the
 * app its own quota.
 *
 * The API uses it via two environment variables:
 *   OPEN_METEO_URL       = https://<worker-name>.<account>.workers.dev/v1/forecast
 *   OPEN_METEO_PROXY_KEY = the same value as this Worker's PROXY_KEY secret
 *
 * Only GET /v1/forecast is forwarded. When the PROXY_KEY secret is set, requests must carry it
 * in the X-Proxy-Key header, so the Worker cannot be used as an open proxy by others.
 */

const UPSTREAM = 'https://api.open-meteo.com/v1/forecast'

export default {
  async fetch(request, env) {
    const url = new URL(request.url)
    if (url.pathname !== '/v1/forecast') {
      return json({ error: true, reason: 'Not found' }, 404)
    }
    if (request.method !== 'GET') {
      return json({ error: true, reason: 'Method not allowed' }, 405)
    }
    if (env.PROXY_KEY && request.headers.get('X-Proxy-Key') !== env.PROXY_KEY) {
      return json({ error: true, reason: 'Forbidden' }, 403)
    }

    const upstream = await fetch(UPSTREAM + url.search, {
      headers: { 'User-Agent': 'weather-aware-truck-routing-proxy/1.0' },
    })
    // Pass status and body through unchanged, so the API's error handling still sees
    // Open-Meteo's own 4xx/429 reasons.
    const headers = { 'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json' }
    const retryAfter = upstream.headers.get('Retry-After')
    if (retryAfter) headers['Retry-After'] = retryAfter
    return new Response(upstream.body, { status: upstream.status, headers })
  },
}

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
