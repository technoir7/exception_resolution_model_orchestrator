import Link from 'next/link'

import { processInvoice } from '@/app/actions'
import { Submit } from '@/app/client'
import { ErrorBanner, Field, StatusBadge } from '@/app/ui'
import { api } from '@/lib/api'
import { describe, latestDecision, type Decision } from '@/lib/decision'
import { cost, day, money, when } from '@/lib/format'
import type { AuditTimeline, ExceptionPage, Invoice, InvoiceCost } from '@/lib/types'

function DecisionCard({ decision, exceptionId }: { decision: Decision; exceptionId?: string }) {
    const approved = decision.outcome === 'approved'
    return (
        <div className={`card border-l-4 ${approved ? 'border-l-green-500' : 'border-l-orange-500'}`}>
            <h2 className="text-lg font-medium text-gray-900 mb-1">{approved ? 'Approved for payment' : 'Held for a person'}</h2>
            <p className="text-gray-800 mb-4">{decision.why}</p>
            {decision.verdicts.map((v, i) => (
                <p key={i} className="text-sm text-gray-600">
                    {v.model}: <strong>{v.decision}</strong>
                    {v.reason !== 'none' && <> on {v.reason.replaceAll('_', ' ')}</>}, {Math.round(v.confidence * 100)}% sure
                </p>
            ))}
            {decision.unreadable > 0 && <p className="text-sm text-gray-600">{decision.unreadable} unreadable answer(s) asked again</p>}
            <h3 className="text-sm font-medium text-gray-500 mt-4 mb-1">What the rules flagged</h3>
            {decision.flags.length ? (
                <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1">
                    {decision.flags.map((f) => <li key={f}>{f}</li>)}
                </ul>
            ) : (
                <p className="text-sm text-gray-700">Nothing</p>
            )}
            {exceptionId && (
                <Link href={`/exceptions/${exceptionId}`} className="btn-primary inline-block mt-4 text-sm">Decide</Link>
            )}
        </div>
    )
}

