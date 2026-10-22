import Link from 'next/link'

import { processPending, uploadPdf } from '@/app/actions'
import { Submit } from '@/app/client'
import { ErrorBanner, Pager, StatusBadge, Tabs } from '@/app/ui'
import { api } from '@/lib/api'
import { money, when } from '@/lib/format'
import type { Invoice, Page } from '@/lib/types'

const STATUSES = [
    { value: '', label: 'All' },
    { value: 'pending', label: 'Not processed' },
    { value: 'approved', label: 'Approved' },
    { value: 'exception', label: 'Held' },
    { value: 'rejected', label: 'Rejected' },
]

type Search = { status?: string; page?: string; error?: string }

export default async function InvoicesPage({ searchParams }: { searchParams: Promise<Search> }) {
    const { status = '', page = '1', error } = await searchParams
    const query = new URLSearchParams({ page, ...(status && { status }) })
    const [invoices, pending] = await Promise.all([
        api<Page<Invoice>>(`/invoices?${query}`),
        api<Page<Invoice>>('/invoices?status=pending&page_size=1'),
    ])
    const href = (p: number) => `/invoices?${new URLSearchParams({ page: String(p), ...(status && { status }) })}`

    return (
        <div>
            <div className="flex flex-wrap justify-between items-start gap-4 mb-6">
                <h1 className="text-2xl font-bold text-gray-900">Invoices</h1>
                <div className="flex flex-wrap gap-3">
                    <form action={uploadPdf} className="flex items-center gap-2">
                        <input type="file" name="pdf" accept="application/pdf" className="text-sm text-gray-600" />
                        <Submit busy="Reading…">Read a PDF</Submit>
                    </form>
                    {pending.total > 0 && (
                        <form action={processPending}>
                            <Submit busy="Processing…" className="btn-secondary">Process {pending.total} waiting</Submit>
                        </form>
                    )}
                </div>
            </div>
            <ErrorBanner message={error} />
            <Tabs current={status} tabs={STATUSES.map((s) => ({ ...s, href: s.value ? `/invoices?status=${s.value}` : '/invoices' }))} />

            <div className="card overflow-x-auto p-0">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            {['Invoice', 'Vendor', 'Amount', 'Status', 'Received as', 'Received'].map((h) => (
                                <th key={h} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {invoices.items.map((invoice) => (
                            <tr key={invoice.id} className="hover:bg-gray-50">
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <Link href={`/invoices/${invoice.id}`} className="text-primary-600 hover:text-primary-800 font-medium">
                                        {invoice.invoice_number}
                                    </Link>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">{invoice.vendor_name}</td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-medium">{money(invoice.total_amount, invoice.currency)}</td>
                                <td className="px-6 py-4 whitespace-nowrap"><StatusBadge status={invoice.status} /></td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{invoice.document_type.toUpperCase()}</td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{when(invoice.created_at)}</td>
                            </tr>
                        ))}
                        {invoices.items.length === 0 && (
                            <tr>
                                <td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500">No invoices here.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
            <Pager page={invoices.page} pages={invoices.pages} href={href} />
        </div>
    )
}
