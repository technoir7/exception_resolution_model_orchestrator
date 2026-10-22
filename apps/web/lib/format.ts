// How the dashboard writes amounts, times and codes.

export function money(amount: string | number | null | undefined, currency = 'USD'): string {
    if (amount === null || amount === undefined) return '—'
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(Number(amount))
}

/** A model's cost: often a fraction of a cent, which two decimals would show as $0.00. */
export function cost(usd: string | number): string {
    const value = Number(usd)
    if (value === 0 || value >= 1) return money(value)
    return '$' + value.toPrecision(3).replace(/0+$/, '')
}

/** The API stores UTC and, on some databases, returns it without a zone. */
export function instant(timestamp: string): Date {
    return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(timestamp) ? timestamp : timestamp + 'Z')
}

export function when(timestamp: string): string {
    return instant(timestamp).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

/** A calendar date, such as an invoice's, the same in every time zone. */
export function day(isoDate: string | null | undefined): string {
    if (!isoDate) return '—'
    return new Date(isoDate + 'T00:00:00Z').toLocaleDateString('en-US', { dateStyle: 'medium', timeZone: 'UTC' })
}

const ACRONYMS = new Set(['ap', 'po', 'llm', 'bpo', 'pdf', 'json'])

export function label(code: string): string {
    const words = code.split('_').map((w) => (ACRONYMS.has(w) ? w.toUpperCase() : w))
    return words.join(' ').replace(/^[a-z]/, (c) => c.toUpperCase())
}

export function overdue(deadline: string, now: Date = new Date()): boolean {
    return instant(deadline) < now
}
