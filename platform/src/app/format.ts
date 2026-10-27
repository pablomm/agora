/** Lower case without accents, to match "poblacion" with "Población". */
export const fold = (text: string) =>
  text
    .normalize('NFKD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()

/** Numbers as Spanish readers write them (1.234.567; 12,5 %). */
const integer = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 })
const decimal = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const decimal2 = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const compact = new Intl.NumberFormat('es-ES', { notation: 'compact', maximumFractionDigits: 1 })

/** Units of counts (whole numbers); the rest are rates and ratios. */
const COUNT_UNITS = new Set(['personas', 'contratos', 'viviendas', 'hogares', 'núcleos', 'parejas', 'plazas', 'empresas'])
/** Amounts shown whole, with their unit. */
const WHOLE_UNITS = new Set(['€', 'kWh'])
/** Ratios that vary little between places, shown with two decimals. */
const FINE_UNITS = new Set(['hijos por núcleo'])

/** A variable's value with its unit's precision: counts as integers, fine ratios with two decimals, the rest with one. */
export function formatValue(value: number, unit: string): string {
  if (unit === '%') return `${decimal.format(value)} %`
  if (WHOLE_UNITS.has(unit)) return `${integer.format(value)} ${unit}`
  if (COUNT_UNITS.has(unit)) return integer.format(value)
  if (FINE_UNITS.has(unit)) return decimal2.format(value)
  return decimal.format(value)
}

/** Short form for axes and legends (1,2 mil; 3,5 M). */
export function formatCompact(value: number, unit: string): string {
  if (unit === '%') return `${decimal.format(value)} %`
  if (WHOLE_UNITS.has(unit)) return `${integer.format(value)} ${unit}`
  if (COUNT_UNITS.has(unit)) return Math.abs(value) < 1000 ? integer.format(Math.round(value)) : compact.format(value)
  if (FINE_UNITS.has(unit)) return decimal2.format(value)
  return decimal.format(value)
}

/** Whether values in this unit are counts (shown as "nº" in the layers list). */
export const isCount = (unit: string) => COUNT_UNITS.has(unit)

const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

/** Periods are years (2025) or months as YYYYMM (202509). */
export const isMonth = (period: number) => period > 9999

/** A period for people: "2025", "sep 2025". */
export function formatPeriod(period: number): string {
  return isMonth(period) ? `${MONTHS[(period % 100) - 1]} ${Math.floor(period / 100)}` : String(period)
}

/** A period as a point in time (years, with months as fractions), for chart axes. */
export function periodTime(period: number): number {
  return isMonth(period) ? Math.floor(period / 100) + ((period % 100) - 1) / 12 : period
}

export const formatInteger = (value: number) => integer.format(value)

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB']

/** A file's size, like ls -h: 900 KB, 64 MB, 2,6 GB. */
export function formatBytes(bytes: number): string {
  let value = bytes
  let index = 0
  while (value >= 1024 && index < BYTE_UNITS.length - 1) {
    value /= 1024
    index++
  }
  return `${new Intl.NumberFormat('es-ES', { maximumFractionDigits: value < 10 && index > 0 ? 1 : 0 }).format(value)} ${BYTE_UNITS[index]}`
}
