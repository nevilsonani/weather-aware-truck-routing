import { useId, useState } from 'react'
import { usePlaceSearch } from '../../api/hooks'
import type { Place } from '../../api/types'
import { Spinner } from '../../components/Spinner'
import { useDebouncedValue } from '../../lib/useDebouncedValue'

interface Props {
  label: string
  placeholder: string
  value: Place | null
  onChange: (place: Place | null) => void
  marker: 'origin' | 'destination'
}

/** Combobox (WAI-ARIA 1.2 pattern): free text search, arrow keys, Enter to pick, Esc to close. */
export function PlaceInput({ label, placeholder, value, onChange, marker }: Props) {
  const id = useId()
  const listId = `${id}-list`
  const [text, setText] = useState(value?.label ?? '')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const query = useDebouncedValue(text, 250)
  const search = usePlaceSearch(open && !value ? query : '')
  const results = search.data ?? []

  // Keep the text in sync when the value is set from outside (examples, swap): adjust state
  // during render instead of in an effect, so there is no extra render with stale text.
  const [syncedValue, setSyncedValue] = useState(value)
  if (value !== syncedValue) {
    setSyncedValue(value)
    setText(value?.label ?? '')
  }

  const choose = (place: Place) => {
    setSyncedValue(place)
    onChange(place)
    setText(place.label)
    setOpen(false)
  }

  const showList = open && !value && text.trim().length >= 2
  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-600">
        {label}
      </label>
      <div className="relative">
        <span
          aria-hidden
          className={`absolute top-1/2 left-3 size-2.5 -translate-y-1/2 border-2 border-slate-900 ${
            marker === 'origin' ? 'rounded-full' : 'rotate-45'
          }`}
        />
        <input
          id={id}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && results[active] ? `${listId}-${active}` : undefined}
          autoComplete="off"
          spellCheck={false}
          value={text}
          placeholder={placeholder}
          onChange={(e) => {
            setText(e.target.value)
            setActive(0)
            setOpen(true)
            if (value) {
              setSyncedValue(null) // our own edit: do not let the sync below reset the text
              onChange(null)
            }
          }}
          onFocus={(e) => {
            setOpen(true)
            if (value) e.currentTarget.select() // typing replaces the chosen place
          }}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={(e) => {
            if (!showList) return
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((i) => Math.min(i + 1, results.length - 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((i) => Math.max(i - 1, 0))
            } else if (e.key === 'Enter' && results[active]) {
              e.preventDefault()
              choose(results[active])
            } else if (e.key === 'Escape') {
              setOpen(false)
            }
          }}
          className="w-full rounded-lg border border-slate-300 bg-white py-2 pr-9 pl-8 text-sm shadow-xs outline-none transition placeholder:text-slate-400 focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
        />
        <span className="absolute top-1/2 right-3 -translate-y-1/2 text-slate-400">
          {search.isFetching ? (
            <Spinner className="size-3.5" />
          ) : value ? (
            <span className="text-[10px] font-medium text-emerald-600" title={value.timezone}>
              ✓
            </span>
          ) : null}
        </span>
      </div>
      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label={`${label} suggestions`}
          className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg"
        >
          {search.isError && <li className="px-3 py-2 text-red-600">Search is unavailable right now.</li>}
          {!search.isError && results.length === 0 && !search.isFetching && (
            <li className="px-3 py-2 text-slate-500">No matching places.</li>
          )}
          {results.map((place, i) => (
            <li
              key={place.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(place)}
              onMouseEnter={() => setActive(i)}
              className={`cursor-pointer px-3 py-1.5 ${i === active ? 'bg-slate-100' : ''}`}
            >
              <div className="font-medium text-slate-900">{place.name}</div>
              <div className="truncate text-xs text-slate-500">{place.label}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
