import { RISK_LEVELS, UNKNOWN_STYLE } from '../../lib/risk'

export function MapLegend() {
  return (
    <section
      aria-label="Map legend"
      className="pointer-events-auto rounded-lg border border-slate-200/80 bg-white/95 px-3 py-2 text-[11px] text-slate-600 shadow-sm backdrop-blur"
    >
      <h2 className="mb-1 font-semibold uppercase tracking-wide text-slate-500">Checkpoint risk</h2>
      <ul className="grid grid-cols-2 gap-x-3 gap-y-0.5">
        {[...RISK_LEVELS, { key: 'unknown', ...UNKNOWN_STYLE }].map((level) => (
          <li key={level.key} className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full ring-1 ring-white" style={{ background: level.color }} />
            {level.label}
          </li>
        ))}
      </ul>
      <ul className="mt-1.5 flex gap-3 border-t border-slate-100 pt-1.5">
        <li className="flex items-center gap-1">
          <span className="flex size-3.5 items-center justify-center rounded-full bg-blue-600 text-[8px] font-bold text-white">
            A
          </span>
          Truck
        </li>
        <li className="flex items-center gap-1">
          <span className="flex size-3.5 items-center justify-center rounded-sm border-2 border-slate-900 text-[7px] font-bold">
            R
          </span>
          Rest / break
        </li>
      </ul>
    </section>
  )
}
