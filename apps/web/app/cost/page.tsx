import { Stat, Tabs } from '@/app/ui'
import { api } from '@/lib/api'
import { cost, day, money } from '@/lib/format'
import type { CostSummary } from '@/lib/types'

const PERIODS = [7, 30, 90]

function daysBefore(isoDate: string, days: number): string {
    const d = new Date(isoDate + 'T00:00:00Z')
    d.setUTCDate(d.getUTCDate() - days)
    return d.toISOString().slice(0, 10)
}

export default async function SpendPage({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
    const { days = '30' } = await searchParams
    const today = new Date().toISOString().slice(0, 10)
    const spend = await api<CostSummary>(`/metrics/cost?start_date=${daysBefore(today, Number(days))}&end_date=${today}`)
    const invoices = Object.values(spend.invoices_by_status).reduce((a, b) => a + (b ?? 0), 0)
    const total = Number(spend.total_cost_usd)

    return (
        <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-1">Model spend</h1>
            <p className="text-gray-500 mb-6">
                {day(spend.start_date)} to {day(spend.end_date)}, UTC. Each call is recorded at what it cost when it was made,
                including reads of PDFs that were then refused.
            </p>
            <Tabs current={days} tabs={PERIODS.map((d) => ({ value: String(d), label: `${d} days`, href: `/cost?days=${d}` }))} />

            <dl className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-8">
                <Stat title="Spent" value={cost(spend.total_cost_usd)} />
                <Stat title="Per invoice" value={cost(spend.cost_per_invoice)} note={`${money(Number(spend.cost_per_invoice) * 1000)} per thousand`} />
                <Stat title="Invoices received" value={invoices} />
                <Stat title="Spent today" value={cost(spend.spent_today)} note={`of a ${money(spend.daily_cap_usd)} daily cap`} />
            </dl>

            <div className="card p-0 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            {['Model', 'Calls', 'Tokens in', 'Tokens out', 'Cost', 'Share'].map((h, i) => (
                                <th key={h} className={`px-6 py-3 text-xs font-medium text-gray-500 uppercase ${i ? 'text-right' : 'text-left'}`}>{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 text-sm">
                        {spend.by_model.map((m) => (
                            <tr key={m.model_id ?? 'unknown'}>
                                <td className="px-6 py-3 font-medium text-gray-900">{m.model_id ?? 'unknown'}</td>
                                <td className="px-6 py-3 text-right">{m.calls.toLocaleString()}</td>
                                <td className="px-6 py-3 text-right">{m.input_tokens.toLocaleString()}</td>
                                <td className="px-6 py-3 text-right">{m.output_tokens.toLocaleString()}</td>
                                <td className="px-6 py-3 text-right font-medium">{cost(m.cost_usd)}</td>
                                <td className="px-6 py-3 text-right">{total ? Math.round((Number(m.cost_usd) / total) * 100) : 0}%</td>
                            </tr>
                        ))}
                        {spend.by_model.length === 0 && (
                            <tr><td colSpan={6} className="px-6 py-8 text-center text-gray-500">No model calls in this period.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
