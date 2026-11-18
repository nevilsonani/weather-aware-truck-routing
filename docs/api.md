# API reference

Base path: `/api/v1`. JSON in and out, gzip-compressed responses. Units are part of every key
(`_mi`, `_s`, `_lbs`, `_mph`, `_in_hr`, `_utc`). Times are ISO-8601 UTC (`Z`), and every
location-bound time comes with an IANA `timezone` for local display.

Live OpenAPI: `/api/schema` (Swagger UI at `/api/docs`).

---

## `POST /trips/plan`

```json
{
  "origin":      { "lat": 39.7392, "lon": -104.9903, "label": "Denver, Colorado" },
  "destination": { "lat": 41.8781, "lon": -87.6298,  "label": "Chicago, Illinois" },
  "departure": "2026-11-20T08:00",
  "load_weight_lbs": 42000,
  "sample_interval_mi": 25,
  "apply_hos": true
}
```

| Field | Rules |
|---|---|
| `departure` | Optional. **Naive** = wall-clock time at the origin; with an offset/`Z` = that instant; omitted = now. Must be within now−1 h … now+7 days. |
| `load_weight_lbs` | 0 … 100,000. Gross weight sent to the truck router = load + tare (35,000 lb default). |
| `sample_interval_mi` | 10, 25 or 50. |
| `apply_hos` | Insert FMCSA breaks/rests into ETAs (default `true`). |

Response (abridged):

```json
{
  "trip": {
    "origin": { "lat": 39.7392, "lon": -104.9903, "label": "Denver, Colorado", "timezone": "America/Denver" },
    "destination": { "...": "...", "timezone": "America/Chicago" },
    "departure_utc": "2026-11-20T15:00:00Z",
    "load_weight_lbs": 42000, "gross_weight_lbs": 77000,
    "sample_interval_mi": 25, "apply_hos": true, "provider": "valhalla"
  },
  "recommendation": {
    "route_id": "B",
    "status": "caution",
    "headline": "Route B has the lowest weather exposure, but expect 25.0 mi High.",
    "ranking": ["B", "A", "C"],
    "reasons": [
      "Fewer Severe miles than Route A (0.0 mi vs 50.0 mi)",
      "Fewer High miles than Route C (25.0 mi vs 75.0 mi)"
    ],
    "criteria": ["weather_coverage", "no_travel_miles", "severe_miles", "high_miles", "average_risk", "travel_time"]
  },
  "routes": [
    {
      "id": "A", "label": "Route A", "name": "via I-76 · I-80",
      "rank": 2, "recommended": false,
      "not_recommended_because": { "criterion": "severe_miles", "text": "Fewer Severe miles than Route A (0.0 mi vs 50.0 mi)" },
      "distance_mi": 1014.96,
      "driving_time_s": 56712, "stop_time_s": 37800, "total_time_s": 94512,
      "departure_utc": "2026-11-20T15:00:00Z",
      "arrival_utc": "2026-11-21T17:15:12Z", "arrival_timezone": "America/Chicago",
      "geometry": "<encoded polyline, precision 6>",
      "summary": {
        "miles_by_level": { "low": 900.0, "moderate": 64.96, "high": 0, "severe": 50.0, "no_travel": 0, "unknown": 0 },
        "average_risk": 0.21, "max_level": "severe", "checkpoint_count": 42
      },
      "checkpoints": [
        {
          "index": 12, "distance_mi": 300.0, "lat": 40.81, "lon": -100.12, "road": "I-80",
          "eta_utc": "2026-11-20T19:41:00Z", "elapsed_s": 16860, "timezone": "America/Chicago",
          "coverage_mi": [287.5, 312.5],
          "weather": { "wind_mph": 38.2, "gust_mph": 51.0, "rain_in_hr": 0.0, "snow_in_hr": 0.12 },
          "risk": { "level": "severe", "score": 3, "wind": "severe", "rain": "low", "snow": "low",
                    "load_escalated": true, "drivers": ["wind"] },
          "reasons": ["Wind 38 mph → High; load 42,000 lb > 40,000 lb raises it to Severe"]
        }
      ],
      "rest_stops": [
        { "kind": "break", "start_utc": "2026-11-20T23:00:00Z", "end_utc": "2026-11-20T23:30:00Z",
          "distance_mi": 512.3, "lat": 40.7, "lon": -98.4 },
        { "kind": "rest", "start_utc": "2026-11-21T02:30:00Z", "end_utc": "2026-11-21T12:30:00Z",
          "distance_mi": 704.9, "lat": 41.2, "lon": -95.9 }
      ],
      "timeline": [[0, 0.0], [282, 5.0], ["…elapsed seconds", "miles driven…"]],
      "notices": []
    }
  ],
  "corridor": { "west": -105.87, "east": -86.75, "south": 38.51, "north": 42.66,
                "nx": 35, "ny": 10, "cells": [3, 4, 5, "…"], "buffer_mi": 43.3 },
  "warnings": [],
  "generated_at": "2026-11-20T14:58:31Z"
}
```

