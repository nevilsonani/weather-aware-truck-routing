import { describe, expect, it } from 'vitest'
import type { Heatmap, Meta } from '../../api/types'
import { buildLut, buildScale } from './colorScales'
import { HeatmapRenderer } from './renderer'

function heatmap(): Heatmap {
  // 2x2 grid, only the top row is in the corridor; two hourly frames.
  return {
    start_utc: '2026-11-18T12:00:00Z',
    departure_utc: '2026-11-18T12:00:00Z',
    step_s: 3600,
    frame_count: 2,
    hours: 1,
    grid: { west: 0, east: 2, south: 0, north: 2, nx: 2, ny: 2, cells: [0, 1] },
    layers: {
      risk: [
        [0, -1],
        [4, 2],
      ],
      wind_mph: [
        [10, 20],
        [30, null],
      ],
      rain_in_hr: [
        [0, 0],
        [0, 0],
      ],
      snow_in_hr: [
        [0, 0],
        [0, 0],
      ],
    },
    warnings: [],
  }
}

class FakeImageData {
  readonly data: Uint8ClampedArray
  readonly width: number
  readonly height: number
  constructor(width: number, height: number) {
    this.width = width
    this.height = height
    this.data = new Uint8ClampedArray(width * height * 4)
  }
}

describe('HeatmapRenderer', () => {
  it('interpolates between hourly frames and bridges a missing hour', () => {
    const r = new HeatmapRenderer(heatmap())
    expect(r.valueAt('wind', 0, 0.5)).toBeCloseTo(20)
    expect(r.valueAt('wind', 1, 0.5)).toBe(20) // next hour missing: hold the known value
    expect(r.valueAt('risk', 1, 0)).toBe(2) // -1 (no data) is treated as missing too
    expect(r.valueAt('risk', 0, 0.25)).toBeCloseTo(1)
    expect(Number.isNaN(r.valueAt('wind', 2, 0.5))).toBe(true) // outside the corridor
  })

  it('maps instants to fractional frames and clamps', () => {
    const r = new HeatmapRenderer(heatmap())
    const start = Date.parse('2026-11-18T12:00:00Z')
    expect(r.frameAt(start + 30 * 60_000)).toBeCloseTo(0.5)
    expect(r.frameAt(start - 10 * 3_600_000)).toBe(0)
    expect(r.frameAt(start + 10 * 3_600_000)).toBe(1)
  })

  it('fills corridor cells, fades their edges and leaves other cells transparent', () => {
    const r = new HeatmapRenderer(heatmap(), 4) // 2x2 grid upsampled to 4x4 pixels
    const image = new FakeImageData(r.width, r.height) as unknown as ImageData
    const lut = new Uint8ClampedArray(4 * 8).fill(255)
    r.render(image, 'wind', 0, lut, 70)
    const alphaAt = (x: number, y: number) => image.data[(y * r.width + x) * 4 + 3]
    expect(alphaAt(1, 1)).toBeGreaterThan(200) // inside the corridor row
    expect(alphaAt(0, 0)).toBeLessThan(alphaAt(1, 1)) // grid corner fades softly
    expect(alphaAt(1, r.height - 1)).toBe(0) // bottom row is outside the corridor
  })
})

describe('colour scales', () => {
  const meta = {
    wind_basis: 'sustained',
    conditions: {
      wind: {
        unit: 'mph',
        thresholds: [
          { level: 'moderate', value: 25, inclusive: true },
          { level: 'high', value: 35, inclusive: true },
          { level: 'severe', value: 45, inclusive: true },
          { level: 'no_travel', value: 55, inclusive: true },
        ],
      },
    },
  } as unknown as Meta

  it('anchors ramp colours on the backend thresholds', () => {
    const scale = buildScale('wind', meta)
    expect(scale.ticks.map((t) => t.value)).toEqual([25, 35, 45, 55])
    expect(scale.max).toBeGreaterThan(55)
  })

  it('builds a LUT that is transparent at zero and opaque-ish at No Travel', () => {
    const scale = buildScale('wind', meta)
    const lut = buildLut(scale, 256)
    expect(lut[3]).toBe(0)
    const index = Math.round((55 / scale.max) * 255) * 4
    expect(lut[index + 3]).toBeGreaterThan(150)
  })
})
