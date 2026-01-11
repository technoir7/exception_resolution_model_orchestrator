import Link from 'next/link'

interface AuditEvent {
    id: string
    step: string
    duration_ms: number
    completed_at: string
    status: string
}

interface InvoiceDetail {
    id: string
    invoice_number: string
    vendor_name: string
    vendor_id: string
    invoice_date: string
    due_date: string
    po_number: string
    total_amount: string
    status: string
    line_items: Array<{
        line_number: number
        description: string
        quantity: number
        unit_price: string
        amount: string
    }>
    audit_events: AuditEvent[]
}

async function getInvoice(id: string): Promise<InvoiceDetail> {
    // Mock data for demo
    return {
        id,
        invoice_number: 'INV-2024-001',
        vendor_name: 'Acme Supplies Inc',
        vendor_id: 'V001',
        invoice_date: '2024-01-15',
        due_date: '2024-02-14',
        po_number: 'PO-2024-001',
        total_amount: '$5,400.00',
        status: 'approved',
        line_items: [
            { line_number: 1, description: 'Widget A', quantity: 100, unit_price: '$25.00', amount: '$2,500.00' },
            { line_number: 2, description: 'Widget B', quantity: 50, unit_price: '$50.00', amount: '$2,500.00' },
        ],
        audit_events: [
            { id: '1', step: 'ingestion', duration_ms: 15, completed_at: '2024-01-15 10:00:01', status: 'success' },
            { id: '2', step: 'validation', duration_ms: 45, completed_at: '2024-01-15 10:00:02', status: 'success' },
            { id: '3', step: 'matching', duration_ms: 120, completed_at: '2024-01-15 10:00:03', status: 'success' },
            { id: '4', step: 'llm_call', duration_ms: 850, completed_at: '2024-01-15 10:00:04', status: 'success' },
            { id: '5', step: 'verification', duration_ms: 30, completed_at: '2024-01-15 10:00:05', status: 'success' },
            { id: '6', step: 'pipeline_completed', duration_ms: 5, completed_at: '2024-01-15 10:00:05', status: 'success' },
        ],
    }
}

export default async function InvoiceDetailPage({ params }: { params: { id: string } }) {
    const invoice = await getInvoice(params.id)

    return (
        <div>
            <div className="flex items-center gap-4 mb-6">
                <Link href="/invoices" className="text-gray-500 hover:text-gray-700">
                    ← Back to Invoices
                </Link>
            </div>

            <div className="flex justify-between items-start mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">{invoice.invoice_number}</h1>
                    <p className="text-gray-500">{invoice.vendor_name}</p>
                </div>
                <span className={`status-badge ${invoice.status === 'approved' ? 'status-approved' : 'status-exception'}`}>
                    {invoice.status}
                </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Invoice Details */}
                <div className="lg:col-span-2 space-y-6">
                    <div className="card">
                        <h2 className="text-lg font-medium text-gray-900 mb-4">Invoice Details</h2>
                        <dl className="grid grid-cols-2 gap-4">
                            <div>
                                <dt className="text-sm text-gray-500">Invoice Number</dt>
                                <dd className="text-sm font-medium text-gray-900">{invoice.invoice_number}</dd>
                            </div>
                            <div>
                                <dt className="text-sm text-gray-500">PO Number</dt>
                                <dd className="text-sm font-medium text-gray-900">{invoice.po_number}</dd>
                            </div>
                            <div>
                                <dt className="text-sm text-gray-500">Invoice Date</dt>
                                <dd className="text-sm font-medium text-gray-900">{invoice.invoice_date}</dd>
                            </div>
                            <div>
                                <dt className="text-sm text-gray-500">Due Date</dt>
                                <dd className="text-sm font-medium text-gray-900">{invoice.due_date}</dd>
                            </div>
                            <div>
                                <dt className="text-sm text-gray-500">Vendor ID</dt>
                                <dd className="text-sm font-medium text-gray-900">{invoice.vendor_id}</dd>
                            </div>
                            <div>
                                <dt className="text-sm text-gray-500">Total Amount</dt>
                                <dd className="text-sm font-medium text-gray-900">{invoice.total_amount}</dd>
                            </div>
                        </dl>
                    </div>

                    {/* Line Items */}
                    <div className="card p-0 overflow-hidden">
                        <div className="px-6 py-4 border-b border-gray-200">
                            <h2 className="text-lg font-medium text-gray-900">Line Items</h2>
                        </div>
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">#</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Qty</th>
                                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Unit Price</th>
                                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Amount</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200">
                                {invoice.line_items.map((item) => (
                                    <tr key={item.line_number}>
                                        <td className="px-6 py-4 text-sm text-gray-500">{item.line_number}</td>
                                        <td className="px-6 py-4 text-sm text-gray-900">{item.description}</td>
                                        <td className="px-6 py-4 text-sm text-gray-900 text-right">{item.quantity}</td>
                                        <td className="px-6 py-4 text-sm text-gray-900 text-right">{item.unit_price}</td>
                                        <td className="px-6 py-4 text-sm text-gray-900 text-right font-medium">{item.amount}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* Audit Timeline */}
                <div className="card">
                    <h2 className="text-lg font-medium text-gray-900 mb-4">Audit Timeline</h2>
                    <div className="space-y-4">
                        {invoice.audit_events.map((event, idx) => (
                            <div key={event.id} className="flex gap-3">
                                <div className="flex flex-col items-center">
                                    <div className={`w-3 h-3 rounded-full ${event.status === 'success' ? 'bg-green-500' : 'bg-red-500'}`} />
                                    {idx < invoice.audit_events.length - 1 && (
                                        <div className="w-0.5 h-full bg-gray-200 mt-1" />
                                    )}
                                </div>
                                <div className="flex-1 pb-4">
                                    <p className="text-sm font-medium text-gray-900 capitalize">
                                        {event.step.replace('_', ' ')}
                                    </p>
                                    <p className="text-xs text-gray-500">
                                        {event.completed_at} • {event.duration_ms}ms
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="mt-4 pt-4 border-t border-gray-200">
                        <button className="btn-secondary w-full text-sm">
                            Request Replay
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}
