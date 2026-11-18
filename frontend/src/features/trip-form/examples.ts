import type { Place } from '../../api/types'

const place = (name: string, region: string, lat: number, lon: number, timezone: string): Place => ({
  id: `example:${name}`,
  name,
  label: `${name}, ${region}, United States`,
  lat,
  lon,
  kind: 'city',
  country_code: 'US',
  timezone,
})

const DENVER = place('Denver', 'Colorado', 39.7392, -104.9903, 'America/Denver')

/** Demo trips (each within the public truck router's ~930-mile straight-line limit). */
export const EXAMPLE_TRIPS: ReadonlyArray<{ label: string; origin: Place; destination: Place }> = [
  {
    label: 'Denver → Chicago',
    origin: DENVER,
    destination: place('Chicago', 'Illinois', 41.8781, -87.6298, 'America/Chicago'),
  },
  {
    label: 'Seattle → Boise',
    origin: place('Seattle', 'Washington', 47.6062, -122.3321, 'America/Los_Angeles'),
    destination: place('Boise', 'Idaho', 43.615, -116.2023, 'America/Boise'),
  },
  {
    label: 'Salt Lake City → Denver',
    origin: place('Salt Lake City', 'Utah', 40.7608, -111.891, 'America/Denver'),
    destination: DENVER,
  },
  {
    label: 'Dallas → Atlanta',
    origin: place('Dallas', 'Texas', 32.7767, -96.797, 'America/Chicago'),
    destination: place('Atlanta', 'Georgia', 33.749, -84.388, 'America/New_York'),
  },
]