export default async function InvoicePage({ params, searchParams }: {
    params: Promise<{ id: string }>
    searchParams: Promise<{ error?: string }>
}) {
    const [{ id }, { error }] = await Promise.all([params, searchParams])
    const [invoice, timeline, spend] = await Promise.all([
        api<Invoice>(`/invoices/${id}`),
        api<AuditTimeline>(`/audit/${id}`),
        api<InvoiceCost>(`/metrics/cost/invoices/${id}`),
    ])
    const decision = latestDecision(timeline.events)
    const held = invoice.status === 'exception'
        ? (await api<ExceptionPage>(`/exceptions?invoice_id=${id}`)).items.find((e) => e.status !== 'resolved')
        : undefined
    const extra = invoice.extracted_data ?? {}

    return (
        <div>
            <Link href="/invoices" className="text-gray-500 hover:text-gray-700">← Invoices</Link>
            <div className="flex flex-wrap justify-between items-start gap-4 mt-4 mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">{invoice.invoice_number}</h1>
                    <p className="text-gray-500">{invoice.vendor_name} · {money(invoice.total_amount, invoice.currency)}</p>
                </div>
                <div className="flex items-center gap-3">
                    <StatusBadge status={invoice.status} />
                    {invoice.status === 'pending' && (
                        <form action={processInvoice.bind(null, id)}>
                            <Submit busy="Checking…">Process</Submit>
                        </form>
                    )}
                </div>
            </div>
            <ErrorBanner message={error} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    {decision && <DecisionCard decision={decision} exceptionId={held?.id} />}

                    <div className="card">
                        <h2 className="text-lg font-medium text-gray-900 mb-4">The invoice</h2>
                        <dl className="grid grid-cols-2 md:grid-cols-3 gap-4">
                            <Field name="Invoice date">{day(invoice.invoice_date)}</Field>
                            <Field name="Due">{day(invoice.due_date)}</Field>
                            <Field name="PO">{invoice.po_number ?? '—'}</Field>
                            <Field name="Vendor on file">{invoice.vendor_id}</Field>
                            <Field name="Pay to">
                                {extra.remit_to ? `${extra.remit_to.bank}, account ending ${extra.remit_to.account_last4}` : '—'}
                            </Field>
                            <Field name="Received as">
                                {invoice.document_type === 'pdf'
                                    ? `PDF${invoice.original_filename ? ` (${invoice.original_filename})` : ''}, read by ${extra.read_by ?? 'a model'}`
                                    : invoice.document_type.toUpperCase()}
                            </Field>
                            {extra.service_period && <Field name="Service period from">{day(extra.service_period)}</Field>}
                        </dl>
                        {extra.notes && <p className="mt-4 text-sm text-gray-700 bg-gray-50 rounded-md p-3">“{extra.notes}”</p>}
                    </div>

                    <div className="card p-0 overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    {['#', 'Description', 'Qty', 'Unit price', 'Amount'].map((h, i) => (
                                        <th key={h} className={`px-6 py-3 text-xs font-medium text-gray-500 uppercase ${i > 1 ? 'text-right' : 'text-left'}`}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200">
                                {(invoice.line_items ?? []).map((line) => (
                                    <tr key={line.line_number}>
                                        <td className="px-6 py-3 text-sm text-gray-500">{line.line_number}</td>
                                        <td className="px-6 py-3 text-sm text-gray-900">{line.description}</td>
                                        <td className="px-6 py-3 text-sm text-gray-900 text-right">{Number(line.quantity)}</td>
                                        <td className="px-6 py-3 text-sm text-gray-900 text-right">{money(line.unit_price, invoice.currency)}</td>
                                        <td className="px-6 py-3 text-sm text-gray-900 text-right font-medium">{money(line.amount, invoice.currency)}</td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot className="text-sm">
                                <tr><td colSpan={4} className="px-6 pt-3 text-right text-gray-500">Subtotal</td><td className="px-6 pt-3 text-right">{money(invoice.subtotal, invoice.currency)}</td></tr>
                                <tr><td colSpan={4} className="px-6 text-right text-gray-500">Tax</td><td className="px-6 text-right">{money(invoice.tax_amount, invoice.currency)}</td></tr>
                                <tr><td colSpan={4} className="px-6 pb-3 text-right font-medium">Total</td><td className="px-6 pb-3 text-right font-semibold">{money(invoice.total_amount, invoice.currency)}</td></tr>
                            </tfoot>
                        </table>
                    </div>
                </div>

                <div className="space-y-6">
                    <div className="card">
                        <h2 className="text-lg font-medium text-gray-900 mb-1">Model cost</h2>
                        <p className="text-3xl font-semibold text-gray-900 mb-3">{cost(spend.total_cost_usd)}</p>
                        <ul className="text-sm text-gray-600 space-y-1">
                            {spend.calls.map((call, i) => (
                                <li key={i}>{call.model_id}: {call.input_tokens.toLocaleString()} tokens in, {call.output_tokens} out, {cost(call.cost_usd)}</li>
                            ))}
                            {spend.calls.length === 0 && <li>No model calls.</li>}
                        </ul>
                    </div>

                    <div className="card">
                        <h2 className="text-lg font-medium text-gray-900 mb-4">Audit trail</h2>
                        {timeline.events.length === 0 && <p className="text-sm text-gray-500">Not processed yet.</p>}
                        <ol className="space-y-3">
                            {timeline.events.map((event) => (
                                <li key={event.id} className="flex gap-3">
                                    <span className={`mt-1.5 w-2.5 h-2.5 shrink-0 rounded-full ${event.actor_type === 'user' ? 'bg-primary-600' : 'bg-gray-400'}`} />
                                    <div>
                                        <p className="text-sm text-gray-900">{describe(event)}</p>
                                        <p className="text-xs text-gray-500">{when(event.completed_at)} · {event.duration_ms.toLocaleString()} ms</p>
                                    </div>
                                </li>
                            ))}
                        </ol>
                    </div>
                </div>
            </div>
        </div>
    )
}
