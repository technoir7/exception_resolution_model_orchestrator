import Link from 'next/link'

import { Pager, StatusBadge, Tabs } from '@/app/ui'
import { api } from '@/lib/api'
import { label, money, overdue, when } from '@/lib/format'
import type { ExceptionPage } from '@/lib/types'

const STATUSES = [
    { value: 'open', label: 'Open' },
    { value: 'escalated', label: 'Escalated' },
    { value: 'resolved', label: 'Resolved' },
    { value: '', label: 'All' },
]

// apps/api/models/exception.py: ExceptionCategory
const CATEGORIES = [
    'amount_variance', 'quantity_variance', 'duplicate', 'bank_details', 'vendor_mismatch', 'missing_po',
    'missing_receipt', 'missing_fields', 'currency_mismatch', 'llm_validation_failed', 'other',
]

type Search = { status?: string; category?: string; page?: string }

export default async function ExceptionsPage({ searchParams }: { searchParams: Promise<Search> }) {
    const { status = 'open', category = '', page = '1' } = await searchParams
    const filters = (extra: Record<string, string> = {}) =>
        new URLSearchParams({ ...(status && { status }), ...(category && { category }), ...extra })
    const queue = await api<ExceptionPage>(`/exceptions?${filters({ page })}`)

    return (
        <div>
            <div className="flex flex-wrap justify-between items-start gap-4 mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Exceptions</h1>
                    <p className="text-gray-500">{queue.open_count} waiting for a person</p>
                </div>
                <form className="flex gap-2">
                    <input type="hidden" name="status" value={status} />
                    <select name="category" defaultValue={category} className="border border-gray-300 rounded-md px-3 py-2 text-sm">
                        <option value="">Every category</option>
                        {CATEGORIES.map((c) => <option key={c} value={c}>{label(c)}</option>)}
                    </select>
                    <button type="submit" className="btn-secondary text-sm">Filter</button>
                </form>
            </div>
            <Tabs
                current={status}
                tabs={STATUSES.map((s) => ({ ...s, href: `/exceptions?${new URLSearchParams({ status: s.value, ...(category && { category }) })}` }))}
            />

            <div className="space-y-4">
                {queue.items.map((exc) => {
                    const late = (exc.status === 'open' || exc.status === 'escalated') && overdue(exc.sla_deadline)
                    return (
                        <Link key={exc.id} href={`/exceptions/${exc.id}`} className={`card block hover:border-primary-300 ${late ? 'border-red-300' : ''}`}>
                            <div className="flex flex-wrap justify-between items-start gap-4">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="font-medium text-gray-900">{exc.title}</span>
                                        <span className={`status-badge severity-${exc.severity}`}>{exc.severity}</span>
                                        {exc.status !== 'open' && <StatusBadge status={exc.status} />}
                                    </div>
                                    <p className="text-sm text-gray-500">
                                        {exc.invoice?.invoice_number} · {exc.invoice?.vendor_name} · {money(exc.invoice?.total_amount)} · {label(exc.category)} · for the {label(exc.owner_role)}
                                    </p>
                                </div>
                                <div className="text-right text-sm">
                                    <p className="text-gray-500">{exc.status === 'resolved' ? 'Resolved' : 'Due'}</p>
                                    <p className={late ? 'text-red-600 font-medium' : 'text-gray-900'}>
                                        {when(exc.status === 'resolved' && exc.resolved_at ? exc.resolved_at : exc.sla_deadline)}
                                    </p>
                                </div>
                            </div>
                        </Link>
                    )
                })}
                {queue.items.length === 0 && <p className="text-sm text-gray-500">No exceptions here.</p>}
            </div>
            <Pager page={queue.page} pages={queue.pages} href={(p) => `/exceptions?${filters({ page: String(p) })}`} />
        </div>
    )
}
