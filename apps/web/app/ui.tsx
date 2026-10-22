// Small pieces of page shared across the dashboard.

import Link from 'next/link'

const STATUS_STYLE: Record<string, string> = {
    pending: 'status-pending',
    processing: 'status-processing',
    matched: 'status-processing',
    approved: 'status-approved',
    exception: 'status-exception',
    rejected: 'status-rejected',
    open: 'status-exception',
    escalated: 'status-pending',
    resolved: 'status-approved',
}

const STATUS_WORD: Record<string, string> = { exception: 'held', approved: 'approved' }

export function StatusBadge({ status }: { status: string }) {
    return <span className={`status-badge ${STATUS_STYLE[status] ?? 'status-pending'}`}>{STATUS_WORD[status] ?? status.replaceAll('_', ' ')}</span>
}

export function Tabs({ tabs, current }: { tabs: { href: string; label: string; value: string }[]; current: string }) {
    return (
        <div className="flex gap-1 border-b border-gray-200 mb-4">
            {tabs.map((tab) => (
                <Link
                    key={tab.value}
                    href={tab.href}
                    className={`px-3 py-2 text-sm font-medium -mb-px border-b-2 ${
                        tab.value === current ? 'border-primary-600 text-primary-700' : 'border-transparent text-gray-500 hover:text-gray-800'
                    }`}
                >
                    {tab.label}
                </Link>
            ))}
        </div>
    )
}

export function ErrorBanner({ message }: { message?: string }) {
    if (!message) return null
    return <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{message}</div>
}

export function Stat({ title, value, note, tone = 'text-gray-900' }: { title: string; value: React.ReactNode; note?: React.ReactNode; tone?: string }) {
    return (
        <div className="card">
            <dt className="text-sm font-medium text-gray-500">{title}</dt>
            <dd className={`mt-1 text-3xl font-semibold ${tone}`}>{value}</dd>
            {note && <p className="mt-1 text-sm text-gray-500">{note}</p>}
        </div>
    )
}

export function Field({ name, children }: { name: string; children: React.ReactNode }) {
    return (
        <div>
            <dt className="text-sm text-gray-500">{name}</dt>
            <dd className="text-sm font-medium text-gray-900">{children}</dd>
        </div>
    )
}

export function Pager({ page, pages, href }: { page: number; pages: number; href: (page: number) => string }) {
    if (pages <= 1) return null
    return (
        <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
            {page > 1 ? <Link href={href(page - 1)} className="btn-secondary">Previous</Link> : <span />}
            <span>Page {page} of {pages}</span>
            {page < pages ? <Link href={href(page + 1)} className="btn-secondary">Next</Link> : <span />}
        </div>
    )
}
