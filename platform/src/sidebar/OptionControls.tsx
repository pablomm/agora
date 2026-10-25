import { copy } from '../app/copy'
import { optionValue, type Choices, type VariableOption } from '../data/api'

/** One of a few values, side by side (Total · Hombres · Mujeres; or the sources). */
export function Segmented({ label, items, value, onChange }: { label: string; items: { id: string; label: string }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div className="option-control">
      <span className="option-label">{label}</span>
      <div className="segmented" role="radiogroup" aria-label={label}>
        {items.map((item) => (
          <button key={item.id} type="button" role="radio" aria-checked={item.id === value} onClick={() => onChange(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/** "0–4" for Y0T4, "100+" for Y_GE100: the bounds of age-like codes, for a range's short name. */
function bounds(code: string, fallback: string): [string, string] {
  const band = /^Y(\d+)T(\d+)$/.exec(code)
  if (band) return [band[1], band[2]]
  const open = /^Y_GE(\d+)$/.exec(code)
  if (open) return [open[1], `${open[1]}+`]
  return [fallback, fallback]
}

/** A run of ordered values (age groups) with a two-thumb slider: from the first group to the last. */
function RangeOption({ option, value, onChange }: { option: VariableOption; value: string; onChange: (value: string) => void }) {
  const codes = option.values.map((item) => item.code)
  const [first, last = first] = value.split('..')
  const from = Math.max(0, codes.indexOf(first))
  const to = Math.max(from, codes.indexOf(last))
  const set = (start: number, end: number) => onChange(`${codes[start]}..${codes[end]}`)
  const start = bounds(codes[from], option.values[from].label)[0]
  const end = bounds(codes[to], option.values[to].label)[1]
  const span = codes.length - 1
  return (
    <div className="option-control">
      <div className="option-header">
        <span className="option-label">{option.label}</span>
        <output className="option-value">{copy.mapView.ageRange(start, end)}</output>
      </div>
      <div className="dual-range" style={{ '--from': `${(from / span) * 100}%`, '--to': `${(to / span) * 100}%` } as React.CSSProperties}>
        <input
          type="range"
          min={0}
          max={span}
          step={1}
          value={from}
          // When the thumbs meet near the end, the "from" one must be on top to be dragged back.
          style={{ zIndex: from > span / 2 ? 2 : 1 }}
          aria-label={copy.mapView.rangeFrom(option.label)}
          aria-valuetext={option.values[from].label}
          onChange={(event) => set(Math.min(Number(event.target.value), to), to)}
        />
        <input
          type="range"
          min={0}
          max={span}
          step={1}
          value={to}
          aria-label={copy.mapView.rangeTo(option.label)}
          aria-valuetext={option.values[to].label}
          onChange={(event) => set(from, Math.max(Number(event.target.value), from))}
        />
      </div>
      <div className="period-range" aria-hidden="true">
        <span>{bounds(codes[0], option.values[0].label)[0]}</span>
        <span>{bounds(codes[span], option.values[span].label)[1]}</span>
      </div>
    </div>
  )
}

/** The variable's options: a segmented control for a value, a range slider for a run of values. */
export function OptionControls({ options, choices, onChange }: { options: VariableOption[]; choices: Choices; onChange: (choices: Choices) => void }) {
  return options.map((option) => {
    const value = optionValue(option, choices)
    const change = (next: string) => onChange({ ...choices, [option.dimension]: next })
    return option.range ? (
      <RangeOption key={option.dimension} option={option} value={value} onChange={change} />
    ) : (
      <Segmented
        key={option.dimension}
        label={option.label}
        items={option.values.map((item) => ({ id: item.code, label: item.label }))}
        value={value}
        onChange={change}
      />
    )
  })
}
