/** Helpers for `<input type="datetime-local">` values expressed in an arbitrary IANA zone. */

const partsFormatters = new Map<string, Intl.DateTimeFormat>()

function zonedParts(ms: number, timeZone: string): Record<string, string> {
  let fmt = partsFormatters.get(timeZone)
  if (!fmt) {
    fmt = new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
    partsFormatters.set(timeZone, fmt)
  }
  return Object.fromEntries(fmt.formatToParts(new Date(ms)).map((p) => [p.type, p.value]))
}

/** Wall-clock "YYYY-MM-DDTHH:mm" of an instant in `timeZone`. */
export function toLocalInputValue(ms: number, timeZone: string): string {
  const p = zonedParts(ms, timeZone)
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

/** The next top-of-hour after `ms`, as a wall-clock value in `timeZone`. */
export function nextHourInputValue(ms: number, timeZone: string): string {
  const next = Math.ceil((ms + 60_000) / 3_600_000) * 3_600_000
  return toLocalInputValue(next, timeZone)
}

export function timeZoneAbbreviation(timeZone: string, ms = Date.now()): string {
  const part = new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'short' })
    .formatToParts(new Date(ms))
    .find((p) => p.type === 'timeZoneName')
  return part?.value ?? timeZone
}
