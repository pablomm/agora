/** Numbers as Spanish readers write them (1.234.567; 12,5 %). */
const integer = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 })
const decimal = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const compact = new Intl.NumberFormat('es-ES', { notation: 'compact', maximumFractionDigits: 1 })

/** A variable's value with its unit's precision: counts as integers, the rest with one decimal. */
export function formatValue(value: number, unit: string): string {
  if (unit === '%') return `${decimal.format(value)} %`
  if (unit === 'personas') return integer.format(value)
  return decimal.format(value)
}

/** Short form for axes and legends (1,2 mil; 3,5 M). */
export function formatCompact(value: number, unit: string): string {
  if (unit === '%') return `${decimal.format(value)} %`
  if (unit === 'personas') return Math.abs(value) < 1000 ? integer.format(value) : compact.format(value)
  return decimal.format(value)
}

export const formatInteger = (value: number) => integer.format(value)
