import Link from 'next/link'

import { Stat } from '@/app/ui'
import { api } from '@/lib/api'
import { cost, label, money, overdue } from '@/lib/format'
import type { CostSummary, ExceptionPage } from '@/lib/types'

export default async function OverviewPage() {
    const [spend, open] = await Promise.all([
        api<CostSummary>('/metrics/cost'),
        api<ExceptionPage>('/exceptions?status=open&page_size=5'),
    ])
    const counts = spend.invoices_by_status
    const invoices = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0)
    const approved = counts.approved ?? 0
    const capUsed = Math.min(100, (Number(spend.spent_today) / Number(spend.daily_cap_usd)) * 100)

    if (invoices === 0 && open.total === 0) {
        return (
            <div className="card max-w-2xl">
                <h1 className="text-xl font-semibold text-gray-900 mb-2">No invoices yet</h1>
                <p className="text-sm text-gray-700">
                    Upload a PDF on the <Link href="/invoices" className="text-primary-600">Invoices</Link> page, or load the
                    samples with <code>make seed</code> and <code>make demo</code>.
                </p>
            </div>
        )
    }

    return (
        <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-6">Overview</h1>
            <dl className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-8">
                <Stat title="Invoices, last 30 days" value={invoices} note={`${counts.pending ?? 0} not yet processed`} />
                <Stat
                    title="Approved for payment"
                    value={approved}
                    tone="text-green-600"
                    note={invoices ? `${Math.round((approved / invoices) * 100)}% of invoices` : undefined}
                />
                <Stat title="Waiting for a person" value={open.total} tone="text-orange-600" note={<Link href="/exceptions" className="text-primary-600">Open the queue</Link>} />
                <Stat title="Model spend" value={cost(spend.total_cost_usd)} note={`${cost(spend.cost_per_invoice)} per invoice`} />
            </dl>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="card lg:col-span-2">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">Latest held</h2>
                    {open.items.length === 0 && <p className="text-sm text-gray-500">Nothing is waiting for a person.</p>}
                    <ul className="divide-y divide-gray-100">
                        {open.items.map((exc) => (
                            <li key={exc.id} className="py-3">
                                <Link href={`/exceptions/${exc.id}`} className="font-medium text-gray-900 hover:text-primary-600">
                                    {exc.title}
                                </Link>
                                <p className="text-sm text-gray-500">
                                    {exc.invoice?.invoice_number} · {exc.invoice?.vendor_name} · {money(exc.invoice?.total_amount)} · {label(exc.category)}
                                    {overdue(exc.sla_deadline) && <span className="ml-2 text-red-600 font-medium">overdue</span>}
                                </p>
                            </li>
                        ))}
                    </ul>
                </div>
                <div className="card">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">Model spend today</h2>
                    <p className="text-3xl font-semibold text-gray-900">{cost(spend.spent_today)}</p>
                    <div className="w-full bg-gray-200 rounded-full h-2 my-3">
                        <div className="bg-primary-600 h-2 rounded-full" style={{ width: `${capUsed}%` }} />
                    </div>
                    <p className="text-sm text-gray-500">
                        of a {money(spend.daily_cap_usd)} daily cap. Past it, invoices go to a person without a model&apos;s review.
                    </p>
                </div>
            </div>
        </div>
    )
}