Notes:

- `checkpoints[].coverage_mi` is the stretch of road the checkpoint represents (midpoint rule).
  The per-level miles in `summary` are sums of these, so they always add up to `distance_mi`.
- `weather`/`risk` are `null` when no forecast exists for that place and time. Such checkpoints
  count as `unknown` miles and are excluded from the average.
- `timeline` maps wall-clock seconds since departure to miles driven, including stationary
  stops. The UI uses it to place each truck on the map for any slider hour.

## `POST /trips/heatmap`

Send back the plan's `corridor`, `departure_utc` and load:

```json
{ "grid": { "west": -105.87, "east": -86.75, "south": 38.51, "north": 42.66, "nx": 35, "ny": 10, "cells": [3, 4, 5] },
  "departure": "2026-11-20T15:00:00Z",
  "load_weight_lbs": 42000 }
```

```json
{
  "start_utc": "2026-11-20T15:00:00Z", "departure_utc": "2026-11-20T15:00:00Z",
  "step_s": 3600, "frame_count": 49, "hours": 48,
  "grid": { "...": "same as request" },
  "layers": {
    "risk":       [[0, 1, 3], "… one row per frame, one value per cell (-1 = no data)"],
    "wind_mph":   [[12.4, 27.1, 46.0], "…"],
    "rain_in_hr": [[0.0, 0.02, 0.11], "…"],
    "snow_in_hr": [[0.0, 0.0, 0.0], "…"]
  },
  "warnings": []
}
```

The grid's rows are evenly spaced in Web-Mercator Y between `north` (row 0) and `south`, and
its columns evenly in longitude. A `nx × ny` image stretched over the bounds is therefore
geographically exact.

## `GET /places/search?q=denver&limit=6&lat=39.5&lon=-98.35`

`lat`/`lon` optionally bias results. Each result carries its IANA time zone, which the UI uses
to explain departure times.

```json
{ "results": [ { "id": "R1411339", "name": "Denver", "label": "Denver, Colorado, United States",
                 "lat": 39.739236, "lon": -104.984862, "kind": "city", "country_code": "US",
                 "timezone": "America/Denver" } ] }
```

## `GET /meta`

Risk levels, threshold tables (with inclusive/exclusive flags), load rules, ranking criteria,
allowed intervals, HOS limits and heat-map hours. The UI builds legends and hints from this,
so the rules live in one place.

## Errors

```json
{ "error": { "code": "invalid_trip", "message": "Origin and destination must be at least 1 mile apart.", "details": {} } }
```

| Status | `code` | Meaning |
|---|---|---|
| 400 | `validation_error` | Malformed fields; `details` maps field → messages |
| 422 | `invalid_trip`, `no_route` | Valid input describing an impossible trip |
| 429 | `throttled` | Per-client rate limit |
| 503 | `upstream_unavailable` | Routing or weather provider down, rate limited or timing out |
