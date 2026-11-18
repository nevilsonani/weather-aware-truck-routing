/** Display formatting. Times are always rendered in an explicit IANA zone. */

const numberFormat = new Intl.NumberFormat('en-US')

export function formatMiles(miles: number, digits = 0): string {
  return `${miles.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })} mi`
}

export function formatLbs(lbs: number): string {
  return `${numberFormat.format(Math.round(lbs))} lb`
}

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  const minutes = totalMinutes % 60
  if (days > 0) return `${days}d ${hours}h ${String(minutes).padStart(2, '0')}m`
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, '0')}m`
  return `${minutes}m`
}

const formatters = new Map<string, Intl.DateTimeFormat>()

type Style = 'full' | 'short'

function formatter(timeZone: string, style: Style): Intl.DateTimeFormat {
  const key = `${timeZone}|${style}`
  let fmt = formatters.get(key)
  if (!fmt) {
    fmt = new Intl.DateTimeFormat('en-US', {
      timeZone,
      weekday: 'short',
      month: style === 'full' ? 'short' : undefined,
      day: style === 'full' ? 'numeric' : undefined,
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    })
    formatters.set(key, fmt)
  }
  return fmt
}

/** "Wed, Nov 18, 2:35 PM MST" in the given zone (the checkpoint's local time). */
export function formatDateTime(isoOrMs: string | number, timeZone: string): string {
  return formatter(timeZone, 'full').format(new Date(isoOrMs))
}

/** "Wed 2:35 PM MST": compact form for dense lists. */
export function formatShortDateTime(isoOrMs: string | number, timeZone: string): string {
  return formatter(timeZone, 'short').format(new Date(isoOrMs)).replace(',', '')
}

/**
 * Fixed-decimals without rounding up, so a value just under a risk threshold never *reads* as
 * the threshold (34.96 mph is shown as 34.9, not 35, next to a "Moderate" label).
 */
export function truncate(value: number, digits: number): string {
  const factor = 10 ** digits
  return (Math.floor(value * factor + 1e-9) / factor).toFixed(digits)
}

export function formatRate(inPerHour: number): string {
  return `${truncate(inPerHour, 2)} in/hr`
}
