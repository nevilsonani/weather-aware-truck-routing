import { type KeyboardEvent, useRef } from 'react'

interface Option<T extends string | number> {
  value: T
  label: string
}

interface Props<T extends string | number> {
  label: string
  value: T
  options: readonly Option<T>[]
  onChange: (value: T) => void
  size?: 'sm' | 'md'
  disabled?: boolean
}

/** Accessible radio group styled as a segmented control (roving tab index, arrow keys). */
export function SegmentedControl<T extends string | number>({
  label,
  value,
  options,
  onChange,
  size = 'md',
  disabled = false,
}: Props<T>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([])
  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  )

  const onKeyDown = (event: KeyboardEvent) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    if (!step) return
    event.preventDefault()
    const next = (selectedIndex + step + options.length) % options.length
    onChange(options[next].value)
    refs.current[next]?.focus()
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      onKeyDown={onKeyDown}
      className="flex rounded-lg bg-slate-100 p-0.5"
    >
      {options.map((option, i) => {
        const checked = i === selectedIndex
        return (
          <button
            key={option.value}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={`flex-1 rounded-md font-medium transition-colors disabled:opacity-50 ${
              size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-2 py-1.5 text-sm'
            } ${checked ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
