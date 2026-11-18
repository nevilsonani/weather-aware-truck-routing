import type { Heatmap, HeatmapMetric } from '../../api/types'

const LAYER_KEY: Record<HeatmapMetric, keyof Heatmap['layers']> = {
  risk: 'risk',
  wind: 'wind_mph',
  rain: 'rain_in_hr',
  snow: 'snow_in_hr',
}

/**
 * Paints corridor forecast frames into a small RGBA bitmap that MapLibre stretches over the
 * grid's bounds (rows are Mercator-even, so the stretch is exact).
 *
 * Per frame the cost is O(output pixels): values are linearly interpolated between the two
 * neighbouring forecast hours (smooth scrubbing/animation), then bilinearly upsampled in
 * *value* space (not colour space) using precomputed sample tables. Coverage of valid
 * neighbours becomes alpha, giving the corridor soft edges.
 */
export class HeatmapRenderer {
  readonly width: number
  readonly height: number
  private readonly nx: number
  private readonly ny: number
  private readonly frames = new Map<HeatmapMetric, Float32Array[]>()
  private readonly scratch: Float32Array
  private readonly sampleIndex: Int32Array // 4 source cells per output pixel
  private readonly sampleWeight: Float32Array
  private readonly heatmap: Heatmap

  constructor(heatmap: Heatmap, maxSide = 640) {
    this.heatmap = heatmap
    const { nx, ny } = heatmap.grid
    this.nx = nx
    this.ny = ny
    const upscale = Math.max(1, Math.min(8, Math.floor(maxSide / Math.max(nx, ny))))
    this.width = nx * upscale
    this.height = ny * upscale
    this.scratch = new Float32Array(nx * ny)
    this.sampleIndex = new Int32Array(this.width * this.height * 4)
    this.sampleWeight = new Float32Array(this.width * this.height * 4)
    this.buildSampleTables(upscale)
  }

  get frameCount(): number {
    return this.heatmap.frame_count
  }

  /** Fractional frame index for an instant (clamped to the available frames). */
  frameAt(ms: number): number {
    const f = (ms - Date.parse(this.heatmap.start_utc)) / (this.heatmap.step_s * 1000)
    return Math.min(Math.max(f, 0), this.frameCount - 1)
  }

  /** Interpolated value at a cell for a fractional frame (NaN = no data). */
  valueAt(metric: HeatmapMetric, cell: number, frame: number): number {
    const frames = this.denseFrames(metric)
    const i0 = Math.floor(frame)
    const i1 = Math.min(i0 + 1, frames.length - 1)
    return lerpMissing(frames[i0][cell], frames[i1][cell], frame - i0)
  }

  render(target: ImageData, metric: HeatmapMetric, frame: number, lut: Uint8ClampedArray, max: number): void {
    const frames = this.denseFrames(metric)
    const i0 = Math.floor(frame)
    const i1 = Math.min(i0 + 1, frames.length - 1)
    const t = frame - i0
    const a = frames[i0]
    const b = frames[i1]
    const values = this.scratch
    for (let c = 0; c < values.length; c++) values[c] = lerpMissing(a[c], b[c], t)

    const lutMax = lut.length / 4 - 1
    const out = target.data
    const idx = this.sampleIndex
    const wts = this.sampleWeight
    for (let p = 0, s = 0; p < out.length; p += 4, s += 4) {
      let sum = 0
      let weight = 0
      for (let k = 0; k < 4; k++) {
        const v = values[idx[s + k]]
        if (v === v) {
          // not NaN
          const w = wts[s + k]
          sum += v * w
          weight += w
        }
      }
      if (weight < 0.02) {
        out[p + 3] = 0
        continue
      }
      const value = sum / weight
      const l = Math.round((Math.min(Math.max(value, 0), max) / max) * lutMax) * 4
      out[p] = lut[l]
      out[p + 1] = lut[l + 1]
      out[p + 2] = lut[l + 2]
      // Smoothstep the coverage so the corridor edge fades rather than ending in a hard step.
      const coverage = weight * weight * (3 - 2 * weight)
      out[p + 3] = lut[l + 3] * coverage
    }
  }

  private denseFrames(metric: HeatmapMetric): Float32Array[] {
    let frames = this.frames.get(metric)
    if (!frames) {
      const { cells } = this.heatmap.grid
      const isRisk = metric === 'risk'
      frames = this.heatmap.layers[LAYER_KEY[metric]].map((row) => {
        const dense = new Float32Array(this.nx * this.ny).fill(Number.NaN)
        row.forEach((value, i) => {
          if (value !== null && !(isRisk && value < 0)) dense[cells[i]] = value
        })
        return dense
      })
      this.frames.set(metric, frames)
    }
    return frames
  }

  private buildSampleTables(upscale: number): void {
    const { nx, ny, width, height } = this
    for (let py = 0; py < height; py++) {
      const gy = (py + 0.5) / upscale - 0.5
      const y0 = Math.floor(gy)
      const fy = gy - y0
      for (let px = 0; px < width; px++) {
        const gx = (px + 0.5) / upscale - 0.5
        const x0 = Math.floor(gx)
        const fx = gx - x0
        const base = (py * width + px) * 4
        const corners: Array<[number, number, number]> = [
          [x0, y0, (1 - fx) * (1 - fy)],
          [x0 + 1, y0, fx * (1 - fy)],
          [x0, y0 + 1, (1 - fx) * fy],
          [x0 + 1, y0 + 1, fx * fy],
        ]
        corners.forEach(([x, y, w], k) => {
          const inside = x >= 0 && y >= 0 && x < nx && y < ny
          // Outside the grid: point at cell 0 with zero weight (never contributes).
          this.sampleIndex[base + k] = inside ? y * nx + x : 0
          this.sampleWeight[base + k] = inside ? w : 0
        })
      }
    }
  }
}

/** Linear interpolation that falls back to whichever end has data (NaN only if both are missing). */
function lerpMissing(a: number, b: number, t: number): number {
  if (a !== a) return b
  if (b !== b) return a
  return a + t * (b - a)
}
