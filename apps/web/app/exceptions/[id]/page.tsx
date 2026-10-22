import Link from 'next/link'

import { resolveException } from '@/app/actions'
import { Submit } from '@/app/client'
import { ErrorBanner, Field, StatusBadge } from '@/app/ui'
import { api } from '@/lib/api'
import { label, money, overdue, when } from '@/lib/format'
import type { Exception } from '@/lib/types'

// apps/api/services/exception_handler.py: RESOLUTIONS
const ACTIONS = [
    { value: 'approve', label: 'Approve for payment' },
    { value: 'reject', label: 'Reject the invoice' },
    { value: 'escalate', label: 'Escalate: leave it held for someone senior' },
    { value: 'reprocess', label: 'Send it back through the checks' },
]

export default async function ExceptionPage({ params, searchParams }: {
    params: Promise<{ id: string }>
    searchParams: Promise<{ error?: string }>
}) {
    const [{ id }, { error }] = await Promise.all([params, searchParams])
    const exc = await api<Exception>(`/exceptions/${id}`)
    const open = exc.status !== 'resolved'
    const flags = exc.details?.flags ?? []

    return (
        <div>
            <Link href="/exceptions" className="text-gray-500 hover:text-gray-700">← Exceptions</Link>
            <ErrorBanner message={error} />
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-4">
                <div className="lg:col-span-2 space-y-6">
                    <div className="card">
                        <div className="flex flex-wrap justify-between items-start gap-2 mb-4">
                            <div>
                                <h1 className="text-xl font-bold text-gray-900">{exc.title}</h1>
                                <p className="text-gray-500">{label(exc.category)}</p>
                            </div>
                            <div className="flex gap-2">
                                <span className={`status-badge severity-${exc.severity}`}>{exc.severity}</span>
                                <StatusBadge status={exc.status} />
                            </div>
                        </div>
                        {exc.description && <p className="text-gray-800 mb-4">{exc.description}</p>}
                        <h2 className="text-sm font-medium text-gray-500 mb-1">What the rules flagged</h2>
                        {flags.length ? (
                            <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1 mb-4">{flags.map((f) => <li key={f}>{f}</li>)}</ul>
                        ) : (
                            <p className="text-sm text-gray-700 mb-4">Nothing: the model held it on its own reading.</p>
                        )}
                        <dl className="grid grid-cols-2 gap-4 border-t border-gray-200 pt-4">
                            <Field name="Invoice">
                                <Link href={`/invoices/${exc.invoice_id}`} className="text-primary-600 hover:text-primary-800">
                                    {exc.invoice?.invoice_number}
                                </Link>{' '}
                                · {exc.invoice?.vendor_name} · {money(exc.invoice?.total_amount)}
                            </Field>
                            <Field name="For the">{label(exc.owner_role)}</Field>
                            <Field name="Held">{when(exc.created_at)}</Field>
                            <Field name="Due">
                                <span className={open && overdue(exc.sla_deadline) ? 'text-red-600' : ''}>
                                    {when(exc.sla_deadline)}
                                    {open && overdue(exc.sla_deadline) && ' (overdue)'}
                                </span>
                            </Field>
                        </dl>
                    </div>
                </div>

                <div className="card h-fit">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">Decision</h2>
                    {exc.resolution_action && (
                        <div className="mb-4 text-sm text-gray-700">
                            <p><strong>{label(exc.resolution_action)}</strong>{exc.resolved_at && <>, {when(exc.resolved_at)}</>}</p>
                            <p className="mt-1">{exc.resolution}</p>
                        </div>
                    )}
                    {open && (
                        <form action={resolveException.bind(null, id)} className="space-y-4">
                            <fieldset className="space-y-2">
                                {ACTIONS.map((a) => (
                                    <label key={a.value} className="flex items-start gap-2 text-sm text-gray-800">
                                        <input type="radio" name="action" value={a.value} required className="mt-1" />
                                        {a.label}
                                    </label>
                                ))}
                            </fieldset>
                            <textarea
                                name="resolution"
                                required
                                rows={4}
                                placeholder="Why: what you checked, and with whom"
                                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                            />
                            <Submit busy="Saving…">Record decision</Submit>
                        </form>
                    )}
                </div>
            </div>
        </div>
    )
}
