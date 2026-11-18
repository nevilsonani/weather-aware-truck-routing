import { describe, expect, it } from 'vitest'
import { RouteLine, bracket, decodePolyline, haversineMi, interpolate } from './geo'

describe('decodePolyline', () => {
  it('decodes the reference polyline (precision 5) as [lon, lat]', () => {
    const coords = decodePolyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@', 5)
    expect(coords).toEqual([
      [-120.2, 38.5],
      [-120.95, 40.7],
      [-126.453, 43.252],
    ])
  })

  it('throws on truncated input', () => {
    expect(() => decodePolyline('_p~iF~ps|U_', 5)).toThrow('Truncated')
  })
})

describe('interpolate', () => {
  const xs = [0, 10, 10, 20]
  const ys = [0, 100, 100, 300]
  it('interpolates, clamps and tolerates repeated x values', () => {
    expect(interpolate(xs, ys, -5)).toBe(0)
    expect(interpolate(xs, ys, 5)).toBe(50)
    expect(interpolate(xs, ys, 15)).toBe(200)
    expect(interpolate(xs, ys, 99)).toBe(300)
  })

  it('bracket finds the containing segment', () => {
    expect(bracket([0, 1, 2, 3], 2.5)).toBe(2)
    expect(bracket([0, 1, 2, 3], 0)).toBe(0)
  })
})

describe('RouteLine', () => {
  const line = new RouteLine(
    [
      [-100, 40],
      [-99, 40],
      [-98, 40],
    ],
    200,
  )

  it('rescales geometric length to the reported mileage', () => {
    expect(line.length).toBeCloseTo(200, 6)
    expect(haversineMi([-100, 40], [-98, 40])).not.toBeCloseTo(200, 0)
  })

  it('positions points by mile marker', () => {
    expect(line.positionAt(0)).toEqual([-100, 40])
    expect(line.positionAt(100)[0]).toBeCloseTo(-99, 6)
    expect(line.positionAt(500)).toEqual([-98, 40])
  })

  it('slices sub-lines including interpolated ends', () => {
    const part = line.slice(50, 150)
    expect(part).toHaveLength(3)
    expect(part[0][0]).toBeCloseTo(-99.5, 6)
    expect(part[1]).toEqual([-99, 40])
    expect(part[2][0]).toBeCloseTo(-98.5, 6)
  })
})

describe('truncate', () => {
  it('never rounds a value up across a threshold', async () => {
    const { truncate } = await import('./format')
    expect(truncate(34.96, 0)).toBe('34')
    expect(truncate(0.2499, 2)).toBe('0.24')
    expect(truncate(0.1, 2)).toBe('0.10') // exact values survive float error
  })
})
